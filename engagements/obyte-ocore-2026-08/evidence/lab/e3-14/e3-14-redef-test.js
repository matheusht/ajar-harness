// E3-14 cap-proof: AA self-redefinition is structurally impossible.
// Real path: storage.insertAADefinitions (the exact function the stabilization flow uses to
// register AA definitions) against the real aa_addresses table (address PRIMARY KEY + OR IGNORE).
// Test: insert the same address twice with DIFFERENT definitions -> second must be ignored.
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const util = require("util");
  const conn = await db.takeConnectionFromPool();

  // two distinct valid-looking AA definitions (address = chash160 of the definition, as the
  // composer sets it — aa_composer.js:1295)
  const def1 = ["autonomous agent", { messages: [{ app: "text", payload: "def-one" }] }];
  const def2 = ["autonomous agent", { messages: [{ app: "text", payload: "def-two-DIFFERENT" }] }];
  const addr1 = objectHash.getChash160(JSON.stringify(def1));
  const addr2 = objectHash.getChash160(JSON.stringify(def2));
  const unit = "E3-14-TEST-UNIT-" + "0".repeat(28); // synthetic 44-char unit hash
  console.log("E3-14 addr1=", addr1, "addr2=", addr2);

  // direct call 1: defines addr1 with def1
  await util.promisify(storage.insertAADefinitions)(conn, [{ address: addr1, definition: def1 }], unit, 1, 1, false);
  // direct call 2: SAME address, DIFFERENT definition (a would-be self-redefinition)
  await util.promisify(storage.insertAADefinitions)(conn, [{ address: addr1, definition: def2 }], unit, 2, 2, true);
  // control: a genuinely NEW address still inserts
  await util.promisify(storage.insertAADefinitions)(conn, [{ address: addr2, definition: def2 }], unit, 3, 3, false);

  const rows = await conn.query("SELECT address, definition, unit, mci FROM aa_addresses ORDER BY mci");
  console.log("E3-14 AA_ADDRESSES " + JSON.stringify(rows.map(r => ({ address: r.address, unit: r.unit, mci: r.mci }))));
  const rows1 = await conn.query("SELECT definition FROM aa_addresses WHERE address=?", [addr1]);
  const row1 = rows1 && rows1[0];
  const keptDef = row1 && row1.definition;
  const originalKept = keptDef === JSON.stringify(def1);
  console.log("E3-14 RESULT addr1 definition kept = ORIGINAL (", originalKept, ") -> ",
    originalKept ? "OVERWRITE-IMPOSSIBLE" : "OVERWRITTEN!!!");
  conn.release();
};
