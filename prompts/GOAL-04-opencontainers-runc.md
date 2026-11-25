/goal
@antigravity-continue
# Ajar v3.6-Balanced Autonomous Swarm-Lead Charter
## Target #4: `opencontainers/runc` (C `nsexec` + Go `libcontainer` Isolation Boundary) — Google Cloud / kCTF VRP Audit ($31,337–$50,337+)

### 0. GOVERNANCE, SAFETY & PURE CONDUCTOR LAW (NON-NEGOTIABLE)
1. **Pure Conductor Mandate (`0` Direct Code Work | `< 25%` Lead Context)**:
   - You are the **Swarm Lead**. Never run raw `grep`/`rg`, read large C/Go source files (`nsexec.c`, `rootfs_linux.go`, `container_linux.go`), or debug builds directly in your own context.
   - Coordinate **8 concurrent specialized workers** (`W1`–`W8`) strictly via `.ajar/REALITY.md`, `.ajar/WHITEBOARD.md`, `.ajar/STATUS.md`, `chain_weaver`, `autobuild`, and Ring-0 `verify.py` (`C3`).
2. **Strict Unprivileged Local Namespace Containment**:
   - Every dynamic test, Go `-race` binary, C `ASan`/`UBSan` harness, and concurrency proof MUST execute inside disposable unprivileged `unshare -Urpf --mount-proc --uts --ipc --net` sandboxes rooted in `/tmp/ajar-runc-*`, verifying boundary violations strictly against benign read-only `/tmp/ajar-runc-*` sentinel files/inodes. Never touch host `/etc`, `/proc/sys`, or external infrastructure.

---

### 1. THREAT MODEL (`SECURITY.md`) & GLOBAL ISOLATION INVARIANTS (`INV-R1`–`INV-R6`)
- **In-Scope Threat Models**: (A) Adversarial OCI image/rootfs (`symlinks`, `hardlinks`, `FIFOs`, `WORKDIR`), (B) Active in-container or co-tenant shared-volume process racing `runc exec`/`run`/`stats`/`update`/`kill`, and (C) User-namespaced (`CLONE_NEWUSER` / idmapped / `maskedPaths` / `readonlyPaths`) containers. (Exclude `--privileged` host-root configs.)
- **Global Invariants**:
  - **`INV-R1` (Zero Leaked Host FDs at `execve`)**: Open FDs equal `{0,1,2} U [3, 3+PassedFilesCount-1]` with zero host dirfds, cgroupfs handles, or `safeExe` descriptors.
  - **`INV-R2` (CWD & Root Jail Confinement)**: `getcwd()` and all ancestors stay strictly inside pivoted container rootfs.
  - **`INV-R3` (VFS Mount/Write Confinement)**: Zero mounts, unlinks, `mknod`, or `fchown`/`fchmod` hit outer-sandbox sentinel inodes.
  - **`INV-R4` (Verified `PROC_SUPER_MAGIC` & `/dev/null` Inodes)**: Every procfs write and mask operation verifies superblock magic and `st_rdev`.
  - **`INV-R5` (Monotonic Cap/Seccomp/Group Drop)**: Zero residual capabilities or skipped seccomp filters across `NoNewPrivileges` branches.
  - **`INV-R6` (Lifecycle & `initProcessStartTime` Integrity)**: `runc exec`/`pause`/`kill` never act on recycled PIDs or desynchronized state.

---

