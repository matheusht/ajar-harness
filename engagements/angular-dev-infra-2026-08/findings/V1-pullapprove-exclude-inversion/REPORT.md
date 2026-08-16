# V1 — PullApproveGroupArray.exclude inverts review-gate conditions (missing negation)

- **Engagement:** angular-dev-infra-2026-08 · **Pinned commit:** `04230133d395dfb032d782b8e63b4fcbbd406aa5`
- **Attribution:** `angular/dev-infra` — the bug is in the `ng-dev` pullapprove library (`ng-dev/pullapprove/pullapprove_arrays.ts`), shipped in `@angular/ng-dev` and used by the org's PullApprove evaluation.
- **Origin:** independent confirmation via the deepsec scanner pass (finding slug `other-logic-bug`), verified by the orchestrator against source and both flagship consumer configs.

## One sentence on why it is real

`PullApproveGroupArray.exclude` is a copy-paste of `include`: it filters groups IN when the pattern matches instead of filtering them out, so every `groups.*.exclude(...)` condition in the org's PullApprove configs evaluates inverted, and two flagship repos' review-gate conditions demonstrably fail open.

## Mechanism

`ng-dev/pullapprove/pullapprove_arrays.ts`:

```ts
export class PullApproveGroupArray extends Array<PullApproveGroup> {
  include(pattern: string): PullApproveGroupArray {
    return new PullApproveGroupArray(...this.filter((s) => s.groupName.match(pattern)));
  }

  /** Returns a new array which only includes files that did not match the given pattern. */
  exclude(pattern: string): PullApproveGroupArray {
    return new PullApproveGroupArray(...this.filter((s) => s.groupName.match(pattern)));
    //                                                                        ^ missing !
  }
}
```

The doc comment says "did not match"; the code matches. The negation is absent.

## Reachability (production gates)

- the angular/angular config (evidence-angular-pullapprove.yml attached):
  - `:47-48` anchors `no-groups-above-this-pending` / `no-groups-above-this-rejected` = `len(groups.active.pending.exclude("required-minimum-review")) == 0` — intended "no group pending/rejected other than required-minimum-review"; buggy "required-minimum-review is not pending/rejected" — **other groups' pending/rejected states no longer block**. These anchors gate the `public-api` and `size-tracking` group conditions (`:366-367`, `:401-402`).
  - `:78` override "At least one group must match this PR" = `len(groups.active.exclude("required-minimum-review").exclude("global-*")) == 0 and len(groups.approved.include("global-*")) == 0` — the first clause is now always true (a group cannot match both names), so the **no-matching-group failure enforcement collapses to the global-* clause and effectively never fires**.
- the angular/components config (evidence-components-pullapprove.yml attached):
  - `:10` anchor `no-groups-above-this-active` = `len(groups.active.exclude("components-team")) == 0`, used as the `components-team` group's own condition (`:87`) alongside an all-files glob. Buggy: "components-team is not active" — self-contradictory for its own activation, so **the components-team group can never activate and its review requirements are not enforced by PullApprove**.

## Impact (honest)

- Confirmed: the shared library primitive inverts; both flagship orgs' production PullApprove configs exercise it; the intended "exclude X from this gate condition" semantics are broken in both.
- Demonstrated fail-open directions: (a) angular/angular's "no matching review group" failure override is neutralized (a PR touching paths no group covers is no longer failed for it); (b) angular/components' baseline team activation condition cannot be satisfied.
- Not claimed: a universal "all reviews bypassable" — the exact per-PR effect depends on the group graph and which conditions fire; some conditions may become stricter, others (shown above) fail open. The security-relevant direction is confirmed for the two cases above.
- Cap: PullApprove is one layer of review enforcement; GitHub branch protection and org review policies sit on top. The bug corrupts the layer that expresses per-area review requirements.

## Negative control

- The sibling `PullApproveStringArray.exclude` (files array) has the negation and is correct — the divergence is exactly the missing `!` in the group variant.

## Replay / contamination

- Orchestrator re-read the file at the pin and re-fetched both consumer configs from the live public repos (interface reads) on 2026-08-14. Identical findings.

## Severity / category

- **Medium** (CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N = 3.7). Category: Product Vulnerability / repo-configuration in scope. The integrity impact is on review-gate conditions in flagship Google OSS repos.
- CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N = 3.7 (Low-Medium); severity field `medium` reflects the review-gate integrity class. Operator may re-score after triager review.

## Remediation

1. Fix the missing negation in `ng-dev/pullapprove/pullapprove_arrays.ts` (`exclude` must filter OUT matching groups).
2. Add a unit test asserting `exclude` returns non-matching groups (the deepsec pass noted zero behavioral tests around this helper).
3. After the fix, audit the org's `.pullapprove.yml` files for conditions that silently changed behavior (the angular/angular `:78` override and components `:10` anchor will change meaning when the library is fixed).

## Unresolved caveats

- Exact per-PR gate outcomes require running the org's full group graphs through the fixed evaluator; the two demonstrated fail-open cases are the confirmed minimum.
- Novelty not checked (operator's pre-filing step).
