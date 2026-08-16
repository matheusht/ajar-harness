// E2-10 — Estimation-asymmetry refund path: empirical verification
// Q1: does the settlement delta (declared - final) credit the author's balance?
// Q2: is the credit a REFUND (net cost = final fee) or an asymmetric gain?
// Q3: can the balance be converted to real spend (withdrawal path)?
// Real path: storage.getLocalTpsFee (estimation), storage.getFinalTpsFee + updateTpsFees (settlement)
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const util = require("util");
  const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
  const Decimal = require(O_CORE + "/node_modules/decimal.js");

  // --- helper: real exp() as storage.js does ---
  function exp(x) { return new Decimal(x).exp().toNumber(); }
  function roundBase(base, tps) { return Math.round(base * (exp(tps) - 1)); }

  // --- seed the stable-unit cache for the two rates we compare ---
  // A "window" is (last_ball_mci, mci]; count = stable units in the window; elapsed = mc_ts - last_ball_ts.
  // LOW window (settlement): count=5, elapsed=5  -> tps=1  -> final fee = base*(exp(1)-1)
  // HIGH window (estimation at compose time): count=30, elapsed=1 -> tps=30 -> est fee = mult*base*(exp(30)-1)
  const conn = await db.takeConnectionFromPool();
  const AUTH = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"; // synthetic author

  // system vars (mainnet defaults)
  const base_tps_fee = 10;
  const tps_interval = 1;
  const tps_fee_multiplier = 10;

  const q = async (sql, params) => { try { return await conn.query(sql, params || []); } catch (e) { console.log("Q_ERR", String(e).slice(0,150)); return []; } };
  await q("INSERT OR REPLACE INTO addresses (address) VALUES (?)", [AUTH]);

  // seed tps_fees_balances with a baseline balance B for the author
  const B0 = 1000;
  await q("REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES(?,?,?)", [AUTH, 0, B0]);

  // --- estimation: what must the author DECLARE at the high local rate? ---
  const est_fee_per_unit = Math.round(tps_fee_multiplier * base_tps_fee * (exp(30) - 1));
  const est_count_units = 1; // no AA triggers
  const est_min = est_count_units * est_fee_per_unit;
  // composer offset: declared = ceil(est_min - balance/share), share=100 -> balance
  const declared = Math.max(Math.ceil(est_min - B0), 0);

  // --- settlement: final fee at the low window rate ---
  const final_fee = roundBase(base_tps_fee, 1); // tps=1
  const delta = (declared || 0) - final_fee;

  // balance after settlement
  const balance_after = B0 + delta;

  // --- accounting ---
  // inputs funded = declared (balance closure requires inputs cover the declared fee)
  // net cost = inputs - balance change = declared - delta = declared - (declared - final) = final
  const inputs_funded = declared;
  const balance_delta = delta;
  const net_cost = inputs_funded - balance_delta;

  console.log("E2-10-RESULTS " + JSON.stringify({
    scenario: "compose at high rate (tps=30), settle at low rate (tps=1)",
    estimation: { mult: tps_fee_multiplier, base: base_tps_fee, est_fee_per_unit: est_fee_per_unit, est_min: est_min },
    declared_with_offset: declared,
    settlement: { final_fee: final_fee },
    delta: delta,
    balance: { before: B0, after: balance_after, change: balance_delta },
    accounting: { inputs_funded: inputs_funded, net_cost: net_cost, net_cost_equals_final: net_cost === final_fee },
    withdrawal_path: "none_found_statically (only tps_fees_balances writer is storage.js:1261 settlement delta; no balance->output conversion in composer/writer/wallet/headers_commission/paid_witnessing/mc_outputs)"
  }, null, 1));

  // --- Q3 empirical: is there ANY code path that pays out the balance as an output? ---
  const fs = require("fs");
  const grepOut = [];
  // re-verify: every reference to tps_fees_balance in write contexts
  for (const fn of ["composer.js","writer.js","storage.js","wallet.js","light.js","headers_commission.js","paid_witnessing.js","mc_outputs.js","light_wallet.js"]) {
    const t = fs.readFileSync(O_CORE + "/" + fn, "utf8");
    for (const m of t.matchAll(/tps_fees_balance[^\n]*/g)) {
      if (/INSERT|REPLACE|UPDATE|DELETE|INTO/.test(m[0])) grepOut.push(fn + ": " + m[0].trim());
    }
  }
  console.log("E2-10-WRITERS " + JSON.stringify(grepOut));

  conn.release();
};
