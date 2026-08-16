// p2 seed — real-path ledger-state builder for the crash-family reachability experiments.
// HONESTY NOTE (for the reviewer): the lab cannot stand up a full real Obyte network (the genesis
// joint content is not in this repo; hub/witness stack out of scope). DB rows are seeded DIRECTLY
// with schema-exact values mirroring what writer.saveJoint + the private-chain flow produce on a
// real node. The code under test (validation.validate, validateSpendProofs, checkForDoublespends,
// validateDivisiblePrivatePayment) is 100% real pinned code driven through its real entry points.
// Absolute heights are minimal stand-ins; the RELATIONS the code checks (conflict included +
// sequence + mci <= last_ball_mci) are what matter.
"use strict";
const crypto = require("crypto");

const GENESIS = "oj8yEksX9Ubq7lLc+p6F2uyHUuynugeVq4+ikT67X6E="; // livenet genesis (lab is livenet-mode)

function genKeyPair(objectHash, ecdsaSig, secp256k1) {
  let priv = crypto.randomBytes(32);
  while (!secp256k1.privateKeyVerify(priv)) priv = crypto.randomBytes(32);
  const pub = secp256k1.publicKeyCreate(priv, true);
  const pubB64 = Buffer.from(pub).toString("base64");
  const definition = ["sig", { pubkey: pubB64 }];
  const address = objectHash.getChash160(definition);
  return { priv, pub, pubB64, definition, address };
}

function signUnit(objectHash, ecdsaSig, objUnit, priv) {
  const hashToSign = objectHash.getUnitHashToSign(objUnit);
  const b64sig = ecdsaSig.sign(hashToSign, priv);
  if (b64sig.length !== 88) throw Error("unexpected sig length " + b64sig.length);
  objUnit.authors[0].authentifiers.r = b64sig;
  objUnit.unit = objectHash.getUnitHash(objUnit);
  return objUnit;
}

// build a serial v4 unit: base payment (inline) + optional private payment (payload_location none + spend_proofs)
function buildUnit(params) {
  const { objectHash, objectLength, owner, timestamp, parentUnits, lastBall, lastBallUnit, baseInput,
          baseInputAmount, privatePayloadHash, spendProofs, tpsFee } = params;
  const messages = [
    { app: "payment", payload_location: "inline",
      payload: { inputs: [baseInput], outputs: [{ address: owner.address, amount: 0 }] } },
  ];
  if (privatePayloadHash) {
    const msg = { app: "payment", payload_location: "none", payload_hash: privatePayloadHash };
    if (spendProofs) msg.spend_proofs = spendProofs;
    messages.push(msg);
  }
  const objUnit = {
    version: "4.0", alt: "1",
    // dash placeholder = real signature length (44) — mirrors composer.js:890-895, keeps commissions stable across signing
    authors: [{ address: owner.address, authentifiers: { r: "----------------------------------------------------------------------------------------" } }],
    parent_units: parentUnits, last_ball: lastBall, last_ball_unit: lastBallUnit,
    timestamp, messages, headers_commission: 0, payload_commission: 0, tps_fee: tpsFee || 100000,
  };
  // iterate commissions + base output amount until the base closure balances (recompute hash each pass)
  for (let i = 0; i < 4; i++) {
    objUnit.headers_commission = objectLength.getHeadersSize(objUnit);
    objUnit.payload_commission = objectLength.getTotalPayloadSize(objUnit);
    const fees = objUnit.headers_commission + objUnit.payload_commission + (objUnit.tps_fee || 0);
    const baseOut = Math.max(0, baseInputAmount - fees);
    messages[0].payload.outputs[0].amount = baseOut;
    messages[0].payload_hash = objectHash.getBase64Hash(messages[0].payload, true);
    objUnit.payload_commission = objectLength.getTotalPayloadSize(objUnit);
  }
  return objUnit;
}

function q(db, sql, params) {
  return new Promise((resolve, reject) => {
    db.takeConnectionFromPool((conn) => {
      conn.query(sql, params || [], (rows, err) => {
        conn.release();
        if (err) return reject(new Error(sql.slice(0, 60) + " | " + err));
        resolve(rows);
      });
    });
  });
}

