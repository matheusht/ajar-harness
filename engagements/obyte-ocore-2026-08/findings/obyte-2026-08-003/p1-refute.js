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
	const gBall = await query("SELECT * FROM balls WHERE unit=?", [genesis.unit]);
	console.log("GENESIS-BALL-DB:", gBall.length);

	// spend proof P that the "sender" (attacker) retains
	const P = objectHash.getBase64Hash({ asset: "X", amount: 123, address: victim_addr, blinding: "attacker-knows" });

	// ---- C) victim unit U2 with spend_proofs (P) — single-authored, NO explicit address
	//         (validation.js:1557-1562 forbids an address in single-authored spend proofs) ----
	const victimSigner = makeSigner(keys.victim);
	const U2 = await composeUnit(victimSigner, victim_addr, [{ spend_proof: P }], "U2");
	await validateAndSave(U2, "U2");
	const sp = await query("SELECT unit, address, spend_proof FROM spend_proofs ORDER BY spend_proof_index");
	console.log("SPEND-PROOFS-ROWS:", JSON.stringify(sp));

	// ---- D) NEGATIVE CONTROL 1: attacker reuses P (implied attacker address) -> no conflict row -> accepted ----
	const attackerSigner = makeSigner(keys.attacker);
	const A_own = await composeUnit(attackerSigner, attacker_addr, [{ spend_proof: P }], "A_own");
	await validateAndSave(A_own, "A_own");
	console.log("NEGATIVE-CONTROL-1: unit with (P, implied attacker_addr) accepted, NO crash");

	// ---- E1) P1-CONSTRUCTION: attacker unit A with EXPLICIT (address: victim_addr) spend proof ----
	//         expected: CLEAN rejection at validation.js:1557-1562 ("when single-authored, must not put
	//         address in spend proof"), BEFORE checkForDoublespends — i.e. NO crash
	const A_victim = await composeUnit(attackerSigner, attacker_addr, [{ address: victim_addr, spend_proof: P }], "A_victim");
	console.log("A_victim composed:", A_victim.unit.unit, "-> validating...");
	try {
		await validateAndSave(A_victim, "A_victim");
		console.log("UNEXPECTED: A_victim validated without crash");
	} catch (e) {
		console.log("P1-CONSTRUCTION-RESULT: clean rejection (NO crash):", e.message);
	}

	// ---- E2) multi-authored variant: address must be an author (validation.js:1564-1568) ----
	const keys2 = { attacker2: makeKey() };
	const attacker2_addr = addrOf(keys2.attacker2);
	const attacker2Signer = makeSigner(keys2.attacker2);
	const A_multi = await new Promise((resolve, reject) => {
		composer.composeJoint({
			paying_addresses: [attacker_addr, attacker2_addr],
			signing_addresses: [attacker_addr, attacker2_addr],
			outputs: [{ address: attacker_addr, amount: 0 }],
			witnesses: [witness_addr],
			messages: [{
				app: "payment",
				payload_location: "none",
				payload_hash: objectHash.getBase64Hash({ fake: "A_multi" }),
				spend_proofs: [{ address: attacker_addr, spend_proof: P }],
			}],
			signer: {
				readDefinition: (conn, address, cb) => cb(null, address === attacker_addr ? defOf(keys.attacker) : defOf(keys2.attacker2)),
				readSigningPaths: (conn, address, cb) => cb({ r: constants.SIG_LENGTH }),
				readPrivateKey: (address, path, cb) => cb(null, Buffer.from(address === attacker_addr ? keys.attacker.priv : keys2.attacker2.priv, "hex")),
			},
			callbacks: {
				ifOk: (joint, assocPrivatePayloads, unlock_callback) => { unlock_callback(); resolve(joint); },
				ifError: (e) => reject(new Error("A_multi compose error: " + JSON.stringify(e))),
				ifNotEnoughFunds: (e) => reject(new Error("A_multi not enough funds: " + e)),
			},
		});
	});
	console.log("A_multi composed:", A_multi.unit.unit, "-> validating... (address=attacker1 is an author)");
	await validateAndSave(A_multi, "A_multi");
	console.log("MULTI-AUTHORED VARIANT: accepted (no row (P, attacker1)), NO crash");
}

main().then(() => {
	console.log("RESULT: no crash observed");
	process.exit(0);
}).catch(e => {
	console.log("RESULT-ERROR:", e.message);
	process.exit(2);
});
