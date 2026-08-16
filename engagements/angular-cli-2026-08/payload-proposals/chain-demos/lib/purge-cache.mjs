// packages/angular/build/src/utils/purge-cache.ts
import { readdir, rm } from "node:fs/promises";
import { join as join2 } from "node:path";

// packages/angular/build/src/utils/normalize-cache.ts
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
var VERSION = "0.0.0-PLACEHOLDER";
function hasCacheMetadata(value) {
  return !!value && typeof value === "object" && "cli" in value && !!value["cli"] && typeof value["cli"] === "object" && "cache" in value["cli"];
}
function getCacheBasePath(workspaceRoot, cachePathSetting) {
  if (isAbsolute(cachePathSetting)) {
    return cachePathSetting;
  }
  try {
    let currentDir = workspaceRoot;
    while (true) {
      const gitPath = join(currentDir, ".git");
      if (existsSync(gitPath)) {
        const stat = statSync(gitPath);
        if (stat.isFile()) {
          const content = readFileSync(gitPath, "utf8");
          const match = /^gitdir:\s*(.+)$/m.exec(content);
          if (match) {
            const gitdir = resolve(currentDir, match[1].trim());
            const commondirPath = join(gitdir, "commondir");
            if (existsSync(commondirPath)) {
              const commondir = readFileSync(commondirPath, "utf8").trim();
              const commonGitDir = resolve(gitdir, commondir);
              return resolve(dirname(commonGitDir), cachePathSetting);
            }
          }
        }
      }
      const parentDir = dirname(currentDir);
      if (parentDir === currentDir) {
        break;
      }
      currentDir = parentDir;
    }
  } catch {
  }
  return resolve(workspaceRoot, cachePathSetting);
}
function normalizeCacheOptions(projectMetadata, worspaceRoot) {
  const cacheMetadata = hasCacheMetadata(projectMetadata) ? projectMetadata.cli.cache : {};
  const {
    // Webcontainers do not currently benefit from persistent disk caching and can lead to increased browser memory usage
    enabled = !process.versions.webcontainer,
    environment = "local",
    path = ".angular/cache"
  } = cacheMetadata;
  const isCI = process.env["CI"] === "1" || process.env["CI"]?.toLowerCase() === "true";
  let cacheEnabled = enabled;
  if (cacheEnabled) {
    switch (environment) {
      case "ci":
        cacheEnabled = isCI;
        break;
      case "local":
        cacheEnabled = !isCI;
        break;
    }
  }
  const cacheBasePath = getCacheBasePath(worspaceRoot, path);
  return {
    enabled: cacheEnabled,
    basePath: cacheBasePath,
    path: join(cacheBasePath, VERSION)
  };
}

// packages/angular/build/src/utils/purge-cache.ts
async function purgeStaleBuildCache(context) {
  const projectName = context.target?.project;
  if (!projectName) {
    return;
  }
  const metadata = await context.getProjectMetadata(projectName);
  const { basePath, path, enabled } = normalizeCacheOptions(metadata, context.workspaceRoot);
  if (!enabled) {
    return;
  }
  let baseEntries;
  try {
    baseEntries = await readdir(basePath, { withFileTypes: true });
  } catch {
    return;
  }
  const entriesToDelete = baseEntries.filter((d) => d.isDirectory()).map((d) => join2(basePath, d.name)).filter((cachePath) => cachePath !== path).map((stalePath) => rm(stalePath, { force: true, recursive: true, maxRetries: 3 }));
  await Promise.allSettled(entriesToDelete);
}
export {
  purgeStaleBuildCache
};
/**
 * @license
 * Copyright Google LLC All Rights Reserved.
 *
 * Use of this source code is governed by an MIT-style license that can be
 * found in the LICENSE file at https://angular.dev/license
 */