async function seedLedger(db, storage, objectHash, owner, scenario) {
  const genesis_ball = objectHash.getBallHash(GENESIS);
  const objectLength = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/object_length.js");
  const ecdsaSig = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/signature.js");

  // 0) owner identity: addresses + definitions rows (FK targets for unit_authors)
  await q(db, "INSERT OR IGNORE INTO addresses (address) VALUES (?)", [owner.address]);
  await q(db, "INSERT OR IGNORE INTO definitions (definition_chash, definition, has_references) VALUES (?,?,?)",
    [owner.address, JSON.stringify(owner.definition), 0]);

  // 1) genesis
  await q(db, "INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    [GENESIS, "1.0", "1", 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, "good", null]);
  await q(db, "INSERT OR IGNORE INTO balls (ball, unit) VALUES (?,?)", [genesis_ball, GENESIS]);

  // 2) U0base — pre-existing base coin source (output 100000000 to owner)
  const objU0base = buildUnit({ objectHash, objectLength, owner, timestamp: 1700000000,
    parentUnits: [GENESIS], lastBall: genesis_ball, lastBallUnit: GENESIS,
    baseInput: { type: "issue" }, baseInputAmount: 100000000, tpsFee: 0 });
  signUnit(objectHash, ecdsaSig, objU0base, owner.priv);
  await q(db, "INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit, last_ball_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    [objU0base.unit, "4.0", "1", 1700000000, objU0base.headers_commission, objU0base.payload_commission, 1, 1, 0, 0, 1, 0, 1, "good", GENESIS, GENESIS]);
  await q(db, "INSERT OR IGNORE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [objU0base.unit, GENESIS]);
  await q(db, "INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [objU0base.unit, owner.address, owner.address]);
  await q(db, "INSERT OR IGNORE INTO outputs (unit, message_index, output_index, address, amount, blinding, asset) VALUES (?,?,?,?,?,?,?)",
    [objU0base.unit, 0, 0, owner.address, 100000000, null, null]);
  await q(db, "INSERT OR IGNORE INTO balls (ball, unit) VALUES (?,?)", [objectHash.getBallHash(objU0base.unit), objU0base.unit]);

  // 3) U0priv — the private output X
  const asset = scenario.asset || crypto.randomBytes(32).toString("base64");
  // the asset itself needs a definition unit + assets row (outputs.asset FK -> assets.unit -> units.unit)
  await q(db, "INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit, last_ball_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    [asset, "4.0", "1", 1700000000, 0, 0, 1, 1, 0, 0, 1, 0, 1, "good", GENESIS, GENESIS]);
  await q(db, "INSERT OR IGNORE INTO balls (ball, unit) VALUES (?,?)", [objectHash.getBallHash(asset), asset]);
  await q(db, "INSERT OR IGNORE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [asset, GENESIS]);
  await q(db, "INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [asset, owner.address, owner.address]);
  await q(db, "INSERT OR IGNORE INTO assets (unit, message_index, cap, is_private, is_transferrable, auto_destroy, fixed_denominations, issued_by_definer_only, cosigned_by_definer, spender_attested) VALUES (?,?,?,?,?,?,?,?,?,?)",
    [asset, 0, null, 1, 1, 0, 0, 0, 0, 0]);
  const X = { unit: crypto.randomBytes(32).toString("base64"), message_index: 0, output_index: 0,
    amount: 500, address: owner.address, blinding: crypto.randomBytes(12).toString("base64"), asset };
  await q(db, "INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit, last_ball_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    [X.unit, "4.0", "1", 1700000000, 0, 0, 1, 1, 0, 0, 1, 0, 1, "good", GENESIS, GENESIS]);
  await q(db, "INSERT OR IGNORE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [X.unit, GENESIS]);
  await q(db, "INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [X.unit, owner.address, owner.address]);
  await q(db, "INSERT OR IGNORE INTO outputs (unit, message_index, output_index, address, amount, blinding, asset) VALUES (?,?,?,?,?,?,?)",
    [X.unit, 0, 0, owner.address, X.amount, X.blinding, asset]);
  await q(db, "INSERT OR IGNORE INTO balls (ball, unit) VALUES (?,?)", [objectHash.getBallHash(X.unit), X.unit]);

  // 4) U1 — the CONFLICTING private payment unit (spent X first)
  const P = objectHash.getBase64Hash({ asset, unit: X.unit, message_index: 0, output_index: 0, address: owner.address, amount: X.amount, blinding: X.blinding });
  const objU1 = buildUnit({ objectHash, objectLength, owner, timestamp: 1700000001,
    parentUnits: [GENESIS], lastBall: genesis_ball, lastBallUnit: GENESIS,
    baseInput: { unit: objU0base.unit, message_index: 0, output_index: 0 }, baseInputAmount: 100000000, tpsFee: 100000,
    privatePayloadHash: "H" + crypto.randomBytes(20).toString("base64"), spendProofs: [{ spend_proof: P }] });
  signUnit(objectHash, ecdsaSig, objU1, owner.priv);
  const u1seq = scenario.u1Sequence || "good";
  const u1stable = scenario.u1Stable === undefined ? 0 : scenario.u1Stable;
  await q(db, "INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit, last_ball_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    [objU1.unit, "4.0", "1", 1700000001, objU1.headers_commission, objU1.payload_commission, 1, 1, 0, 0, 1, 0, u1stable, u1seq, GENESIS, GENESIS]);
  await q(db, "INSERT OR IGNORE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [objU1.unit, GENESIS]);
  await q(db, "INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [objU1.unit, owner.address, owner.address]);
  await q(db, "INSERT OR IGNORE INTO balls (ball, unit) VALUES (?,?)", [objectHash.getBallHash(objU1.unit), objU1.unit]);
  await q(db, "INSERT OR IGNORE INTO spend_proofs (unit, message_index, spend_proof_index, spend_proof, address) VALUES (?,?,?,?,?)",
    [objU1.unit, 1, 0, P, owner.address]);
  await q(db, "INSERT OR IGNORE INTO inputs (unit, message_index, input_index, type, src_unit, src_message_index, src_output_index, serial_number, amount, asset, is_unique, address) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
    [objU1.unit, 1, 0, "transfer", X.unit, 0, 0, null, X.amount, asset, null, owner.address]);

  return { GENESIS, genesis_ball, P, asset, X, objU0base, objU1, U0baseHash: objU0base.unit, U1hash: objU1.unit, objectLength, ecdsaSig };
}

// zero EVERY upgrade MCI (mirrors constants.js devnet block) so the lab's mci=0 behaves like the
// current era — the attack scenario happens at the current chain height, not at genesis.
function zeroEraConstants(constants) {
  const names = ["lastBallStableInParentsUpgradeMci", "witnessedLevelMustNotRetreatUpgradeMci",
    "skipEvaluationOfUnusedNestedAddressUpgradeMci", "spendUnconfirmedUpgradeMci",
    "branchedMinMcWlUpgradeMci", "otherAddressInDefinitionUpgradeMci", "attestedInDefinitionUpgradeMci",
    "altBranchByBestParentUpgradeMci", "anyDefinitionChangeUpgradeMci", "formulaUpgradeMci",
    "witnessedLevelMustNotRetreatFromAllParentsUpgradeMci", "timestampUpgradeMci",
    "aaStorageSizeUpgradeMci", "aa2UpgradeMci", "aa3UpgradeMci", "unstableInitialDefinitionUpgradeMci",
    "includeKeySizesUpgradeMci", "v4UpgradeMci", "pemCurvesFixMci",
    "noPrivateAssetsWithConditionsUpgradeMci", "bestParentPrefersOpUpgradeMci",
    "anyDefinitionChangeUpgradeMci", "lastBallStableInParentsUpgradeMci", "noPendingDefinitionUpgradeMci"];
  for (const n of names) if (typeof constants[n] === "number") constants[n] = 0;
}

module.exports = { genKeyPair, signUnit, buildUnit, q, seedLedger, GENESIS, zeroEraConstants };
