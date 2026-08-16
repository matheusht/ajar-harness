# M2 run_target amplifier — compiled kill-pair artifacts (E1-R6/KP-M2RT)

- kp-m2rt.mjs / driver.mjs: live-verified serializeOptions pass-through (option VALUES verbatim as
  --key=value; executeNgCommand child argv proof) + path.join relative-..-traversal exfil
  (join(ws, '../outside/secret.ts') resolves above ws; content read).
- CORRECTION-NOTE.md: the two mechanism corrections (relative traversal, not absolute pass-through;
  fileReplacements is NOT a channel — [object Object] mangling).
- ws/ fixture + outside/secret.ts: the traversal fixture.
- The executeNgCommand mock mirrors the source-verified host (host.ts:171-228); not a full ng build E2E.
