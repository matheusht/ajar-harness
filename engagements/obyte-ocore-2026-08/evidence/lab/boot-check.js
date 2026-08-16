// boot-check: verify the in-process lab boots the pinned ocore cleanly (DB inits lazily)
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  // hashing module works
  const h = objectHash.getBase64Hash({ a: 1, b: "x" });
  console.log("HASH-OK", typeof h === "string" && h.length > 20);
  // signature module loads
  console.log("SIG-MODULE-OK", typeof signature.sign === "function" && typeof signature.verify === "function");
  // storage module loads with query functions
  console.log("STORAGE-OK", typeof storage.readUnit === "function");
  // DB connection pool works (lazy init + query)
  await new Promise((resolve, reject) => {
    db.takeConnectionFromPool((conn) => {
      conn.query("SELECT 1 AS ok", (rows) => {
        console.log("DB-QUERY-OK", rows && rows[0] && rows[0].ok === 1);
        conn.release();
        resolve();
      });
    });
  });
};
