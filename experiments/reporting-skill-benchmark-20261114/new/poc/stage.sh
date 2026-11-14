#!/bin/sh
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp -R "$HERE/module" "$WORK/module"
for arm in singlebug declare segwit redirect acp panic mpc accept; do
  mkdir -p "$WORK/module/poc-$arm"
  cp "$HERE/arms/$arm/main.go" "$WORK/module/poc-$arm/main.go"
done
export GOFLAGS=-mod=mod GOSUMDB=off GOTOOLCHAIN=local
cd "$WORK/module"
for arm in singlebug declare segwit redirect acp panic mpc accept; do
  go build -trimpath -buildvcs=false -o "./bin-$arm" "./poc-$arm"
done
echo "-- binary hashes (deterministic: -buildvcs=false)"
for arm in singlebug declare segwit redirect acp panic mpc accept; do
  printf "SHA256 bin-%s = %s\n" "$arm" "$(shasum -a 256 "./bin-$arm" | cut -d' ' -f1)"
done
echo "== arm 1: legacy SINGLE (0x03) and allowlisted 0x83 vs control 0x01 =="
./bin-singlebug
echo "== arm 2: no-override reach (PSBT declares allowlisted 0x83; caller passes nothing) =="
./bin-declare
echo "== arm 3: P2WPKH SINGLE (0x03) vs control 0x01 =="
./bin-segwit
echo "== arm 4: SIGHASH_NONE (0x02) output redirection vs control 0x01 =="
./bin-redirect
echo "== arm 5: 0x83 prepared-signature append-input survival vs control 0x01 =="
./bin-acp
echo "== arm 6: unguarded NonWitnessUtxo index (PSBT says index 99, funding tx has one output) =="
./bin-panic
echo "== arm 7: SDK MPC flow (GenerateMPCUnsignedPSBT -> sign -> GenerateMPCSignedPSBT) =="
./bin-mpc
echo "== arm 8: does the attacker transaction pass the script engine? =="
./bin-accept
