# Exceptional report patterns

Research note for `reporting.vulnerability-report-writing`. Sources reviewed 2026-11-13:

- V12 Security public PoCs: `github.com/v12-security/pocs`
  - `ghostscript/REPORT.md`
  - `office_jdbc_bugs/libreoffice/REPORT.md`
  - `misc/20260622-rabby.md`
  - `pintheft/README.md`
  - `postgresql/server/README.md`
  - `thorchain/20260602/README.md`
- Nebula Security `github.com/NebuSec/CyberMeowfia`
  - `Nginx-PoolSlip/README.md`
  - `security-research/Ndays/Android-CVE-2026-43074/README.MD`
- GitHub Security Lab report template: `github.com/github/securitylab/blob/main/docs/report-template.md`
- HackerOne quality-report guidance: `docs.hackerone.com/en/articles/8475116-quality-reports`

External reports are evidence of craft and packaging, not facts to copy into a harness report.

## The transferable structure

The two vendor-advisory reports share an exact heading order:

```text
Summary -> Impact -> Vulnerability Details -> Proof of Concept Files -> Reproduction
-> Expected Security Behavior -> Tested Versions
```

Three choices matter:

1. Impact comes before the mechanism. A reader can route the report without understanding the
   full exploit.
2. The package manifest comes before the commands. The reader sees what exists before being asked
   to run it.
3. Tested versions come last, after the reader has seen the proof work.

The harness's old order put affected versions third and impact seventh. That is the largest
structural divergence.

## Twelve patterns

### 1. Capability first, non-requirements second

Ghostscript opens:

> "A crafted PostScript program can make Ghostscript execute an attacker-chosen shell command
> while running under the `-dSAFER` sandbox. The program never references an external file and
> never depends on a fixed address..."

The second sentence removes the two reasons a reviewer would dismiss the PoC: it needs a file drop
or a hardcoded address. State the capability, then what it does not need.

### 2. Title names the defective property, a real symbol, the actor, and the outcome

> "Unsigned Finality Metadata in Attestation Signing Allows Malicious Proposer to Bypass
> Confirmation Requirements and Steal Pool Funds"

> "Missing redaction of hardware-keyring data in persistAllKeyrings leads to plaintext disclosure
> of GridPlus pairing credentials"

Both name a symbol that appears in the body, an actor, and a consequence. Both fit the 150-character
platform cap. The Android drop uses the inverse for a fragment: CVE first, build codename second.

### 3. Impact before mechanism, manifest before commands

The Ghostscript report order is Summary, Impact, Vulnerability Details, Proof of Concept Files,
Reproduction, Expected Security Behavior, Tested Versions. LibreOffice uses the same sequence.
The reader can stop after Impact if the bug is not theirs.

### 4. Citation grammar: commit-pinned, fence header, negative marker

Rabby writes:

```typescript
// src/background/service/keyring/index.ts:57-60 (pre-fix)
const UNENCRYPTED_IGNORE_KEYRING = [
```

and marks the offending member inline:

```typescript
LatticeKeyring,        // <-- GridPlus Hardware
```

Thorchain marks the unsigned schema field:

```protobuf
int64 finalise_height = 8;   // NOT SIGNED
```

The code fence carries the path and line range; the prose explains the guard; the report closes
with a source-area index (`file` + `symbols`). Do not make the reader guess which line matters.

### 5. Jargon budget: one anchor per project symbol

Ghostscript introduces a project term with an immediate gloss:

> "A procedure-source filter stream use-after-free (`psi/zfproc.c`)..."
>
> "ShadingType 5 (a free-form Gouraud triangle mesh)..."

There is no paragraph explaining what a use-after-free is. Spend the definition budget on
project-specific vocabulary, not general security concepts.

### 6. Impact is the primitive, not the demo

Ghostscript:

> "The proof of concept runs `id` and writes its output to a file. The underlying primitive is
> arbitrary command execution; the demonstration command is incidental."

LibreOffice:

> "The proof of concept uses a JDBC driver that launches Calculator, but the primitive is
> arbitrary Java bytecode execution through a loaded driver class."

Severity is scored on the primitive. The demo is evidence, not the claim.

### 7. Proof package: manifest with roles, generated vs authored

Ghostscript's package tree is followed by a role sentence per file, generator flags, and the
retarget point ("editing the `layout` dict"). The report says which files are generated and which
are safe to delete. The script imports the builder so bytes never diverge.

