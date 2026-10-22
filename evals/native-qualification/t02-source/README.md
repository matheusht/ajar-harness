# T02 live-path preparation source

`SOURCE-MANIFEST.json` pins this post-transfer source state for explicit
`check_v2_cloud_owned_source.py --current-manifest` checks. The immutable
20 October transfer ZIP and manifest remain the default historical authority;
this file does not replace them.

This source combines the owned stop owner and managed runner, same-image PHP
8.4.27 offline rehearsal, and an opt-in sealed-capture bridge to the fixed
reviewer packet. It also carries a dormant OpenCode 2.0.32 exclusive-CA patch
and dual-chain checker. The managed runner does not invoke that checker, and
the patch has not been qualified in a built image. The unconditional
`cloud_live_route_not_qualified` denial remains before output creation and
Docker.

Fresh owned rehearsals from this branch use
`smoke/check_v2_managed_owned_integrated.py` with the exact source commit.
The older same-image controller and its receipt remain pinned to their original
source commit; that receipt must be replayed from that source state.

The source manifest and offline receipts are preparation evidence only. They
do not prove protected original observation, fresh native review, live TLS or
provider behavior, all-route containment, or the first-test interruption and
resume required for T04. They do not complete #158 or #161, unblock #159,
#160, or #162, or change the #165 no-go decision.
