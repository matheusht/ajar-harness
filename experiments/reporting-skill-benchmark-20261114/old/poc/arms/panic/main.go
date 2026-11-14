package main

import (
	"fmt"

	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/btcutil/psbt"
	"github.com/btcsuite/btcd/chaincfg"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
	"github.com/btcsuite/btcd/wire"
	"github.com/okx/go-wallet-sdk/coins/bitcoin"
)

const wif = "cPnvkvUYyHcSSS26iD1dkrJdV7k1RoUqJLhn3CYxpo398PdLVE22"

func main() {
	w, _ := btcutil.DecodeWIF(wif)
	h := btcutil.Hash160(w.PrivKey.PubKey().SerializeCompressed())
	spk, _ := bitcoin.PayToPubKeyHashScript(h)
	fund := wire.NewMsgTx(2)
	fund.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0x71}, Index: 0}, nil, nil))
	fund.AddTxOut(wire.NewTxOut(100000, spk))

	tx := wire.NewMsgTx(2)
	tx.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: fund.TxHash(), Index: 99}, nil, nil))
	tx.AddTxOut(wire.NewTxOut(90000, spk))
	pkt, _ := psbt.NewFromUnsignedTx(tx)
	pkt.Inputs[0].NonWitnessUtxo = fund
	var b bytesBuffer
	_ = pkt.Serialize(&b)
	psbtHex := fmt.Sprintf("%x", b.Bytes())

	for _, entry := range []string{"raw", "keypath"} {
		func() {
			defer func() {
				if r := recover(); r != nil {
					fmt.Printf("CELL P-%s panic=%v\n", entry, r)
				}
			}()
			if entry == "raw" {
				_, err := bitcoin.SignRawPSBTTransaction(psbtHex, wif)
				fmt.Printf("CELL P-raw no_panic err=%v\n", err)
			} else {
				_, err := bitcoin.SignPsbtWithKeyPathAndScriptPath(psbtHex, wif, &chaincfg.TestNet3Params, &bitcoin.SignPsbtOption{AutoFinalized: true})
				fmt.Printf("CELL P-keypath no_panic err=%v\n", err)
			}
		}()
	}
}

type bytesBuffer struct{ b []byte }

func (x *bytesBuffer) Write(p []byte) (int, error) { x.b = append(x.b, p...); return len(p), nil }
func (x *bytesBuffer) Bytes() []byte               { return x.b }
