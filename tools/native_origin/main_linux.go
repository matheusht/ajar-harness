package main

import (
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const socketPath = "/origin/socket/ingress.sock"

type procNode struct {
	pid       int
	parent    int
	starttime uint64
}

func procAt(root string, pid int) (procNode, error) {
	if pid <= 0 {
		return procNode{}, errors.New("pid_invalid")
	}
	raw, err := os.ReadFile(filepath.Join(root, strconv.Itoa(pid), "stat"))
	if err != nil {
		return procNode{}, err
	}
	observed, parent, start, err := parseProcStat(raw)
	if err != nil || observed != pid {
		return procNode{}, errors.New("proc_stat_mismatch")
	}
	return procNode{pid, parent, start}, nil
}

// Resolve the live chain twice, rejecting exited or recycled processes.
func checkLineage(procRoot string, sender, root int, rootStart uint64) ([]procNode, error) {
	if sender <= 0 || root <= 0 || rootStart == 0 {
		return nil, errors.New("lineage_input_invalid")
	}
	var chain []procNode
	seen := map[int]bool{}
	for pid := sender; len(chain) < 64; {
		if seen[pid] {
			return nil, errors.New("lineage_cycle")
		}
		seen[pid] = true
		node, err := procAt(procRoot, pid)
		if err != nil {
			return nil, err
		}
		chain = append(chain, node)
		if pid == root {
			if node.starttime != rootStart {
				return nil, errors.New("lineage_root_recycled")
			}
			for _, previous := range chain {
				again, err := procAt(procRoot, previous.pid)
				if err != nil || again != previous {
					return nil, errors.New("lineage_changed")
				}
			}
			return chain, nil
		}
		if node.parent <= 0 || node.parent == pid {
			return nil, errors.New("lineage_root_missing")
		}
		pid = node.parent
	}
	return nil, errors.New("lineage_too_deep")
}

type armRecord struct {
	Kind       string `json:"kind"`
	Status     string `json:"status"`
	Role       string `json:"role"`
	Target     string `json:"target"`
	RunNonce   string `json:"run_nonce"`
	DispatchID string `json:"dispatch_id"`
	GateNonce  string `json:"gate_nonce"`
	RootPID    int    `json:"root_pid"`
	RootStart  uint64 `json:"root_starttime"`
	Heartbeat  int64  `json:"heartbeat_unix_ms"`
}

type ingressConfig struct {
	role, target, nonce, socketDir, ledgerDir, armsDir string
	port, uid                                          int
}

func readArm(config ingressConfig) (armRecord, error) {
	var arm armRecord
	raw, err := os.ReadFile(filepath.Join(config.armsDir, config.role+".json"))
	if err != nil || len(raw) > 4096 {
		return arm, errors.New("arm_unavailable")
	}
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&arm) != nil || decoder.Decode(new(any)) != io.EOF {
		return arm, errors.New("arm_invalid")
	}
	age := time.Now().UnixMilli() - arm.Heartbeat
	if arm.Kind != "native-origin-arm-v1" || arm.Status != "armed" ||
		arm.Role != config.role || arm.Target != config.target || arm.RunNonce != config.nonce ||
		len(arm.DispatchID) != 32 || len(arm.GateNonce) != 32 || arm.RootPID <= 1 ||
		arm.RootStart == 0 || age < -2000 || age > 5000 {
		return arm, errors.New("arm_not_current")
	}
	if _, err := hex.DecodeString(arm.DispatchID); err != nil {
		return arm, errors.New("arm_dispatch_invalid")
	}
	if _, err := hex.DecodeString(arm.GateNonce); err != nil {
		return arm, errors.New("arm_gate_invalid")
	}
	return arm, nil
}

func sendAll(fd int, data []byte) error {
	for len(data) > 0 {
		chunk := data
		if len(chunk) > 32*1024 {
			chunk = chunk[:32*1024]
		}
		n, err := syscall.SendmsgN(fd, chunk, nil, nil, 0)
		if err != nil || n != len(chunk) {
			return errors.New("socket_write_failed")
		}
		data = data[n:]
	}
	return nil
}

func failureReply(fd int) {
	_ = sendAll(fd, []byte("HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/plain\r\nContent-Length: 21\r\nConnection: close\r\n\r\norigin route refused\n"))
}

