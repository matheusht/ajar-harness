// E1-16 — issue-type spend proof as an F3 sibling: duplicate serial issuance across addresses
// Real path: synthetic genesis -> asset definition -> issue units, all through
// validation.validate + writer.saveJoint (the real consensus entry). Pinned a7eb776.
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const DATA = path.join(__dirname, ".e1-16data");
fs.rmSync(DATA, { recursive: true, force: true });
fs.mkdirSync(DATA, { recursive: true });

// patch desktop_app BEFORE any other ocore require (constants.js calls getAppRootDir at load)
const desktop_app = require(O_CORE + "/desktop_app.js");
desktop_app.getAppRootDir = function () { return O_CORE; };
desktop_app.getAppDataDir = function () { return DATA; };

const crypto = require("crypto");
const ecdsa = require(O_CORE + "/node_modules/secp256k1");

function makeKey() {
  let priv;
  do { priv = crypto.randomBytes(32); } while (!ecdsa.privateKeyVerify(priv));
  const pub = Buffer.from(ecdsa.publicKeyCreate(priv, true));
  return { priv: priv.toString("hex"), pub: pub.toString("base64") };
}
// address = chash160 of the definition (needs objectHash; computed after load)
const objectHash0 = require(O_CORE + "/object_hash.js");
const defOf0 = (k) => ["sig", { pubkey: k.pub }];
const addrOf = (k) => objectHash0.getChash160(defOf0(k));
function defOf(key) { return defOf0(key); }
function signHash(hashBuf, privHex) {
  return Buffer.from(ecdsa.ecdsaSign(hashBuf, Buffer.from(privHex, "hex")).signature).toString("base64");
}

