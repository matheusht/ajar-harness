"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// packages/angular_devkit/build_angular/src/utils/action-executor.ts
var action_executor_exports = {};
__export(action_executor_exports, {
  BundleActionExecutor: () => BundleActionExecutor
});
module.exports = __toCommonJS(action_executor_exports);
var import_piscina = __toESM(require("piscina"));

// packages/angular_devkit/build_angular/src/utils/environment-options.ts
var import_node_os = require("node:os");
function isDisabled(variable) {
  return variable === "0" || variable.toLowerCase() === "false";
}
function isEnabled(variable) {
  return variable === "1" || variable.toLowerCase() === "true";
}
function isPresent(variable) {
  return typeof variable === "string" && variable !== "";
}
var debugOptimizeVariable = process.env["NG_BUILD_DEBUG_OPTIMIZE"];
var debugOptimize = (() => {
  if (!isPresent(debugOptimizeVariable) || isDisabled(debugOptimizeVariable)) {
    return {
      mangle: true,
      minify: true,
      beautify: false
    };
  }
  const debugValue = {
    mangle: false,
    minify: false,
    beautify: true
  };
  if (isEnabled(debugOptimizeVariable)) {
    return debugValue;
  }
  for (const part of debugOptimizeVariable.split(",")) {
    switch (part.trim().toLowerCase()) {
      case "mangle":
        debugValue.mangle = true;
        break;
      case "minify":
        debugValue.minify = true;
        break;
      case "beautify":
        debugValue.beautify = true;
        break;
    }
  }
  return debugValue;
})();
var mangleVariable = process.env["NG_BUILD_MANGLE"];
var allowMangle = isPresent(mangleVariable) ? !isDisabled(mangleVariable) : debugOptimize.mangle;
var shouldBeautify = debugOptimize.beautify;
var allowMinify = debugOptimize.minify;
var maxWorkersVariable = process.env["NG_BUILD_MAX_WORKERS"];
var maxWorkers = isPresent(maxWorkersVariable) ? +maxWorkersVariable : Math.min(4, Math.max((0, import_node_os.availableParallelism)() - 1, 1));
var parallelTsVariable = process.env["NG_BUILD_PARALLEL_TS"];
var useParallelTs = !isPresent(parallelTsVariable) || !isDisabled(parallelTsVariable);
var debugPerfVariable = process.env["NG_BUILD_DEBUG_PERF"];
var debugPerformance = isPresent(debugPerfVariable) && isEnabled(debugPerfVariable);
var watchRootVariable = process.env["NG_BUILD_WATCH_ROOT"];
var shouldWatchRoot = isPresent(watchRootVariable) && isEnabled(watchRootVariable);
var typeCheckingVariable = process.env["NG_BUILD_TYPE_CHECK"];
var useTypeChecking = !isPresent(typeCheckingVariable) || !isDisabled(typeCheckingVariable);
var buildLogsJsonVariable = process.env["NG_BUILD_LOGS_JSON"];
var useJSONBuildLogs = isPresent(buildLogsJsonVariable) && isEnabled(buildLogsJsonVariable);

// packages/angular_devkit/build_angular/src/utils/action-executor.ts
var workerFile = require.resolve('/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/node_modules/.n1d-build/pb.worker.cjs');
var BundleActionExecutor = class _BundleActionExecutor {
  constructor(workerOptions) {
    this.workerOptions = workerOptions;
  }
  workerOptions;
  workerPool;
  ensureWorkerPool() {
    if (this.workerPool) {
      return this.workerPool;
    }
    this.workerPool = new import_piscina.default({
      filename: workerFile,
      name: "inlineLocales",
      workerData: this.workerOptions,
      maxThreads: maxWorkers,
      recordTiming: false
    });
    return this.workerPool;
  }
  async inline(action) {
    return this.ensureWorkerPool().run(action, { name: "inlineLocales" });
  }
  inlineAll(actions) {
    return _BundleActionExecutor.executeAll(actions, (action) => this.inline(action));
  }
  static async *executeAll(actions, executor) {
    const executions = /* @__PURE__ */ new Map();
    for (const action of actions) {
      const execution = executor(action);
      executions.set(
        execution,
        execution.then((result) => [execution, result])
      );
    }
    while (executions.size > 0) {
      const [execution, result] = await Promise.race(executions.values());
      executions.delete(execution);
      yield result;
    }
  }
  stop() {
    if (this.workerPool) {
      void this.workerPool.destroy();
    }
  }
};
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  BundleActionExecutor
});
/**
 * @license
 * Copyright Google LLC All Rights Reserved.
 *
 * Use of this source code is governed by an MIT-style license that can be
 * found in the LICENSE file at https://angular.dev/license
 */
