# Historical reference pack

Search these files for mechanisms, fixes, preconditions and counterarguments.
Read the complete relevant entry, including its conditions and linked sources.
The library keeps the selected file version; following a link retains a separate
source version. This pack contains historical excerpts and synthesis, not complete
copies of every cited primary source. Private engagement casebooks are excluded.

| File | Useful questions |
| --- | --- |
| [GHSA fix diffs](ghsa-fix-diff-corpus.md) | What code shape changed? Which guard, canonicalization or ownership check matters? |
| [Rejected and disputed CVEs](rejected-disputed-cve-corpus.md) | What precondition or trust-boundary assumption undermines the reported impact? What disagreement remains? |
| [Project Zero and ZDI chains](project-zero-zdi-chain-corpus.md) | Which partial effect enabled a later step? Which environmental conditions must coexist? |

## Read these corrections with the historical originals

The originals retain their historical wording and provenance. Their `verified`,
`re-fetched`, `IN`, `CONTESTED`, promotion thresholds and funnel/stage instructions
are descriptions of prior collection work, not current verification or research
requirements. No entry is automatically a recommended technique or evidence for
the current target. Follow primary sources when their exact facts matter.

Several disputed-CVE summaries overstate what their quoted sources establish:

- The PostgreSQL row groups `pg_execute_server_program` with superuser access.
  Evaluate the actual role grants and intended OS-command authority separately;
  membership in that role does not establish every other superuser privilege.
- HttpOnly can prevent direct script access to a cookie. It does not by itself
  rule out other consequences of script execution. The Concrete CMS row's
  cookie argument addresses its stated theft path, not every possible impact.
- A vendor's intended-behavior statement is a counterargument to inspect against
  the actual promised boundary. Administrator access, a nondefault configuration
  or a rejected/disputed identifier alone does not settle every narrower claim.
- The curl retry-delay entry describes one bounded argument about impact. Keep
  its observable arithmetic effect separate from that argument, and reassess
  any later composition under the actual caller's conditions.

These are interpretation corrections, not a fresh external-source audit. Visible
source disagreements remain part of the pack. Unknown compatibility is a research
question. No search match proves a finding, and no search miss excludes a viable
mechanism.
