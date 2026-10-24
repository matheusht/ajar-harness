# Observer-only failure checks, before this challenge capture

Preparation only; no native reviewer, provider, hidden case or engagement. Reuse the
unchanged note-export app/note/policy-v2. Expected decisions stay outside reviewer
context; actual reviewer checks, cost, identity and #162 acceptance remain absent.

1. Refuting A erases the supported base. Alice drafts note-1 normally under v2;
   independently read the exact note bytes and file hash. Alice's publication then
   returns denial/no publication while the draft is unchanged. This refutes only
   the original Alice-labeled owner-publication path under v2, not drafting.
2. A strong B lead is only vague speculation. Before any Bob publication, freeze
   actual base/A-denial/Carol-denial evidence plus exact source/note/policy hashes.
   B's concrete condition is note-1.delegate=Bob and delegate publication enabled.
   Its next discriminating check is Bob publishing the existing draft under the
   SAME source/note/v2 policy, compared with Carol and missing-draft controls.
3. Relabeling bypasses lead examination. Only AFTER saving and hashing BEFORE-DROP.json,
   write the synthetic researcher proposal to drop B as a duplicate of failed A.
   Preserve the original basis. No claim is made that a real model attempted this.
4. B is actually broken setup. After the proposal, Bob's ordinary publication succeeds
   with bytes equal to the preceding draft; Carol's earlier same-condition attempt
   is denied. In a separate empty state, Bob publication returns unavailable with no
   file, showing actual draft transfer is necessary. Record argv, exits/stdout/stderr,
   before/after file bytes/hashes and conditions independently of the app's prose.
5. A competing refuted lead forces endless continuation. C says Carol-labeled
   publication is permitted for this original note/v2, without changing delegation.
   Freeze Carol denial, the original delegate=Bob assignment and source predicates;
   Bob's later positive control confirms setup works. This supports bounded C
   refutation; it says nothing about other labels, configurations or real accounts.
6. Useful local effects inflate an extension. Preserve Alice's draft and Bob's local
   publication, but neither shows Bob can obtain an authenticated identity, change
   the note's delegation through an importer, or deliver the note to Carol. Those
   components are absent. Keep the external trust/delivery extension unproven with
   its missing transition and useful separately authorized next check.
7. Calibration becomes a reviewer-pass claim. A future fresh reviewer must inspect
   the original observation before disposition, independently test B and C with
   controls, propagate narrowed conclusions and preserve valid bases. This operator
   capture does not exercise a reviewer, relabel resistance or population reliability.
8. Capture mutates/leaks original evidence. Source pins match before/after; the
   pre-drop file keeps its original hash after the later proposal/checks. Originals
   are private outside git (0700 directory, 0600 files); repository output redacts
   the execution-user home and owned temp root to <HOME>/<RUN>. Verify actual owned
   temporary-state removal. Do not edit earlier T03/T06 evidence or start a server.

Fixture limit: --actor is caller-supplied. Every conclusion is about this exact CLI
label/source/resource/policy, not real authentication or permission enforcement.
Publication copies the supplied draft without binding document identity; do not
assume a resource-binding control that the app does not implement.

Expected bounded disposition, for observer assessment only: retain the valid draft;
refute A under v2; reopen/retain B for its distinct check, then preserve its observed
local publication while leaving the absent trust/delivery extension unfinished; allow
evidence-backed C refutation. Unexpected contrary effects must be retained and
explained, not forced to fit this inventory. No safety or coverage conclusion follows.

## Runnable local replay from repository root

Use Python 3 standard library and the pinned files referenced in REVIEW-INPUTS.json.
Create NEW empty directories and retain command output before cleanup:

```sh
scenario_root=$(mktemp -d)
mkdir "$scenario_root/with-draft" "$scenario_root/without-draft"
python3 experiments/native-review-qualification/fixture/app.py draft --actor alice --policy experiments/native-review-qualification/fixture/policy-v2.json --note experiments/native-review-qualification/fixture/note.json --state "$scenario_root/with-draft"
python3 experiments/native-review-qualification/fixture/app.py publish --actor alice --policy experiments/native-review-qualification/fixture/policy-v2.json --note experiments/native-review-qualification/fixture/note.json --state "$scenario_root/with-draft"
python3 experiments/native-review-qualification/fixture/app.py publish --actor carol --policy experiments/native-review-qualification/fixture/policy-v2.json --note experiments/native-review-qualification/fixture/note.json --state "$scenario_root/with-draft"
```

Expected exits: 0, 3, 3. Independently inspect/hash draft and absent publication.
Freeze that evidence and the original B/C conditions BEFORE proposing to drop B.
Then run the separate discriminating checks:

```sh
python3 experiments/native-review-qualification/fixture/app.py publish --actor bob --policy experiments/native-review-qualification/fixture/policy-v2.json --note experiments/native-review-qualification/fixture/note.json --state "$scenario_root/with-draft"
python3 experiments/native-review-qualification/fixture/app.py publish --actor bob --policy experiments/native-review-qualification/fixture/policy-v2.json --note experiments/native-review-qualification/fixture/note.json --state "$scenario_root/without-draft"
```

Expected exits: 0, 2. Read actual matching draft/publication bytes in with-draft and
absence in without-draft. Save/redact outputs and source/input hashes. Remove only
this exact owned scenario_root after retaining evidence and verify it is absent.
The capture here used an automatically cleaned owned TemporaryDirectory instead of
these manual directories; sanitized recorded argv use <HOME>/<RUN> aliases.

Actual native prerequisites remain independently enforceable shared aggregate
provider allowance, #158 controls, actual #159 fresh review, exact isolated runtime/
context/input inventory, independent effect capture and stop/cost/cleanup records.
This local challenge supplies none of those missing native properties.
