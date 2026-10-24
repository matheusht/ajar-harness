package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeProcFixture(t *testing.T, base string, pid, parent int, start uint64) {
	t.Helper()
	dir := filepath.Join(base, fmt.Sprint(pid))
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	fields := []string{"S", fmt.Sprint(parent)}
	for len(fields) < 20 {
		fields = append(fields, "0")
	}
	fields[19] = fmt.Sprint(start)
	if err := os.WriteFile(filepath.Join(dir, "stat"), []byte(fmt.Sprintf("%d (fixture worker) %s\n", pid, strings.Join(fields, " "))), 0600); err != nil {
		t.Fatal(err)
	}
}

func TestExactRootLineage(t *testing.T) {
	base := t.TempDir()
	writeProcFixture(t, base, 10, 1, 100)
	writeProcFixture(t, base, 11, 10, 110)
	writeProcFixture(t, base, 12, 11, 120)
	writeProcFixture(t, base, 20, 1, 200)
	chain, err := checkLineage(base, 12, 10, 100)
	if err != nil || len(chain) != 3 || chain[0].pid != 12 || chain[2].pid != 10 {
		t.Fatalf("valid lineage: %+v %v", chain, err)
	}
	if _, err := checkLineage(base, 20, 10, 100); err == nil {
		t.Fatal("accepted unrelated process")
	}
	if _, err := checkLineage(base, 12, 10, 101); err == nil {
		t.Fatal("accepted recycled root")
	}
	if err := os.Remove(filepath.Join(base, "10", "stat")); err != nil {
		t.Fatal(err)
	}
	if _, err := checkLineage(base, 12, 10, 100); err == nil {
		t.Fatal("accepted exited root")
	}
}