const KEYS = { A1: makeKey(), A2: makeKey(), W: makeKey() };
KEYS.A1.addr = addrOf(KEYS.A1); KEYS.A2.addr = addrOf(KEYS.A2); KEYS.W.addr = addrOf(KEYS.W);
const witness_addr = KEYS.W.addr;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- boot env (p1-refute pattern) ----
async function main() {
  const constants = require(O_CORE + "/constants.js");
  const conf = require(O_CORE + "/conf.js");
  conf.bLight = true;
  const objectHash = require(O_CORE + "/object_hash.js");
  const objectLength = require(O_CORE + "/object_length.js");

  // synthetic genesis: base bytes to A1, A2, W
  const TOTAL = 1000000;
  function buildGenesis() {
    const g = {
      version: "3.0",
      alt: "1",
      timestamp: Math.round(Date.now() / 1000),
      authors: [{ address: witness_addr, definition: defOf(KEYS.W), authentifiers: { r: "-" } }],
      messages: [],
      witnesses: [witness_addr],
      headers_commission: 0,
      payload_commission: 0,
    };
    const payload = {
      inputs: [{ type: "issue", amount: TOTAL, serial_number: 1 }],
      outputs: [
        { address: KEYS.A1.addr, amount: 0 },
        { address: KEYS.A2.addr, amount: 0 },
        { address: witness_addr, amount: 0 },
      ],
    };
    g.messages = [{ app: "payment", payload_location: "inline", payload, payload_hash: objectHash.getBase64Hash(payload, true) }];
    g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), KEYS.W.priv);
    g.headers_commission = objectLength.getHeadersSize(g);
    g.payload_commission = objectLength.getTotalPayloadSize(g);
    const spendable = TOTAL - g.headers_commission - g.payload_commission;
    payload.outputs[0].amount = Math.floor(spendable * 0.4);
    payload.outputs[1].amount = Math.floor(spendable * 0.3);
    payload.outputs[2].amount = spendable - payload.outputs[0].amount - payload.outputs[1].amount;
    payload.outputs.sort((a, b) => (a.address < b.address ? -1 : 1));
    g.messages[0].payload_hash = objectHash.getBase64Hash(payload, true);
    g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), KEYS.W.priv);
    g.unit = objectHash.getUnitHash(g);
    return g;
  }

  constants.TOTAL_WHITEBYTES = TOTAL;
  const genesis = buildGenesis();
  const genesisBall = objectHash.getBallHash(genesis.unit);
  constants.GENESIS_UNIT = genesis.unit;
  constants.COUNT_WITNESSES = 1;
  constants.MAJORITY_OF_WITNESSES = 1;

  const db = require(O_CORE + "/db.js");
  conf.bLight = false;

  await new Promise((resolve) => {
    db.takeConnectionFromPool((conn) => {
      conn.query("SELECT 1", () => { conn.release(); resolve(); });
    });
  });
  const q = (sql, params) => new Promise((resolve) => {
    db.takeConnectionFromPool((conn) => {
      conn.query(sql, params || [], (rows) => { conn.release(); resolve(rows); });
    });
  });
  const rows = [
    ["op_list", JSON.stringify([witness_addr]), -1],
    ["threshold_size", "10000", -1],
    ["base_tps_fee", "10", -1],
    ["tps_interval", "60", -1],
    ["tps_fee_multiplier", "10", -1],
  ];
  for (const [subject, value, mci] of rows)
    await q("INSERT OR IGNORE INTO system_vars (subject, value, vote_count_mci) VALUES (?,?,?)", [subject, value, mci]);

  const storage = require(O_CORE + "/storage.js");
  const network = require(O_CORE + "/network.js");
  const validation = require(O_CORE + "/validation.js");
  const writer = require(O_CORE + "/writer.js");
  [
    "aa2UpgradeMci", "aa3UpgradeMci", "v4UpgradeMci", "pemCurvesFixMci", "noPrivateAssetsWithConditionsUpgradeMci",
    "timestampUpgradeMci", "includeKeySizesUpgradeMci", "lastBallStableInParentsUpgradeMci",
    "witnessedLevelMustNotRetreatUpgradeMci", "witnessedLevelMustNotRetreatFromAllParentsUpgradeMci",
    "branchedMinMcWlUpgradeMci", "altBranchByBestParentUpgradeMci", "spendUnconfirmedUpgradeMci",
    "bestParentPrefersOpUpgradeMci", "tpsFeeRecipientsFixMci", "unstableInitialDefinitionUpgradeMci",
  ].forEach((k) => { constants[k] = 0; });
  constants.COUNT_WITNESSES = 1;
  constants.MAJORITY_OF_WITNESSES = 1;

  for (let i = 0; i < 200 && typeof storage.getMinRetrievableMci() !== "number"; i++) await sleep(100);

  function makeSigner(key) {
    return {
      readDefinition: (conn, address, cb) => cb(null, defOf(key)),
      readSigningPaths: (conn, address, cb) => cb({ r: constants.SIG_LENGTH }),
      readPrivateKey: (address, path, cb) => cb(null, Buffer.from(key.priv, "hex")),
    };
  }

  function validateAndSave(joint, label) {
    return new Promise((resolve, reject) => {
      validation.validate(joint, {
        ifOk: (objValidationState, unlock) => {
          console.log("E1-16 " + label + " VALIDATION OK sequence=" + objValidationState.sequence);
          objValidationState.count_primary_aa_triggers = objValidationState.count_primary_aa_triggers || 0;
          writer.saveJoint(joint, objValidationState, null, () => {
            unlock();
            console.log("E1-16 " + label + " SAVED " + joint.unit.unit);
            // cache repair: saved units are stable+on-MC in this lab; remove stale unstable entries
            const saved = joint.unit.unit;
            delete storage.assocUnstableUnits[saved];
            if (storage.assocStableUnits[saved]) storage.assocStableUnits[saved].is_free = 0;
            resolve(objValidationState);
          });
        },
        ifUnitError: (e) => { console.log("E1-16 " + label + " UNIT-ERROR: " + e); reject(new Error(label + " unit error: " + e)); },
        ifJointError: (e) => { console.log("E1-16 " + label + " JOINT-ERROR: " + e); reject(new Error(label + " joint error: " + e)); },
        ifTransientError: (e) => { console.log("E1-16 " + label + " TRANSIENT: " + e); reject(new Error(label + " transient: " + e)); },
        ifNeedParentUnits: (a) => { console.log("E1-16 " + label + " NEED-PARENTS"); reject(new Error(label + " need parents")); },
        ifNeedHashTree: () => { console.log("E1-16 " + label + " NEED-HASH-TREE"); reject(new Error(label + " need hash tree")); },
      });
    });
  }

  // buildUnit: generic unit with [assetMsg] + a base payment funding the fees
  // baseInputIdx: which genesis output index the author spends for fees
  function buildUnit(key, baseInputIdx, assetMsg, extraMsgs, label, anchor) {
    const anc = anchor || { parent_units: [genesis.unit], last_ball: genesisBall, last_ball_unit: genesis.unit };
    const baseInput = { unit: genesis.unit, message_index: 0, output_index: baseInputIdx };
    const baseChange = { address: key.addr, amount: 0 }; // placeholder
    const messages = assetMsg ? [assetMsg] : [];
    if (extraMsgs) for (const m of extraMsgs) messages.push(m);
    messages.push({ app: "payment", payload_location: "inline", payload: { inputs: [baseInput], outputs: [baseChange] } });
    const u = {
      version: "4.0",
      alt: "1",
      timestamp: Math.round(Date.now() / 1000),
      authors: [{ address: key.addr, definition: defOf(key), authentifiers: { r: "-" } }],
      parent_units: anc.parent_units,
      last_ball: anc.last_ball,
      last_ball_unit: anc.last_ball_unit,
      messages,
      headers_commission: 0,
      payload_commission: 0,
      tps_fee: 0,
    };
    u.messages.forEach((m) => { if (m.payload_location === "inline" && !m.payload_hash) m.payload_hash = objectHash.getBase64Hash(m.payload, true); });
    u.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(u), key.priv);
    u.headers_commission = objectLength.getHeadersSize(u);
    u.payload_commission = objectLength.getTotalPayloadSize(u);
    const genesisOut = gOut.find((o) => o.output_index === baseInputIdx);
    const baseInputAmount = genesisOut.amount; // actual genesis output amount
    const change = baseInputAmount - u.headers_commission - u.payload_commission;
    baseChange.amount = change;
    u.messages[u.messages.length - 1].payload_hash = objectHash.getBase64Hash(u.messages[u.messages.length - 1].payload, true);
    u.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(u), key.priv);
    u.unit = objectHash.getUnitHash(u);
    return u;
  }

  await validateAndSave({ unit: genesis, ball: genesisBall }, "GENESIS");
  const gRows = await q("SELECT unit, main_chain_index, is_stable FROM units WHERE unit=?", [genesis.unit]);
  console.log("E1-16 GENESIS-DB:", JSON.stringify(gRows[0]));
  // rebuild the in-memory caches from the DB; the genesis save leaves a stale unstable entry
  await storage.initCaches();
  delete storage.assocUnstableUnits[genesis.unit];
  const gOut = await q("SELECT output_index, address, amount FROM outputs WHERE unit=? ORDER BY output_index", [genesis.unit]);
  console.log("E1-16 GENESIS-OUTPUTS:", JSON.stringify(gOut));
  // find each author's genesis output index
  const idxOf = (addr) => gOut.find((o) => o.address === addr).output_index;

  // ---- 1. define a PUBLIC uncapped non-definer-only asset (A1 is the definer but anyone may issue) ----
  const assetDefPayload = {
    is_private: false, is_transferrable: true, auto_destroy: false,
    fixed_denominations: false, issued_by_definer_only: false,
    cosigned_by_definer: false, spender_attested: false,
  };
  const assetMsg = { app: "asset", payload_location: "inline", payload: assetDefPayload };
  const assetUnit = buildUnit(KEYS.A1, idxOf(KEYS.A1.addr), assetMsg, null, "ASSET-DEF");
  await validateAndSave({ unit: assetUnit }, "ASSET-DEF");
  const assetHash = assetUnit.unit;
  console.log("E1-16 ASSET:", assetHash);
  const assetBallRow = await q("SELECT ball FROM balls WHERE unit=?", [assetHash]);
  const assetBall = assetBallRow[0] ? assetBallRow[0].ball : genesisBall;
  const assetAnchor = { parent_units: [assetHash], last_ball: assetBall, last_ball_unit: assetHash };

  // ---- 2. A1 issues serial 1 (U1) ----
  function issueUnit(key, baseInputIdx, serial, amount, label) {
    const issuePayload = {
      asset: assetHash,
      inputs: [{ type: "issue", amount, serial_number: serial }],
      outputs: [{ address: key.addr, amount }],
    };
    const issueMsg = { app: "payment", payload_location: "inline", payload: issuePayload };
    return buildUnit(key, baseInputIdx, issueMsg, null, label, assetAnchor);
  }

  const U1 = issueUnit(KEYS.A1, idxOf(KEYS.A1.addr), 1, 1000, "U1-A1-issue-serial1");
  await validateAndSave({ unit: U1 }, "U1-A1-issue-serial1").catch((e) => console.log("U1 outcome:", e.message));

  // ---- 3. THE TEST: A2 issues serial 1 (U2) ----
  const U2 = issueUnit(KEYS.A2, idxOf(KEYS.A2.addr), 1, 1000, "U2-A2-issue-serial1");
  await validateAndSave({ unit: U2 }, "U2-A2-issue-serial1").catch((e) => console.log("U2 outcome:", e.message));

  // ---- 4. CONTROL A: A1 issues serial 1 again (same address) ----
  const U3 = issueUnit(KEYS.A1, idxOf(KEYS.A1.addr), 1, 1000, "U3-A1-issue-serial1-again");
  await validateAndSave({ unit: U3 }, "U3-A1-issue-serial1-again").catch((e) => console.log("U3 outcome:", e.message));

  // ---- 5. CONTROL B: definer-only asset, non-definer issue attempt ----
  const assetDefPayload2 = {
    is_private: false, is_transferrable: true, auto_destroy: false,
    fixed_denominations: false, issued_by_definer_only: true,
    cosigned_by_definer: false, spender_attested: false,
  };
  const assetMsg2 = { app: "asset", payload_location: "inline", payload: assetDefPayload2 };
  const assetUnit2 = buildUnit(KEYS.A1, idxOf(KEYS.A1.addr), assetMsg2, null, "ASSET-DEF-2");
  await validateAndSave({ unit: assetUnit2 }, "ASSET-DEF-2").catch((e) => console.log("asset2 outcome:", e.message));
  const assetHash2 = assetUnit2.unit;
  function issueUnitOn(key, baseInputIdx, asset, serial, amount, label) {
    const issuePayload = { asset, inputs: [{ type: "issue", amount, serial_number: serial }], outputs: [{ address: key.addr, amount }] };
    const issueMsg = { app: "payment", payload_location: "inline", payload: issuePayload };
    return buildUnit(key, baseInputIdx, issueMsg, null, label, assetAnchor);
  }
  const U4 = issueUnitOn(KEYS.A2, idxOf(KEYS.A2.addr), assetHash2, 1, 1000, "U4-A2-issue-defineronly");
  await validateAndSave({ unit: U4 }, "U4-A2-issue-defineronly").catch((e) => console.log("U4 outcome:", e.message));

  // ---- report DB state ----
  const issueRows = await q("SELECT unit, serial_number, amount, asset, address, is_unique FROM inputs WHERE type='issue' ORDER BY unit");
  console.log("E1-16 ISSUE-INPUTS-DB:", JSON.stringify(issueRows, null, 1));
  const assetRows = await q("SELECT unit, cap, issued_by_definer_only FROM assets ORDER BY unit");
  console.log("E1-16 ASSETS-DB:", JSON.stringify(assetRows, null, 1));
  const spentRows = await q("SELECT unit, address, amount FROM outputs WHERE asset=? ORDER BY unit", [assetHash]);
  console.log("E1-16 ASSET-OUTPUTS:", JSON.stringify(spentRows, null, 1));
  console.log("E1-16 DONE");
  process.exit(0);
}
main().catch((e) => { console.error("E1-16 FATAL", e); process.exit(1); });
