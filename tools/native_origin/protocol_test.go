package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestRequestEnvelope(t *testing.T) {
	request, err := makeRequest("B", "POST", "/jsonrpc.php", "application/json", []byte(`{"jsonrpc":"2.0","method":"getMe","id":7}`))
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := parseRequest(request)
	if err != nil {
		t.Fatal(err)
	}
	if parsed.method != "POST" || parsed.path != "/jsonrpc.php" || parsed.actor != "B" || string(parsed.body) != `{"jsonrpc":"2.0","method":"getMe","id":7}` {
		t.Fatalf("wrong parsed request: %+v", parsed)
	}
	if bytes.Contains(bytes.ToLower(request), []byte("authorization:")) || bytes.Contains(bytes.ToLower(request), []byte("cookie:")) {
		t.Fatal("client request carried credential header")
	}
}

func TestRequestFailsClosed(t *testing.T) {
	base, err := makeRequest("A", "GET", "/", "", nil)
	if err != nil {
		t.Fatal(err)
	}
	cases := map[string][]byte{
		"authorization":     bytes.Replace(base, []byte("\r\n\r\n"), []byte("\r\nAuthorization: Basic fake\r\n\r\n"), 1),
		"cookie":            bytes.Replace(base, []byte("\r\n\r\n"), []byte("\r\nCookie: stolen\r\n\r\n"), 1),
		"duplicate actor":   bytes.Replace(base, []byte("\r\n\r\n"), []byte("\r\nX-Native-Actor: B\r\n\r\n"), 1),
		"transfer encoding": bytes.Replace(base, []byte("\r\n\r\n"), []byte("\r\nTransfer-Encoding: chunked\r\n\r\n"), 1),
		"pipelined":         append(append([]byte(nil), base...), base...),
		"short body":        []byte("POST /jsonrpc.php HTTP/1.1\r\nHost: localhost\r\nX-Native-Actor: A\r\nContent-Length: 3\r\n\r\nx"),
	}
	for name, wire := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := parseRequest(wire); err == nil {
				t.Fatal("accepted invalid request")
			}
		})
	}
	if _, err := makeRequest("C", "POST", "/jsonrpc.php", "application/json", bytes.Repeat([]byte("x"), maxRequestBytes)); err == nil {
		t.Fatal("accepted oversized body")
	}
}

func TestResponseID(t *testing.T) {
	valid := []byte("HTTP/1.1 200 OK\r\nX-LRH-Request-ID: 0123456789abcdef0123456789abcdef\r\nContent-Length: 2\r\n\r\n{}")
	id, err := responseID(valid)
	if err != nil || id != "0123456789abcdef0123456789abcdef" {
		t.Fatalf("valid ID: %q %v", id, err)
	}
	for _, wire := range [][]byte{
		[]byte("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"),
		[]byte("HTTP/1.1 200 OK\r\nX-LRH-Request-ID: wrong\r\nContent-Length: 0\r\n\r\n"),
		bytes.Replace(valid, []byte("Content-Length"), []byte("X-LRH-Request-ID: 0123456789abcdef0123456789abcdef\r\nContent-Length"), 1),
	} {
		if _, err := responseID(wire); err == nil {
			t.Fatalf("accepted missing/ambiguous ID: %q", wire)
		}
	}
}

func TestProcStatParser(t *testing.T) {
	fields := []string{"S", "11"}
	for len(fields) < 20 {
		fields = append(fields, "0")
	}
	fields[19] = "987654"
	stat := []byte("42 (curl worker) " + strings.Join(fields, " ") + "\n")
	pid, parent, start, err := parseProcStat(stat)
	if err != nil || pid != 42 || parent != 11 || start != 987654 {
		t.Fatalf("bad parsed proc stat: %d %d %d %v", pid, parent, start, err)
	}
	for _, raw := range []string{"42 bad", "42 (x) S 1", "42 (x) S 1 " + strings.Repeat("0 ", 18) + "NaN"} {
		if _, _, _, err := parseProcStat([]byte(raw)); err == nil {
			t.Fatalf("accepted bad proc stat: %q", raw)
		}
	}
}
