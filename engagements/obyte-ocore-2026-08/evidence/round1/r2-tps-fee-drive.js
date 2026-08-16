// R2 refutation evidence — P6: drive getFinalTpsFee + updateTpsFees through the REAL storage path
// with a synthetic stable-unit cache (same functions the stabilization flow calls at main_chain.js:~1257).
// Measures: final fee at count=N with equal-second timestamps, and the author balance delta.
// Run: cd <ocore> && node lab-obyte.js <abs path to this file>
module.exports = async function (db, storage) {
  const eventBus = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/event_bus.js");
  // wait for the real boot initCaches to finish (it loads system vars + stable units from the DB)
  await new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("caches_ready timeout")), 30000);
    eventBus.once("caches_ready", () => { clearTimeout(t); resolve(); });
  });

  const T = Math.round(Date.now() / 1000) - 10; // shared second for MC unit and last-ball unit
  const AUTHOR = "AUTHOR0000000000000000000000000000";
  const HONEST = "HONEST0000000000000000000000000000";

  function mkUnit(id, mci, parent) {
    const props = {
      unit: "unit-" + id,
      main_chain_index: mci,
      timestamp: T,
      last_ball_unit: "lastball",
      best_parent_unit: parent ? "unit-" + parent : "lastball",
      parent_units: parent ? ["unit-" + parent, "lastball"] : [],
      count_aa_responses: 0,
      bAA: false,
      is_on_main_chain: mci === 0 ? 1 : 0,
      sequence: "good",
      level: mci,
      witnessed_level: mci,
      author_addresses: [AUTHOR],
    };
    return props;
  }

  const N = 30; // flood count in the window
  const lastball = mkUnit("lastball", 0, null);
  lastball.is_on_main_chain = 1;
  storage.assocStableUnits["lastball"] = lastball;
  storage.assocStableUnitsByMci[0] = [lastball];

  const chain = [lastball];
  for (let i = 1; i <= N; i++) {
    const p = mkUnit("u" + i, i, "u" + (i - 1));
    if (i === N) p.is_on_main_chain = 1; // MC unit of mci N
    storage.assocStableUnits[p.unit] = p;
    (storage.assocStableUnitsByMci[i] = storage.assocStableUnitsByMci[i] || []).push(p);
    chain.push(p);
  }
  // honest unit settles on the same MCI N, declared the normal-rate fee (~10*(e-1)=17)
  const honest = mkUnit("honest", N, "u" + (N - 1));
  honest.unit = "unit-honest";
  honest.tps_fee = 17;
  honest.author_addresses = [HONEST];
  storage.assocStableUnits[honest.unit] = honest;
  storage.assocStableUnitsByMci[N].push(honest);

  const mc = chain[N];
  const fee = storage.getFinalTpsFee(mc);
  console.log("count=" + N + " elapsed=(T-T)||1 (getFinalTps internal)");
  console.log("final tps fee (base units) =", fee, "=", (fee / 1e9).toFixed(6), "GBYTE");

  const conn = await db.takeConnectionFromPool();
  await conn.query("DELETE FROM tps_fees_balances");
  await storage.updateTpsFees(conn, [N]);
  for (const a of [AUTHOR, HONEST]) {
    const [row] = await conn.query("SELECT tps_fees_balance FROM tps_fees_balances WHERE address=? AND mci<=? ORDER BY mci DESC LIMIT 1", [a, N]);
    console.log("author " + a.slice(0, 6) + " tps_fees_balance after settlement =", row ? row.tps_fees_balance : "none", "(", (row ? row.tps_fees_balance : 0) / 1e9, "GBYTE )");
    // validation.js:1087 gate with a normal declared fee of 17
    if (row) {
      const rejected = row.tps_fees_balance + 17 < 17;
      console.log("  -> next unit with declared=17 rejected by min-fee gate:", rejected);
    }
  }
  console.log("note: honest unit's own final fee on poisoned MCI =", storage.getFinalTpsFee(honest), "-> delta = 17 - fee =", 17 - storage.getFinalTpsFee(honest));
  conn.release();
};
