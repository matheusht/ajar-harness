# Derived V2 PHP observer parity — 20 October 2026

The [parity receipt](parity-result.json) (SHA-256
`22a4ddf640d9d769b0bce0ac5648e0df34ebd6c3e021e45eff841dee99df1ddc`)
passed 13/13 checks with zero model/provider calls. The exact local derived
OpenCode V2 image ID is
`sha256:31b7fa2b80f17bbddfeffd0577634257df40490f1b8d4c57f8507b40956cdf15`;
its actual PHP is 8.4.26 with `gd` and `pdo_sqlite`. Both release arms used
the same T01 observer script, Docker resource flags, public JSON-RPC sequence,
synthetic users and pinned source archives, changing only the PHP image.

The [public observer result](evidence/observer-results.public.json) (SHA-256
`5704771eddfebe3e47b9342c33be1b38cc49322ed50d16c3ba611679ff8b48df`)
matched T01's ordinary admin/authorized reads and Bob's private-project 403
in both arms. Bob's created swimlane metadata read succeeded on the vulnerable
release and was denied on the fixed release. Both owned containers and ports
were absent after the run, as were their disposable databases. The original
T01 result remained SHA-256
`9db3bc220484a7a786729847f3c8fa8cc1d364a74b1e4a81d2bb78f80dc924fa`.

The public result changes only four `cleanup.run_dir`/`cleanup.db_path` values
to redact the operator's local home path. The frozen parity receipt records
the private raw result's SHA-256
`ab97dcd490ebce86e024ef2095649243437a1f6914b0dba605a5c4fed7133bc2`;
that raw file remains local and is not included here. The published JSON
preserves the observed behavior and cleanup booleans.

The original [researcher brief](../../RESEARCHER-BRIEF.md) remains byte-for-byte
SHA-256 `8f2b5604870cf86719ae94ac180cb6cbe0c5c12cdd2356bc90f4104bb7179a5a`
and is copied here as [original-RESEARCHER-BRIEF.md](original-RESEARCHER-BRIEF.md).
The separately versioned [PHP 8.4.26 brief](../../T02-RESEARCHER-BRIEF-PHP-8.4.26.md)
is SHA-256 `40044703ca38909e80b1db6f79694ed98e27e5892aedf9e269b4256188ad837e`.
It is prepared for explicit future launch selection after independent review;
this receipt does not alter the accepted T01 seed, authorize #160, or prove a
model-driven Kanboard workflow. Exact source and both brief versions are
archived under `source/`.

From the repository root, with Python 3, Docker Desktop, the exact local
derived image and the two cached source archives under
`/private/tmp/native-qualification-observer-20261019-final`, repeat into a new
private directory:

```sh
python3 evals/native-qualification/smoke/check_v2_php_parity.py --output NEW_OUTPUT_DIRECTORY
```

Expect 13 passing checks, redacted request/server traces, exact semantic
comparison to T01, and container/port/database cleanup. No network download is
needed: the runner verifies and copies the two cached archives before testing.
