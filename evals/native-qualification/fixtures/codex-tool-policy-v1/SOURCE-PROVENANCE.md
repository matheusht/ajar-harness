# Immutable Docker source provenance

This candidate derives from the pinned Docker Engine/Moby 28.0.4 release.

- Upstream: `https://github.com/moby/moby`
- Release tag: `v28.0.4` resolves to annotated tag object `3bfe60f8c91fca3ea00d87273756372fae7e1f5d`; peeled source commit is `6430e49a55babd9b8f4d08e70ecb2b68900770fe`.
- Immutable source archive: `https://github.com/moby/moby/archive/6430e49a55babd9b8f4d08e70ecb2b68900770fe.tar.gz`
- Downloaded archive SHA-256: `acce901a0e586cde0bcd4b2a226d716a036dde700fdf2f7e9c2912d9da4fc935`.
- License: repository `LICENSE`, Apache-2.0; SHA-256 `7c87873291f289713ac5df48b1f2010eb6963752bbd6b530416ab99fc37914a8`.

Files that define the actual Docker container defaults:

| Source | Immutable URL | SHA-256 | Use |
|---|---|---|---|
| `profiles/seccomp/default.json` | `https://github.com/moby/moby/blob/6430e49a55babd9b8f4d08e70ecb2b68900770fe/profiles/seccomp/default.json` | `9c1025c88ccaa517b648da571961838744ea2137f176bfe6a48b21294cae9c76` | Static form of the default Docker seccomp policy. |
| `profiles/seccomp/default_linux.go` | `https://github.com/moby/moby/blob/6430e49a55babd9b8f4d08e70ecb2b68900770fe/profiles/seccomp/default_linux.go` | `4529ff8a038f4365ba865d30be2468f6c64b80c832567d978e91906999cc632b` | Source logic for capability-conditioned and argument-filtered syscalls. |
| `profiles/apparmor/template.go` | `https://github.com/moby/moby/blob/6430e49a55babd9b8f4d08e70ecb2b68900770fe/profiles/apparmor/template.go` | `767fda737f039af996827ae29c3654650bad0868f92091ce45b82b102e041801` | Runtime-generated default *container* AppArmor profile template. |

`contrib/apparmor/template.go` is also in this release, but it is the AppArmor profile for the Docker daemon (`/usr/bin/docker`), not the container's `docker-default`; it is not the derivation base here.

Relevant source facts, from this commit:

- `profiles/apparmor/template.go` grants generic `network, capability, file, umount`, then has `deny mount,`. It confirms why the current profile blocks Bubblewrap's mount namespace setup.
- `profiles/seccomp/default_linux.go` with CAP_SYS_ADMIN absent allows `clone` only when the namespace flag mask equals zero; architecture-specific `s390` ordering is handled separately. The default profile returns `ENOSYS` for `clone3` when CAP_SYS_ADMIN is absent.
- The capability-gated group includes `mount`, `mount_setattr`, `move_mount`, `open_tree`, `setns`, `umount`, `umount2`, and `unshare` under CAP_SYS_ADMIN. This branch's top-level container drops every capability, so these calls remain blocked until a candidate makes a narrow syscall allowance; kernel capability checks must still decide whether the operation is allowed in the caller's current user namespace.
- The exact source does not establish the required bwrap syscall or mount argument set. No candidate allowance should be treated as qualified until directly observed and replayed.

The immutable archive URL above supplies the derivation source. The candidate profiles and license are retained beside this document. Loading this named profile is limited to the disposable-host replay; it does not replace Docker defaults or change production environment settings.

The actual tested bwrap binary is supported by two files at the immutable Codex source commit used by the diagnostic:

- Codex commit 6ff1e1ca3b30fc8b914720681fcf5fe62e95f856; builder: codex-rs/linux-sandbox/src/bwrap.rs, SHA-256 82a48f532e11da94f608ca8785bac1fdd989a3276fe9fe255b9d0c0d3d60dd8d.
- Vendored Bubblewrap: codex-rs/vendor/bubblewrap/bubblewrap.c, SHA-256 9bc38fb46080b6854e0c414ccb5fbd369d9d7c0230fdfa877283d31aef0c5720.
- Immutable URLs: https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/linux-sandbox/src/bwrap.rs and https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/vendor/bubblewrap/bubblewrap.c.
- The exact harmless diagnostic argv is retained in evals/native-qualification/smoke/check_codex_sandbox_policy_diagnostic.py in the immutable implementation snapshot: --ro-bind / / --dev /dev --unshare-user --unshare-pid --unshare-ipc --unshare-net --proc /proc --cap-drop ALL -- /bin/true. Its bwrap SHA-256 is 77360cb751ccedc5971391444ac86a8a33c15b04d6b4a6fe45f5d25496e62c4c.

For this exact path, bubblewrap.c forms one clone() flags value containing NEWNS, NEWUSER, NEWPID, NEWIPC, and NEWNET. The source's opt_needs_devpts branch (triggered by --dev) can call unshare(CLONE_NEWUSER) after the initial clone. The ordinary setup then calls mount() for propagation, tmpfs, binds and proc/dev mounts; pivot_root(); and umount2() for old-root cleanup. The normal diagnostic invocation does not pass pid namespace or user namespace file descriptors, so its source path does not require setns(); it does not call chroot().
