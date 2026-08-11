// E1-9 — F4 end-to-end flood through REAL validation + save + stabilization
// Question: can an HONEST unit settling in a flood window be poisoned (r2's -106,865 GBYTE
// balance model), or does the real estimation gate prevent it?
// Real-path: validation.validate + writer.saveJoint for every unit (real hashes, real signatures,
// real DB rows, real caches); real main_chain.stabilizeMci (markMcIndexStable + updateTpsFees).
// Seeded boundary: custom genesis (trust root, like the initial DB) + MC topology (main_chain_index
// assignment — normally done by updateMainChain's best-parent walk, which needs witnesses the lab
// cannot simulate).
"use strict";
const crypto = require("crypto");
const util = require("util");

module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
  const objectLength = require(O_CORE + "/object_length.js");
  const writer = require(O_CORE + "/writer.js");
  const main_chain = require(O_CORE + "/main_chain.js");
  const kvstore = require(O_CORE + "/kvstore.js");
  const ecdsa = require(O_CORE + "/node_modules/secp256k1");
  const eventBus = require(O_CORE + "/event_bus.js");

  const out = { checkpoints: [], flood: [], errors: [] };
  const log = (tag, o) => { out.checkpoints.push({ tag, ...o }); console.log("[E1-9]", tag, JSON.stringify(o)); };

  // ---- keys ----
  function genKeyPair() {
    let priv = crypto.randomBytes(32);
    while (!ecdsa.privateKeyVerify(priv)) priv = crypto.randomBytes(32);
    const pub = ecdsa.publicKeyCreate(priv, true);
    const pubB64 = Buffer.from(pub).toString("base64");
    const definition = ["sig", { pubkey: pubB64 }];
    return { priv, pubB64, definition, address: objectHash.getChash160(definition) };
  }
  const attacker = genKeyPair();
  const honest = genKeyPair();

  // ---- genesis ----
  const TOTAL = 1e14; // attacker balance: 10% of the 1e15 supply (realistic whale)
  const H0 = 1e9; // honest author's seed (1 GBYTE)
  const T = Math.round(Date.now() / 1000) - 120; // shared second (elapsed=0 -> ||1 at settlement)
  const GENESIS_WITNESSES = [
    "2TO6NYBGX3NF5QS24MQLFR7KXYAMCIE5","4GDZSXHEFVFMHCUCSHZVXBVF5T2LJHMU","APABTE2IBKOIHLS2UNK6SAR4T5WRGH2J",
    "DXYWHSZ72ZDNDZ7WYZXKWBBH425C6WZN","FAB6TH7IRAVHDLK2AAWY5YBE6CEBUACF","FOPUBEUPBC6YLIQDLKL6EW775BMV7YOH",
    "GFK3RDAPQLLNCMQEVGGD2KCPZTLSG3HN","I2ADHGP4HL6J37NQAD73J7E5SKFIXJOT","JMFXY26FN76GWJJG7N36UI2LNONOGZJV",
    "JPQKPRI5FMTQRJF4ZZMYZYDQVRD55OTC","TKT4UESIKTTRALRRLWS4SENSTJX6ODCW","UE25S4GRWZOLNXZKY4VWFHNJZWUSYCQC"
  ].sort();

  function buildGenesis() {
    const objUnit = {
      version: "1.0", alt: "1",
      authors: [{ address: attacker.address, authentifiers: { r: "" } }],
      timestamp: T,
      witnesses: GENESIS_WITNESSES,
      messages: [
        { app: "payment", payload_location: "inline",
          payload: { inputs: [{ type: "issue", amount: TOTAL + H0, serial_number: 1 }],
                     outputs: [ { address: attacker.address, amount: TOTAL },
                                { address: honest.address, amount: H0 } ] } }
      ]
    };
    const hashToSign = objectHash.getUnitHashToSign(objUnit);
    objUnit.authors[0].authentifiers.r = signature.sign(hashToSign, attacker.priv);
    objUnit.unit = objectHash.getUnitHash(objUnit);
    return objUnit;
  }

  // ---- unit builder (v4, real hash/sig, fee-adaptive) ----
  function buildUnit({ author, timestamp, parentUnits, lastBall, lastBallUnit, baseInput, inputAmount, tpsFee }) {
    const messages = [
      { app: "payment", payload_location: "inline",
        payload: { inputs: [baseInput], outputs: [{ address: author.address, amount: 0 }] } }
    ];
    const objUnit = {
      version: "4.0", alt: "1",
      authors: [{ address: author.address, authentifiers: { r: "----------------------------------------------------------------------------------------" } }],
      parent_units: parentUnits, last_ball: lastBall, last_ball_unit: lastBallUnit,
      timestamp, messages, headers_commission: 0, payload_commission: 0, tps_fee: tpsFee,
    };
    for (let i = 0; i < 4; i++) {
      objUnit.headers_commission = objectLength.getHeadersSize(objUnit);
      objUnit.payload_commission = objectLength.getTotalPayloadSize(objUnit);
      const fees = objUnit.headers_commission + objUnit.payload_commission + (objUnit.tps_fee || 0);
      const baseOut = Math.max(0, inputAmount - fees);
      messages[0].payload.outputs[0].amount = baseOut;
      messages[0].payload_hash = objectHash.getBase64Hash(messages[0].payload, true);
      objUnit.payload_commission = objectLength.getTotalPayloadSize(objUnit);
    }
    const hashToSign = objectHash.getUnitHashToSign(objUnit);
    objUnit.authors[0].authentifiers.r = signature.sign(hashToSign, author.priv);
    objUnit.unit = objectHash.getUnitHash(objUnit);
    return objUnit;
  }

  // ---- real validate+save ----
  function validateAndSave(objJoint, label) {
    return new Promise((resolve) => {
      validation.validate(objJoint, {
        ifUnitError: (e) => resolve({ ok: false, error: "unit: " + e, label }),
        ifJointError: (e) => resolve({ ok: false, error: "joint: " + e, label }),
        ifTransientError: (e) => resolve({ ok: false, error: "transient: " + e, label }),
        ifNeedParentUnits: () => resolve({ ok: false, error: "need_parents", label }),
        ifNeedHashTree: () => resolve({ ok: false, error: "need_hash_tree", label }),
        ifOk: (objValidationState, unlock) => {
          writer.saveJoint(objJoint, objValidationState, null, () => {
            unlock();
            resolve({ ok: true, label, unit: objJoint.unit.unit });
          });
        },
        ifOkUnsigned: (bSerial, unlock) => { unlock(); resolve({ ok: false, error: "unsigned", label }); }
      });
    });
  }

  function q(conn, sql, params) {
    return new Promise((res, rej) => conn.query(sql, params || [], (rows, err) => err ? rej(err) : res(rows)));
  }

  // ---- init caches (the lab needs initCaches to load system vars); tolerate a missed event ----
  console.log("[E1-9] waiting for caches_ready...");
  await new Promise((res) => {
    let done = false;
    const t = setTimeout(() => { if (!done) { done = true; res(); } }, 60000);
    eventBus.once("caches_ready", () => { if (!done) { done = true; clearTimeout(t); res(); } });
  });
  console.log("[E1-9] caches wait done");

  // ---- seed genesis (trust root — mirrors the initial DB) ----
  constants.GENESIS_UNIT = "seed-pending";
  const genesis = buildGenesis();
  constants.GENESIS_UNIT = genesis.unit;
  const genesisBall = objectHash.getBallHash(genesis.unit);
  const conn = await new Promise((res) => db.takeConnectionFromPool(res));
  await q(conn, "INSERT OR IGNORE INTO addresses (address) VALUES (?)", [attacker.address]);
  await q(conn, "INSERT OR IGNORE INTO addresses (address) VALUES (?)", [honest.address]);
  await q(conn, "INSERT OR IGNORE INTO definitions (definition_chash, definition, has_references) VALUES (?,?,?)",
    [attacker.address, JSON.stringify(attacker.definition), 0]);
  await q(conn, "INSERT OR IGNORE INTO definitions (definition_chash, definition, has_references) VALUES (?,?,?)",
    [honest.address, JSON.stringify(honest.definition), 0]);
  await q(conn, "INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    [genesis.unit, "1.0", "1", T, 0, 0, 0, 1, 0, 0, 0, 0, 1, "good", null]);
  await q(conn, "INSERT OR IGNORE INTO balls (ball, unit) VALUES (?,?)", [genesisBall, genesis.unit]);
  await q(conn, "INSERT OR IGNORE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [genesis.unit, genesis.unit]);
  await q(conn, "INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [genesis.unit, attacker.address, attacker.address]);
  await q(conn, "INSERT OR IGNORE INTO messages (unit, message_index, app, payload_location, payload_hash) VALUES (?,?,?,?,?)",
    [genesis.unit, 0, "payment", "inline", objectHash.getBase64Hash(genesis.messages[0].payload, true)]);
  await q(conn, "INSERT OR IGNORE INTO outputs (unit, message_index, output_index, address, amount, blinding, asset) VALUES (?,?,?,?,?,?,?)",
    [genesis.unit, 0, 0, attacker.address, TOTAL, null, null]);
  await q(conn, "INSERT OR IGNORE INTO outputs (unit, message_index, output_index, address, amount, blinding, asset) VALUES (?,?,?,?,?,?,?)",
    [genesis.unit, 0, 1, honest.address, H0, null, null]);
  conn.release();
  // genesis joint in kvstore (readJoint needs it)
  const batch = kvstore.batch();
  batch.put("j\n" + genesis.unit, JSON.stringify({ unit: genesis }));
  await util.promisify(batch.write.bind(batch))({ sync: true });
  // reload caches so the genesis is known
  storage.assocStableUnits[genesis.unit] = { unit: genesis.unit, main_chain_index: 0, is_on_main_chain: 1, is_stable: 1, sequence: "good", timestamp: T, level: 0, witnessed_level: 0, best_parent_unit: genesis.unit, parent_units: [], author_addresses: [attacker.address] };
  storage.assocStableUnitsByMci[0] = [storage.assocStableUnits[genesis.unit]];
  log("genesis", { unit: genesis.unit, attackers: TOTAL, honest: H0, ts: T });

  // ---- Phase 1: HONEST unit H (submitted first, normal fee) ----
  const minH = await storage.getLocalTpsFee(conn ? null : null, { unit: "x", parent_units: [], best_parent_unit: genesis.unit, last_ball_unit: genesis.unit, timestamp: T }, 1);
  // getLocalTpsFee needs conn; retry with a pooled conn
  const conn2 = await new Promise((res) => db.takeConnectionFromPool(res));
  const honestProps = { unit: "h-probe", parent_units: [genesis.unit], best_parent_unit: genesis.unit, last_ball_unit: genesis.unit, timestamp: T, count_primary_aa_triggers: 0, max_aa_responses: undefined };
  const minH2 = await storage.getLocalTpsFee(conn2, honestProps, 1);
  conn2.release();
  log("honest-min-fee", { min_fee: minH2 });
  const declaredH = Math.max(200, Math.ceil(minH2 * 1.01));
  const objH = buildUnit({ author: honest, timestamp: T, parentUnits: [genesis.unit], lastBall: genesisBall, lastBallUnit: genesis.unit,
    baseInput: { unit: genesis.unit, message_index: 0, output_index: 1 }, inputAmount: H0, tpsFee: declaredH });
  const rH = await validateAndSave({ unit: objH }, "H");
  log("honest-save", { ok: rH.ok, error: rH.error || null, declared: declaredH, unit: rH.unit });
  out.honest = { ...rH, declared: declaredH, min: minH2 };

  // ---- Phase 2: FLOOD f1..fN (attacker, escalating declared fees) ----
  const N = 30;
  let prevUnit = genesis.unit;
  let prevOutputIndex = 0; // attacker's genesis output
  let prevAmount = TOTAL;
  for (let i = 1; i <= N; i++) {
    // estimation gate at submission (real function)
    const c = await new Promise((res) => db.takeConnectionFromPool(res));
    const props = { unit: "f" + i, parent_units: [prevUnit], best_parent_unit: prevUnit, last_ball_unit: genesis.unit, timestamp: T, count_primary_aa_triggers: 0, max_aa_responses: undefined };
    let minFee;
    try { minFee = await storage.getLocalTpsFee(c, props, 1); }
    catch (e) { c.release(); out.errors.push("minfee " + i + ": " + e.message); log("flood-minfee-err", { i, err: e.message }); break; }
    c.release();
    // declared = max(min, affordable); affordable = remaining balance - commissions - 1
    const tpsFee = Math.max(minFee, 0);
    const affordable = prevAmount - 100000; // leave room for commissions + change
    if (tpsFee > affordable) {
      out.flood.push({ i, rejected: "unaffordable", min_fee: tpsFee, affordable, declared: tpsFee });
      log("flood-stall", { i, min_fee: tpsFee, affordable });
      break;
    }
    const objF = buildUnit({ author: attacker, timestamp: T, parentUnits: [prevUnit], lastBall: genesisBall, lastBallUnit: genesis.unit,
      baseInput: { unit: prevUnit, message_index: 0, output_index: prevOutputIndex }, inputAmount: prevAmount, tpsFee });
    const r = await validateAndSave({ unit: objF }, "f" + i);
    if (!r.ok) {
      out.flood.push({ i, rejected: r.error, min_fee: tpsFee, declared: tpsFee });
      log("flood-reject", { i, err: r.error, min_fee: tpsFee });
      break;
    }
    out.flood.push({ i, saved: true, declared: tpsFee, min_fee: minFee, unit: r.unit });
    log("flood-saved", { i, declared: tpsFee, unit: r.unit });
    // update chain state: the new unit's output 0 is the next input
    prevUnit = r.unit;
    prevOutputIndex = 0;
    // read back the actual output amount (commissions deducted)
    const cr = await new Promise((res) => db.takeConnectionFromPool(res));
    const rows = await q(cr, "SELECT amount FROM outputs WHERE unit=? AND message_index=0 AND output_index=0", [r.unit]);
    cr.release();
    prevAmount = rows.length ? rows[0].amount : 0;
  }

  // ---- Phase 3: MC topology + stabilization (real stabilizeMci per mci) ----
  const savedUnits = out.flood.filter(f => f.saved).map(f => f.unit);
  const M = savedUnits.length;
  log("flood-total", { M, saved: savedUnits.length });
  // assign main_chain_index: flood f1..fM at mci 1..M (on-MC path), honest H at mci M+1 (top of window)
  const c3 = await new Promise((res) => db.takeConnectionFromPool(res));
  for (let i = 0; i < M; i++) {
    await q(c3, "UPDATE units SET is_on_main_chain=1, main_chain_index=?, best_parent_unit=? WHERE unit=?",
      [i + 1, i === 0 ? genesis.unit : savedUnits[i - 1], savedUnits[i]]);
  }
  if (out.honest.ok) {
    await q(c3, "UPDATE units SET is_on_main_chain=1, main_chain_index=?, best_parent_unit=? WHERE unit=?",
      [M + 1, M > 0 ? savedUnits[M - 1] : genesis.unit, out.honest.unit]);
  }
  c3.release();
  log("mc-topology", { flood_mci: "1.." + M, honest_mci: M + 1 });

  // reload unstable caches (initCaches loads unstable units into assocUnstableUnits)
  await new Promise((res, rej) => {
    storage.initCaches((err) => err ? rej(err) : res());
  });
  // mark each unstable unit's props in the cache (main_chain_index etc.)
  for (let i = 0; i < M; i++) {
    const u = savedUnits[i];
    if (storage.assocUnstableUnits[u])
      Object.assign(storage.assocUnstableUnits[u], { main_chain_index: i + 1, is_on_main_chain: 1, sequence: "good", timestamp: T, level: i + 1, witnessed_level: i + 1, best_parent_unit: i === 0 ? genesis.unit : savedUnits[i - 1], last_ball_unit: genesis.unit, is_stable: 0, author_addresses: [attacker.address] });
  }
  if (out.honest.ok && storage.assocUnstableUnits[out.honest.unit])
    Object.assign(storage.assocUnstableUnits[out.honest.unit], { main_chain_index: M + 1, is_on_main_chain: 1, sequence: "good", timestamp: T, level: M + 1, witnessed_level: M + 1, best_parent_unit: M > 0 ? savedUnits[M - 1] : genesis.unit, last_ball_unit: genesis.unit, is_stable: 0, author_addresses: [honest.address] });

  // ---- stabilize (real path: markMcIndexStable -> updateTpsFees per mci) ----
  const maxMci = M + (out.honest.ok ? 1 : 0);
  for (let mci = 1; mci <= maxMci; mci++) {
    try {
      await main_chain.stabilizeMci(mci);
      log("stabilized", { mci });
    } catch (e) {
      out.errors.push("stabilize " + mci + ": " + e.message);
      log("stabilize-err", { mci, err: e.message });
    }
  }

  // ---- Phase 4: measure ----
  const c4 = await new Promise((res) => db.takeConnectionFromPool(res));
  const bal = async (addr) => {
    const rows = await q(c4, "SELECT tps_fees_balance FROM tps_fees_balances WHERE address=? ORDER BY mci DESC LIMIT 1", [addr]);
    return rows.length ? rows[0].tps_fees_balance : null;
  };
  const act = async (unit) => {
    const rows = await q(c4, "SELECT actual_tps_fee FROM units WHERE unit=?", [unit]);
    return rows.length ? rows[0].actual_tps_fee : null;
  };
  out.measure = {
    honest_balance: out.honest.ok ? await bal(honest.address) : null,
    attacker_balance: await bal(attacker.address),
    honest_actual_fee: out.honest.ok ? await act(out.honest.unit) : null,
    flood_actual_fees: {},
  };
  for (const f of out.flood.filter(f => f.saved)) out.measure.flood_actual_fees[f.unit] = await act(f.unit);
  c4.release();
  log("measure", out.measure);

  // ---- Phase 5: post-flood honest submission (availability check) ----
  // honest author tries to author AFTER the flood stabilized (rate back to normal?)
  // NOTE: with all units stable at count M+1, the current rate estimate depends on the caches;
  // we measure the min fee for a new unit now.
  const c5 = await new Promise((res) => db.takeConnectionFromPool(res));
  let postMin;
  try {
    postMin = await storage.getLocalTpsFee(c5, { unit: "post", parent_units: [out.honest.ok ? out.honest.unit : (M > 0 ? savedUnits[M - 1] : genesis.unit)], best_parent_unit: out.honest.ok ? out.honest.unit : (M > 0 ? savedUnits[M - 1] : genesis.unit), last_ball_unit: genesis.unit, timestamp: T, count_primary_aa_triggers: 0, max_aa_responses: undefined }, 1);
  } catch (e) { postMin = "err: " + e.message; }
  c5.release();
  out.measure.post_flood_min_fee = postMin;
  log("post-flood-min-fee", { postMin });

  console.log("E1-9-RESULT " + JSON.stringify(out, null, 1));
};
