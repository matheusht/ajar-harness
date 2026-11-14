# Filing checklist — btc-psbt-sighash-override

Policy must-haves → where they are satisfied:
- Textual description + repro steps → `REPORT.md`.
- Attachments → `poc/` (self-contained: `module/` pinned copy, five arms, `stage.sh`,
  `expected.stdout` verbatim, `build-meta.txt` with full SHA-256s). Add 2–3 screenshots of the cells.
- Working video PoC on request → `VIDEO-POC.md` storyboard, ready to record.
- First-reporter + 24-hour window → operator decision before filing.
- Chains pay the highest severity only → this report stands alone.
- AI disclosure → in `REPORT.md`; human validation of the cells is the operator's step.

Review trail (this engagement): `reviews/REVIEW-poc.md` (reproduction; found the P2WPKH arm),
`REVIEW-tech.md` (claim audit; R1–R11, source-verified), `REVIEW-voice.md` +
`REPORT-humanized.md` (voice base), `REVIEW-triage.md` (triager simulation; the three fixes it asked
for are all in: self-contained PoC, verbatim expected output, full hashes).

Known-remaining before filing: record the video; human run-through of the cells; decide whether to
file alone or with the sibling drafts (duplicate risk flagged by the triage review).
