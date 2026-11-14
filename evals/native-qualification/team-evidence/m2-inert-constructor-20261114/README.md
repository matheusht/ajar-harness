# Inert boundary constructor — 14 November 2026

Fallible environment selection and runtime profile setup now run from `start`, after the runner owns a boundary object. The existing explicit unused-preparation cancellation can then preserve setup failure codes and release a reservation when nothing was admitted.

Failure-first evidence: four signed public CLI invalid-setup cases failed before the change; the constructor check also failed. The original combined CLI red run included an incorrectly classified generic factory fixture; `unknown-control-before.json` records its corrected engineering-simulation control. Unknown factories remain held.

Repeat from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_engagement_public_cli_e2e.py --output /tmp/inert-public-cli.json
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_engagement_native_boundary_e2e.py --output /tmp/inert-boundary.json
```

Expected: all 12 public CLI scenarios and 23 boundary scenarios pass. The real CLI setup cases run three generations without environment/native admission or charges, then stop and resume without retry. Boundary peers are engineering simulations; host certificates/network checks are local. No Docker, SSH, provider inference or research acceptance is proved. Source digests in the saved results bind checks to the composed source bytes.
