// E3-16 — multi-asset private payment per-tuple uniqueness (f8 last gap)
// Real path: validation.validate + writer.saveJoint for the attack units; genesis + private
// assets + first issues seeded schema-exact (p2-lab convention). Pinned a7eb776.
// Questions:
//  Q1 cross-asset proof reuse: can a spend proof for asset A be used for asset B?
//  Q2 the uniqueness key: (asset, proof, address) or (proof, address)?
//  Q3a same-asset double-claim in ONE unit (two payload messages, same proof P) -> shared-state dedup?
//  Q3b cross-asset reference of one output (payload A vs payload B claim the same X) -> asset filter?
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const DATA = path.join(__dirname, ".e3-16data");
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
  return { priv: priv.toString("hex"), pub: pub.toString("base64"), addr: objectHash.getChash160(["sig", { pubkey: pub.toString("base64") }]) };
}
const defOf = (k) => ["sig", { pubkey: k.pub }];
function signHash(hashBuf, privHex) {
  return Buffer.from(ecdsa.ecdsaSign(hashBuf, Buffer.from(privHex, "hex")).signature).toString("base64");
}

// the exact spend-proof formula (divisible_asset.js:125-136)
function transferSpendProof(asset, unit, message_index, output_index, address, amount, blinding) {
  return objectHash.getBase64Hash({
    asset, unit, message_index, output_index, address, amount, blinding
  });
}