func receiveWithCredentials(fd int) ([]byte, *syscall.Ucred, error) {
	data := make([]byte, maxRequestBytes+1)
	ancillary := make([]byte, syscall.CmsgSpace(syscall.SizeofUcred))
	n, oobn, flags, _, err := syscall.Recvmsg(fd, data, ancillary, 0)
	if err != nil || n == 0 || n > maxRequestBytes || flags&(syscall.MSG_TRUNC|syscall.MSG_CTRUNC) != 0 {
		return nil, nil, errors.New("packet_invalid")
	}
	messages, err := syscall.ParseSocketControlMessage(ancillary[:oobn])
	if err != nil || len(messages) != 1 || messages[0].Header.Level != syscall.SOL_SOCKET || messages[0].Header.Type != syscall.SCM_CREDENTIALS {
		return nil, nil, errors.New("sender_credentials_missing")
	}
	credentials, err := syscall.ParseUnixCredentials(&messages[0])
	if err != nil || credentials.Pid <= 0 {
		return nil, nil, errors.New("sender_credentials_invalid")
	}
	// The sender must half-close after its single packet. A queued second packet
	// or a connection kept open cannot be forwarded as one unambiguous request.
	second := make([]byte, 1)
	more, _, moreFlags, _, moreErr := syscall.Recvmsg(fd, second, nil, 0)
	if moreErr != nil || more != 0 || moreFlags&syscall.MSG_TRUNC != 0 {
		return nil, nil, errors.New("packet_sequence_invalid")
	}
	return data[:n], credentials, nil
}

type ledgerNode struct {
	PID       int    `json:"pid"`
	Parent    int    `json:"parent"`
	Starttime uint64 `json:"starttime"`
}

type requestRecord struct {
	Kind            string       `json:"kind"`
	RunNonce        string       `json:"run_nonce"`
	Role            string       `json:"role"`
	Target          string       `json:"target"`
	DispatchID      string       `json:"dispatch_id"`
	GateNonce       string       `json:"gate_nonce"`
	RootPID         int          `json:"root_pid"`
	RootStarttime   uint64       `json:"root_starttime"`
	SenderUID       uint32       `json:"sender_uid"`
	SenderPID       int          `json:"sender_pid"`
	SenderStarttime uint64       `json:"sender_starttime"`
	Ancestry        []ledgerNode `json:"ancestry"`
	Method          string       `json:"method"`
	RouteSHA256     string       `json:"route_sha256"`
	BodySHA256      string       `json:"body_sha256"`
	RequestSHA256   string       `json:"request_sha256"`
	BrokerRequestID string       `json:"broker_request_id"`
	ResponseSHA256  string       `json:"response_sha256"`
}

func appendRecord(file *os.File, row requestRecord) error {
	encoded, err := json.Marshal(row)
	if err != nil || len(encoded) > 8192 {
		return errors.New("ledger_record_invalid")
	}
	encoded = append(encoded, '\n')
	if n, err := file.Write(encoded); err != nil || n != len(encoded) {
		return errors.New("ledger_write_failed")
	}
	return file.Sync()
}

func forward(port int, request []byte) ([]byte, error) {
	connection, err := net.DialTimeout("tcp", net.JoinHostPort("127.0.0.1", strconv.Itoa(port)), 3*time.Second)
	if err != nil {
		return nil, err
	}
	defer connection.Close()
	if err := connection.SetDeadline(time.Now().Add(15 * time.Second)); err != nil {
		return nil, err
	}
	if _, err := connection.Write(request); err != nil {
		return nil, err
	}
	response, err := io.ReadAll(io.LimitReader(connection, maxResponseBytes+1))
	if err != nil || len(response) > maxResponseBytes {
		return nil, errors.New("broker_response_unavailable")
	}
	return response, nil
}

