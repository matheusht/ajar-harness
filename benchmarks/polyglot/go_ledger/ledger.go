package goledger

import "errors"

var (
	ErrInsufficientFunds = errors.New("insufficient funds")
	ErrNegativeAmount    = errors.New("negative amount")
)

type Ledger struct {
	balances map[string]int64
}

func NewLedger(initial map[string]int64) *Ledger {
	cp := make(map[string]int64, len(initial))
	for k, v := range initial {
		cp[k] = v
	}
	return &Ledger{balances: cp}
}

func (l *Ledger) BalanceOf(acct string) int64 {
	return l.balances[acct]
}

func (l *Ledger) TotalSupply() int64 {
	var total int64
	for _, v := range l.balances {
		total += v
	}
	return total
}

// Transfer moves amount from sender to recipient.
// BUG: caches recipient balance before writing sender debit, inflating supply on self-transfer.
func (l *Ledger) Transfer(from, to string, amount int64) error {
	if amount < 0 {
		return ErrNegativeAmount
	}
	fromBal := l.balances[from]
	toBal := l.balances[to]
	if fromBal < amount {
		return ErrInsufficientFunds
	}
	l.balances[from] = fromBal - amount
	l.balances[to] = toBal + amount
	return nil
}
