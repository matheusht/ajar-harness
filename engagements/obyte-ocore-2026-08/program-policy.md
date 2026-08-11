# program-policy.md — Obyte Foundation, Immunefi

Transcribed 2026-08-11 from the program page supplied by the operator. This is the binding ruleset.
**Obyte adheres to Primacy of Rules**: the program runs strictly under the terms on that page, not
under Primacy of Impact. An impact that is real but not listed does not qualify.

## Program

Obyte is a distributed ledger built on a directed acyclic graph. Access to the ledger is
decentralized and open. The Foundation is securing the network, the core library, the GUI wallet,
and some Autonomous Agents. **Primary areas of concern: loss of user funds, DoS (not DDoS), and
total network shutdown.**

## Rewards — paid in GBYTE, BTC, or USDT on BSC, denominated in USD

### Blockchain / DLT

| Level | Amount |
|---|---|
| Critical | max $50,000 / min $2,500 |
| High | flat $1,700 |
| Medium | flat $1,000 |

Critical is 10% of funds directly affected, capped at $50,000, with a $2,500 floor. The ratio used
is funds at risk — including all affected projects on top of the ledger — against market cap, taken
as the average of CoinMarketCap and CoinGecko at the time of submission.

**The $50,000 tier has exactly two qualifying conditions.** The bug must be able to cause
**unrecoverable total network shutdown of the entire Obyte network**, or allow **unpermitted
execution of transactions from accounts of other users without their private keys**. *"All other
critical bug reports are capped at a flat rate of USD 2 500."*

### Smart Contract (Autonomous Agent assets only — deferred scope)

Critical flat $2,500 (10% of funds directly affected, max $2,500), High flat $1,700, Medium flat
$1,000.

### Websites and Applications

Critical flat $2,500, High flat $1,700, Medium flat $1,000.

### Repeatable-attack limitation

High is flat, so a repeated attack pays the same as a one-time attack. There is no uplift for
repeatability at High.

## Impacts in scope

*All Smart Contract impacts relate only to Autonomous Agent assets.*

| Level | Impact |
|---|---|
| Critical | Direct theft of any user funds, at-rest or in-motion, other than unclaimed yield |
| Critical | Permanent freezing of funds |
| Critical | Protocol insolvency |
| High | Temporary freezing of funds for at least 1 year |
| Medium | Smart contract unable to operate due to lack of token funds |
| Medium | Temporary freezing of funds |

## Out of scope

**Program-specific:**

- For anything involving funds lost or frozen, **minimum impact USD 1,000**. Below is out of scope.
- **Blockchain/DLT: temporary disruptions of network availability — node crashes, DoS — are OUT OF
  SCOPE when a fix resolves them without network coordination. Disruptions that REQUIRE network
  coordination to resolve are IN SCOPE**, assessed as temporary freezing of network transactions.
- Web/app "stealing user cookies" and "bypassing authentication" only count at ≥ USD 1,000 loss.
  Web/app "ability to execute system commands" only counts if the actions run as root.
- Direct financial damage where the total is **≤ 200% of the attacker's total expense**.

**Smart-contract specific:**

- Incorrect data from third-party oracles. *This does not exclude oracle manipulation or flash-loan
  attacks.*
- Basic economic and governance attacks, e.g. 51%.
- Lack of liquidity. Sybil attacks. Centralization risk.

**All categories:**

- Attacks the reporter already exploited themselves, causing damage.
- Attacks requiring leaked keys or credentials.
- Attacks requiring privileged addresses, without additional modification to those privileges.
- Depegging of an external stablecoin the attacker did not cause through a code bug.
- Secrets or keys in GitHub without proof of production use.
- Best-practice recommendations. Feature requests.
- Test files and configuration files.
- Phishing or social engineering against employees or customers.

## Prohibited activities

- **Any testing on mainnet or public testnet deployed code. All testing must run on local forks of
  either public testnet or mainnet.**
- Any testing with pricing oracles or third-party smart contracts.
- Phishing or social engineering against employees or customers.
- Any testing with third-party systems, applications, browser extensions, or websites.
- Any denial-of-service attack executed against project assets.
- Automated testing that generates significant traffic.
- Public disclosure of an unpatched vulnerability in an embargoed bounty.
- Anything else the Immunefi Rules prohibit.

## Feasibility limitations

Immunefi applies standards for what either side may cite. The named ones are: chain rollbacks,
pre-impact bug monitoring, attack investment amount, attacks carrying financial risk to the
attacker, and the rule for when an impactful attack is downgraded to griefing. Consult these before
arguing a severity up or down.

## Process

- **Proof of concept is always required, for every severity.** Web and app reports without a PoC are
  rejected outright.
- **KYC is not required** for payout.
- **Responsible publication: Category 3 — approval required.**
- Payouts come from the Obyte Foundation directly.

## Eligibility

Ineligible: compensated Obyte Foundation team members, and employees or team members of third-party
suppliers to a Foundation affiliate who work in a technical capacity and have assets covered by this
program.

## Reference

Autonomous Agents developer documentation:
`https://developer.obyte.org/autonomous-agents/getting-started-guide`