func handle(fd int, config ingressConfig, ledger *os.File, seen map[string]bool) {
	defer syscall.Close(fd)
	if syscall.SetsockoptInt(fd, syscall.SOL_SOCKET, syscall.SO_PASSCRED, 1) != nil {
		failureReply(fd)
		return
	}
	timeout := syscall.NsecToTimeval((5 * time.Second).Nanoseconds())
	if syscall.SetsockoptTimeval(fd, syscall.SOL_SOCKET, syscall.SO_RCVTIMEO, &timeout) != nil {
		failureReply(fd)
		return
	}
	request, credentials, err := receiveWithCredentials(fd)
	if err != nil || int(credentials.Uid) != config.uid {
		failureReply(fd)
		return
	}
	arm, err := readArm(config)
	if err != nil {
		failureReply(fd)
		return
	}
	chain, err := checkLineage("/proc", int(credentials.Pid), arm.RootPID, arm.RootStart)
	if err != nil {
		failureReply(fd)
		return
	}
	parsed, err := parseRequest(request)
	if err != nil {
		failureReply(fd)
		return
	}
	// A sender must still be the same live process at the forwarding boundary.
	last, err := procAt("/proc", chain[0].pid)
	if err != nil || last != chain[0] {
		failureReply(fd)
		return
	}
	response, err := forward(config.port, request)
	if err != nil {
		failureReply(fd)
		return
	}
	requestID, err := responseID(response)
	if err != nil || seen[requestID] {
		// A broker error with no ID is useful to the tool but cannot enter proof.
		_ = sendAll(fd, response)
		return
	}
	row := requestRecord{Kind: "native-origin-request-v1", RunNonce: config.nonce,
		Role: config.role, Target: config.target, DispatchID: arm.DispatchID,
		GateNonce: arm.GateNonce, RootPID: arm.RootPID, RootStarttime: arm.RootStart,
		SenderUID: credentials.Uid, SenderPID: chain[0].pid,
		SenderStarttime: chain[0].starttime, Method: parsed.method,
		RouteSHA256: digest([]byte(parsed.path)), BodySHA256: digest(parsed.body),
		RequestSHA256: digest(request), BrokerRequestID: requestID,
		ResponseSHA256: digest(response)}
	for _, node := range chain {
		row.Ancestry = append(row.Ancestry, ledgerNode{node.pid, node.parent, node.starttime})
	}
	if err := appendRecord(ledger, row); err != nil {
		failureReply(fd)
		return
	}
	seen[requestID] = true
	_ = sendAll(fd, response)
}

func runIngress(args []string) error {
	if len(args) != 7 {
		return errors.New("ingress_arguments_invalid")
	}
	port, err := strconv.Atoi(args[2])
	if err != nil || port < 1 || port > 65535 {
		return errors.New("ingress_port_invalid")
	}
	uid, err := strconv.Atoi(args[6])
	if err != nil || uid < 1 {
		return errors.New("ingress_uid_invalid")
	}
	config := ingressConfig{role: args[0], target: args[1], port: port,
		socketDir: args[3], ledgerDir: args[4], armsDir: args[5], uid: uid}
	config.nonce = os.Getenv("LRH_RUN_NONCE")
	if len(config.nonce) != 32 || len(config.role) > 32 || len(config.target) > 32 {
		return errors.New("ingress_identity_invalid")
	}
	if _, err := hex.DecodeString(config.nonce); err != nil {
		return errors.New("ingress_nonce_invalid")
	}
	// Same-UID agent processes must not open /proc/<ingress>/root or /fd.
	if _, _, errno := syscall.RawSyscall(syscall.SYS_PRCTL, uintptr(4), 0, 0); errno != 0 {
		return errors.New("ingress_nondumpable_failed")
	}
	syscall.Umask(0077)
	ledgerFD, err := syscall.Open(filepath.Join(config.ledgerDir, "requests.jsonl"),
		syscall.O_WRONLY|syscall.O_APPEND|syscall.O_CREAT|syscall.O_EXCL|syscall.O_NOFOLLOW, 0600)
	if err != nil {
		return err
	}
	ledger := os.NewFile(uintptr(ledgerFD), "requests.jsonl")
	defer ledger.Close()
	if err := ledger.Sync(); err != nil {
		return err
	}
	socket := filepath.Join(config.socketDir, "ingress.sock")
	if _, err := os.Lstat(socket); !errors.Is(err, os.ErrNotExist) {
		return errors.New("ingress_socket_preexisting")
	}
	listener, err := syscall.Socket(syscall.AF_UNIX, syscall.SOCK_SEQPACKET, 0)
	if err != nil {
		return err
	}
	defer syscall.Close(listener)
	// Enable credentials before accept so a client cannot race its first packet.
	if err := syscall.SetsockoptInt(listener, syscall.SOL_SOCKET, syscall.SO_PASSCRED, 1); err != nil {
		return err
	}
	if err := syscall.Bind(listener, &syscall.SockaddrUnix{Name: socket}); err != nil {
		return err
	}
	if err := os.Chmod(socket, 0600); err != nil {
		return err
	}
	if err := syscall.Listen(listener, 8); err != nil {
		return err
	}
	seen := map[string]bool{}
	for {
		fd, _, err := syscall.Accept(listener)
		if err != nil {
			return err
		}
		handle(fd, config, ledger, seen)
	}
}