A bare zip listing is not a package. A manifest with `path`, `role`, `authored|generated`, and
`regenerate_cmd` is.

### 8. Declare the environment delta and what it masks

Thorchain patches the mocknet's confirmation requirement and says why:

> "The second adjusts the mocknet's hardcoded confirmation requirement (the default value of 1
> makes all transactions instantly final, masking the vulnerability)."

This is the difference between "reproducible" and "reproducible only after two constants change,
here is why each is necessary." A proof that patches the target must enumerate each delta with a
`masks` clause.

### 9. Reproduction names silent-failure conditions

Ghostscript:

> "The shading decomposition that carries the write primitive is elided on
> `nullpage`/`bbox`/`pdfwrite`, so the PoC must be rendered to a raster device..."

and:

> "The proof file is created even though Ghostscript may exit with a non-zero status after the
> command runs..."

Every element exists because the naive test gives a false negative. Add `## Will not work if`
before the steps.

### 10. Expected output is per-step and evidence slots keep the miss

LibreOffice shows the exact HTTP requests:

```text
GET /poc-calculator.odb
GET /evil-calculator-driver.jar
```

Thorchain prints an ordered evidence chain, including an absent slot:

```text
(no ready=false logs found; tx may have reached required confs quickly)
```

The absent slot is not deleted. The conclusion names which slots carried it. Do not round evidence
to make totals match.

### 11. Tested versions are parseable, with run count and rate

Ghostscript:

```text
Rendered with: gs -q -dSAFER -dBATCH -dNOPAUSE -sDEVICE=pbmraw -r10 -g60x60 -o /dev/null
Result: command executed (8/8 runs)
```

and:

> "The two underlying bugs were located in GhostPDL 10.08.0 source and confirmed present at
> identical source lines; behavioral validation ran on the 10.02.1 system build."

The `audited_version` / `executed_version` split is explicit. The Android note includes a build
fingerprint, page size, and success rate. A single green run is not a rate.

### 12. Cleanup placement follows blast radius

Pintheft prints the restore command before executing the corrupted target:

```sh
sudo cp /tmp/.backup_<name>_<pid> <target> && sudo chmod u+s <target>
```

The warning block is at the top; the cleanup command is recoverable; the residual risk is named.
Nginx uses a one-line container cleanup. Match placement to radius, not to habit.

## What the best reports omit

- Discovery narrative, tool/agent transcripts, and work timestamps.
- CVSS vectors in vendor advisories that do not have a severity field.
- Inline exploit source when a manifest and generator are enough.
- Abandoned hypotheses and failed attempts that do not change whether the proof runs or how a
  reader would score it. A constraint that changes the surviving stage is not a failed attempt;
  keep it in Dead ends and constraints.
- Generic hardening advice.
- Screenshots where text is greppable.
- Affected ranges beyond what was actually run.

Understating exposure is what makes the rest credible.

## Three document types

| Type | Length | Audience | Contains |
|---|---|---|---|
| Vendor advisory REPORT | 175–245 lines | maintainer | summary, impact, root cause, package, repro, expected behavior, tested versions |
| Narrative README/report | 160–565 lines | researcher and maintainer | provenance, full root cause, impact argument, PoC, evidence chain |
| Chain report | 245 + 25×N lines, tables excluded | maintainer | chain overview, per-link anchors and edges, stage cards, per-stage evidence and `n/N`, dead ends, build-keyed offsets, fix reachability |
| Drop README | 30–40 lines | operator | target pin, run command, cleanup |

Choose the type before writing. A bounty submission is the vendor-advisory type plus the
platform's severity field. A drop README is not a substitute for a report. A chain report grows
with the number of capability transitions, not with the number of bugs mentioned.

## Mapping to the harness

- Put Impact second in the report body, before the full mechanism.
- Put the package manifest before the commands.
- Put `## Tested` at the end of the body, as a parseable block.
- Add `## Expected security behavior` as a section distinct from `## Suggested fix`.
- Add `## Will not work if` and `## Environment deltas`.
- Separate `impact.primitive` from `impact.demonstration`.
- Keep evidence slots with `shown | absent | contradicted`.
- Require a cleanup radius and an undo command for host or persistent effects.
- Translate harness vocabulary before it reaches the page.
