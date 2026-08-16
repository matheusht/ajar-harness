// IR-F4 independent probe — persistence of -Infinity in the INT column ACROSS a pool reopen.
// Unlike r2-sqlite-infinity-test.js (single connection, SELECT after REPLACE), this one:
//   1) REPLACEs -Infinity / +Infinity / NaN / huge-finite via the REAL db.js pool
//   2) closes the pool (drops all connections, sqlite file flushed)
//   3) re-opens a NEW pool against the same file (simulates process restart)
//   4) re-reads the values and checks the min-fee gate semantics
// Also dumps the raw sqlite file storage class via the sqlite3 CLI when available.
// Run: cd <ocore> && node lab-obyte.js <abs path to this file>
module.exports = async function (db, storage) {
  const path = require("path");
  const fs = require("fs");
  const os = require("os");
  const { execSync } = require("child_process");

  // locate the lab scratch dir (desktop_app.getAppDataDir was patched by lab.js)
  const appDataDir = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/desktop_app.js").getAppDataDir();
  console.log("appDataDir =", appDataDir);
  const dbFile = path.join(appDataDir, "byteball.sqlite");
  console.log("dbFile exists:", fs.existsSync(dbFile), dbFile);

  // --- phase 1: write the poison values ---
  let conn = await db.takeConnectionFromPool();
  await conn.query("CREATE TABLE IF NOT EXISTS tps_fees_balances (address VARCHAR(32) NOT NULL, mci INT NOT NULL, tps_fees_balance INT NOT NULL DEFAULT 0)");
  await conn.query("DELETE FROM tps_fees_balances");
  await conn.query("REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES(?,?,?)", ["A", 1, -Infinity]);
  await conn.query("REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES(?,?,?)", ["B", 1, Infinity]);
  await conn.query("REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES(?,?,?)", ["C", 1, NaN]);
  await conn.query("REPLACE INTO tps_fees_balances (address, mci, tps_fees_balance) VALUES(?,?,?)", ["D", 1, -10686474581524]);
  console.log("phase1: wrote A=-Infinity B=+Infinity C=NaN D=-10686474581524");
  conn.release();

  // --- phase 2: close the pool (flush + close the sqlite file) ---
  await new Promise((resolve) => setTimeout(resolve, 300));
  const dbModule = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/db.js");
  if (dbModule.close) {
    await dbModule.close();
    console.log("pool closed (db.close called)");
  } else {
    // no exported close: drop all connections via the pool internals
    console.log("db module has no close export; relying on connection release");
  }

  // --- phase 3: raw sqlite3 CLI read of storage class + value (if CLI available) ---
  try {
    const raw = execSync(`sqlite3 "${dbFile}" "SELECT address, typeof(tps_fees_balance), tps_fees_balance FROM tps_fees_balances ORDER BY address;"`, { encoding: "utf8", timeout: 15000 });
    console.log("sqlite3 CLI raw rows (address | typeof | value):");
    console.log(raw);
  } catch (e) {
    console.log("sqlite3 CLI unavailable or failed:", e.message.split("\n")[0]);
  }
  // also show the column affinity as declared
  try {
    const schema = execSync(`sqlite3 "${dbFile}" ".schema tps_fees_balances"`, { encoding: "utf8", timeout: 15000 });
    console.log("schema:", schema.trim());
  } catch (e) {
    console.log("schema read failed:", e.message.split("\n")[0]);
  }

  // --- phase 4: reopen a NEW pool (fresh db.js require = fresh pool against same file) ---
  delete require.cache[require.resolve("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/db.js")];
  const db2 = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/db.js");
  await new Promise((resolve) => setTimeout(resolve, 1500)); // let pool open
  let conn2;
  try { conn2 = await db2.takeConnectionFromPool(); } catch (e) { console.log("reopen pool error:", e.message); return; }

  console.log("--- after REOPEN (new pool, same file) ---");
  for (const addr of ["A", "B", "C", "D"]) {
    const [row] = await conn2.query("SELECT tps_fees_balance FROM tps_fees_balances WHERE address=? AND mci<=? ORDER BY mci DESC LIMIT 1", [addr, 1]);
    const v = row.tps_fees_balance;
    console.log(addr, "re-read:", v, "| typeof:", typeof v, "| finite:", Number.isFinite(v), "| isNaN:", Number.isNaN(v));
  }
  // gate semantics after reopen
  const min_tps_fee = 17, declared = 17;
  for (const addr of ["A", "B", "C", "D"]) {
    const [row] = await conn2.query("SELECT tps_fees_balance FROM tps_fees_balances WHERE address=? AND mci<=? ORDER BY mci DESC LIMIT 1", [addr, 1]);
    const bal = row.tps_fees_balance;
    console.log(addr, "after reopen -> rejected by min-fee gate:", (bal + declared < min_tps_fee));
  }
  conn2.release();
};
