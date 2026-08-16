// packages/angular/cli/src/commands/mcp/tools/run-target/options-serializer.ts
function serializeOptions(options, excludeKeys = /* @__PURE__ */ new Set()) {
  const args = [];
  if (!options) {
    return args;
  }
  for (const [key, value] of Object.entries(options)) {
    if (excludeKeys.has(key)) {
      continue;
    }
    if (!/^[a-zA-Z0-9-_]+$/.test(key)) {
      throw new Error(
        `Invalid option key: '${key}'. Option keys must be alphanumeric, hyphens, or underscores.`
      );
    }
    if (typeof value === "boolean") {
      args.push(value ? `--${key}` : `--no-${key}`);
    } else if (Array.isArray(value)) {
      for (const item of value) {
        args.push(`--${key}=${item}`);
      }
    } else if (value !== null && value !== void 0) {
      args.push(`--${key}=${value}`);
    }
  }
  return args;
}

// packages/angular/cli/src/commands/mcp/host.ts
var CommandError = class extends Error {
  constructor(message, logs, code) {
    super(message);
    this.logs = logs;
    this.code = code;
  }
  logs;
  code;
};

// packages/angular/cli/src/commands/mcp/utils.ts
function getCommandErrorLogs(e) {
  if (e instanceof CommandError) {
    return [...e.logs, e.message];
  } else if (e instanceof Error) {
    return [e.message];
  } else {
    return [String(e)];
  }
}

// packages/angular/cli/src/commands/mcp/tools/run-target/generic-target-strategy.ts
var BUILT_IN_COMMANDS = /* @__PURE__ */ new Set([
  "build",
  "test",
  "e2e",
  "serve",
  "deploy",
  "extract-i18n",
  "lint"
]);
var GenericTargetStrategy = class {
  canHandle(targetName, builder) {
    return true;
  }
  async execute(input, context) {
    if (input.targetName === "serve" || input.options?.["watch"] === true) {
      throw new Error(
        `Watch mode execution (serve target or watch option) is not yet supported by 'run_target'. Please use the legacy 'devserver_start' / 'devserver_wait_for_build' tools instead.`
      );
    }
    const args = [];
    if (BUILT_IN_COMMANDS.has(input.targetName)) {
      args.push(input.targetName, input.projectName);
    } else {
      args.push("run", `${input.projectName}:${input.targetName}`);
    }
    if (input.configuration) {
      args.push(`--configuration=${input.configuration}`);
    }
    let options = input.options;
    if (input.targetName === "test") {
      options = {
        ...options,
        watch: false
      };
    }
    args.push(...serializeOptions(options));
    let status = "success";
    let logs;
    try {
      const result = await context.host.executeNgCommand(args, { cwd: input.workspacePath });
      logs = result.logs;
    } catch (e) {
      status = "failure";
      logs = getCommandErrorLogs(e);
    }
    return { status, logs };
  }
};
export {
  GenericTargetStrategy,
  serializeOptions
};
/**
 * @license
 * Copyright Google LLC All Rights Reserved.
 *
 * Use of this source code is governed by an MIT-style license that can be
 * found in the LICENSE file at https://angular.dev/license
 */
