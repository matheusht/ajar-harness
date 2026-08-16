// p1-bootstrap.js — standalone lab boot: custom genesis + real-path unit insertion
// Usage: node p1-bootstrap.js <command>  (commands: genesis | chain | attack)
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const OUT = path.join(__dirname);

// ---------- env BEFORE any ocore require ----------
const genesisFile = path.join(OUT, "p1-genesis.json");
let keys, genesis, addresses;
if (fs.existsSync(genesisFile)) {
  const saved = JSON.parse(fs.readFileSync(genesisFile, "utf8"));
  keys = saved.keys; genesis = saved.genesis; addresses = saved.addresses;
  process.env.GENESIS_UNIT = genesis.unit;
}
process.env.COUNT_WITNESSES = "1";
process.env.MAJORITY_OF_WITNESSES = "1";

// pre-provision the lab DB (private-network operator pattern) — must complete BEFORE db.js loads
const dataDir = path.join(OUT, ".p1data");
const dbFile = path.join(dataDir, "byteball.sqlite");
const command = process.argv[2];

function preProvision() {
  if (command !== "chain" || !addresses || fs.existsSync(dbFile)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    fs.mkdirSync(dataDir, { recursive: true });
    fs.copyFileSync(path.join(O_CORE, "initial-db/initial.byteball.sqlite"), dbFile);
    const sqlite3 = require(O_CORE + "/node_modules/sqlite3");
    const witness = addresses.witness_addr;
    const rows = [
      ["op_list", JSON.stringify([witness]), -1],
      ["base_tps_fee", "10", -1],
      ["tps_interval", "1", -1],
      ["tps_fee_multiplier", "10", -1],
      ["threshold_size", "10000", -1],
    ];
    const d = new sqlite3.Database(dbFile);
    d.serialize(() => {
      d.run(`CREATE TABLE IF NOT EXISTS system_vars (
        subject VARCHAR(50) NOT NULL,
        value TEXT NOT NULL,
        vote_count_mci INT NOT NULL,
        is_emergency TINYINT NOT NULL DEFAULT 0,
        creation_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (subject, vote_count_mci DESC))`);
      const stmt = d.prepare(`INSERT OR REPLACE INTO system_vars (subject, value, vote_count_mci) VALUES (?,?,?)`);
      rows.forEach(r => stmt.run(r[0], r[1], r[2]));
      stmt.finalize(() => d.close(() => { console.log("pre-provisioned op_list:", JSON.stringify([witness])); resolve(); }));
    });
  });
}

// ---------- patch desktop_app ----------
const desktop_app = require(O_CORE + "/desktop_app.js");
desktop_app.getAppRootDir = function () { return O_CORE; };
desktop_app.getAppDataDir = function () { return dataDir; };

const constants = require(O_CORE + "/constants.js");
const conf = require(O_CORE + "/conf.js");
conf.bLight = false;
// zero ALL upgrade MCIs so every rule applies from genesis
["aa2UpgradeMci", "aa3UpgradeMci", "v4UpgradeMci", "pemCurvesFixMci", "noPrivateAssetsWithConditionsUpgradeMci",
 "timestampUpgradeMci", "includeKeySizesUpgradeMci", "lastBallStableInParentsUpgradeMci",
 "witnessedLevelMustNotRetreatUpgradeMci", "witnessedLevelMustNotRetreatFromAllParentsUpgradeMci",
 "branchedMinMcWlUpgradeMci", "altBranchByBestParentUpgradeMci", "spendUnconfirmedUpgradeMci",
 "bestParentPrefersOpUpgradeMci", "tpsFeeRecipientsFixMci"].forEach(k => { constants[k] = 0; });
constants.COUNT_WITNESSES = 1;
constants.MAJORITY_OF_WITNESSES = 1;

// require the rest lazily AFTER pre-provisioning completes
const lib = {};
function loadLib() {
  if (lib.db) return lib;
  lib.db = require(O_CORE + "/db.js");
  lib.storage = require(O_CORE + "/storage.js");
  lib.objectHash = require(O_CORE + "/object_hash.js");
  lib.ecdsa = require(O_CORE + "/node_modules/secp256k1");
  return lib;
}
const crypto = require("crypto");
const util = require("util");

function sign(hashBuf, privHex) { const ecdsa = loadLib().ecdsa; const r = ecdsa.ecdsaSign(hashBuf, Buffer.from(privHex, "hex")); return r.signature.toString("base64"); }

