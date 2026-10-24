package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"
)

const maxRequestBytes = 64 * 1024
const maxResponseBytes = 4 * 1024 * 1024

type requestMeta struct {
	method string
	path   string
	actor  string
	body   []byte
}

func digest(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func makeRequest(actor, method, path, contentType string, body []byte) ([]byte, error) {
	if !validActor(actor) || !validRoute(method, path) || len(body) > maxRequestBytes {
		return nil, errors.New("request_invalid")
	}
	if method == "GET" && (len(body) != 0 || contentType != "") {
		return nil, errors.New("get_body_invalid")
	}
	if method == "POST" && contentType != "application/json" && contentType != "application/x-www-form-urlencoded" {
		return nil, errors.New("content_type_invalid")
	}
	var header strings.Builder
	fmt.Fprintf(&header, "%s %s HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nX-Native-Actor: %s\r\n", method, path, actor)
	if method == "POST" {
		fmt.Fprintf(&header, "Content-Type: %s\r\nContent-Length: %d\r\n", contentType, len(body))
	}
	header.WriteString("\r\n")
	if header.Len()+len(body) > maxRequestBytes {
		return nil, errors.New("request_oversize")
	}
	return append([]byte(header.String()), body...), nil
}

func validActor(actor string) bool { return actor == "A" || actor == "B" || actor == "C" }

func validRoute(method, path string) bool {
	if method != "GET" && method != "POST" || len(path) == 0 || len(path) > 4096 || path[0] != '/' {
		return false
	}
	return !strings.ContainsAny(path, "\x00\r\n \t\\") && !strings.Contains(path, "..")
}

func parseRequest(wire []byte) (requestMeta, error) {
	var empty requestMeta
	if len(wire) == 0 || len(wire) > maxRequestBytes {
		return empty, errors.New("request_size_invalid")
	}
	boundary := bytes.Index(wire, []byte("\r\n\r\n"))
	if boundary < 0 || boundary > 16*1024 {
		return empty, errors.New("request_header_invalid")
	}
	lines := strings.Split(string(wire[:boundary]), "\r\n")
	if len(lines) < 2 || len(lines) > 32 {
		return empty, errors.New("request_lines_invalid")
	}
	start := strings.Split(lines[0], " ")
	if len(start) != 3 || start[2] != "HTTP/1.1" || !validRoute(start[0], start[1]) {
		return empty, errors.New("request_line_invalid")
	}
	headers := map[string]string{}
	for _, line := range lines[1:] {
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 || parts[0] == "" || strings.ContainsAny(parts[0], " \t") || strings.ContainsAny(parts[1], "\x00\r\n") {
			return empty, errors.New("request_header_invalid")
		}
		key := strings.ToLower(parts[0])
		if _, exists := headers[key]; exists {
			return empty, errors.New("request_header_duplicate")
		}
		switch key {
		case "host", "connection", "x-native-actor", "content-type", "content-length":
		default:
			return empty, errors.New("request_header_unexpected")
		}
		headers[key] = strings.TrimSpace(parts[1])
	}
	if headers["host"] != "localhost" || headers["connection"] != "close" || !validActor(headers["x-native-actor"]) {
		return empty, errors.New("request_header_value_invalid")
	}
	body := wire[boundary+4:]
	if start[0] == "GET" {
		if len(body) != 0 || headers["content-length"] != "" || headers["content-type"] != "" {
			return empty, errors.New("get_body_invalid")
		}
	} else {
		if headers["content-type"] != "application/json" && headers["content-type"] != "application/x-www-form-urlencoded" {
			return empty, errors.New("content_type_invalid")
		}
		length, err := strconv.Atoi(headers["content-length"])
		if err != nil || length < 0 || length != len(body) || len(headers["content-length"]) > 6 {
			return empty, errors.New("body_length_invalid")
		}
	}
	return requestMeta{start[0], start[1], headers["x-native-actor"], body}, nil
}

func responseID(wire []byte) (string, error) {
	if len(wire) == 0 || len(wire) > maxResponseBytes {
		return "", errors.New("response_size_invalid")
	}
	boundary := bytes.Index(wire, []byte("\r\n\r\n"))
	if boundary < 0 || boundary > 32*1024 {
		return "", errors.New("response_header_invalid")
	}
	lines := strings.Split(string(wire[:boundary]), "\r\n")
	if len(lines) < 2 || !strings.HasPrefix(lines[0], "HTTP/1.1 ") {
		return "", errors.New("response_line_invalid")
	}
	var found string
	for _, line := range lines[1:] {
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			return "", errors.New("response_header_invalid")
		}
		if strings.EqualFold(parts[0], "X-LRH-Request-ID") {
			value := strings.TrimSpace(parts[1])
			if found != "" || len(value) != 32 {
				return "", errors.New("broker_id_ambiguous")
			}
			for _, char := range value {
				if char < '0' || char > '9' && char < 'a' || char > 'f' {
					return "", errors.New("broker_id_invalid")
				}
			}
			found = value
		}
	}
	if found == "" {
		return "", errors.New("broker_id_absent")
	}
	return found, nil
}

// /proc/<pid>/stat has a parenthesized comm field that may contain spaces.
func parseProcStat(raw []byte) (pid int, parent int, start uint64, err error) {
	value := strings.TrimSpace(string(raw))
	left := strings.Index(value, " (")
	right := strings.LastIndex(value, ") ")
	if left <= 0 || right <= left+1 {
		return 0, 0, 0, errors.New("proc_stat_invalid")
	}
	pid, err = strconv.Atoi(value[:left])
	if err != nil || pid <= 0 {
		return 0, 0, 0, errors.New("proc_pid_invalid")
	}
	fields := strings.Fields(value[right+2:])
	if len(fields) < 20 {
		return 0, 0, 0, errors.New("proc_fields_missing")
	}
	parent, err = strconv.Atoi(fields[1])
	if err != nil || parent < 0 {
		return 0, 0, 0, errors.New("proc_parent_invalid")
	}
	start, err = strconv.ParseUint(fields[19], 10, 64)
	if err != nil || start == 0 {
		return 0, 0, 0, errors.New("proc_start_invalid")
	}
	return pid, parent, start, nil
}