func runClient(args []string) error {
	if len(args) < 3 || len(args) > 4 {
		return errors.New("client_arguments_invalid")
	}
	var body []byte
	var err error
	if args[1] == "POST" {
		body, err = io.ReadAll(io.LimitReader(os.Stdin, maxRequestBytes+1))
		if err != nil {
			return err
		}
	}
	contentType := ""
	if len(args) == 4 {
		contentType = args[3]
	}
	request, err := makeRequest(args[0], args[1], args[2], contentType, body)
	if err != nil {
		return err
	}
	fd, err := syscall.Socket(syscall.AF_UNIX, syscall.SOCK_SEQPACKET, 0)
	if err != nil {
		return err
	}
	defer syscall.Close(fd)
	if err := syscall.Connect(fd, &syscall.SockaddrUnix{Name: socketPath}); err != nil {
		return err
	}
	if n, err := syscall.SendmsgN(fd, request, nil, nil, 0); err != nil || n != len(request) {
		return errors.New("client_packet_failed")
	}
	if err := syscall.Shutdown(fd, syscall.SHUT_WR); err != nil {
		return errors.New("client_packet_close_failed")
	}
	buffer := make([]byte, 32*1024+1)
	for {
		n, _, flags, _, err := syscall.Recvmsg(fd, buffer, nil, 0)
		if err != nil || flags&syscall.MSG_TRUNC != 0 {
			return errors.New("client_response_invalid")
		}
		if n == 0 {
			return nil
		}
		if _, err := os.Stdout.Write(buffer[:n]); err != nil {
			return err
		}
	}
}

func runGate(args []string) error {
	if len(args) < 2 || len(args[0]) != 32 {
		return errors.New("gate_arguments_invalid")
	}
	if _, err := hex.DecodeString(args[0]); err != nil {
		return errors.New("gate_nonce_invalid")
	}
	pid := os.Getpid()
	stat, err := procAt("/proc", pid)
	if err != nil {
		return err
	}
	if _, err := fmt.Fprintf(os.Stdout, "LRH_GATE\t%s\t%d\t%d\n", args[0], pid, stat.starttime); err != nil {
		return err
	}
	var release [1]byte
	if _, err := io.ReadFull(os.Stdin, release[:]); err != nil || release[0] != 'G' {
		return errors.New("gate_release_missing")
	}
	null, err := os.OpenFile("/dev/null", os.O_RDONLY, 0)
	if err != nil {
		return err
	}
	if err := syscall.Dup3(int(null.Fd()), 0, 0); err != nil {
		return err
	}
	return syscall.Exec("/usr/local/bin/opencode", append([]string{"/usr/local/bin/opencode"}, args[1:]...), os.Environ())
}

func probeTCP(args []string) error {
	if len(args) != 2 || net.ParseIP(args[0]) == nil {
		return errors.New("probe_arguments_invalid")
	}
	port, err := strconv.Atoi(args[1])
	if err != nil || port < 1 || port > 65535 {
		return errors.New("probe_port_invalid")
	}
	connection, err := net.DialTimeout("tcp", net.JoinHostPort(args[0], args[1]), 2*time.Second)
	if err != nil {
		fmt.Print("unreachable")
		return nil
	}
	connection.Close()
	fmt.Print("connected")
	return nil
}

func main() {
	var err error
	if len(os.Args) < 2 {
		err = errors.New("mode_missing")
	} else {
		switch os.Args[1] {
		case "ingress":
			err = runIngress(os.Args[2:])
		case "request":
			err = runClient(os.Args[2:])
		case "gate":
			err = runGate(os.Args[2:])
		case "probe-tcp":
			err = probeTCP(os.Args[2:])
		default:
			err = errors.New("mode_invalid")
		}
	}
	if err != nil {
		// Fixed category only. Never print requests, responses, tokens or paths.
		fmt.Fprintln(os.Stderr, "native_origin_unavailable")
		os.Exit(2)
	}
}