function makeKey() {
  const ecdsa = loadLib().ecdsa;
  let priv; do { priv = crypto.randomBytes(32); } while (!ecdsa.privateKeyVerify(priv));
  const pub = ecdsa.publicKeyCreate(priv, true);
  return { priv: Buffer.from(priv).toString("hex"), pub: Buffer.from(pub).toString("base64") };
}

function waitForDb() {
  const db = loadLib().db;
  return new Promise((resolve) => {
    function tryConnect() {
      try {
        db.takeConnectionFromPool((conn) => { conn.query("SELECT 1", () => { conn.release(); resolve(); }); });
      } catch (e) { setTimeout(tryConnect, 500); }
    }
    setTimeout(tryConnect, 500);
  });
}

async function query(sql, params) {
  const db = loadLib().db;
  return new Promise((resolve, reject) => {
    db.takeConnectionFromPool((conn) => {
      conn.query(sql, params || [], (rows) => { conn.release(); resolve(rows); });
    });
  });
}

// ---------- commands ----------
async function cmdGenesis() {
  const { objectHash } = loadLib();
  const sender = makeKey(), recipient = makeKey(), witness = makeKey();
  const def = (k) => ["sig", { pubkey: k.pub }];
  const addr = (k) => objectHash.getChash160(def(k));
  const sender_addr = addr(sender), recipient_addr = addr(recipient), witness_addr = addr(witness);
  if (objectHash.getChash160(["sig", { pubkey: witness.pub }]) !== witness_addr) throw Error("addr mismatch");
  const TOTAL = 1e15;

  const payload = {
    outputs: [
      { address: sender_addr, amount: Math.floor(TOTAL * 0.6) },
      { address: recipient_addr, amount: Math.floor(TOTAL * 0.2) },
      { address: witness_addr, amount: Math.floor(TOTAL * 0.2) },
    ],
  };
  const genesisUnit = {
    version: "4.0",
    alt: "1",
    timestamp: Math.round(Date.now() / 1000),
    authors: [{ address: witness_addr, definition: ["sig", { pubkey: witness.pub }], authentifiers: { r: "AAAA" } }],
    messages: [{ app: "payment", payload_location: "inline", payload: payload }],
    witnesses: [witness_addr],
    headers_commission: 0,
    payload_commission: 0,
  };
  genesisUnit.messages[0].payload_hash = objectHash.getBase64Hash(payload, true);
  const hashToSign = objectHash.getUnitHashToSign(genesisUnit);
  genesisUnit.authors[0].authentifiers.r = sign(hashToSign, witness.priv);
  genesisUnit.messages[0].payload_hash = objectHash.getBase64Hash(payload, true);
  genesisUnit.unit = objectHash.getUnitHash(genesisUnit);
  console.log("GENESIS unit:", genesisUnit.unit);

  fs.writeFileSync(genesisFile, JSON.stringify({ keys: { sender, recipient, witness }, genesis: genesisUnit, addresses: { sender_addr, recipient_addr, witness_addr } }, null, 1));
  console.log("GENESIS-READY");
}

async function cmdChain() {
  const { storage } = loadLib();
  await waitForDb();
  console.log("DB ready");
  await storage.initCaches();
  console.log("caches ready (system vars loaded)");

  // genesis joint must already be in the kvstore (the node-received-from-peer state)
  const kvstore = require(O_CORE + "/kvstore.js");
  await new Promise((res, rej) => kvstore.put("j\n" + genesis.unit, JSON.stringify({ unit: genesis }), (e) => (e ? rej(e) : res())));
  console.log("GENESIS JOINT IN KVSTORE");

  // insert genesis via real writer path
  const writer = require(O_CORE + "/writer.js");
  const state = { last_ball_mci: 0, count_primary_aa_triggers: 0, sequence: "good", arrAdditionalQueries: [], bUnderWriteLock: false, witnessed_level: 0, best_parent_unit: null };
  await util.promisify(writer.saveJoint)({ unit: genesis }, state, null, () => {});
  console.log("GENESIS SAVED");

  const read = await util.promisify(storage.readUnit)(genesis.unit);
  console.log("genesis read back:", read ? read.unit : "MISSING");
  const lastStable = await util.promisify(storage.readLastStableMcUnit)(null);
  console.log("last stable mc unit:", lastStable);
  const bal = await query("SELECT address, amount FROM outputs ORDER BY amount DESC LIMIT 4");
  console.log("genesis outputs:", JSON.stringify(bal));
}

async function main() {
  await preProvision();
  if (command === "genesis") return cmdGenesis();
  if (command === "chain") return cmdChain();
  console.error("usage: node p1-bootstrap.js genesis|chain");
}
main().then(() => process.exit(0)).catch(e => { console.error("ERR:", e); process.exit(1); });
