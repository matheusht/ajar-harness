// R2 refutation evidence — P6 link (2): sqlite Infinity/NaN storage in INT column
// Uses the REAL db.js pool (sqlite3 native binding), same as production storage path.
// Run: cd <ocore> && node lab-obyte.js <abs path to this file>
module.exports = async function (db, storage) {
  const conn = await db.takeConnectionFromPool();
  await conn.query("CREATE TABLE IF NOT EXISTS tps_fees_balances (address VARCHAR(32) NOT NULL, mci INT NOT NULL, tps_fees_balance INT NOT NULL DEFAULT 0)");
  await conn.query("DELETE FROM tps_fees_balances");

  // 1) -Infinity (the claimed poisoned value)
  await conn.query("REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES(?,?,?)", ["A", 1, -Infinity]);
  // 2) +Infinity
  await conn.query("REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES(?,?,?)", ["B", 1, Infinity]);
  // 3) NaN
  await conn.query("REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES(?,?,?)", ["C", 1, NaN]);
  // 4) huge finite 1e14 (count=30 poisoning magnitude)
  await conn.query("REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES(?,?,?)", ["D", 1, -10686474581524]);

  for (const addr of ["A", "B", "C", "D"]) {
    const [row] = await conn.query("SELECT tps_fees_balance FROM tps_fees_balances WHERE address=? AND mci<=? ORDER BY mci DESC LIMIT 1", [addr, 1]);
    const v = row.tps_fees_balance;
    console.log(addr, "stored:", v, "| typeof:", typeof v, "| finite:", Number.isFinite(v), "| isNaN:", Number.isNaN(v));
  }

  // min-fee gate semantics (validation.js:1087): balance + declared < min_tps_fee -> reject
  const min_tps_fee = 17; // ~10*(exp(1)-1) at normal rate
  const declared = 17;
  for (const addr of ["A", "B", "C", "D"]) {
    const [row] = await conn.query("SELECT tps_fees_balance FROM tps_fees_balances WHERE address=? AND mci<=? ORDER BY mci DESC LIMIT 1", [addr, 1]);
    const bal = row.tps_fees_balance;
    const rejected = (bal + declared < min_tps_fee);
    console.log(addr, "author-with-balance", bal, "declared", declared, "-> rejected by gate:", rejected);
  }
  conn.release();
};
