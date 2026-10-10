# Hunter result acceptance, issue 120

Run only against the generated, separately signed local fixture. The two source files
are inert. The parent may read them, but the hunter has no ledger write access.

The selected experiment names an exact primary source, an exact control source,
and a short benign signal. One Docker hunter task must submit both observations
through one broker admission. The parent must reread the allowlisted source bytes,
compare the hunter's raw-output commitments, reject secret-shaped bytes, and write
the linked primary and held control in one ledger transaction. The result returns
the hypothesis to adjudication; it does not confirm a vulnerability.

Failure modes to check before implementation:

| Case | Required observation |
| --- | --- |
| Correct source pair and signal | Two broker-owned attempts, exact source/output hashes, control linked to primary, open adjudication item |
| False child output hash or claimed signal | No attempt, claim, or effect record |
| Missing control | No primary-only success or attempt |
| Wrong or out-of-scope source | No attempt or source contact outside the signed local fixture |
| Source bytes changed after projection | No attempt based on stale bytes |
| Expired or changed admission | No attempt |
| Secret-shaped output | No raw value saved and no attempt |
| Replayed action or lost acknowledgement after commit | One pair only; no second source effect |
| Parent process killed after the Docker session commits | A new driver reacquires the workspace, sees open adjudication, and adds no attempt |
| Crash before commit | Running work remains in the queue |

Set `HARNESS_HUNTER_RESULT_LOST_ACK=1` and use a second fresh output directory to inject an exception after the parent command commits but before it returns its acknowledgment. The test requires the same two attempts, a denied retry, and adjudication still in the queue. This models the lost-response boundary; it does not kill and restart the parent process.

From the repository root, run `HARNESS_DOCKER_QUEUE_TEST_IMAGE=<cached immutable image> HARNESS_DOCKER_QUEUE_TEST_PYTHON=<python in image> HARNESS_HUNTER_RESULT_OUTPUT_DIR=<new output directory> <project-python> tools/docker-work-queue-drain-test.py DockerWorkQueueDrainAcceptanceTest.test_real_docker_hunter_parent_records_matched_source_pair`. The test creates the signing keys and scope in a temporary directory, and saves benign source bytes, the paired ledger, a view commitment, and a result summary in the requested new directory. Then run `<project-python> fixtures/hunter-result-120/verify_saved.py --output <that directory>` and retain both command outputs. Use the configured Python environment for this checkout; a separate worktree may not contain `.venv`. The script does not contact a live target. Docker with a fake provider proves the local boundary only; it does not prove real provider or target behavior.

For the process crash, set the same image and Python variables, set `HARNESS_HUNTER_CRASH_OUTPUT_DIR=<new output directory>`, and run `<project-python> tools/docker-work-queue-drain-test.py DockerWorkQueueDrainAcceptanceTest.test_crash_after_pair_commit_restarts_without_duplicate`. Run the same saved verifier on that directory. The child calls `os._exit(77)` after the Docker session returns with the committed pair, before the outer driver can disarm or acknowledge it. The next driver starts against the same signed engagement and stops before another model session; this checks recovery of the workspace lock and ledger state without claiming an autonomous reviewer continuation.
