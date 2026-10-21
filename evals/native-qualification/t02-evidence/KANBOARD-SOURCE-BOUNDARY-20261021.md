# Historical Kanboard preparation

The [ordinary-runtime receipt](opencode-v2-kanboard-runtime-offline-20261020d/README.md)
and [PHP parity receipt](opencode-v2-php-parity-20261020b/README.md)
record host-driven, no-provider checks against the exact local arm64 image
`sha256:31b7fa2b80f17bbddfeffd0577634257df40490f1b8d4c57f8507b40956cdf15`.
Their frozen source snapshots are retained beside the redacted results. The
published parity observer result is a four-path redacted derivative; its
README identifies both public and private raw hashes. The
archive tarballs and extracted application trees are not copied into this PR;
the receipts name their required local inputs and hashes.

The two public runner scripts and prewritten checks are copied from the local
source without changing their historical image or input pins. The frozen
Dockerfile in each receipt has SHA-256 `f93e4ea1f38b4837af3b763c6e1c1cc3ec80b012c858ba26a568dc792fba3dea`.
The current Dockerfile has SHA-256 `7a1ab9b257fb36a216fc1baafabc757436d0a15ffcb9498b6fbe697da3a9bf4b`,
and the current cloud amd64 image is
`sha256:9ef722322521322a1288a18427ba5bf6ce1479085c97e0ac821982eec4f01769`.
These receipts do not establish application parity on that
image, a model-driven test, original researcher-effect capture, or native
qualification. Rebuild and repeat both observer arms on the intended runtime
before an unhinted application run.
