# Owned synthetic T02 reviewer packet receipt

Run from the repository root with Python 3, a local Docker daemon and any locally
available image containing `sh`. The recorded run used
`nq-kanboard-current:arm64-20261021` at the image ID in `result.json`:

```sh
python3 evals/native-qualification/smoke/check_v2_reviewer_packet.py \
  --output /tmp/t02-reviewer-packet-recheck-20261021 \
  --image nq-kanboard-current:arm64-20261021
```

Use a new output directory for each run. Expected: `PASS` and all checks true in
`result.json`. The script builds a harmless baseline/candidate/note and synthetic
native tool event, creates the exact review packet, mounts it into a network-none
container read-only, then tests byte drift, root replacement and secret refusal.
The receipt records hashes and an image ID, not raw home paths or credentials.

This is an offline packet and mount check only. It does not exercise a native
reviewer, protected original observation, provider, target, shared CONNECT
dispatch or full managed T02 run. The exact pinned T02 image
`sha256:31b7fa2b80f17bbddfeffd0577634257df40490f1b8d4c57f8507b40956cdf15`
was unavailable on this host. The unconditional `cloud_live_route_not_qualified`
denial remains in the runner.
