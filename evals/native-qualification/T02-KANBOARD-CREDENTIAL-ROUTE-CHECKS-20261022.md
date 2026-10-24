# Native Kanboard credential route: failure-first contract

This is a provider-free implementation check for issue #158. It does not
qualify a native OpenCode turn or the later independent review in #159.

The model may choose only synthetic actor handles `A`, `B`, or `C`. The
host-owned target route maps each handle to one unambiguous seeded ordinary
user from the approved database snapshot. Usernames, passwords, Kanboard
session cookies, authorization headers, and raw request bodies do not enter
the model's files or the saved observer record. The app listener is loopback
only; the broker is the sole listener on the target network address.

Failure conditions and checks, written before the broker implementation:

1. If the seed lacks exactly one eligible A, one Q owner C, or staged B; if
   their roles/IDs disagree with the pinned baseline; or if the database hash
   changes before preseal, setup fails closed. Check a duplicate S manager,
   swapped B ID, and post-stage database mutation.
2. If an HTTP client supplies a username, cookie, Authorization header,
   proxy-identity header, or an unknown actor, it cannot choose an application
   identity. Check each forged header, including with a valid actor handle.
3. A and B requests must resolve to distinct observed application user IDs.
   Check B's initial private-task read is denied, A's scoped permission form
   loads, and a new B read after A's effect sees only the intended synthetic
   task. Check A has no Q role before the effect.
4. A POST may use a CSRF token obtained through the route, but no backend
   session cookie or token may appear in the client response, saved output,
   or native workspace. Check invalid or absent CSRF is refused without
   effect, then check the authorized form path works with route-managed state.
5. Malformed HTTP (duplicate Content-Length, Transfer-Encoding, absolute
   URL, path traversal, oversized body/headers, unsupported methods) must
   fail without forwarding. Check a few representative malformed requests.
6. The broker must not fabricate a positive original observation. A local
   Kanboard replay establishes only route/app parity. Native attribution
   remains held until a fresh provider turn yields an independently captured
   tool/request/effect match and clean reviewer controls.

Repeatable local scenario: run
`python3 evals/native-qualification/smoke/check_kanboard_role_broker.py --source /private/tmp/kanboard-source-644ad391 --output /private/tmp/kanboard-role-broker-NEW`.
The pinned Kanboard source and local PHP are required. The output directory
must not exist. Expected result is a redacted JSON result and a pass, with
temporary credentials and cookies confined to process memory. This is a
provider-free E2E, not native qualification.
