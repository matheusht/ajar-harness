// Emitted legacy server main bundle (realistic shape; the inlining pipeline treats this as data)
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const core_1 = require("@angular/core");
const platform_server_1 = require("@angular/platform-server");
globalThis.$localize = Object.assign(globalThis.$localize || {}, { locale: "en-US" });
console.log('[SERVER-MAIN] boot: rendering start');
const appRef = { render: function () { console.log('[SERVER-MAIN] rendered'); } };
exports.default = appRef;
