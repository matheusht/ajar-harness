// E1-6 real-path test — cap enforcement on AA-style issue inputs (divisible assets)
// Self-booting; seeds the base ledger via p2's seedLedger (genesis + U0base with spendable base
// coin), then for each test case seeds a base-funding unit and validates a REAL unit carrying an
// issue input (amount variants) through validation.validate.
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const dst_dir = path.join(__dirname, ".e1-6data");
fs.rmSync(dst_dir, { recursive: true, force: true });
fs.mkdirSync(dst_dir, { recursive: true });

const desktop_app = require(O_CORE + "/desktop_app.js");
desktop_app.getAppRootDir = function () { return O_CORE; };
desktop_app.getAppDataDir = function () { return dst_dir; };
const constants = require(O_CORE + "/constants.js");
constants.aa2UpgradeMci = 0; constants.aa3UpgradeMci = 0; constants.v4UpgradeMci = 0;
constants.pemCurvesFixMci = 0; constants.noPrivateAssetsWithConditionsUpgradeMci = 0;
constants.timestampUpgradeMci = 0; constants.includeKeySizesUpgradeMci = 0;

const db = require(O_CORE + "/db.js");
const storage = require(O_CORE + "/storage.js");
const validation = require(O_CORE + "/validation.js");
const objectHash = require(O_CORE + "/object_hash.js");
const signature = require(O_CORE + "/signature.js");
const objectLength = require(O_CORE + "/object_length.js");
const writer = require(O_CORE + "/writer.js");
const secp256k1 = require(O_CORE + "/node_modules/secp256k1");
const seed = require("/Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/p2/seed.js");

const GENESIS = constants.GENESIS_UNIT;
const genesis_ball = objectHash.getBallHash(GENESIS);
const q = (sql, params) => new Promise((resolve) => {
  db.takeConnectionFromPool((conn) => { conn.query(sql, params || [], (rows) => { conn.release(); resolve(rows); }); });
});

// clone of p2's buildUnit with extra messages support + base-input funding
function buildUnitWithExtra(params) {
  const { objectHash, objectLength, owner, timestamp, parentUnits, lastBall, lastBallUnit, baseInput,
          baseInputAmount, tpsFee, extraMessages } = params;
  const messages = [
    { app: "payment", payload_location: "inline",
      payload: { inputs: [baseInput], outputs: [{ address: owner.address, amount: 0 }] } },
  ].concat(extraMessages || []);
  const objUnit = {
    version: "4.0", alt: "1",
    authors: [{ address: owner.address, authentifiers: { r: "----------------------------------------------------------------------------------------" } }],
    parent_units: parentUnits, last_ball: lastBall, last_ball_unit: lastBallUnit,
    timestamp, messages, headers_commission: 0, payload_commission: 0, tps_fee: tpsFee || 100000,
  };
  for (let i = 0; i < 6; i++) {
    objUnit.headers_commission = objectLength.getHeadersSize(objUnit);
    objUnit.payload_commission = objectLength.getTotalPayloadSize(objUnit);
    const fees = objUnit.headers_commission + objUnit.payload_commission + (objUnit.tps_fee || 0);
    const baseOut = Math.max(0, baseInputAmount - fees);
    messages[0].payload.outputs[0].amount = baseOut;
    messages.forEach((m) => {
      if (m.payload_location === "inline" && m.payload)
        m.payload_hash = objectHash.getBase64Hash(m.payload, true);
    });
    objUnit.payload_commission = objectLength.getTotalPayloadSize(objUnit);
  }
  return objUnit;
}

