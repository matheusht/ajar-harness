// E1-7 Phase A — single-process stabilization: synthetic genesis + witness waypoint loop
// Proves: units STABILIZE (is_stable=1, balls created) via the REAL path
// (composer.composeJoint -> validation.validate -> writer.saveJoint -> writer.js:740 advanceMcStability)
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const DATA = path.join(__dirname, ".e17a-data");
fs.rmSync(DATA, { recursive: true, force: true });
fs.mkdirSync(DATA, { recursive: true });

const crypto = require("crypto");
const ecdsa = require(O_CORE + "/node_modules/secp256k1");

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

const objectHash0 = require(O_CORE + "/object_hash.js");
const keys = { user: makeKey(), witness: makeKey() };
const defOf = (k) => ["sig", { pubkey: k.pub }];
const addrOf = (k) => objectHash0.getChash160(defOf(k));
const user_addr = addrOf(keys.user);
const witness_addr = addrOf(keys.witness);
const TOTAL = 1e15;

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
		inputs: [{ type: "issue", amount: TOTAL, serial_number: 1 }],
		outputs: [
			{ address: user_addr, amount: 0 },
			{ address: witness_addr, amount: 0 },
		],
	};
	g.messages = [{ app: "payment", payload_location: "inline", payload, payload_hash: objectHash.getBase64Hash(payload, true) }];
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.headers_commission = objectLength.getHeadersSize(g);
	g.payload_commission = objectLength.getTotalPayloadSize(g);
	const spendable = TOTAL - g.headers_commission - g.payload_commission;
	payload.outputs[0].amount = Math.floor(spendable * 0.7);
	payload.outputs[1].amount = spendable - payload.outputs[0].amount;
	payload.outputs.sort((a, b) => (a.address < b.address ? -1 : 1));
	g.messages[0].payload_hash = objectHash.getBase64Hash(payload, true);
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.unit = objectHash.getUnitHash(g);
	return g;
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
	console.log("GENESIS:", genesis.unit, "user:", user_addr, "witness:", witness_addr);

	const db = require(O_CORE + "/db.js");
	conf.bLight = false; // BEFORE first connection: migration creates system_vars only when !conf.bLight

	await new Promise((resolve) => {
		db.takeConnectionFromPool((conn) => {
			conn.query("SELECT 1", () => { conn.release(); resolve(); });
		});
	});
	const sysrows = [
		["op_list", JSON.stringify([witness_addr]), -1],
		["threshold_size", "10000", -1],
		["base_tps_fee", "10", -1],
		["tps_interval", "60", -1],
		["tps_fee_multiplier", "10", -1],
	];
	for (const [subject, value, mci] of sysrows) {
		await new Promise((resolve, reject) => {
			db.takeConnectionFromPool((conn) => {
				conn.query("INSERT OR IGNORE INTO system_vars (subject, value, vote_count_mci) VALUES (?,?,?)", [subject, value, mci], () => { conn.release(); resolve(); });
			});
		});
	}
	console.log("PRE-PROVISIONED op_list:", JSON.stringify([witness_addr]));

	const storage = require(O_CORE + "/storage.js");
	const network = require(O_CORE + "/network.js");
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

	for (let i = 0; i < 200 && typeof storage.getMinRetrievableMci() !== "number"; i++) await sleep(100);
	console.log("DB-READY min_retrievable_mci=", storage.getMinRetrievableMci(), "OP-LIST:", JSON.stringify(storage.getOpList(Infinity)));

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
						console.log(label, "SAVED", joint.unit.unit.slice(0, 16) + "...");
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

	function composeUnit(key, address, label) {
		return new Promise((resolve, reject) => {
			composer.composeJoint({
				paying_addresses: [address],
				signing_addresses: [address],
				outputs: [{ address, amount: 0 }],
				messages: [{ app: "text", payload_location: "inline", payload: label }],
				signer: makeSigner(key),
				callbacks: {
					ifOk: (joint, assocPrivatePayloads, unlock_callback) => { unlock_callback(); resolve(joint); },
					ifError: (e) => reject(new Error(label + " compose error: " + JSON.stringify(e).slice(0, 300))),
					ifNotEnoughFunds: (e) => reject(new Error(label + " not enough funds: " + e)),
				},
			});
		});
	}

	await validateAndSave({ unit: genesis, ball: genesisBall }, "GENESIS");

	const dump = async (tag) => {
		const rows = await query("SELECT unit, level, main_chain_index, is_stable, sequence, is_on_main_chain, witnessed_level FROM units ORDER BY main_chain_index");
		const balls = await query("SELECT unit FROM balls ORDER BY rowid");
		console.log(tag, "| units:", JSON.stringify(rows.map(r => ({ mci: r.main_chain_index, lvl: r.level, st: r.is_stable, seq: r.sequence, wl: r.witnessed_level }))));
		console.log(tag, "| balls:", balls.length);
		return rows;
	};

	await dump("AFTER-GENESIS");

	// alternation: user unit, witness waypoint, user unit, witness waypoint, ...
	// stability advances ~1 mci per save once the tip's witness wl >= first_unstable level
	const N_UNITS = 8; // 4 user units + 4 witness waypoints
	for (let i = 1; i <= N_UNITS; i++) {
		const isWitness = (i % 2 === 0);
		const key = isWitness ? keys.witness : keys.user;
		const addr = isWitness ? witness_addr : user_addr;
		const label = (isWitness ? "WAYPOINT" : "USER") + "-" + i;
		const joint = await composeUnit(key, addr, label);
		await validateAndSave(joint, label);
	}
	await sleep(500);
	const final = await dump("FINAL");

	const stableCount = final.filter(r => r.is_stable === 1).length;
	const hasBalls = await query("SELECT COUNT(*) AS c FROM balls");
	console.log("STABLE-COUNT:", stableCount, "BALLS:", hasBalls[0].c);
	if (stableCount >= 2 && hasBalls[0].c >= 2)
		console.log("STABILIZATION-OK: units stabilize on the synthetic network");
	else
		console.log("STABILIZATION-INCOMPLETE: stableCount=" + stableCount + " balls=" + hasBalls[0].c);
}

main().then(() => { console.log("E1-7A-DONE"); process.exit(0); }).catch(e => { console.error("E1-7A-ERR:", e); process.exit(2); });
