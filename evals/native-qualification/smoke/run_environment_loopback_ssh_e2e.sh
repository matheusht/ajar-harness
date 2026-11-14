#!/usr/bin/env bash
# Exercise the real SSH transport on a disposable Linux host without another machine.
set -euo pipefail

if [[ $# != 2 || $(uname -s) != Linux ]]; then
  echo 'usage: run_environment_loopback_ssh_e2e.sh IMAGE_ID OUTPUT_DIRECTORY (Linux, Docker, OpenSSH, passwordless sudo)' >&2
  exit 64
fi
image_id=$1
output_directory=$2
mkdir -p "$output_directory"
output_directory=$(cd "$output_directory" && pwd)
fixture_directory=$(mktemp -d "${RUNNER_TEMP:-/tmp}/oslit-loopback-ssh.XXXXXXXX")
listener_attempted=false
listener_pid=
sshd_binary=$(command -v sshd)
fixture_user=$(id -un)
fixture_port=$(python3 - <<'PY'
import socket
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    print(listener.getsockname()[1])
PY
)

cleanup() {
  outcome=$?
  set +e
  trap - EXIT
  listener_stopped=false
  if [[ $listener_attempted == false ]]; then
    listener_stopped=true
  elif [[ -f "$fixture_directory/sshd.pid" || -n $listener_pid ]]; then
    if [[ -z $listener_pid ]]; then
      listener_pid=$(cat "$fixture_directory/sshd.pid")
    fi
    if [[ $listener_pid =~ ^[0-9]+$ && -d /proc/self ]]; then
      if [[ ! -d /proc/$listener_pid ]]; then
        listener_stopped=true
      elif sudo -n cat "/proc/$listener_pid/cmdline" | tr '\0' ' ' | grep -Fq -- "$fixture_directory/sshd_config"; then
        sudo -n kill -TERM "$listener_pid" 2>/dev/null
        for _ in {1..50}; do
          if [[ ! -d /proc/$listener_pid ]]; then listener_stopped=true; break; fi
          sleep .1
        done
      fi
    fi
  fi
  fixture_removed=false
  if [[ $listener_stopped == true ]]; then
    if rm -rf -- "$fixture_directory" && [[ ! -e $fixture_directory ]]; then
      fixture_removed=true
    else
      outcome=1
    fi
  else
    echo 'Owned SSH listener cleanup could not be verified' >&2
    outcome=1
  fi
  if ! python3 - "$output_directory" "$listener_stopped" "$fixture_removed" "$0" <<'PY'
import hashlib,json,pathlib,sys
output=pathlib.Path(sys.argv[1])/'ssh-listener-cleanup.json'
output.write_text(json.dumps({'kind':'loopback-ssh-fixture-cleanup-v1',
    'listener_stopped':sys.argv[2]=='true',
    'fixture_removed':sys.argv[3]=='true',
    'fixture_sha256':'sha256:'+hashlib.sha256(pathlib.Path(sys.argv[4]).read_bytes()).hexdigest()},indent=2)+'\n')
PY
  then
    outcome=1
  fi
  exit "$outcome"
}
trap cleanup EXIT

ssh-keygen -q -t ed25519 -N '' -f "$fixture_directory/host_key"
ssh-keygen -q -t ed25519 -N '' -f "$fixture_directory/client_key"
cp "$fixture_directory/client_key.pub" "$fixture_directory/authorized_keys"
cat > "$fixture_directory/sshd_config" <<EOF
Port $fixture_port
ListenAddress 127.0.0.1
HostKey $fixture_directory/host_key
PidFile $fixture_directory/sshd.pid
AuthorizedKeysFile $fixture_directory/authorized_keys
AllowUsers $fixture_user
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
UsePAM no
StrictModes yes
AllowTcpForwarding no
AllowAgentForwarding no
X11Forwarding no
LogLevel ERROR
EOF
sudo -n install -d -m 0755 /run/sshd
sudo -n "$sshd_binary" -t -f "$fixture_directory/sshd_config"
listener_attempted=true
sudo -n "$sshd_binary" -f "$fixture_directory/sshd_config" -E "$fixture_directory/sshd.log"
listener_pid=$(cat "$fixture_directory/sshd.pid")
[[ $listener_pid =~ ^[0-9]+$ ]]
python3 - "$fixture_directory" "$fixture_port" "$fixture_user" <<'PY'
import hashlib,json,pathlib,sys
folder=pathlib.Path(sys.argv[1]);port=int(sys.argv[2]);user=sys.argv[3]
key_type,key_data,*_= (folder/'host_key.pub').read_text().split()
known=folder/'known_hosts';known.write_text(f'[127.0.0.1]:{port} {key_type} {key_data}\n')
profile={'host':'127.0.0.1','port':port,'user':user,'known_hosts_file':str(known),
    'known_hosts_sha256':'sha256:'+hashlib.sha256(known.read_bytes()).hexdigest(),
    'identity_file':str(folder/'client_key'),'python_binary':sys.executable}
(folder/'profile.json').write_text(json.dumps(profile)+'\n')
PY
python3 "$(dirname "$0")/check_environment_docker_e2e.py" \
  --endpoint unix:///var/run/docker.sock --image-id "$image_id" \
  --loopback-ssh-profile "$fixture_directory/profile.json" \
  --output "$output_directory/ssh-result.json"
