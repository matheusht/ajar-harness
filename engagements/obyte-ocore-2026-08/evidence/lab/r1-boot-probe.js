// R1 refuter boot probe: what state is the lab in after boot?
"use strict";
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
	const conf = require(process.cwd() + "/conf.js");
	console.log("PROBE conf.bLight =", conf.bLight, "| storage =", conf.storage, "| db.filename =", conf.database.filename);
	// inspect the sqlite file that was created
	const fs = require("fs");
	const path = require("path");
	const desktop_app = require(process.cwd() + "/desktop_app.js");
	const app_data_dir = desktop_app.getAppDataDir();
	console.log("PROBE app_data_dir =", app_data_dir);
	try {
		const files = fs.readdirSync(app_data_dir);
		console.log("PROBE app_data_dir contents:", files);
	} catch (e) { console.log("PROBE readdir err", e.message); }
	// list tables in the DB
	await new Promise((resolve) => {
		db.query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", function (rows) {
			console.log("PROBE tables:", rows.map(r => r.name).join(","));
			resolve();
		});
	});
	console.log("PROBE-DONE");
};