async function main() {
  const constants = require(O_CORE + "/constants.js");
  constants.aa2UpgradeMci = 0; constants.aa3UpgradeMci = 0; constants.v4UpgradeMci = 0;
  constants.pemCurvesFixMci = 0; constants.noPrivateAssetsWithConditionsUpgradeMci = 0;
  constants.timestampUpgradeMci = 0; constants.includeKeySizesUpgradeMci = 0;
  const TOTAL = 1000000000000000; // 1e15 = constants.TOTAL_WHITEBYTES (genesis issue must equal the cap)
  const KEYS = { W: makeKey(), A1: makeKey(), A2: makeKey() };
  const witness_addr = KEYS.W.addr;
  const genesis = {
    version: "4.0", alt: "1",
    timestamp: Math.round(Date.now() / 1000),
    authors: [{ address: witness_addr, definition: defOf(KEYS.W), authentifiers: { r: "-".repeat(88) } }],
    messages: [], witnesses: [witness_addr], headers_commission: 0, payload_commission: 0,
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

  function validateAndSave(joint, label, bSave) {
    return new Promise((resolve, reject) => {
      validation.validate(joint, {
        ifOk: (objValidationState, unlock) => {
          console.log("E3-16 " + label + " VALIDATION OK sequence=" + objValidationState.sequence);
          if (bSave) {
            objValidationState.count_primary_aa_triggers = objValidationState.count_primary_aa_triggers || 0;
            writer.saveJoint(joint, objValidationState, null, () => { unlock(); resolve("saved"); });
          } else { unlock(); resolve("validated"); }
        },
        ifUnitError: (e) => { console.log("E3-16 " + label + " UNIT-ERROR: " + e); reject(new Error(label + ": " + e)); },
        ifJointError: (e) => { console.log("E3-16 " + label + " JOINT-ERROR: " + e); reject(new Error(label + ": " + e)); },
        ifTransientError: (e) => { console.log("E3-16 " + label + " TRANSIENT: " + e); reject(new Error(label + ": " + e)); },
        ifNeedParentUnits: () => reject(new Error(label + ": need parents")),
        ifNeedHashTree: () => reject(new Error(label + ": need hash tree")),
      });
    });
  }

  await validateAndSave({ unit: genesis, ball: genesisBall }, "GENESIS", true);
  await storage.initCaches();
  const gOut = await q("SELECT output_index, address, amount FROM outputs WHERE unit=? ORDER BY output_index", [genesis.unit]);
  const idxOf = (addr) => gOut.find((o) => o.address === addr).output_index;
  await q("INSERT OR IGNORE INTO addresses (address) VALUES (?),(?)", [KEYS.A1.addr, KEYS.A2.addr]);

  // ---- seed TWO PRIVATE divisible assets A and B, each with a first issue (U1A, U1B) ----
  function seedPrivateAsset(tag, issuedByDefinerOnly) {
    const assetHash = objectHash.getBase64Hash({ is_private: true, is_transferrable: false,
      auto_destroy: true, fixed_denominations: false, issued_by_definer_only: issuedByDefinerOnly || false,
      cosigned_by_definer: false, spender_attested: false });
    // asset definition unit row (seeded)
    q("INSERT OR IGNORE INTO units (unit, version, alt, timestamp, is_free, is_stable, is_on_main_chain, main_chain_index, level, sequence, witnessed_level, best_parent_unit, last_ball_unit, headers_commission, payload_commission, tps_fee) VALUES (?,?,?,?,0,1,1,0,1,'good',0,?,?,0,0,0)",
      [assetHash, "4.0", "1", Math.round(Date.now()/1000), genesis.unit, genesis.unit]);
    q("INSERT OR IGNORE INTO unit_authors (unit, address) VALUES (?,?)", [assetHash, KEYS.A1.addr]);
    q("INSERT OR IGNORE INTO assets (unit, message_index, cap, is_private, is_transferrable, auto_destroy, fixed_denominations, issued_by_definer_only, cosigned_by_definer, spender_attested) VALUES (?,0,NULL,1,0,1,0,?,0,0)", [assetHash, issuedByDefinerOnly ? 1 : 0]);
    q("INSERT OR IGNORE INTO asset_denominations (asset, denomination, count_coins, max_issued_serial_number) VALUES (?,1,NULL,1)", [assetHash]);
    const u1 = objectHash.getBase64Hash({ seeded: tag + "-issue", serial: 1, addr: KEYS.A1.addr });
    q("INSERT OR IGNORE INTO units (unit, version, alt, timestamp, is_free, is_stable, is_on_main_chain, main_chain_index, level, sequence, witnessed_level, best_parent_unit, last_ball_unit, headers_commission, payload_commission, tps_fee) VALUES (?,?,?,?,1,0,0,NULL,1,'good',0,?,?,0,0,0)",
      [u1, "4.0", "1", Math.round(Date.now()/1000), genesis.unit, genesis.unit]);
    q("UPDATE units SET latest_included_mc_index=0 WHERE unit=?", [u1]);
    q("INSERT OR IGNORE INTO unit_authors (unit, address) VALUES (?,?)", [u1, KEYS.A1.addr]);
    q("INSERT OR IGNORE INTO inputs (unit, message_index, input_index, asset, denomination, is_unique, type, serial_number, amount, address) VALUES (?,0,0,?,1,1,'issue',1,1000,?)", [u1, assetHash, KEYS.A1.addr]);
    // output X owned by A1 with a blinding value (the private-output row shape)
    const blinding = crypto.randomBytes(12).toString("base64");
    q("INSERT OR IGNORE INTO outputs (unit, message_index, output_index, asset, address, amount, blinding) VALUES (?,0,0,?,?,1000,?)", [u1, assetHash, KEYS.A1.addr, blinding]);
    storage.assocUnstableUnits[u1] = { unit: u1, level: 1, latest_included_mc_index: 0,
      main_chain_index: null, is_on_main_chain: 0, is_free: 1, is_stable: 0, witnessed_level: 0,
      sequence: "good", best_parent_unit: genesis.unit, last_ball_unit: genesis.unit,
      timestamp: Math.round(Date.now()/1000), author_addresses: [KEYS.A1.addr],
      headers_commission: 0, payload_commission: 0, tps_fee: 0, max_aa_responses: null,
      count_aa_responses: null, count_primary_aa_triggers: 0, bAA: false };
    return { assetHash, u1, blinding };
  }
  const A = seedPrivateAsset("A", false);
  const B = seedPrivateAsset("B", true);
  console.log("E3-16 SEEDED asset A=" + A.assetHash + " u1=" + A.u1 + " ; asset B=" + B.assetHash + " u1=" + B.u1);

  // ============ Q1: cross-asset proof reuse (computation) ============
  const P_A = transferSpendProof(A.assetHash, A.u1, 0, 0, KEYS.A1.addr, 1000, A.blinding);
  const P_B = transferSpendProof(B.assetHash, B.u1, 0, 0, KEYS.A1.addr, 1000, A.blinding); // same X fields, asset B only
  const P_A_same = transferSpendProof(A.assetHash, A.u1, 0, 0, KEYS.A1.addr, 1000, A.blinding);
  console.log("E3-16 Q1 P_A=" + P_A);
  console.log("E3-16 Q1 P_B(asset swapped)=" + P_B + " differ=" + (P_A !== P_B) + " (expect true)");
  console.log("E3-16 Q1 P_A deterministic=" + (P_A === P_A_same) + " (expect true)");

  // ============ Q3a: same-asset double-claim in ONE unit (real validation path) ============
  // buildUnit variant with TWO private payment messages both carrying the same spend proof P
  function buildUnitTwoPrivate(key, proofs, label) {
    const messages = [
      { app: "payment", payload_location: "inline", payload: { inputs: [{ unit: genesis.unit, message_index: 0, output_index: idxOf(key.addr) }], outputs: [{ address: key.addr, amount: 0 }] } },
      { app: "payment", payload_location: "none", payload_hash: objectHash.getBase64Hash({ ph: "m1" + label }, true), spend_proofs: proofs },
      { app: "payment", payload_location: "none", payload_hash: objectHash.getBase64Hash({ ph: "m2" + label }, true), spend_proofs: proofs },
    ];
    const u = {
      version: "4.0", alt: "1",
      authors: [{ address: key.addr, definition: defOf(key), authentifiers: { r: "-".repeat(88) } }],
      parent_units: [genesis.unit], last_ball: genesisBall, last_ball_unit: genesis.unit,
      timestamp: Math.round(Date.now() / 1000), messages, headers_commission: 0, payload_commission: 0, tps_fee: 0,
    };
    const baseAmount = gOut.find((o) => o.output_index === idxOf(key.addr)).amount;
    for (let i = 0; i < 4; i++) {
      u.headers_commission = objectLength.getHeadersSize(u);
      u.payload_commission = objectLength.getTotalPayloadSize(u);
      const fees = u.headers_commission + u.payload_commission;
      messages[0].payload.outputs[0].amount = Math.max(0, baseAmount - fees);
      messages[0].payload_hash = objectHash.getBase64Hash(messages[0].payload, true);
    }
    u.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(u), key.priv);
    u.unit = objectHash.getUnitHash(u);
    return u;
  }
  function buildUnitOnePrivate(key, proofs, label) {
    const messages = [
      { app: "payment", payload_location: "inline", payload: { inputs: [{ unit: genesis.unit, message_index: 0, output_index: idxOf(key.addr) }], outputs: [{ address: key.addr, amount: 0 }] } },
      { app: "payment", payload_location: "none", payload_hash: objectHash.getBase64Hash({ ph: "m1" + label }, true), spend_proofs: proofs },
    ];
    const u = {
      version: "4.0", alt: "1",
      authors: [{ address: key.addr, definition: defOf(key), authentifiers: { r: "-".repeat(88) } }],
      parent_units: [genesis.unit], last_ball: genesisBall, last_ball_unit: genesis.unit,
      timestamp: Math.round(Date.now() / 1000), messages, headers_commission: 0, payload_commission: 0, tps_fee: 0,
    };
    const baseAmount = gOut.find((o) => o.output_index === idxOf(key.addr)).amount;
    for (let i = 0; i < 4; i++) {
      u.headers_commission = objectLength.getHeadersSize(u);
      u.payload_commission = objectLength.getTotalPayloadSize(u);
      const fees = u.headers_commission + u.payload_commission;
      messages[0].payload.outputs[0].amount = Math.max(0, baseAmount - fees);
      messages[0].payload_hash = objectHash.getBase64Hash(messages[0].payload, true);
    }
    u.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(u), key.priv);
    u.unit = objectHash.getUnitHash(u);
    return u;
  }

  // control: ONE private message with [P_A] -> the spend-proof dedup must NOT fire (no duplicate within)
  const U_ctrl = buildUnitOnePrivate(KEYS.A1, [{ spend_proof: P_A }], "ctrl");
  console.log("E3-16 DEBUG ctrl hc=", U_ctrl.headers_commission, "recomputed=", objectLength.getHeadersSize(U_ctrl), "pc=", U_ctrl.payload_commission, "recomputed_pc=", objectLength.getTotalPayloadSize(U_ctrl));
  try { await validateAndSave({ unit: U_ctrl }, "U-CTRL-one-msg"); console.log("E3-16 CONTROL (one msg, one proof): accepted"); }
  catch (e) { console.log("E3-16 CONTROL (one msg, one proof): " + e.message); }

  // attack: TWO private messages both with [P_A] -> expect validation.js:1571 "spend proof ... already used"
  const U_dup = buildUnitTwoPrivate(KEYS.A1, [{ spend_proof: P_A }], "dup");
  try { await validateAndSave({ unit: U_dup }, "U-DUP-two-msgs-same-proof"); console.log("E3-16 DUP OUTCOME: ACCEPTED (!!)"); }
  catch (e) { console.log("E3-16 DUP OUTCOME: REJECTED — " + e.message); }

  // ============ Q3b: cross-asset reference (the src-output asset filter) ============
  // the exact query from divisible_asset.js:118-122 against X (an asset-A output)
  const rowsA = await q("SELECT address, amount, blinding FROM outputs WHERE unit=? AND message_index=? AND output_index=? AND asset=?", [A.u1, 0, 0, A.assetHash]);
  const rowsB = await q("SELECT address, amount, blinding FROM outputs WHERE unit=? AND message_index=? AND output_index=? AND asset=?", [A.u1, 0, 0, B.assetHash]);
  console.log("E3-16 Q3b src-output lookup: asset=A rows=" + rowsA.length + " (expect 1); asset=B rows=" + rowsB.length + " (expect 0 -> 'not 1 row' rejection)");

  // ============ Q2: the input-level doublespend key (source-verified via query) ============
  const dupRows = await q("SELECT asset, type, src_unit, src_message_index, src_output_index, COUNT(*) AS c FROM inputs GROUP BY asset, type, src_unit, src_message_index, src_output_index HAVING c>1");
  console.log("E3-16 Q2 duplicate-key rows in inputs: " + JSON.stringify(dupRows) + " (expect [] — per-tuple keys)");

  console.log("E3-16 DONE");
  process.exit(0);
}
main().catch((e) => { console.error("E3-16 FATAL", e); process.exit(1); });
