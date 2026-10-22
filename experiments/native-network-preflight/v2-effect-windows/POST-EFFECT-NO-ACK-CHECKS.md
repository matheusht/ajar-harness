# #161 owned effect-before-ack check — failure conditions before code

Decision: use the existing inert receiver's `post-effect` gate to distinguish a
completed effect from a missing client acknowledgement when the launcher and
CONNECT process both die. The existing dual-loss E2E covers a request held before
dispatch and a fresh request after stop; it never exercises this separate window.
The simplest alternative is to treat an absent client ACK as no effect. The
receiver's durable effect row can falsify that assumption without a provider,
model, target, or live route.

## Failure conditions and E2E checks

1. Use only a nonce-labelled internal Docker network, exact pinned local images,
   one inert receiver, and the sealed producer set. A positive receiver request
   must return its ACK and write exactly one row before the fault. If that control
   fails, later missing ACKs are uninterpretable.
2. Open the producer gate for `post-effect`. The receiver must append and sync
   exactly one `post-effect` row while withholding its response. The producer's
   ACK file and the receiver's `response-attempted` marker must both be absent.
   If the effect row is absent, the crash window was not reached.
3. SIGSTOP and SIGKILL both exact host processes. Require a bounded terminal
   stop result, exact producer freeze, and a valid managed run-stop proof bound
   to the sealed manifest. An UNSAFE marker, a runnable exact producer, or a
   false REVOKED fails this arm.
4. Release the receiver's held response only after the freeze. Its own marker
   must show that it attempted the response. The producer must still have no
   ACK file. The receiver ledger must still have exactly the positive and one
   `post-effect` row. A distinct fresh effect attempt from the stopped producer
   must fail and add no row; a duplicate `post-effect` row fails.
5. Preserve the retained research hash, save the source pins, independent ledger,
   run markers, exact Docker states, and check outcomes, then remove only the
   labelled Docker resources and owned host processes. Any cleanup mismatch
   fails even if the effect assertions passed.

Run `python3 experiments/native-network-preflight/v2-effect-windows/double_loss_e2e.py
--effect-before-ack --output /tmp/issue161-post-effect-UNIQUE` from the repository
root, using a new nonexistent output path. Docker, Python 3, and the pinned
OpenCode/PHP images must already be available locally. Success exits zero and
saves `result.json`, `effects.jsonl`, the receiver's `response-attempted`
marker, copied source, and retained research bytes.

This local arm demonstrates the ambiguity of a missing ACK and the existing
exact-set stop boundary. It does not implement or prove a later controller's
reconciliation decision, safe retry, native model action, provider behavior, or
full #161 acceptance. A caller must inspect the target's independent state or
perform an authorized reset before any repeat effect.
