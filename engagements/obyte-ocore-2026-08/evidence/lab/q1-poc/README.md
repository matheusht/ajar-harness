# Q-1 Max-Impact PoC package — remote zero-cost wallet crash (device-layer)

**Status: QUARANTINE-level** (device/wallet layer — outside the declared DLT surfaces SF-1..SF-10).
The operator decides whether to widen scope; this package is the ready-to-submit maximum-impact PoC
if they do. Finding mechanism verified by E2-16 + ER2-3 + the E3-6 independent loop run.

## The finding

`decryptPackage` (device.js:404-445): when an encrypted device message's `recipient_ephemeral_pubkey`
matches none of {current temp, previous temp, permanent}, the else-branch (device.js:431-432)
schedules an uncaught throw 100 ms later:

```js
else{
    console.log("message encrypted to unknown key");
    setTimeout(function(){
        throw Error("message encrypted to unknown key, device "+my_device_address+", len="+...);
    }, 100);
//  eventBus.emit('nonfatal_error', "message encrypted to unknown key, device "+my_device_address+..., new Error('unknown key'));  // <-- the intended pattern, commented out
    return null;
}
```

The throw is outside the try/catch that wraps `decryptPackage` (device.js:170-173) → uncaught →
`network.js:4377-4379` re-throw → process death.

## The delivery path (remote, zero-cost, unauthenticated-ish)

1. Victim runs their own hub (`bServeAsHub: true` — a real opt-in deployment mode for power
   users/businesses) with a device identity.
2. Attacker (any network peer — no account, no key of the victim's) connects to the victim's hub
   URL (advertised) and sends `["request", {command: "hub/deliver", params: <device message>}]`.
3. The `bToMe` branch of hub/deliver (network.js:3428-3436) **skips the recipient-key check** that
   the non-bToMe branch runs (network.js:3424-3426) — the message is delivered to the hub's own
   device layer.
4. `device.js handleJustsaying('hub/message')` → signature check (the attacker signs with their
   own key — any valid signature passes) → `decryptPackage` → else-branch → scheduled throw →
   **process crash ~100 ms later** (after a clean "failed to decrypt" error response).

## Crash-loop persistence (measured)

| cycle | delivery | crash | victim alive after |
|---|---|---|---|
| 1 | accepted | YES (uncaught throw) | 0 |
| 2 | accepted | YES | 0 |
| 3 | accepted | YES | 0 |

(E2-16 measured 3/3 independently; E3-6's `q1-loop.js` re-measures 3/3 on a fresh run — see
`q1-loop.log`.)

Each delivery re-crashes a restarted victim — a permanent crash-loop at zero attacker cost per
cycle. The victim's wallet (fund-holding) is unavailable until restart; a business hub with a
wallet attached is unavailable for its whole user base until restart.

## Blast radius

- **Primary victims:** nodes running `bServeAsHub: true` with a device identity (own-hub
  deployments — power users, businesses, potentially exchanges running a hub+wallet in one
  process). The device layer runs in the same process as the fund-holding wallet.
- **Public-hub flow:** closed — the recipient-key check (network.js:3424-3426) rejects messages to
  unknown device addresses on the non-bToMe path. Victims must be their own hub.
- **Stale-key edge cases:** a wallet restoring from an old backup (temp keys rotated) can hit the
  else-branch from a legitimate hub's normal flow — the crash fires on legitimately-delivered
  messages in that edge; the attacker version only needs the self-hub.
- **Historical precedent:** Obyte's 2018 wallet chat XSS→RCE was wallet-layer and treated as
  critical by the vendor — remote wallet crashes are in-scope for the vendor even if not for this
  bounty program.
- **Marginal contribution:** without the bug, the else-branch emits the nonfatal_error event and
  returns null — the victim responds "failed to decrypt" and continues. The delta is process death
  on attacker input.

## Reproduction (one command)

```
cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore   # not needed; scripts use abs paths
node /Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/q1-loop.js 3
```

Cycle-by-cycle (manual):
```
node evidence/lab/e2-16-victim.js &          # prints the device address; listens on 6611
VICTIM_ADDR=<addr> node evidence/lab/e2-16-attacker.js   # one ws message -> crash 100ms later
```

Negative control: `VICTIM_PERM=<victim permanent pubkey>` → the permanent branch decrypts (no
crash). (The attacker does not know the victim's permanent key in the attack — the negative
control is the delivery-path fix check.)

## Fix direction

Restore the commented-out `eventBus.emit('nonfatal_error', ...)` (device.js:433) and remove the
`setTimeout throw`; add the recipient-key check to the bToMe branch of hub/deliver
(network.js:3428-3436).

## Cleanup

- Scratch data dirs `.q1-loop-data-*` / `.e2-16-victim-data` (synthetic keys only) — destroyed at
  cleanup; see the engagement cleanup ledger.
- No modifications to the pinned ocore tree (lab symlink removed).
