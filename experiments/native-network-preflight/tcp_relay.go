// Keyless TCP transport to one host listener; host CONNECT gateway owns policy.
package main

import (
	"crypto/tls"
	"crypto/x509"
	"io"
	"net"
	"net/http"
	"net/netip"
	"os"
	"time"
)

func main() {
	if len(os.Args) == 3 && os.Args[1] == "probe" {
		certificate, err := os.ReadFile(os.Args[2])
		if err != nil { os.Exit(2) }
		roots := x509.NewCertPool()
		if !roots.AppendCertsFromPEM(certificate) { os.Exit(2) }
		client := &http.Client{Timeout: 5*time.Second, Transport: &http.Transport{
			Proxy: http.ProxyFromEnvironment, TLSClientConfig: &tls.Config{RootCAs: roots},
		}}
		response, err := client.Get("https://opencode.ai/dummy-positive")
		if err != nil { os.Exit(3) }
		defer response.Body.Close()
		if response.StatusCode != 200 { os.Exit(4) }
		io.Copy(os.Stdout, io.LimitReader(response.Body, 1024))
		return
	}
	host := os.Getenv("HOST_GATEWAY_HOST")
	if host == "" {
		host = "host.docker.internal"
	} else {
		ip, err := netip.ParseAddr(host)
		if err != nil || !ip.Is4() { os.Exit(2) }
		a := ip.As4()
		if !(a[0] == 10 || a[0] == 172 && a[1] >= 16 && a[1] <= 31 || a[0] == 192 && a[1] == 168) { os.Exit(2) }
	}
	listener, err := net.Listen("tcp", ":8080")
	if err != nil { panic("relay listener unavailable") }
	slots := make(chan struct{}, 4)
	for {
		client, err := listener.Accept()
		if err != nil { return }
		select {
		case slots <- struct{}{}:
		default: client.Close(); continue
		}
		go func() {
			defer func() { <-slots }()
			defer client.Close()
			remote, err := net.DialTimeout("tcp", net.JoinHostPort(host, os.Getenv("HOST_GATEWAY_PORT")), 5*time.Second)
			if err != nil { return }
			defer remote.Close()
			go func() { io.Copy(remote, client); remote.(*net.TCPConn).CloseWrite() }()
			io.Copy(client, remote)
		}()
	}
}
