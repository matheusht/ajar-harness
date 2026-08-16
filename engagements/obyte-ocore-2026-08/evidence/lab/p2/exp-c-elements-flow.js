// exp-c — private-elements chain flow (validateDivisiblePrivatePayment path): does the input-level
// 2289 site fire in a CONSISTENT ledger state?
//
// The elements flow (private_payment.js -> divisible_asset.validateAndSaveDivisiblePrivatePayment)
// does NOT run the message-level validateSpendProofs uniqueness check — it recomputes the proofs and
// calls validation.validatePayment directly, so the input-level checkInputDoubleSpend (onDone throw
// at validation.js:2289) is the ONLY doublespend gate in this flow.
//
// Two variants:
//   fork:      B's parents do NOT include U1 (a forked doublespend — the consistent state: B was
//              validated+saved while U1's spend was absent or not included). Expect: accepted as a
//              forked doublespend (no crash) — the input-level graph check mirrors the message-level
//              decision.
//   included:  B's parents INCLUDE U1 (sequence 'good'). Expect: 2289 throw -> crash. This state is
//              LEDGER-INCONSISTENT on the real path: for U1 to be in B's parents, U1 was saved
//              before B's validation, so U1's spend_proofs row existed then, and B's MESSAGE-level
//              check would have rejected B (exp-a 'good' proves this). Demonstrated to show the
//              throw mechanics + why the state cannot arise.
//
// RUN: LAB_NO_NETWORK=1 node lab-obyte.js <abs path>/exp-c-elements-flow.js
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const seed = require("/Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/p2/seed.js");
  const secp256k1 = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/secp256k1");
  const privatePayment = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/private_payment.js");
  seed.zeroEraConstants(constants);

  async function runVariant(variant) {
    const owner = seed.genKeyPair(objectHash, signature, secp256k1);
    const S = await seed.seedLedger(db, storage, objectHash, owner, { u1Sequence: "good", u1Stable: 1 });
    const parents = variant === "included" ? [S.U1hash] : [S.U0baseHash];
    const payload = { asset: S.asset, inputs: [{ unit: S.X.unit, message_index: 0, output_index: 0 }], outputs: [{ address: owner.address, amount: 500, blinding: S.X.blinding }] };
    const privatePayloadHash = objectHash.getBase64Hash(payload, true);
    const objB = seed.buildUnit({ objectHash, objectLength: S.objectLength, owner, timestamp: Math.round(Date.now() / 1000),
      parentUnits: parents, lastBall: S.genesis_ball, lastBallUnit: S.GENESIS,
      baseInput: { unit: S.U0baseHash, message_index: 0, output_index: 0 }, baseInputAmount: 100000000, tpsFee: 100000,
      privatePayloadHash, spendProofs: [{ spend_proof: S.P }] });
    seed.signUnit(objectHash, S.ecdsaSig, objB, owner.priv);
    // seed B's ledger rows (the unit was "already saved" when the private elements arrive)
    await seed.q(db, "INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit, last_ball_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      [objB.unit, "4.0", "1", Math.round(Date.now() / 1000), objB.headers_commission, objB.payload_commission, 1, 0, null, 0, 1, 0, 0, "good", parents[0], S.GENESIS]);
    await seed.q(db, "INSERT OR IGNORE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [objB.unit, parents[0]]);
    await seed.q(db, "INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [objB.unit, owner.address, owner.address]);
    await seed.q(db, "INSERT OR IGNORE INTO messages (unit, message_index, app, payload_hash, payload_location) VALUES (?,?,?,?,?)",
      [objB.unit, 0, "payment", objectHash.getBase64Hash(objB.messages[0].payload, true), "inline"]);
    await seed.q(db, "INSERT OR IGNORE INTO messages (unit, message_index, app, payload_hash, payload_location) VALUES (?,?,?,?,?)",
      [objB.unit, 1, "payment", privatePayloadHash, "none"]);
    // B's spend_proofs row (writer.js would insert at B's save)
    await seed.q(db, "INSERT OR IGNORE INTO spend_proofs (unit, message_index, spend_proof_index, spend_proof, address) VALUES (?,?,?,?,?)",
      [objB.unit, 1, 0, S.P, owner.address]);
    return { owner, S, objB, payload };
  }

  // fork variant — expect clean acceptance (no crash)
  try {
    const { owner, S, objB, payload } = await runVariant("fork");
    const head = { unit: objB.unit, message_index: 1, payload };
    await new Promise((resolve) => {
      privatePayment.validateAndSavePrivatePaymentChain([head], {
        ifError: (err) => { console.log("FORK-RESULT ifError:", err); resolve(); },
        ifOk: () => { console.log("FORK-RESULT ifOk (accepted as forked doublespend, NO crash)"); resolve(); },
      });
    });
  } catch (e) { console.log("FORK-RESULT SYNC-ERR:", String(e)); }

  // included variant — expect the 2289 throw (uncaught -> crash). Ledger-inconsistent state; shown for mechanism.
  const { owner, S, objB, payload } = await runVariant("included");
  console.log("INCLUDED-VARIANT: submitting B=" + objB.unit + " with parents incl. U1 (ledger-inconsistent state)");
  const head = { unit: objB.unit, message_index: 1, payload };
  const p = new Promise((resolve) => {
    privatePayment.validateAndSavePrivatePaymentChain([head], {
      ifError: (err) => { console.log("INCLUDED-RESULT ifError:", err); resolve(); },
      ifOk: () => { console.log("INCLUDED-RESULT ifOk"); resolve(); },
    });
  });
  await p;
  await new Promise((r) => setTimeout(r, 10000));
  console.log("EXP-C-END");
};
