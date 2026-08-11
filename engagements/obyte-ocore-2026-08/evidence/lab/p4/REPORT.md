# P4 — SQL unary-plus predicate: `+competitor_units.sequence='good'`

**Claim under test (from round-0 f2-T-f2-01):** on Oracle MySQL, unary plus coerces the TEXT column
`sequence` to a number (`+'good'` → 0) and `0='good'` coerces the string to a number (TRUE), so the
predicate matches ALL rows on MySQL — widening the competitor set in `findStableConflictingUnits`
(main_chain.js:1391-1416), changing `final-bad`/`good` resolution (`handleNonserialUnits`,
main_chain.js:1310), changing `getBallHash(unit, …, sequence==='final-bad')`
(main_chain.js:1511) → **DB-backend-dependent consensus divergence**.

## Empirical verdict: REFUTED

The predicate was executed **exactly as written** on four engines. It matches only `'good'`
everywhere:

| engine (version) | `+sequence` on TEXT | `(+sequence='good')` result |
|---|---|---|
| sqlite 3.51.0 | no-op (string) | matches only `'good'` ✓ |
| MariaDB 11.x (brew) | string unchanged | matches only `'good'` ✓ |
| Oracle MySQL 8.0.46 (docker `mysql:8.0`) | string unchanged | matches only `'good'` ✓ |
| Percona/MySQL 5.7.44 (docker `percona/percona-server:5.7`) | string unchanged | matches only `'good'` ✓ |

### Why the claim's premise fails

MySQL's unary plus coerces a string to a number **only when the string is a pure integer**:

```sql
SELECT +'123' AS a, +'123abc' AS b, +'good' AS c, +'1e3' AS d;
-- a=123 (numeric), b=123abc (string), c=good (string), d=1e3 (string)
```

`sequence` values are always `'good'` / `'temp-bad'` / `'final-bad'` — code constants
(main_chain.js:1270 `UPDATE units SET sequence=?`, values from validation.js), never numeric strings,
never attacker-controlled. So `+sequence` is always the string unchanged, and
`+sequence='good'` is a **string-vs-string comparison** → correct on every engine.

The coercion the hunter relied on (`0='good'` → TRUE) is real — but it only fires when the LEFT
operand is a genuine number, which unary plus does not produce here.

## Same-pattern sites (all share the safe behavior)

- `main_chain.js:1401,1415` — `+competitor_units.sequence='good'` (the audited site; faithful JOIN
  reproduction tested on MySQL 8.0.46 → only the `'good'` competitor returned).
- `headers_commission.js:27,40,43,58` — `+alt_child_units.sequence='good'`,
  `+chunits.sequence='good'`, `+punits.sequence='good'` (mysql branch of `calcHeadersCommissions`).
  Same string-vs-string semantics; safe on all tested engines.
- `archiving.js:111-112,143-144` — `+…main_chain_index` on NUMERIC columns → unary plus is a true
  no-op → safe by construction.

## Severity determination

**Not a consensus divergence. Not a finding.** The production-DB-mix question is moot: the predicate
is correct on every engine the codebase supports (`conf.storage` = `sqlite` default,
conf.js:68; `mysql` explicitly supported with `USE INDEX`/`FORCE INDEX` hints and
`initial-db/byteball-mysql.sql`).

### Residual (hardening note, not reportable)

The `+` prefix on a string column is a latent stylistic hazard: it relies on unary-plus-no-op
semantics for non-numeric strings, which is undocumented, engine-specific, and could change in a
future MySQL release (or bite if `sequence` ever carried a numeric value). Recommend removing the
`+` (5 sites) as a hygiene change. Impact if it ever diverged: DB-backend-dependent `final-bad`
resolution → divergent ball hashes → consensus split — which is exactly why the hygiene matters.
Do NOT file under the bounty (no demonstrated bug).

## Method / reproducibility

- `test-unary-plus.sh` — runnable test across sqlite, MariaDB, MySQL 8.0 (docker `p4mysql`),
  MySQL 5.7 (docker `p4mysql57`).
- Docker containers used for the two MySQL tests (created for this verification; stopped/removed
  after — see cleanup below).
- Faithful multi-JOIN reproduction of the main_chain.js query shape verified on MySQL 8.0.46
  (returns only the `'good'` competitor; EXPLAIN shows a normal PK-join plan).

## Claim-tuple correction (for rounds.md)

- f2-T-f2-01: **demoted from Tier-A2 to refuted** — premise (`+'good'`→0 on MySQL) empirically false
  on MySQL 5.7 + 8.0. The f2 report rated it "STRONG" on the strength of documented-coercion
  assumption without execution; the refuter pass (P4) executed it. Lesson for the record: SQL-engine
  semantic claims must be executed, not assumed from documentation.
- No other candidate depends on P4.

## Cleanup

- Docker: `docker rm -f p4mysql p4mysql57` (performed after tests; containers were ephemeral,
  password-empty, loopback-only, no host volumes).
- No files modified in the ocore clone; only `evidence/lab/p4/` added in the harness repo.
