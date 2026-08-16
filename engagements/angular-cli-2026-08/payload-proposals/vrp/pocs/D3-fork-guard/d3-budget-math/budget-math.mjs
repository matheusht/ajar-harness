#!/usr/bin/env node
/**
 * D3 budget-math artifact — per-event robot-budget cost vs the 5,000 req/hr installation budget.
 * Grounded in the E2-R5/C5C + E1-R2/L3 per-event cost analysis (labels job ~7-13 calls,
 * issue_labels ~7-10 + AI-key, assistant job 0/2, dispatched evaluation ~6-15 + full clone).
 * Pin: angular-cli d827ba9005 / dev-infra 04230133.
 */
const HOUR_BUDGET = 5000; // documented installation budget, requests per hour
const MONTH_BUDGET = HOUR_BUDGET * 24 * 30;

// Per-event API call costs (midpoint + range) from the adjudicated lanes
const EVENTS = {
  'labels: fork-PR synchronize':   { mid: 10, lo: 7,  hi: 13 },
  'labels: fork-PR reopened':      { mid: 10, lo: 7,  hi: 13 },
  'labels: fork-PR ready_for_review': { mid: 10, lo: 7, hi: 13 },
  'issue_labels: issue opened':    { mid: 5,  lo: 4,  hi: 6 },
  'issue_labels: issue reopened':  { mid: 5,  lo: 4,  hi: 6 },
  'assistant: unlabeled fork PR':  { mid: 0,  lo: 0,  hi: 0 },
  'assistant: action:merge-labeled': { mid: 2, lo: 0, hi: 2 },
  'dispatched branch-manager eval': { mid: 10, lo: 6, hi: 15 }, // + full clone cost
};

const SCENARIOS = [
  { name: 'S1: single attacker, PR churn flood (200 forks x 3 pushes each)', counts: { 'labels: fork-PR synchronize': 600 } },
  { name: 'S2: issue reopen loop (1 issue, 60 reopen cycles/hr)', counts: { 'issue_labels: issue reopened': 60 } },
  { name: 'S3: combined churn + issue loop', counts: { 'labels: fork-PR synchronize': 300, 'issue_labels: issue reopened': 30 } },
  { name: 'S4: bot-driven PR churn (Dependabot-style, 120 PRs/hr labeled)', counts: { 'assistant: action:merge-labeled': 120 } },
  { name: 'S5: coordinated attacker network (10 accounts x 100 PR events)', counts: { 'labels: fork-PR synchronize': 1000 } },
  { name: 'S6: sustained month-long baseline (60 PR events/hr + 10 issue events/hr)', counts: { 'labels: fork-PR synchronize': 60, 'issue_labels: issue opened': 10 } },
];

function costOf(counts) {
  let mid = 0, lo = 0, hi = 0;
  for (const [ev, n] of Object.entries(counts)) {
    const e = EVENTS[ev];
    if (!e) continue;
    mid += e.mid * n; lo += e.lo * n; hi += e.hi * n;
  }
  return { mid, lo, hi };
}

const GB_MIN = 50 * 1e9, GB_MAX = 200 * 1e9; // GitHub rate limits: 5000 req/hr core (unauthenticated 60/hr)
const UNAUTH_LIMIT = 60;

console.log('D3 budget-math — per-event robot-budget costs vs the 5,000 req/hr installation budget');
console.log('Grounded: E2-R5/C5C + E1-R2/L3 per-event analysis. Pin d827ba9005 / 04230133.\n');
console.log('Scenario | est. calls/hr (mid [lo..hi]) | % of 5k/hr budget | % of unauthenticated 60/hr | monthly (30d) | verdict');
for (const s of SCENARIOS) {
  const { mid, lo, hi } = costOf(s.counts);
  const pct = (mid / HOUR_BUDGET) * 100;
  const pctU = (mid / UNAUTH_LIMIT) * 100;
  const month = mid * 24 * 30;
  const verdict = mid >= HOUR_BUDGET ? 'EXCEEDS hourly budget' :
                  mid >= HOUR_BUDGET / 2 ? 'material share (>=50%)' :
                  mid >= HOUR_BUDGET / 5 ? 'notable share (>=20%)' : 'low';
  console.log(`${s.name} | ${mid} [${lo}..${hi}] | ${pct.toFixed(1)}% | ${pctU.toFixed(1)}% | ${(month/1e6).toFixed(0)}M | ${verdict}`);
}

console.log('\n=== rate-limit constraint analysis ===');
console.log(`- GitHub core API: 5,000 req/hr per installation token (documented installation budget — the E12 amplifier's bound).`);
console.log(`- Unauthenticated baseline: 60 req/hr (an attacker WITHOUT a token, e.g. probing or driving events that only hit unauthenticated endpoints).`);
console.log(`- The fork-PR event stream requires NO attacker token: the PR events are created via the UI/API with the attacker's OWN low-rate account; the BUDGET consumption happens on the ANGULAR robot installation token (the labels/issue_labels/assistant jobs).`);
console.log(`- Single-issue reopen loop: GitHub does not rate-limit issue reopen cycles per-se; the loop's bound is the job concurrency + the AI-key usage (issue_labels fires the Gemini call per event).`);
console.log(`- Sustained impact: S3 (combined, 3,150 calls/hr) consumes ~63% of the hourly budget; S1 (6,000) and S5 (10,000) EXCEED it 1.2x-2x. Exceeding = the robot token throttles (429) for the window -> labels/status-check/merge-evaluation jobs fail intermittently -> PRs stall without labels/status; hourly recovery, no lockout (E2-R5/C5E NARROWED-SURVIVES; queue-wedge KILLED).`);
console.log(`- DoS-vs-degradation verdict: per E2-R5/C5E the wedge is NARROWED-SURVIVES — budget exhaustion is real but bounded (hourly recovery, no lockout). The queue-wedge claim was KILLED (no merge calls).`);

console.log('\n=== per-event cost table (from the adjudicated lanes) ===');
for (const [ev, e] of Object.entries(EVENTS)) {
  console.log(`- ${ev}: ${e.mid} calls (range ${e.lo}..${e.hi})`);
}
