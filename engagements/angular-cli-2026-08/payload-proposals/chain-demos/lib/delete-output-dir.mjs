// packages/angular/build/src/utils/delete-output-dir.ts
import { readdir, rm } from "node:fs/promises";
import { join, resolve } from "node:path";
async function deleteOutputDir(root, outputPath, emptyOnlyDirectories) {
  const resolvedOutputPath = resolve(root, outputPath);
  if (resolvedOutputPath === root) {
    throw new Error("Output path MUST not be project root directory!");
  }
  const directoriesToEmpty = emptyOnlyDirectories ? new Set(emptyOnlyDirectories.map((directory) => join(resolvedOutputPath, directory))) : void 0;
  let entries;
  try {
    entries = await readdir(resolvedOutputPath);
  } catch (error) {
    if (error instanceof Error && "code" in error && error.code === "ENOENT") {
      return;
    }
    throw error;
  }
  for (const entry of entries) {
    const fullEntry = join(resolvedOutputPath, entry);
    if (directoriesToEmpty?.has(fullEntry)) {
      await deleteOutputDir(resolvedOutputPath, fullEntry);
      continue;
    }
    await rm(fullEntry, { force: true, recursive: true, maxRetries: 3 });
  }
}
export {
  deleteOutputDir
};
/**
 * @license
 * Copyright Google LLC All Rights Reserved.
 *
 * Use of this source code is governed by an MIT-style license that can be
 * found in the LICENSE file at https://angular.dev/license
 */
