// E3-10 — decisive experiment: is the F4 count=30/elapsed=1 settlement state REACHABLE?
// Two scenarios through the REAL storage path:
//   S1: realistic 1-MCI-at-a-time advance (each unit settles as the stability point reaches it)
//   S2: r2's synthesized lag state (last ball at mci 0, tip at mci 30 — what r2 seeded)
// Measures getFinalTpsFee per unit in each scenario. If S1 gives count=1/tiny fees at every step,
// the count=30 state is unreachable and F4's "every author in the window" claim needs revision.
// Run: cd <ocore> && node lab-obyte.js <abs>/evidence/lab/e310-exp.js
module.exports = async function (db, storage) {
  const util = require("util");
  const eventBus = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/event_bus.js");
  // The fresh scratch DB has no units (assocStableUnits stays empty); the experiment seeds its
  // own cache. Wait for the DB boot (initCaches) to settle, then proceed.
  const deadline = Date.now() + 150000;
  let booted = false;
  while (Date.now() < deadline) {
    if (eventBus._events && (eventBus._events.caches_ready || eventBus.listenerCount && eventBus.listenerCount("caches_ready") >= 0)) {
      try {
        const conn = await db.takeConnectionFromPool();
        await conn.query("SELECT 1");
        conn.release();
        booted = true;
        break;
      } catch (e) { /* db still booting */ }
    }
    await new Promise(r => setTimeout(r, 1000));
  }
  if (!booted) { await new Promise(r => setTimeout(r, 3000)); } // last resort: proceed after the fixed wait
  console.log("boot settled");

  // seed the system vars directly (the lab genesis path gates initial_votes on the full genesis)
  const conn0 = await db.takeConnectionFromPool();
  const svRows = await conn0.query("SELECT COUNT(*) AS c FROM system_vars");
  if (svRows[0].c === 0) {
    await conn0.query(
      "INSERT OR IGNORE INTO system_vars (subject, value, vote_count_mci) VALUES ('op_list','[]',-1),('threshold_size',10000,-1),('base_tps_fee',10,-1),('tps_interval',1,-1),('tps_fee_multiplier',10,-1)");
  }
  conn0.release();
  console.log("system vars seeded");

  const T = Math.round(Date.now() / 1000) - 10;
  const AUTHOR = "AUTHOR0000000000000000000000000000";
  const EXCHANGE = "EXCHANGE00000000000000000000000000";

  function mkUnit(id, mci, parentId, ts, author, declared) {
    return {
      unit: "unit-" + id,
      main_chain_index: mci,
      timestamp: ts,
      last_ball_unit: "unit-lastball",
      best_parent_unit: parentId ? "unit-" + parentId : "unit-lastball",
      parent_units: parentId ? ["unit-" + parentId] : [],
      count_aa_responses: 0,
      bAA: false,
      is_on_main_chain: 1,
      sequence: "good",
      level: mci,
      witnessed_level: mci,
      author_addresses: [author],
      tps_fee: declared,
      actual_tps_fee: 0,
      unit_hash: "u" + id,
      ball: "ball-" + id,
    };
  }

  function resetCaches() {
    // mutate in place — the module functions reference the module-level objects, not the exports
    for (const k of Object.keys(storage.assocStableUnits)) delete storage.assocStableUnits[k];
    for (const k of Object.keys(storage.assocStableUnitsByMci)) delete storage.assocStableUnitsByMci[k];
  }

  const results = {};

  // ============ S1: 1-MCI-at-a-time advance ============
  // The stability point advances 1 at a time (main_chain.js "not trying next any more").
  // Each unit settles when its mci is reached; its last ball is the PREVIOUS unit (count=1).
  resetCaches();
  const lb = mkUnit("lastball", 0, null, T, AUTHOR, 0);
  lb.best_parent_unit = null;
  lb.parent_units = [];
  storage.assocStableUnits[lb.unit] = lb;
  storage.assocStableUnitsByMci[0] = [lb];

  let prevId = "lastball";
  const s1Fees = [];
  for (let i = 1; i <= 30; i++) {
    const u = mkUnit("s1-" + i, i, prevId, T, AUTHOR, 17);
    u.last_ball_unit = "unit-" + prevId; // the 1-at-a-time advance: last ball = the previous unit
    storage.assocStableUnits[u.unit] = u;
    (storage.assocStableUnitsByMci[i] = storage.assocStableUnitsByMci[i] || []).push(u);
    prevId = "s1-" + i;
  }
  // simulate the 1-at-a-time advance: settle each mci in order (the unit at mci i is the last ball
  // for the unit at mci i+1). getFinalTps uses getMcUnitProps(mci) + the last_ball_unit prop.
  for (let i = 1; i <= 30; i++) {
    const u = storage.assocStableUnits["unit-s1-" + i];
    // the unit at mci i-1 is already balled (last ball)
    const fee = storage.getFinalTpsFee(u);
    s1Fees.push({ mci: i, fee });
  }
  results.s1_one_mci_at_a_time = s1Fees;

  // ============ S2: r2's synthesized lag state (last ball at 0, tip at 30) ============
  resetCaches();
  storage.assocStableUnits[lb.unit] = lb;
  storage.assocStableUnitsByMci[0] = [lb];
  const chain = [lb];
  for (let i = 1; i <= 30; i++) {
    const p = mkUnit("s2-" + i, i, "s2-" + (i - 1), T, AUTHOR, 17);
    storage.assocStableUnits[p.unit] = p;
    (storage.assocStableUnitsByMci[i] = storage.assocStableUnitsByMci[i] || []).push(p);
    chain.push(p);
  }
  // r2's drive: last ball stays at mci 0, the mc unit at mci 30 settles with the lag
  const s2Fee = storage.getFinalTpsFee(chain[30]);
  results.s2_lag_state = { count_window: 30, elapsed: "(T-T)||1", fee: s2Fee };

  // ============ S3: honest/exchange unit with a WALL-CLOCK timestamp in the lag state ============
  // The exchange's unit at mci 31 (after the attacker's chain), ts = T+5 (authored 5s after the
  // waypoint). Its settlement uses its OWN timestamp vs the last ball (mci 0, ts T).
  const honest = mkUnit("s3-exch", 31, "s2-30", T + 5, EXCHANGE, 17);
  storage.assocStableUnits[honest.unit] = honest;
  (storage.assocStableUnitsByMci[31] = storage.assocStableUnitsByMci[31] || []).push(honest);
  const s3Fee = storage.getFinalTpsFee(honest);
  results.s3_exchange_wallclock = { ts: "T+5", last_ball_ts: "T", elapsed: 5, count_in_window: "31 (chain+self)", fee: s3Fee };

  console.log("E310-RESULTS " + JSON.stringify(results, null, 1));
  console.log("E310-SUMMARY " + JSON.stringify({
    s1_last_fee: s1Fees[29], // the fee at count=30 under the real 1-at-a-time advance
    s2_lag_fee: s2Fee,       // the fee in the synthesized lag state (r2's drive state)
    s3_exchange_fee: s3Fee,  // the exchange unit's fee with a wall-clock timestamp
  }));
};
