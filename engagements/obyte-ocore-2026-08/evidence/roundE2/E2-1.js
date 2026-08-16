// E2-1 — FEE-ACCOUNTING EMPIRICAL (retry E1-1; the money-creation question)
// Real-path: real composer-style unit construction (p2 pattern), REAL validation.validate,
// REAL storage.getFinalTpsFee / updateTpsFees / updateMissingTpsFees.
// Headline hypothesis: a TEXT-ONLY unit's declared tps_fee is NOT funded anywhere (the balance
// closure validation.js:2654-2656 is payment-path only; validateTpsFee:1049-1099 is a sufficiency
// gate). At settlement, delta = (declared - final) is credited to the author's balance -> the
// author's tps_fees_balance grows with NO matching input burn.
// Run: LAB_NO_NETWORK=1 node lab-obyte.js <abs>/evidence/roundE2/E2-1.js
"use strict";
const crypto = require("crypto");

module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
  const seed = require("/Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/p2/seed.js");
  const secp256k1 = require(O_CORE + "/node_modules/secp256k1");
  const objectLength = require(O_CORE + "/object_length.js");
  const writer = require(O_CORE + "/writer.js");
  seed.zeroEraConstants(constants);
  constants.v4UpgradeMci = 0;
  constants.pemCurvesFixMci = 0;

  function validateUnit(objJoint) {
    return new Promise((resolve) => {
      const callbacks = {
        ifOk: (state) => resolve({ verdict: "ifOk", state }),
        ifOkUnsigned: (b) => resolve({ verdict: "ifOkUnsigned", b }),
        ifUnitError: (err) => resolve({ verdict: "ifUnitError", err }),
        ifJointError: (err) => resolve({ verdict: "ifJointError", err }),
        ifTransientError: (err) => resolve({ verdict: "ifTransientError", err }),
        ifNeedParentUnits: (missing, dontsave) => resolve({ verdict: "ifNeedParentUnits", missing, dontsave }),
        ifNeedHashTree: () => resolve({ verdict: "ifNeedHashTree" }),
      };
      try { validation.validate(objJoint, callbacks); }
      catch (e) { resolve({ verdict: "SYNC-THROW", err: String(e) }); }
    });
  }

  const registerAuthor = async (kp) => {
    await q("INSERT OR IGNORE INTO addresses (address) VALUES (?)", [kp.address]);
    await q("INSERT OR IGNORE INTO definitions (definition_chash, definition, has_references) VALUES (?,?,?)",
      [kp.address, JSON.stringify(kp.definition), 0]);
  };
  const q = (sql, params) => new Promise((res, rej) => db.takeConnectionFromPool((conn) => {
    conn.query(sql, params || [], (rows, err) => { conn.release(); err ? rej(new Error(sql.slice(0,50)+" | "+err)) : res(rows); });
  }));

  async function balanceOf(address, mci) {
    const rows = await q("SELECT tps_fees_balance FROM tps_fees_balances WHERE address=? AND mci<=? ORDER BY mci DESC LIMIT 1", [address, mci]);
    return rows.length ? rows[0].tps_fees_balance : 0;
  }

  // --- boot: seed identity + genesis, initCaches ---
  const owner = seed.genKeyPair(objectHash, signature, secp256k1);
  await seed.seedLedger(db, storage, objectHash, owner, { u1Sequence: "good", u1Stable: 1 });
  // genesis needs a unit_authors row for readUnitProps (JOIN unit_authors) to return 1 row
  await q("INSERT OR IGNORE INTO addresses (address) VALUES (?)", [owner.address]);
  await q("INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [seed.GENESIS, owner.address, owner.address]);
  await storage.initCaches();
  console.log("INIT-CACHES-OK address=" + owner.address.slice(0, 12));

  // helper: build + sign a TEXT-ONLY unit with a chosen declared tps_fee
  function buildTextUnit({ objectHash, objectLength, owner, timestamp, parentUnits, lastBall, lastBallUnit, tpsFee, text }) {
    const payload = text || "e2-1 text-only unit";
    const messages = [{ app: "text", payload_location: "inline", payload, payload_hash: objectHash.getBase64Hash(payload, true) }];
    const objUnit = {
      version: "4.0", alt: "1",
      authors: [{ address: owner.address, definition: owner.definition, authentifiers: { r: "----------------------------------------------------------------------------------------" } }],
      parent_units: parentUnits, last_ball: lastBall, last_ball_unit: lastBallUnit,
      timestamp, messages, headers_commission: 0, payload_commission: 0, tps_fee: tpsFee,
    };
    for (let i = 0; i < 3; i++) {
      objUnit.headers_commission = objectLength.getHeadersSize(objUnit);
      objUnit.payload_commission = objectLength.getTotalPayloadSize(objUnit);
    }
    return objUnit;
  }

  // helper: build + sign a PAYMENT unit (spends baseInput) with a chosen declared tps_fee
  function buildPaymentUnit({ objectHash, objectLength, owner, timestamp, parentUnits, lastBall, lastBallUnit, tpsFee, baseInput, baseInputAmount }) {
    const messages = [{ app: "payment", payload_location: "inline",
      payload: { inputs: [baseInput], outputs: [{ address: owner.address, amount: 0 }] } }];
    const objUnit = {
      version: "4.0", alt: "1",
      authors: [{ address: owner.address, definition: owner.definition, authentifiers: { r: "----------------------------------------------------------------------------------------" } }],
      parent_units: parentUnits, last_ball: lastBall, last_ball_unit: lastBallUnit,
      timestamp, messages, headers_commission: 0, payload_commission: 0, tps_fee: tpsFee,
    };
    for (let i = 0; i < 4; i++) {
      objUnit.headers_commission = objectLength.getHeadersSize(objUnit);
      objUnit.payload_commission = objectLength.getTotalPayloadSize(objUnit);
      const fees = objUnit.headers_commission + objUnit.payload_commission + (objUnit.tps_fee || 0);
      const baseOut = Math.max(0, baseInputAmount - fees);
      messages[0].payload.outputs[0].amount = baseOut;
      messages[0].payload_hash = objectHash.getBase64Hash(messages[0].payload, true);
    }
    return objUnit;
  }

  // deliberately UNBALANCED payment unit: input 2e8, output 5e7, declared fee 2e8 -> the
  // closure (validation.js:2654-2656) must reject (inputs do not cover outputs + declared fee)
  function buildUnbalancedPaymentUnit({ objectHash, objectLength, owner, timestamp, parentUnits, lastBall, lastBallUnit, tpsFee, baseInput, baseInputAmount, outAmount }) {
    const messages = [{ app: "payment", payload_location: "inline",
      payload: { inputs: [baseInput], outputs: [{ address: owner.address, amount: outAmount }] } }];
    const objUnit = {
      version: "4.0", alt: "1",
      authors: [{ address: owner.address, definition: owner.definition, authentifiers: { r: "----------------------------------------------------------------------------------------" } }],
      parent_units: parentUnits, last_ball: lastBall, last_ball_unit: lastBallUnit,
      timestamp, messages, headers_commission: 0, payload_commission: 0, tps_fee: tpsFee,
    };
    for (let i = 0; i < 3; i++) {
      objUnit.headers_commission = objectLength.getHeadersSize(objUnit);
      objUnit.payload_commission = objectLength.getTotalPayloadSize(objUnit);
      messages[0].payload_hash = objectHash.getBase64Hash(messages[0].payload, true);
    }
    return objUnit;
  }

  const genesis_ball = objectHash.getBallHash(seed.GENESIS);
  const T = Math.round(Date.now() / 1000);

  const D_LARGE = 100000000000000; // 1e14 base = 100,000 GBYTE
  // === TEST A — the FUNDING GATE (the money-creation control) ===
  // A1: text-only unit (no base payment) -> must be REJECTED ("no base payment message")
  const A_text = seed.genKeyPair(objectHash, signature, secp256k1);
  await registerAuthor(A_text);
  const textUnit = buildTextUnit({ objectHash, objectLength, owner: A_text, timestamp: T,
    parentUnits: [seed.GENESIS], lastBall: genesis_ball, lastBallUnit: seed.GENESIS, tpsFee: D_LARGE });
  seed.signUnit(objectHash, signature, textUnit, A_text.priv);
  const resA = await validateUnit({ unit: textUnit });
  console.log("TEST-A1 text-only tps_fee=1e14 (no base payment) validation verdict:", resA.verdict, resA.err || "");
  console.log("TEST-A1 money-creation gate:", resA.verdict === "ifUnitError" && /no base payment message/.test(resA.err || "") ? "BLOCKED (funding gate: every valid unit needs an inline base payment whose inputs cover the declared fee)" : "NOT BLOCKED - INVESTIGATE");

  // A2: base payment with declared fee > input -> must be REJECTED ("inputs and outputs do not balance")
  const D_pay_huge = 100000000000000; // 1e14
  const C_pay = seed.genKeyPair(objectHash, signature, secp256k1);
  await registerAuthor(C_pay);
  await q("INSERT OR IGNORE INTO outputs (unit, message_index, output_index, address, amount, blinding, asset) VALUES (?,?,?,?,?,?,?)",
    [seed.GENESIS, 0, 1, C_pay.address, 200000000, null, null]);
  const payHuge = buildUnbalancedPaymentUnit({ objectHash, objectLength, owner: C_pay, timestamp: T,
    parentUnits: [seed.GENESIS], lastBall: genesis_ball, lastBallUnit: seed.GENESIS, tpsFee: D_pay_huge,
    baseInput: { unit: seed.GENESIS, message_index: 0, output_index: 1 }, baseInputAmount: 200000000, outAmount: 50000000 });
  seed.signUnit(objectHash, signature, payHuge, C_pay.priv);
  const resC = await validateUnit({ unit: payHuge });
  console.log("TEST-A2 payment tps_fee=1e14 with 2e8 input validation verdict:", resC.verdict, resC.err ? String(resC.err).slice(0, 80) : "");
  console.log("TEST-A2 unfunded-declared gate:", resC.verdict === "ifUnitError" && /do not balance/.test(resC.err || "") ? "BLOCKED (closure validation.js:2654-2656: declared fee must be funded from inputs)" : "NOT BLOCKED - INVESTIGATE");

  // A3: funded payment -> passes; settlement credits the REFUND (declared - final); net cost = final
  const D_funded = 1000000; // 1e6, fits in the 2e8 input
  const payFunded = buildPaymentUnit({ objectHash, objectLength, owner: C_pay, timestamp: T,
    parentUnits: [seed.GENESIS], lastBall: genesis_ball, lastBallUnit: seed.GENESIS, tpsFee: D_funded,
    baseInput: { unit: seed.GENESIS, message_index: 0, output_index: 1 }, baseInputAmount: 200000000 });
  seed.signUnit(objectHash, signature, payFunded, C_pay.priv);
  const resD = await validateUnit({ unit: payFunded });
  console.log("TEST-A3 funded payment tps_fee=1e6 validation verdict:", resD.verdict, resD.err ? String(resD.err).slice(0, 80) : "");
  const fundedProps = { unit: payFunded.unit, main_chain_index: 1, timestamp: T, last_ball_unit: seed.GENESIS, best_parent_unit: seed.GENESIS, parent_units: [seed.GENESIS], count_aa_responses: 0, bAA: false, is_on_main_chain: 1, sequence: "good", level: 1, witnessed_level: 0, tps_fee: D_funded, author_addresses: [C_pay.address], assocEarnedHeadersCommissionRecipients: null };
  const lastball = { unit: seed.GENESIS, main_chain_index: 0, timestamp: T - 60, is_on_main_chain: 1, is_stable: 1, sequence: "good", level: 0, witnessed_level: 0, author_addresses: [], bAA: false, count_aa_responses: 0 };
  storage.assocStableUnits[seed.GENESIS] = lastball;
  storage.assocStableUnitsByMci[0] = [lastball];
  storage.assocStableUnits[payFunded.unit] = fundedProps;
  storage.assocStableUnitsByMci[1] = [fundedProps];
  const finalF = storage.getFinalTpsFee(fundedProps);
  await q("DELETE FROM tps_fees_balances");
  let conn = await db.takeConnectionFromPool();
  await storage.updateTpsFees(conn, [1]);
  conn.release();
  const balA3 = await balanceOf(C_pay.address, 1);
  console.log("TEST-A3 final(window) fee:", finalF, "| balance after settlement:", balA3, "| refund = declared - final =", D_funded - finalF, "| net cost = declared - refund =", D_funded - (D_funded - finalF));
  console.log("TEST-A3 conservation:", balA3 === D_funded - finalF ? "CONFIRMED (refund only; declared was burned from inputs at save -> net cost = final)" : "NOT CONSERVED - INVESTIGATE");

  // === TEST C — DOUBLE-APPLICATION: call updateTpsFees for the same mci twice ===
  const beforeC = await balanceOf(C_pay.address, 1);
  conn = await db.takeConnectionFromPool();
  await storage.updateTpsFees(conn, [1]); // second application of the same mci
  conn.release();
  const afterC = await balanceOf(C_pay.address, 1);
  console.log("TEST-C double-call updateTpsFees([1]): balance before", beforeC, "-> after", afterC, "(delta applied again:", afterC !== beforeC, ")");

  // === TEST D — ER-4 MySQL watermark scenario (sqlite-equivalent: stale watermark) ===
  // On MySQL, getLastTpsFeesMci orders by creation_date; a same-second tie-break can return a
  // STALE watermark while the balances already include the mci=1 delta. In sqlite we simulate the
  // same stale state faithfully: insert a NEWER-rowid row at mci=0 so the watermark query
  // (ORDER BY rowid DESC) returns 0, while the mci=1 delta remains applied. updateMissingTpsFees
  // then reprocesses mci 1 -> reads the already-updated balance -> applies the delta AGAIN.
  // make the funded unit a STABLE DB unit at mci=1 so last_stable_mci=1 (the reprocess target)
  await q("INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit, last_ball_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    [payFunded.unit, "4.0", "1", T, payFunded.headers_commission, payFunded.payload_commission, 1, 1, 1, 1, 1, 0, 1, "good", seed.GENESIS, seed.GENESIS]);
  await q("INSERT OR IGNORE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [payFunded.unit, seed.GENESIS]);
  await q("INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [payFunded.unit, C_pay.address, C_pay.address]);
  await q("INSERT OR IGNORE INTO balls (ball, unit) VALUES (?,?)", [objectHash.getBallHash(payFunded.unit), payFunded.unit]);
  await q("INSERT OR IGNORE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES (?,?,?)", [C_pay.address, 0, 0]); // newest rowid, stale watermark
  const watermarkBefore = await q("SELECT mci FROM tps_fees_balances ORDER BY rowid DESC LIMIT 1", []);
  const balBeforeD = await balanceOf(C_pay.address, 1);
  await storage.updateMissingTpsFees();
  const balAfterD = await balanceOf(C_pay.address, 1);
  console.log("TEST-D stale-watermark: watermark=", watermarkBefore[0] && watermarkBefore[0].mci, "| balance before reprocess=", balBeforeD, "-> after=", balAfterD, "| double-application:", balAfterD !== balBeforeD ? "YES (reprocessed mci 1 with the delta applied again)" : "no");

  console.log("E2-1-DONE");
  console.log(JSON.stringify({
    TEST_A_validation: resA.verdict, TEST_A_final_fee: finalFee, TEST_A_balance: balA, TEST_A_money_created: balA > finalFee,
    TEST_A_negctrl: { verdict: resB.verdict, balance: balB },
    TEST_B_payment_huge: { verdict: resC.verdict, err: resC.err ? String(resC.err).slice(0, 80) : "" },
    TEST_B2_payment_funded: { verdict: resD.verdict },
    TEST_C_double: { before: beforeC, after: afterC },
    TEST_D_stale_watermark: { beforeC: beforeC, after: afterD },
  }, null, 1));
};
