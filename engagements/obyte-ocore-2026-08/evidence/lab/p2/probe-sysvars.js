// probe: dump system_vars + basic table state after lab boot
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  await new Promise((resolve, reject) => {
    db.takeConnectionFromPool((conn) => {
      conn.query("SELECT subject, value, mci, vote_count_mci FROM system_vars ORDER BY subject, vote_count_mci", (rows) => {
        for (const r of rows) {
          console.log("SYSVAR", r.subject, "vote_count_mci=" + r.vote_count_mci, "mci=" + r.mci, "value=" + String(r.value).slice(0, 60));
        }
        console.log("---tables---");
        conn.query("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('units','inputs','outputs','spend_proofs','system_vars','balls','unit_authors','definitions','assets','messages')", (trows) => {
          console.log("TABLES", trows.map(t => t.name).join(","));
          conn.release();
          resolve();
        });
      });
    });
  });
};
