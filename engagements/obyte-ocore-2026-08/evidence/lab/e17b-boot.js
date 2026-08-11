// E1-7 Phase B — shared deterministic boot for the two-node lab.
// Both processes derive the SAME synthetic genesis (fixed keys) and the same op_list.
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const crypto = require("crypto");
const ecdsa = require(O_CORE + "/node_modules/secp256k1");

// FIXED keys (lab-only, synthetic; never used on any real network)
const KEY_USER = "1111111111111111111111111111111111111111111111111111111111111111";
const KEY_WITNESS = "2222222222222222222222222222222222222222222222222222222222222222";
// fallback if those fail ecdsa (unlikely): deterministic from sha256
function fixedKey(seed) {
	let priv = Buffer.from(seed, "hex");
	if (!ecdsa.privateKeyVerify(priv)) priv = crypto.createHash("sha256").update(seed).digest();
	return { priv: priv.toString("hex"), pub: Buffer.from(ecdsa.publicKeyCreate(priv, true)).toString("base64") };
}
const keys = { user: fixedKey(KEY_USER), witness: fixedKey(KEY_WITNESS) };

const signHash = (hashBuf, privHex) => Buffer.from(ecdsa.ecdsaSign(hashBuf, Buffer.from(privHex, "hex")).signature).toString("base64");
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const TOTAL = 1e15;

function defOf(k) { return ["sig", { pubkey: k.pub }]; }

async function boot(dataDir, port, opts) {
	opts = opts || {};
	fs.rmSync(dataDir, { recursive: true, force: true });
	fs.mkdirSync(dataDir, { recursive: true });

	const desktop_app = require(O_CORE + "/desktop_app.js");
	desktop_app.getAppRootDir = function () { return O_CORE; };
	desktop_app.getAppDataDir = function () { return dataDir; };

	const objectHash0 = require(O_CORE + "/object_hash.js");
	const user_addr = objectHash0.getChash160(defOf(keys.user));
	const witness_addr = objectHash0.getChash160(defOf(keys.witness));

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
			outputs: [{ address: user_addr, amount: 0 }, { address: witness_addr, amount: 0 }],
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

	const constants = require(O_CORE + "/constants.js");
	const conf = require(O_CORE + "/conf.js");
	conf.bLight = true;
	conf.port = port;
	if (opts.bServeAsHub) conf.bServeAsHub = true;

	const objectLength = require(O_CORE + "/object_length.js");
	const genesis = buildGenesis(objectHash0, objectLength);
	const genesisBall = objectHash0.getBallHash(genesis.unit);
	constants.GENESIS_UNIT = genesis.unit;
	constants.COUNT_WITNESSES = 1;
	constants.MAJORITY_OF_WITNESSES = 1;

	const db = require(O_CORE + "/db.js");
	conf.bLight = false;

	await new Promise((resolve) => {
		db.takeConnectionFromPool((conn) => { conn.query("SELECT 1", () => { conn.release(); resolve(); }); });
	});
	const sysrows = [
		["op_list", JSON.stringify([witness_addr]), -1],
		["threshold_size", "10000", -1],
		["base_tps_fee", "10", -1],
		["tps_interval", "60", -1],
		["tps_fee_multiplier", "10", -1],
	];
	for (const [subject, value, mci] of sysrows) {
		await new Promise((resolve) => {
			db.takeConnectionFromPool((conn) => {
				conn.query("INSERT OR IGNORE INTO system_vars (subject, value, vote_count_mci) VALUES (?,?,?)", [subject, value, mci], () => { conn.release(); resolve(); });
			});
		});
	}

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
		db.takeConnectionFromPool((conn) => { conn.query(sql, params || [], (rows) => { conn.release(); resolve(rows); }); });
	});
	for (let i = 0; i < 300 && typeof storage.getMinRetrievableMci() !== "number"; i++) await sleep(100);

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
					console.log("[" + label + "] VALIDATION OK sequence=" + objValidationState.sequence);
					objValidationState.count_primary_aa_triggers = objValidationState.count_primary_aa_triggers || 0;
					writer.saveJoint(joint, objValidationState, null, () => {
						unlock();
						console.log("[" + label + "] SAVED " + joint.unit.unit.slice(0, 12) + "...");
						resolve(objValidationState);
					});
				},
				ifUnitError: (e) => { console.log("[" + label + "] UNIT-ERROR", e); reject(new Error(label + " unit error: " + e)); },
				ifJointError: (e) => { console.log("[" + label + "] JOINT-ERROR", e); reject(new Error(label + " joint error: " + e)); },
				ifTransientError: (e) => { console.log("[" + label + "] TRANSIENT", e); reject(new Error(label + " transient: " + e)); },
				ifNeedParentUnits: (arr) => { console.log("[" + label + "] NEED-PARENTS", arr); reject(new Error(label + " need parents: " + arr.join(","))); },
				ifNeedHashTree: () => { console.log("[" + label + "] NEED-HASH-TREE"); reject(new Error(label + " need hash tree")); },
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
					ifError: (e) => reject(new Error(label + " compose error: " + JSON.stringify(e).slice(0, 250))),
					ifNotEnoughFunds: (e) => reject(new Error(label + " not enough funds: " + e)),
				},
			});
		});
	}

	// save the genesis on THIS node
	await validateAndSave({ unit: genesis, ball: genesisBall }, "GENESIS");

	return {
		db, storage, network, validation, objectHash, composer, writer, constants, query,
		genesis, genesisBall, keys, user_addr, witness_addr, validateAndSave, composeUnit,
	};
}

module.exports = { boot, keys, defOf, signHash, sleep, TOTAL, O_CORE };
