package main

import (
	"bytes"
	"encoding/base64"
	"encoding/hex"
	"fmt"

	"github.com/btcsuite/btcd/btcec/v2/ecdsa"
	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/btcutil/psbt"
	"github.com/btcsuite/btcd/chaincfg"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
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

	for _, sh := range []int{0x83, 0x01} {
		opt := &bitcoin.SignPsbtOption{AutoFinalized: true, ToSignInputs: []*bitcoin.ToSignInput{{Index: idx, Address: ownAddr, SigHashTypes: []int{sh}}}}
		signed, err := bitcoin.SignPsbtWithKeyPathAndScriptPath(psbtHex, wif, &chaincfg.TestNet3Params, opt)
		if err != nil {
			fmt.Printf("CELL H1-sign-0x%02x err=%v\n", sh, err)
			continue
		}
		sraw, _ := hex.DecodeString(signed)
		sp, _ := psbt.NewFromRawBytes(bytes.NewReader(sraw), false)
		for i := range sp.Inputs {
			if i != idx && len(sp.Inputs[i].FinalScriptSig)+len(sp.Inputs[i].FinalScriptWitness) == 0 {
				sp.Inputs[i].FinalScriptWitness = []byte{0x00}
			}
		}
		tx, xerr := psbt.Extract(sp)
		if xerr != nil {
			fmt.Printf("CELL H1-extract-0x%02x err=%v\n", sh, xerr)
			continue
		}
		sig := tx.TxIn[idx].Witness[0]
		scriptCode, _ := bitcoin.PayToPubKeyHashScript(pkh)

		fetch0 := txscript.NewMultiPrevOutFetcher(map[wire.OutPoint]*wire.TxOut{})
		for i := range sp.Inputs {
			if sp.Inputs[i].WitnessUtxo != nil {
				fetch0.AddPrevOut(tx.TxIn[i].PreviousOutPoint, sp.Inputs[i].WitnessUtxo)
			}
		}
		h0 := txscript.NewTxSigHashes(tx, fetch0)
		ht0 := txscript.SigHashType(sig[len(sig)-1])
		d0, _ := txscript.CalcWitnessSigHash(scriptCode, h0, ht0, tx, idx, sp.Inputs[idx].WitnessUtxo.Value)
		ps0, e0 := ecdsa.ParseDERSignature(sig[:len(sig)-1])
		fmt.Printf("CELL H1-0x%02x control_original_valid=%v (hash_byte=0x%02x)\n", sh, e0==nil && ps0.Verify(d0, pub), ht0)

		mod := tx.Copy()
		attacker := wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0xaa}, Index: 0}, nil, [][]byte{{0x00}})
		mod.AddTxIn(attacker)
		prevOuts := map[wire.OutPoint]*wire.TxOut{}
		for i := range sp.Inputs {
			if sp.Inputs[i].WitnessUtxo != nil {
				prevOuts[tx.TxIn[i].PreviousOutPoint] = sp.Inputs[i].WitnessUtxo
			}
		}
		prevOuts[attacker.PreviousOutPoint] = wire.NewTxOut(5000, []byte{0x6a})
		fetcher := txscript.NewMultiPrevOutFetcher(prevOuts)
		hashes := txscript.NewTxSigHashes(mod, fetcher)
		ht := txscript.SigHashType(sig[len(sig)-1])
		digest, derr := txscript.CalcWitnessSigHash(scriptCode, hashes, ht, mod, idx, sp.Inputs[idx].WitnessUtxo.Value)
		if derr != nil {
			fmt.Printf("CELL H1-0x%02x digest err=%v\n", sh, derr)
			continue
		}
		parsed, perr := ecdsa.ParseDERSignature(sig[:len(sig)-1])
		ok := perr == nil && parsed.Verify(digest, pub)
		fmt.Printf("CELL H1-acp-0x%02x sig_survives_appended_input=%v\n", sh, ok)
		_ = signed
	}
}