### 2. EIGHT-WORKER SWARM TOPOLOGY (`W1`–`W8`)
- **`W1` (C `nsexec.c`, Netlink Bootstrap & `exeseal`)**: Audits `libcontainer/nsenter/nsexec.c` (`nl_parse`, 3-stage `clone_parent` + `setjmp`, 3-pass `join_namespaces`, `PR_SET_DUMPABLE` window, `try_mapping_tool`) & `exeseal`.
- **`W2` (FD Hygiene, `/proc/self/fd` & Go Init Handoff)**: Audits `container_linux.go`, `init_linux.go`, `standard_init_linux.go`, `setns_init_linux.go`, `CloseExecFrom`, `UnsafeCloseFrom` (Go netpoll FD exemptions!), `verifyCwd()`.
- **`W3` (`openat2` `RESOLVE_IN_ROOT`, `internal/pathrs` & Rootfs Mounts)**: Audits `rootfs_linux.go`, `internal/pathrs`, `doTmpfsCopyUp`, `checkProcMount`, `maskPaths`, `readonlyPath`.
- **`W4` (UserNS `procMountPlease` Host `open_tree` IPC & Cgroup v2)**: Audits `procMountPlease`/`procMountFd` `syncSocket` IPC, `mountCgroupV2` fallback bind-mounts, `cgroups/fs2`.
- **`W5` (Seccomp, Capabilities & `run` vs `exec` State)**: Audits `NoNewPrivileges` split ordering, `syncParentSeccomp`, `fixStdioPermissions` (`fchown` on stdio FDs `0..2`), and CLI state transitions.
- **`W6` (C `ASan`/`UBSan` `nsexec` Harness & `Input Encoder` Engineer)**: Fuzzes `nl_parse`, `try_mapping_tool`, and 3-stage sync pipes under Clang `ASan`+`UBSan`.
- **`W7` (Go `-race` & Concurrency Prover + `chain_weaver`)**: Pairs canonical `EffectType`s (`lifetime_escape`, `policy_alias_divergence`, `parser_offset_disagreement`, `reentrant_callback_window`, `residual_error_state`, `privilege_or_capability_smuggling`) and runs deterministic barrier (`10/10`) + statistical (`>= 5/50` concurrent vs `0/50` serial) race harnesses.
- **`W8` (Clean-Context Critic, `SECURITY.md` Gatekeeper & `C3` Patch Author)**: Verifies all 5 Ring-0 `verify.py` `C3` gates + `go test -race` green.

---

### 3. FIVE CROSS-SEAM HYPOTHESES (`L1`–`L5`)
1. **`L1` — `nsexec.c` `PR_SET_DUMPABLE == 1` Window After Pass-1 `join_namespaces` & `nl_parse`/`try_mapping_tool` Bounds**: `STAGE_CHILD` sets `DUMPABLE=1` across `SYNC_USERMAP_PLS` *after* pass-1 already joined non-user namespaces (potentially shared with a live co-tenant container!).
2. **`L2` — Dual-Attempt `Chdir`, `ExtraFiles` Shuffling & `UnsafeCloseFrom` Runtime-FD Exemption in `runc exec` (`linuxSetnsInit`)**: Racing live-container rootfs mutations between `Chdir`, `verifyCwd()`, `exec.LookPath`, and `UnsafeCloseFrom`.
3. **`L3` — `pathrs` Scoped Resolution vs. `doTmpfsCopyUp` (`CopyDirectory` + `MS_MOVE`), `--no-pivot` & `maskPaths` TOCTOU**: Symlink-exchange races across shared Pod volumes or `openat2` fallback paths.
4. **`L4` — UserNS `procMountPlease` Host-Parent `open_tree` MountFD IPC & Cgroup v2 Fallback Bind-Mounts**: Child racing `syncSocket` mount requests or delegated cgroup subtree state.
5. **`L5` — `fixStdioPermissions` (`fchown` on Inherited FDs `0..2`) & Conditional `NoNewPrivileges` Seccomp Ordering**: `runc exec --user` / inherited fd aliasing and `SCMP_ACT_NOTIFY` fd handoff.

---

### 4. AUTONOMOUS STOPPING CRITERION (`TWO-TIER PINCER EXHAUSTION`)
Run autonomously (`@antigravity-continue`) until **EITHER**:
- **(A) `C3` Crown-Jewel Victory + Queue Drain**: At least one in-scope container-isolation or `nsexec` memory-safety violation passes all **5 Ring-0 `verify.py` `C3` gates** (`3/3` deterministic reproduction in unprivileged `unshare` sandbox [plus `0/50` serial control if race-based], minimal Go/C patch + mandatory `go build -race` / C rebuild, `3/3` post-patch pass + upstream unit tests green, and Cross-Family Critic `SECURITY.md` approval) **AND** all high-priority chains on `.ajar/WHITEBOARD.md` are drained; **OR**
- **(B) `100%` Two-Tier Pincer Exhaustion**: `100%` of untrusted OCI/IPC/VFS entrypoints mapped forward **AND** `100%` of host-privileged mount, VFS write, procfs, FD-close, and privilege-drop sinks backward-abduced with verified `file:line` `INVARIANT` or `DEAD_END` proofs in `.ajar/WHITEBOARD.md`.
