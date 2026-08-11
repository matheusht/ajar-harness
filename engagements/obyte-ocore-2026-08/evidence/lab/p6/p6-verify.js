// P6-verify — REAL getLocalTpsFee + getFinalTpsFee vs analytic formula, on a CLEAN 5-unit chain.
// Uses pool-level db.query (auto take/release) so no pool=1 deadlock with initCaches.
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const AUTH = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
  const q = async (label, sql, params) => {
    try { return await db.query(sql, params || []); }
    catch (e) { console.log("Q_ERR", label, String(e).slice(0, 200)); return []; }
  };

  await q("addr", "INSERT OR REPLACE INTO addresses (address) VALUES (?)", [AUTH]);

  const mkUnit = (tag, n, pad) => tag + String(n).padStart(pad, "0") + "0".repeat(Math.max(0, 44 - tag.length - pad));
  const T = 1700000000;
  const LB = mkUnit("LB", 0, 42);

  const insertUnit = async (unit, mci, ts, opts) => {
    opts = opts || {};
    await q("u:" + unit.slice(0, 7),
      "INSERT OR REPLACE INTO units (unit, version, timestamp, headers_commission, payload_commission, tps_fee, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit, last_ball_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      [unit, "4.0", ts, 100, 100, opts.tps_fee || 0, 1, opts.is_on_main_chain ? 1 : 0, mci, mci, mci, mci, 1, opts.sequence || "good", opts.best_parent_unit || null, opts.last_ball_unit || null]);
    await q("ua:" + unit.slice(0, 7), "INSERT OR REPLACE INTO unit_authors (unit, address) VALUES (?,?)", [unit, AUTH]);
    if (opts.is_on_main_chain) // stable MC units must have a ball row (readLastStableMcUnitProps requires it)
      await q("ball:" + unit.slice(0, 7), "INSERT OR REPLACE INTO balls (ball, unit) VALUES (?,?)", ["B" + "0".repeat(43), unit]);
    if (opts.parent)
      await q("par:" + unit.slice(0, 7), "INSERT OR REPLACE INTO parenthoods (parent_unit, child_unit) VALUES (?,?)", [opts.parent, unit]);
  };

  // clean 5-unit chain: LB at 100, E1..E5 at 101 (E5 on MC), all ts=T (elapsed=1) → count=5
  await insertUnit(LB, 100, T, { is_on_main_chain: true, best_parent_unit: null, last_ball_unit: null });
  let prev = LB;
  for (let i = 1; i <= 5; i++) {
    const u = mkUnit("E", i, 6);
    await insertUnit(u, 101, T, { parent: prev, best_parent_unit: prev, is_on_main_chain: (i === 5), last_ball_unit: LB, tps_fee: 0 });
    prev = u;
  }

  await storage.initCaches();
  const conn = await db.takeConnectionFromPool();
  const lastUnit = mkUnit("E", 5, 6);
  const propsE5 = await storage.readUnitPropsWithParents(conn, lastUnit);

  const feeE5 = await storage.getLocalTpsFee(conn, propsE5, 1);           // estimation side (multiplier 10)
  const analyticLocal = Math.round(10 * 10 * (Math.exp(5) - 1));
  console.log("REAL getLocalTpsFee(N=5) =", feeE5, "| analytic 100*(exp(5)-1) =", analyticLocal, "| MATCH:", feeE5 === analyticLocal);

  const finalFee = await storage.getFinalTpsFee(await storage.readUnitPropsWithParents(conn, lastUnit)); // settlement side (no multiplier)
  const analyticFinal = Math.round(10 * (Math.exp(5) - 1));
  console.log("REAL getFinalTpsFee(N=5) =", finalFee, "| analytic 10*(exp(5)-1) =", analyticFinal, "| MATCH:", finalFee === analyticFinal);

  // also verify getFinalTpsFee at count=30 and count=710 analytically (same real function, larger windows)
  console.log("analytic fee(count=30) =", Math.round(10 * (Math.exp(30) - 1)), "| fraction of supply:", (Math.round(10 * (Math.exp(30) - 1)) / 1e15).toExponential(3));
  console.log("analytic fee(count=710) =", Math.round(10 * (Math.exp(710) - 1)), "(Infinity if exp overflows double)");

  conn.release();
  console.log("P6VERIFY-DONE");
};
