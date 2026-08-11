// E1-1 — fee-accounting conservation test (real storage path)
// Questions: (1) does the settlement delta apply once per call (no dedup -> double-call doubles it);
// (2) is the declared fee consumed from inputs (balance closure) making the rebate conserved;
// (3) recipients split.  Uses the same synthetic-cache approach as r2-tps-fee-drive.js.
module.exports = async function (db, storage) {
  // poll until the real boot initCaches has loaded system vars (avoid the caches_ready race)
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    try {
      const v = storage.getSystemVar("base_tps_fee", 1000000);
      if (typeof v === "number" && v > 0) break;
    } catch (e) {}
    await new Promise(r => setTimeout(r, 1000));
  }

  const T = Math.round(Date.now() / 1000) - 10;
  const AUTHOR = "E1AUTHOR00000000000000000000000000";
  const RECIP = "E1RECIP000000000000000000000000000";

  // seed a unit at mci 5 whose DECLARED tps_fee differs from the FINAL settlement fee
  // declared = 1000000 (huge over-declare), final computed from the count/elapsed window
  storage.assocStableUnitsByMci[5] = [];
  const unit = {
    unit: "e1-unit-5",
    main_chain_index: 5,
    timestamp: T,
    last_ball_unit: "e1-lastball",
    best_parent_unit: "e1-lastball",
    parent_units: ["e1-lastball"],
    count_aa_responses: 0,
    bAA: false,
    is_on_main_chain: 1,
    sequence: "good",
    level: 5,
    witnessed_level: 5,
    tps_fee: 1000000, // declared
    author_addresses: [AUTHOR],
    assocEarnedHeadersCommissionRecipients: { [AUTHOR]: 60, [RECIP]: 40 },
  };
  storage.assocStableUnits["e1-unit-5"] = unit;
  storage.assocStableUnitsByMci[5].push(unit);
  // last-ball cache entry
  storage.assocStableUnits["e1-lastball"] = {
    unit: "e1-lastball", main_chain_index: 4, timestamp: T, last_ball_unit: "e1-lastball",
    best_parent_unit: "e1-lastball", parent_units: [], count_aa_responses: 0, bAA: false,
    is_on_main_chain: 1, sequence: "good", level: 4, witnessed_level: 4,
  };
  storage.getMcUnitProps = (mci) => unit; // ensure the settlement reads this unit

  const q = async (sql, p) => (await db.takeConnectionFromPool()).query(sql, p || []);
  const bal = async (addr) => {
    const conn = await db.takeConnectionFromPool();
    const [row] = await conn.query("SELECT tps_fees_balance FROM tps_fees_balances WHERE address=? ORDER BY rowid DESC LIMIT 1", [addr]);
    conn.release();
    return row ? row.tps_fees_balance : 0;
  };

  const conn = await db.takeConnectionFromPool();
  await storage.updateTpsFees(conn, [5]); // first application
  const a1 = await bal(AUTHOR), r1 = await bal(RECIP);
  await storage.updateTpsFees(conn, [5]); // second application (what a double-call would do)
  const a2 = await bal(AUTHOR), r2 = await bal(RECIP);
  conn.release();

  console.log("E1-1-RESULTS " + JSON.stringify({
    author_after_1st: a1,
    recip_after_1st: r1,
    author_after_2nd: a2,
    recip_after_2nd: r2,
    author_delta_1st: a1, // balance starts 0
    recip_delta_1st: r1,
    second_application_moved_balance: a2 !== a1 || r2 !== r1,
    note: "balance starts at 0; if 2nd call moves it, updateTpsFees has no dedup",
  }, null, 1));
};
