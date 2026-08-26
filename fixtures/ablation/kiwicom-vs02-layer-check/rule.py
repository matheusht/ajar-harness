"""Lesson from memory-disposition-r4-kiwicom-vs02-reversal-and-verification.

Verbatim: "A confidently-written refuted verdict can itself be a false negative when the regrade
checks the wrong layer. VS-02 was refuted on generic apimachinery empty-RV validation, but core
Secrets opt out via AllowUnconditionalUpdate()==true and the apiserver populates empty-RV updates
before validation runs ... Read the actual code path a claim traverses, including resource-specific
strategy opt-outs."

As a rule: a refutation that rests on a GENERIC layer does not stand until someone has checked
whether the specific resource opts out of that layer.
"""


def decide(case, lesson_applied):
    """Return the verdict for a refutation. 'stands' or 'reopen'."""
    if not lesson_applied:
        # Baseline: a refutation with a cited code path and a passing test is accepted.
        return "stands" if case.get("cites_code_path") else "reopen"

    # With the lesson: a generic-layer refutation must also rule out a resource-specific opt-out.
    if case.get("refutation_layer") == "generic" and not case.get("checked_resource_opt_out"):
        return "reopen"
    if case.get("verified_against") == "fake-client":
        return "reopen"
    return "stands" if case.get("cites_code_path") else "reopen"
