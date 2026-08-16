// C4A negative controls
const { createRequire } = require('node:module');
const path = require('node:path');
const fs = require('node:fs');
const projectRoot = path.join(__dirname, 'project');
const projectRequire = createRequire(projectRoot + '/');
const BASE = '@angular/common/locales/global';
const localeResolver = (l) => projectRequire.resolve(path.join(BASE, l));
function findLocaleDataPath(locale, resolver) {
  const scrubbed = locale.replace(/-x(-[a-zA-Z0-9]{1,8})+$/, '');
  try { return resolver(scrubbed); } catch { return scrubbed === 'en-US' ? findLocaleDataPath('en', resolver) : null; }
}
// N1: benign locale resolves inside the package (no escape)
const fr = findLocaleDataPath('fr', localeResolver);
console.log('[N1] fr ->', fr, '| null (no @angular/common fr data installed) or in-package?', !fr || fr.includes('@angular/common'));
// N2: malicious KEY resolves the attacker file (escape) — the discriminator
const evil = findLocaleDataPath('../../../../../evil-locale', localeResolver);
console.log('[N2] malicious key ->', evil, '| OUTSIDE package?', evil && !evil.includes('@angular/common'));
// N3: ensureValidSubPath would REJECT the explicit subPath form of the same traversal
const i18nOpts = require('/tmp/c4a-ds/i18n-options.bundle.mjs');
