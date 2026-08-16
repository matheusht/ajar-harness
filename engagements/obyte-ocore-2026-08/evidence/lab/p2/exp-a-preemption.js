// exp-a — 2289 refutation base: message-level preemption + (c) + 1662 address-binding.
//
// Runs THREE scenarios against the REAL validation.validate() entry with seeded ledger state:
//   no-sp:        B's private payment carries NO spend_proofs -> expect "private payment must come with spend proof(s)"
//   good:         U1 conflict record is sequence='good', included in B's parents -> expect clean message-level
//                 rejection ("conflicting spend proof in inner unit") BEFORE the input-level 2289 site can fire
//   addr-binding: B single-authored with "address" in spend_proofs -> expect "when single-authored, must not put
//                 address in spend proof" (proves the spend-proof address must be an author -> the 1662 "spent from
//                 another address" throw precondition can never hold for the message-level path)
//
// RUN: LAB_NO_NETWORK=1 node lab-obyte.js <abs path>/exp-a-preemption.js
// (LAB_NO_NETWORK skips the module-load auto-start that runs initCaches against the unseeded DB;
//  we seed first, then call storage.initCaches() once to populate system vars + caches.)
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const seed = require("/Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/p2/seed.js");
  const secp256k1 = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/secp256k1");
  seed.zeroEraConstants(constants);

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

  // seed scenario 1 first so initCaches sees a consistent DB (genesis has a ball)
  const owner0 = seed.genKeyPair(objectHash, signature, secp256k1);
  await seed.seedLedger(db, storage, objectHash, owner0, { u1Sequence: "good", u1Stable: 1 });
  await storage.initCaches();
  console.log("INIT-CACHES-OK");

  const results = [];
  for (const scenario of ["no-sp", "good", "addr-binding"]) {
    const owner = seed.genKeyPair(objectHash, signature, secp256k1);
    const S = await seed.seedLedger(db, storage, objectHash, owner, { u1Sequence: "good", u1Stable: 1 });
    const spendProofs = scenario === "no-sp" ? undefined
      : scenario === "addr-binding" ? [{ spend_proof: S.P, address: owner.address }]
      : [{ spend_proof: S.P }];
    // a real private payment unit always carries the payload_hash (payload travels via the private chain)
    const privatePayloadHash = objectHash.getBase64Hash({ asset: S.asset, inputs: [{ unit: S.X.unit, message_index: 0, output_index: 0 }], outputs: [{ address: owner.address, amount: 300, blinding: S.X.blinding }] }, true);
    const objB = seed.buildUnit({ objectHash, objectLength: S.objectLength, owner, timestamp: Math.round(Date.now() / 1000),
      parentUnits: [S.U1hash], lastBall: S.genesis_ball, lastBallUnit: S.GENESIS,
      baseInput: { unit: S.U0baseHash, message_index: 0, output_index: 0 }, baseInputAmount: 100000000, tpsFee: 100000,
      privatePayloadHash, spendProofs });
    seed.signUnit(objectHash, S.ecdsaSig, objB, owner.priv);
    const res = await validateUnit({ unit: objB });
    results.push({ scenario, verdict: res.verdict, err: res.err || "", detail: res.state ? JSON.stringify(res.state).slice(0, 120) : "" });
    console.log("RESULT", scenario, JSON.stringify(results[results.length - 1]));
  }
  console.log("EXP-A-DONE");
  for (const r of results) console.log("SUMMARY", r.scenario, "->", r.verdict, r.err);
};