async function seedFundingUnit(owner, tag) {
  const unit = buildUnitWithExtra({
    objectHash, objectLength, owner, timestamp: 1700000000 + tag,
    parentUnits: [GENESIS], lastBall: genesis_ball, lastBallUnit: GENESIS,
    baseInput: { type: "issue" }, baseInputAmount: 100000000, tpsFee: 0
  });
  seed.signUnit(objectHash, signature, unit, owner.priv);
  await q("INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit, last_ball_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    [unit.unit, "4.0", "1", 1700000000 + tag, unit.headers_commission, unit.payload_commission, 1, 1, 0, 0, 1, 0, 1, "good", GENESIS, GENESIS]);
  await q("INSERT OR IGNORE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [unit.unit, GENESIS]);
  await q("INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [unit.unit, owner.address, owner.address]);
  await q("INSERT OR IGNORE INTO outputs (unit, message_index, output_index, address, amount, blinding, asset) VALUES (?,?,?,?,?,?,?)",
    [unit.unit, 0, 0, owner.address, 100000000, null, null]);
  await q("INSERT OR IGNORE INTO balls (ball, unit) VALUES (?,?)", [objectHash.getBallHash(unit.unit), unit.unit]);
  return unit;
}

function main() {
  return new Promise(async (resolve, reject) => {
    try {
      const owner = seed.genKeyPair(objectHash, signature, secp256k1);
      await seed.seedLedger(db, storage, objectHash, owner, { u1Sequence: "good", u1Stable: 1 });
      await q("INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [GENESIS, owner.address, owner.address]);
      await storage.initCaches();
      console.log("E1-6 INIT-CACHES-OK owner=", owner.address);

      const validateUnit = (unit) => new Promise((res) => {
        try {
          validation.validate({ unit }, {
            ifUnitError: (err) => res({ result: "REJECTED", err: String(err).slice(0, 150) }),
            ifJointError: (err) => res({ result: "JOINT-ERR", err: String(err).slice(0, 150) }),
            ifTransientError: (err) => res({ result: "TRANSIENT", err: String(err).slice(0, 150) }),
            ifOk: (state) => res({ result: "OK", state }),
            ifOkUnsigned: () => res({ result: "OK-UNSIGNED" }),
            ifNeedParentUnits: () => res({ result: "NEED-PARENTS" }),
            ifNeedHashTree: () => res({ result: "NEED-HT" })
          });
        } catch (e) { res({ result: "SYNC-THROW", err: String(e).slice(0, 150) }); }
      });

      // --- 1) fund the asset-definition unit + build it ---
      const funding0 = await seedFundingUnit(owner, 1);
      const CAP = 9000000000000000; // MAX_CAP = 9e15 (< 2^53, exact)
      const assetMsg = {
        app: "asset", payload_location: "inline",
        payload: {
          cap: CAP, is_private: false, is_transferrable: true, auto_destroy: false,
          fixed_denominations: false, issued_by_definer_only: true,
          cosigned_by_definer: false, spender_attested: false
        }
      };
      const assetUnit = buildUnitWithExtra({
        objectHash, objectLength, owner, timestamp: 1700000010,
        parentUnits: [GENESIS], lastBall: genesis_ball, lastBallUnit: GENESIS,
        baseInput: { unit: funding0.unit, message_index: 0, output_index: 0 }, baseInputAmount: 100000000, tpsFee: 100000,
        extraMessages: [assetMsg]
      });
      seed.signUnit(objectHash, signature, assetUnit, owner.priv);
      const ar = await validateUnit(assetUnit);
      console.log("E1-6 asset-def validation:", JSON.stringify(ar));
      if (ar.result !== "OK") { console.log("E1-6-ABORT cannot define asset"); resolve(); return; }
      // seed the asset's DB rows directly (schema-exact; validation consumes the assets table +
      // the asset unit row via loadAssetWithListOfAttestedAuthors) — same convention as p2's seed
      await q("INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit, last_ball_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [assetUnit.unit, "4.0", "1", 1700000010, assetUnit.headers_commission, assetUnit.payload_commission, 1, 1, 0, 0, 1, 0, 1, "good", GENESIS, GENESIS]);
      await q("INSERT OR IGNORE INTO balls (ball, unit) VALUES (?,?)", [objectHash.getBallHash(assetUnit.unit), assetUnit.unit]);
      await q("INSERT OR IGNORE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [assetUnit.unit, GENESIS]);
      await q("INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [assetUnit.unit, owner.address, owner.address]);
      await q("INSERT OR IGNORE INTO assets (unit, message_index, cap, is_private, is_transferrable, auto_destroy, fixed_denominations, issued_by_definer_only, cosigned_by_definer, spender_attested) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [assetUnit.unit, 1, CAP, 0, 1, 0, 0, 1, 0, 0]);
      console.log("E1-6 asset seeded:", assetUnit.unit);

      // --- 2) issue-input units: each with its own base funding ---
      const cases = [
        ["amount=CAP (exact)", CAP, 1],
        ["amount=CAP+1 (one over)", CAP + 1, 1],
        ["amount=2*CAP (double)", CAP * 2, 1],
        ["amount=CAP serial=2", CAP, 2],
        ["amount=2^53-1 (MAX_SAFE)", Number.MAX_SAFE_INTEGER, 1],
        ["amount=2^53 (unsafe boundary)", 2 ** 53, 1],
        ["amount=2^53+1", 2 ** 53 + 1, 1]
      ];
      for (let ci = 0; ci < cases.length; ci++) {
        const [label, amount, serial] = cases[ci];
        const fund = await seedFundingUnit(owner, 100 + ci);
        const issueMsg = {
          app: "payment", payload_location: "inline",
          payload: {
            asset: assetUnit.unit,
            inputs: [{ type: "issue", amount, serial_number: serial }],
            outputs: [{ address: owner.address, amount }]
          }
        };
        const unit = buildUnitWithExtra({
          objectHash, objectLength, owner, timestamp: 1700000020 + ci,
          parentUnits: [GENESIS], lastBall: genesis_ball, lastBallUnit: GENESIS,
          baseInput: { unit: fund.unit, message_index: 0, output_index: 0 }, baseInputAmount: 100000000, tpsFee: 100000,
          extraMessages: [issueMsg]
        });
        seed.signUnit(objectHash, signature, unit, owner.priv);
        const r = await validateUnit(unit);
        console.log("E1-6", label, "->", JSON.stringify(r));
      }
      console.log("E1-6-DONE");
      resolve();
    } catch (e) { console.error("E1-6-ERR", e); reject(e); }
  });
}

main().then(() => process.exit(0)).catch(() => process.exit(1));
