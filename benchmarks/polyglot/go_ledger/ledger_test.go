package goledger

import (
	"os"
	"testing"
)

func TestBenignTransfers(t *testing.T) {
	l := NewLedger(map[string]int64{"alice": 1000, "bob": 500})
	before := l.TotalSupply()
	if err := l.Transfer("alice", "bob", 250); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := l.BalanceOf("alice"); got != 750 {
		t.Fatalf("alice = %d, want 750", got)
	}
	if got := l.BalanceOf("bob"); got != 750 {
		t.Fatalf("bob = %d, want 750", got)
	}
	if after := l.TotalSupply(); after != before {
		t.Fatalf("supply changed: %d != %d", after, before)
	}
	if err := l.Transfer("alice", "bob", 9999); err != ErrInsufficientFunds {
		t.Fatalf("expected ErrInsufficientFunds, got %v", err)
	}
}

func TestPoCSelfTransferConservation(t *testing.T) {
	if os.Getenv("RUN_POC") != "1" {
		t.Skip("set RUN_POC=1 to execute PoC")
	}
	l := NewLedger(map[string]int64{"alice": 1000, "bob": 500})
	before := l.TotalSupply()
	if err := l.Transfer("alice", "alice", 600); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	after := l.TotalSupply()
	if after != before {
		t.Fatalf("CONSERVATION_VIOLATED: supply inflated from %d to %d", before, after)
	}
}
