# rounds.md — angular-cli-2026-08

Route statuses: `unexplored` · `active` · `candidate` · `held` · `blocked` · `exhausted`

**`blocked` records the specific missing mechanism**, never a mood. Reopen only on a materially new
construction. A `held` vector is a wrong turn to revisit, not a dry verdict.

No family gets more than half a round before rotation.

## Family registry

| Family | Status | Rounds | Missing mechanism (if blocked) |
|---|---|---|---|
| release + publish path | unexplored | — | |
| CI workflows (7) | unexplored | — | |
| lockfile + build-graph integrity | unexplored | — | |
| ng add / ng update fetch-execute | unexplored | — | |
| schematic engine + task execution | unexplored | — | |
| devkit/core path + virtual-fs | unexplored | — | |
| workspace + JSON schema parsing | unexplored | — | |
| architect builder resolution | unexplored | — | |
| @angular/ssr request handling | unexplored | — | |
| ngtools/webpack loader paths | unexplored | — | |

## Primitive registry

| Primitive | Confirmed by | Composes with |
|---|---|---|
| | | |

## Round log

| # | Date | Scope | Lanes | Result | Next |
|---|---|---|---|---|---|
| 0 | | blind, one family per hunter | | | |
