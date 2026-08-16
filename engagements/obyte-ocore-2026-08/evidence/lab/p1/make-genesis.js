// p1-bootstrap.js — bootstrap a real spendable ledger in the lab via a custom genesis
// Real-path: construct genesis unit -> compute hash -> set GENESIS_UNIT -> post via writer/validation
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";

// patch desktop_app before any ocore require (constants.js calls getAppRootDir at load)
const desktop_app = require(O_CORE + "/desktop_app.js");
desktop_app.getAppRootDir = function () { return O_CORE; };
desktop_app.getAppDataDir = function () { return __dirname + "/.p1data"; };

// --- keys first (secp256k1) ---
const ecdsa = require(O_CORE + "/node_modules/secp256k1");
const crypto = require("crypto");

function makeKey() {
  let priv;
  do { priv = crypto.randomBytes(32); } while (!ecdsa.privateKeyVerify(priv));
  const pub = ecdsa.publicKeyCreate(priv, true);
  return { priv: Buffer.from(priv).toString("hex"), pub: Buffer.from(pub).toString("base64") };
}

const sender = makeKey();
const recipient = makeKey();
const witness = makeKey();
console.log(JSON.stringify({ sender, recipient, witness }, null, 1));

// --- build genesis unit ---
// compute addresses AFTER object_hash loads; requires chash160 of pub b64
const objectHash = require(O_CORE + "/object_hash.js");
const sender_addr = objectHash.getChash160(sender.pub);
const recipient_addr = objectHash.getChash160(recipient.pub);
const witness_addr = objectHash.getChash160(witness.pub);
console.log("addresses:", { sender_addr, recipient_addr, witness_addr });

// TOTAL_WHITEBYTES = 1e15 base units (max 9e15); fund generously
const TOTAL = 1e15;
const genesis = {
  version: "4.0",
  alt: "1",
  timestamp: Math.round(Date.now() / 1000),
  authors: [],
  messages: [
    {
      app: "payment",
      payload_location: "inline",
      payload: {
        inputs: [],
        outputs: [
          { address: sender_addr, amount: Math.floor(TOTAL * 0.6) },
          { address: recipient_addr, amount: Math.floor(TOTAL * 0.2) },
          { address: witness_addr, amount: Math.floor(TOTAL * 0.2) },
        ],
      },
    },
  ],
  witnesses: [witness_addr],
  headers_commission: 0,
  payload_commission: 0,
};
genesis.unit = objectHash.getUnitHash(genesis);
console.log("genesis unit hash:", genesis.unit);
fs.writeFileSync(path.join(__dirname, "p1-genesis.json"), JSON.stringify({ genesis, sender, recipient, witness }, null, 1));
console.log("GENESIS-READY");
