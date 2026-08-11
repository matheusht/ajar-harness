// debug: step-by-step probe of the hang point
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const log = (m) => console.log("STEP", m, new Date().toISOString().slice(11, 23));
  log("start");
  const conn = await db.takeConnectionFromPool();
  log("conn taken");
  try {
    const rows = await conn.query("SELECT count(*) AS n FROM units");
    log("units count: " + JSON.stringify(rows));
  } catch (e) { log("units query err " + String(e).slice(0, 100)); }

  log("calling initCaches");
  try {
    await storage.initCaches();
    log("initCaches done");
  } catch (e) { log("initCaches err " + String(e).slice(0, 200)); }

  log("calling updateTpsFees on empty window");
  try {
    await storage.updateTpsFees(conn, [5]);
    log("updateTpsFees done");
  } catch (e) { log("updateTpsFees err " + String(e).slice(0, 200)); }

  conn.release();
  log("done");
};
