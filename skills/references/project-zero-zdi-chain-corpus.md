# Project Zero + ZDI disclosed root-cause chain corpus

> Reference corpus for `docs/research/project-zero-zdi-chain-corpus.md` (deep-research pass #5).
> Calibration data, not a matchable target property. Grounds `skills/ajar-chain/SKILL.md` §3b (candidates),
> `skills/ajar-falsify/SKILL.md` §3/§4 (root-cause/severity re-derivation), `skills/ajar-reproduce/SKILL.md` §5 lens 4/6.

## Provenance & method

Built via two background workflows (Sonnet-5 web collectors + Opus reviewers/critic, orchestrator
assembly). Run 1 `wf_89f20aef-90e` (8 collectors → 3 per-axis reviewers → 2 verifiers → 1 critic):
47 collected → 30 IN. Run 2 top-up `wf_d7d0ccf0-fcc` (3 gap collectors → reviewer → verifier): 18 → 15 IN,
filling hypervisor guest→host, wireless-proximity zero-click, and GPU/TEE classes the run-1 critic found missing.

**After merge + dedup + correction: 36 IN + 4 CONTESTED** (from 45 raw triaged rows → 37 unique items; the critic-flagged cross-axis
triple-counts — Pixel-9 Dolby/BigWave ×4, FORCEDENTRY ×2, CVE-2025-38236 ×2, KASLR ×2, Acrobat/ESXi ×2 —
were collapsed to one row each, unioning axis tags). Axis coverage: **A (chains, ≥2 disclosed stages) = 22**, B (root-cause/severity) = 22, C (mechanism-fidelity) = 17.

**Cross-domain diversity (the plan's acceptance criterion, not volume):** gpu-tee 8, virtualization 6, enterprise-server 4, os-kernel 3, mobile-ics 3, itw-chain 3, wireless-proximity 3, browser-renderer 2, kernel-messaging 2, browser-sandbox 2.

**Anti-hallucination gate.** Every cited id was grep-checked against the collector returns; two independent
Sonnet verifier passes re-fetched each cited ZDI advisory / P0 post confirming CVE + CVSS + chain claim; and
the operator hand-re-fetched **6** items across both rounds against the live primary pages (ZDI-26-329, the
MSG_OOB Linux post, ZDI-21-821, the Pixel-9 Dolby post, Ian Beer's AWDL post, Mind-the-Gap) — 0 discrepancies,
0 confabulated CVEs/URLs. Rows are labelled `re-fetched` where an agent confirmed the primary page this run.

**Corrections applied at assembly:**
- ProxyShell (ZDI-21-821/822): the disclosed RCE stage is CVE-2021-31207 (post-auth arbitrary file write / webshell); CVE-2021-34523 is the middle PowerShell EoP. Recorded as the canonical 3-CVE chain 34473(SSRF)->34523(EoP)->31207(RCE).
- Exynos baseband (CVE-2023-24033 set) demoted to CONTESTED: P0 withheld the per-CVE mechanism; both stages self-marked `(inferred)` — a reachability claim, not a disclosed handoff.

---

## Axis A — cross-domain multi-stage chains (22) → `skills/ajar-chain/SKILL.md` §3b candidates

Each is a real disclosed ≥2-stage chain. **These are §3b candidates, not canonical §3 angle-shapes** —
promotion happens only on repeated cross-instance evidence per chainability §0. Stage notation:
`primitive` → *boundary crossed* → **capability gained**.

### [browser-renderer] ZDI-26-329 / ZDI-26-330 / ZDI-26-331
**CVE:** CVE-2026-45492 (ZDI-26-329), CVE-2026-45494 (ZDI-26-330), CVE-2026-45495 (ZDI-26-331)  ·  **Product/version:** Microsoft Edge (patched by Microsoft prior to 2026-06-04 public disclosure)  ·  **CVSS:** ZDI-26-329: CVSS:3.0/AV:N/AC:L/PR:N/UI:R/S:U/C:N/I:L/A:N (4.3); ZDI-26-330: CVSS:3.0/AV:N/AC:H/PR:N/UI:R/S:U/C:H/I:N/A:N (5.0); ZDI-26-331: CVSS:3.0/AV:N/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H (7.5)  ·  **Disclosed:** 2026-06-04 (reported to vendor 2026-05-20; Pwn2Own Berlin 2026, 2026-05-13)  ·  **Axes:** A,B

Chain:
    1. `"insufficient validation of the origin of web content" in Edge's cross-device managed sign-in feature (CVE-2026-45492)` → *origin/trust boundary of the managed-sign-in navigation flow* → **origin validation / security bypass, usable in conjunction with other bugs (per advisory text)**
    2. `"lack of proper validation of user-supplied data" in Edge navigation handling, enabling script injection (CVE-2026-45494)` → *cross-origin script-execution boundary (Universal XSS)* → **execute arbitrary script in the context of another origin**
    3. `"lack of proper validation of a user-supplied path prior to using it in file operations" in feedback-log-file handling, i.e. directory traversal (CVE-2026-45495)` → *filesystem / current-user process boundary* → **remote code execution in the context of the current user**

- **Root cause:** Quoted per-CVE from the three ZDI advisories: CVE-2026-45492 - "insufficient validation of the origin of web content" (cross-device managed sign-in); CVE-2026-45494 - "the lack of proper validation of user-supplied data, which can lead to the injection of arbitrary script" (navigation handling, UXSS); CVE-2026-45495 - "the lack of proper validation of a user-supplied path prior to using it in file operations" (feedback log file handling, directory traversal). All three advisories state the bug "can leverage this in conjunction with other vulnerabilities to execute code in the context of the current user."
- **Reported-vs-real impact:** ZDI's Pwn2Own writeup reports the combined result as a full renderer sandbox escape via 4 chained logic bugs, but the 3 disclosed CVEs individually carry only low-to-moderate CVSS (4.3, 5.0, 7.5) reflecting narrow origin-bypass / UXSS / path-traversal primitives -- none is independently rated as sandbox-escape-class, and the 4th bug has no separately identified advisory/CVE in this dataset.
- **Source:** https://www.zerodayinitiative.com/advisories/ZDI-26-331/

### [browser-sandbox] P0-blog-in-wild-ios-exploit-chain-4-2019
**CVE:** CVE-2019-7286 (sandbox escape); CVE-2019-7287 (kernel privilege escalation)  ·  **Product/version:** iOS cfprefsd (XPC preferences daemon) chained with an IOKit kernel driver external method iOS 12.0 through 12.1 (both 0-days, unpatched at discovery)  ·  **CVSS:** not stated in the P0 post  ·  **Disclosed:** reported to Apple with a 7-day deadline; emergency-patched in iOS 12.1.4, publicly detailed 2019-08-29  ·  **Axes:** A,B

Chain:
    1. `cfprefsd XPC object lifetime bug: "a reference being dropped when none was taken" in object lifetime management in XPC (CVE-2019-7286)` → *sandboxed WebKit-driven app process -> cfprefsd XPC service* → **sandbox escape out of the app/renderer sandbox**
    2. `IOKit device driver external method that "in the very first statement performs an unbounded memmove with a length argument directly controlled by the attacker" (CVE-2019-7287)` → *unsandboxed userland -> XNU kernel via the IOKit external-method call surface* → **kernel privilege escalation to root, enabling implant installation**

- **Root cause:** One of five real-world iPhone exploit chains found by TAG in a watering-hole campaign; this chain's two 0-days were still unpatched when P0 discovered them, forcing Apple's emergency iOS 12.1.4 release. Root cause quotes are anchored above verbatim from the post.
- **Source:** https://projectzero.google/2019/08/in-wild-ios-exploit-chain-4.html

### [browser-sandbox] P0-blog-in-wild-series-windows-exploits-2021
**CVE:** CVE-2020-6418 (renderer entry); CVE-2020-0938, CVE-2020-1020 (font sandbox escape); CVE-2020-1027 (CSRSS EoP)  ·  **Product/version:** Google Chrome (renderer/V8) chained with Windows atmfd.dll (Type 1 font parsing, GDI) and sxssrv.dll (CSRSS) Chrome 60-63/68-72/78-80 (V8); Windows 8.1 and earlier (font path); Windows 10 up to build 18363 (CSRSS path)  ·  **CVSS:** not stated in the P0 posts (pre-CVSS-vector disclosure style)  ·  **Disclosed:** reported to Chrome as 7-day 0-day (~Feb 2020); Windows bugs reported Mar 17 (font) and Mar 23 (CSRSS) 2020, patched Apr 14 2020; full write-up published 2021-01  ·  **Axes:** A,B

Chain:
    1. `V8 TurboFan compiler bug: "the function InferReceiverMapsUnsafe assumes that a JSCreate node can only modify the map of its value output. However, in reality, the node can trigger a property access on the new_target parameter" -> double/tagged-pointer type confusion (CVE-2020-6418)` → *attacker-controlled JS in the sandboxed Chrome renderer process* → **arbitrary memory read/write and native code execution confined to the renderer sandbox**
    2. `atmfd.dll Type 1 font parser stack write-what-where: "the function initializes numMasters pointers on the stack, then reads the same-sized array of fixed point values from the input stream, and writes each of them to the corresponding pointer" with no bounds check (CVE-2020-0938/CVE-2020-1020)` → *sandboxed renderer -> Windows kernel-mode GDI/font driver reachable from the sandbox on Windows 8.1 and earlier* → **arbitrary kernel memory write, i.e. escape of the Chrome sandbox**
    3. `CSRSS sxssrv.dll validation bug: "the buffer size for the validation is calculated based on the Length field rather than MaximumLength", enabling a "memcpy with fully controlled contents and size" (CVE-2020-1027)` → *sandboxed process -> CSRSS, a SYSTEM-privileged Windows subsystem process, via thread creation and a ROP chain* → **privilege escalation from sandboxed renderer to SYSTEM on Windows 10**

- **Root cause:** Multi-stage in-the-wild watering-hole chain documented by P0 as three separate technical posts: a V8 TurboFan alias/type-inference bug in the renderer, then either a decades-old ATM Type-1 font-parsing stack overwrite (surprisingly still reachable on Win8.1 despite Chrome's win32k lockdown) or a CSRSS length-field confusion, used as the sandbox-escape/EoP stage to reach SYSTEM.
- **Reported-vs-real impact:** P0 explicitly flags the font-bug pairing as unexpected/anomalous: it 'oddly' targeted Windows 8/8.1 even though those still support Chrome's win32k lockdown mitigation that should have blocked the font-driver reachability path -- i.e. the attackers used an escape route P0 did not expect to still be viable.
- **Source:** https://projectzero.google/2021/01/in-wild-series-windows-exploits.html

### [enterprise-server] ZDI-21-821 / ZDI-21-822 / ZDI-21-815 (ProxyShell — ZDI-CAN-13611 / ZDI-CAN-13614 / ZDI-CAN-13690)
**CVE:** CVE-2021-34473 (Pre-Auth Path Confusion / ACL Bypass) -> CVE-2021-34523 (Exchange PowerShell Backend EoP) -> CVE-2021-31207 / ZDI-21-815 (Post-Auth Arbitrary File Write RCE)  ·  **Product/version:** Microsoft Exchange Server 2013 / 2016 / 2019  ·  **CVSS:** ZDI-21-821 (CVE-2021-34473): 10.0 / CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H; ZDI-21-822 (CVE-2021-34523): 9.8 / CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H; ZDI-21-815 (CVE-2021-31207): 7.2 / CVSS:3.0/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H  ·  **Disclosed:** 2021-07-19  ·  **Axes:** A,B

Chain:
    1. `Pre-auth path confusion / ACL bypass via ExplicitLogon URI normalization in Frontend proxy (ZDI-21-821, CVE-2021-34473)` → *unauthenticated remote attacker -> internal Exchange `/powershell` backend reached without credentials* → **pre-auth ACL bypass and SSRF access to backend Exchange endpoints**
    2. `Improper X-Rps-CAT access-token validation on Exchange PowerShell backend (ZDI-21-822, CVE-2021-34523, Orange Tsai / Pwn2Own 2021)` → *unprivileged internal-endpoint access -> arbitrary Exchange user token deserialization* → **elevation of privilege to Exchange administrator PowerShell remoting session**
    3. `Post-auth arbitrary file write via New-MailboxExportRequest UNC FilePath export to IIS webroot `.aspx` webshell (ZDI-21-815, CVE-2021-31207)` → *Exchange Mailbox Import Export cmdlet -> filesystem webroot* → **arbitrary post-auth file write and remote code execution as SYSTEM**

- **Root cause:** ZDI-21-821 (`CVE-2021-34473`, CWE-918): lack of proper URI normalization before stripping `/autodiscover/autodiscover.json` lets unauthenticated requests reach internal Exchange backends. ZDI-21-822 (`CVE-2021-34523`, CWE-269/CWE-287): Exchange PowerShell backend deserializes a caller-supplied `X-Rps-CAT` query token without verifying privileges, escalating to an Exchange admin session. ZDI-21-815 (`CVE-2021-31207`, CWE-22/CWE-434): `New-MailboxExportRequest -FilePath` writes attacker-controlled mail contents to an arbitrary UNC `.aspx` path, yielding SYSTEM RCE.
- **Reported-vs-real impact:** All three stages are required for unauthenticated SYSTEM code execution: `CVE-2021-34473` crosses the pre-auth network boundary, `CVE-2021-34523` elevates to Exchange admin PowerShell, and `CVE-2021-31207` converts admin cmdlet access into arbitrary `.aspx` webshell execution (`CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H` combined).
- **Source:** https://www.zerodayinitiative.com/advisories/ZDI-21-821/ ; https://www.zerodayinitiative.com/advisories/ZDI-21-822/ ; https://www.zerodayinitiative.com/advisories/ZDI-21-815/

### [enterprise-server] ZDI-26-412 / ZDI-26-413 (ZDI-CAN-31490 / ZDI-CAN-31491)
**CVE:** CVE-2026-50522  ·  **Product/version:** Microsoft SharePoint not specified in advisory  ·  **CVSS:** 8.1 / AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H  ·  **Disclosed:** 2026-07-15  ·  **Axes:** A,B

Chain:
    1. `improper verification of a cryptographic signature on a session security token (ZDI-26-413)` → *unauthenticated network attacker -> a forged/unverified token accepted as trusted by SharePoint's session-security-token handling* → **attacker-controlled token trusted with no authentication**
    2. `deserialization of untrusted data inside SessionSecurityTokenHandler (ZDI-26-412)` → *trusted-token context -> deserialization of an attacker-supplied payload in the service account's process* → **arbitrary code execution in the context of the service account**

- **Root cause:** ZDI-26-412: "the lack of proper validation of user-supplied data, which can result in deserialization of untrusted data" within the SessionSecurityTokenHandler class. ZDI-26-413: "the issue results from the lack of proper verification of a cryptographic signature" in session security token handling; ZDI-26-413's advisory states this flaw "can be combined with other vulnerabilities to enable arbitrary code execution" under the service account, no authentication required. Both advisories were assigned the SAME CVE (CVE-2026-50522), which is disclosed evidence the two root causes are treated as one combined chain by the vendor.
- **Reported-vs-real impact:** Pwn2Own Berlin-style entry: neither the signature-verification bypass nor the deserialization bug alone is stated to be pre-auth RCE; the advisories' own text ties full unauthenticated code-execution impact to the combination of the two, reflected in the high (AC:H) complexity metric rather than a trivial single-step exploit.
- **Source:** https://www.zerodayinitiative.com/advisories/ZDI-26-412/

### [gpu-tee] p0-mali-mind-the-gap-2022
**CVE:** CVE-2022-36449 (also references CVE-2022-33917, CVE-2021-39793/CVE-2022-22706)  ·  **Product/version:** Arm Mali GPU Kernel Driver (Valhall/Bifrost) Bifrost r0p0-r38p0 & r39p0 before r38p1; Valhall r19p0-r38p0 & r39p0 before r38p1; device Google Pixel 6 (also Samsung, Xiaomi, Oppo)  ·  **CVSS:** 6.5 MEDIUM (CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:N) per NVD  ·  **Disclosed:** 2022-11-22 (post); bugs found Jun-Jul 2022, ARM patched Jul-Aug 2022, derestricted mid-Sep 2022  ·  **Axes:** A

Chain:
    1. `Five distinct Mali GPU kernel driver bugs (P0 issues 2325/2327/2333 = physical page UAF; 2331 = physical address disclosure; 2334 = memory corruption)` → *unprivileged GPU job-submission ioctls reaching kernel physical page management* → **physical page use-after-free / stale mapping under attacker control**
    2. `attacker forces kernel to reuse the freed physical pages` → *kernel re-issues the freed pages as page tables* → **attacker-controlled page table content**
    3. `controlled page tables` → *MMU translation for the calling process* → **"an attacker with native code execution in an app context could gain full access to the system, bypassing Android's permissions model and allowing broad access to user data"**

- **Root cause:** ARM's advisory: "A non-privileged user can get a write access to read-only memory pages." Project Zero: the three UAF-class issues "lead to a physical page use-after-free condition"; forcing the kernel to reuse these pages as page tables yields full attacker control.
- **Reported-vs-real impact:** app-context native code execution escalates to full system access / Android permission-model bypass; discovered vulns were patched by ARM Jul-Aug 2022 but remained un-downstreamed to Pixel 6 and other OEM devices for months
- **Source:** https://projectzero.google/2022/11/mind-the-gap.html

### [gpu-tee] p0-analyzing-modern-itw-android-2023
**CVE:** CVE-2023-0266 (ALSA UAF), CVE-2023-26083 (Mali GPU tlstream info leak); chain also uses CVE-2022-4262 (Chrome 0-day), CVE-2022-3038 (Chrome n-day), CVE-2022-22706 (Mali GPU n-day, unpatched downstream)  ·  **Product/version:** Linux ALSA subsystem (32-bit compat ioctl) + Arm Mali GPU Kernel Driver, on Samsung Android (64-bit kernel w/ 32-bit compat layer) Samsung device (S10 family referenced); Mali driver n-day fixed upstream Jan 2022 but not downstreamed  ·  **CVSS:** not stated in post  ·  **Disclosed:** post 2023-09; CVE-2023-26083 reported to Arm 2023-01-17  ·  **Axes:** A

Chain:
    1. `Chrome renderer 0-day (CVE-2022-4262) + Chrome sandbox n-day (CVE-2022-3038)` → *browser sandbox* → **code execution as system_server / app-context, entry point to kernel-facing exploitation**
    2. `Mali GPU tlstream performance tracer exposes kernel pointers as object IDs to unprivileged code (CVE-2023-26083): "available to unprivileged code, traces all GPU operations across the whole system ... and uses kernel pointers as object identifiers"` → *GPU driver ioctl/tracing interface* → **kernel heap-address (KASLR) disclosure**
    3. `ALSA 32-bit compat ioctl missing-lock race (CVE-2023-0266) reintroduced by a 2017 64-bit-only refactor: "this commit only addressed the 64-bit ioctl code, introducing a race condition into the 32-bit compatibility layer"` → *kernel snd_kcontrol object lifetime* → **use-after-free -> forged snd_kcontrol object; combined with Mali-driven heap spray and the leaked kernel pointer for a stable arbitrary write and, via ashmem file_operations type confusion, stable kernel read/write**

- **Root cause:** "this commit only addressed the 64-bit ioctl code, introducing a race condition into the 32-bit compatibility layer" (ALSA); Mali tlstream "uses kernel pointers as object identifiers" and was reachable by unprivileged code (Mali GPU info leak)
- **Reported-vs-real impact:** chrome-sandboxed renderer compromise escalated to full kernel read/write via a GPU-driver kernel-pointer leak feeding an unrelated kernel UAF -- a commercial surveillance-vendor chain
- **Source:** https://projectzero.google/2023/09/analyzing-modern-in-wild-android-exploit.html

### [gpu-tee] androidoffsec-cve-2024-23380
**CVE:** CVE-2024-23380  ·  **Product/version:** Qualcomm Adreno GPU kernel driver (KGSL), Virtual Buffer Object (VBO) bind/unbind path Qualcomm KGSL driver, multiple Snapdragon platforms; fixed July 2024  ·  **CVSS:** 7.8 HIGH (CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H) per NVD  ·  **Disclosed:** fixed July 2024; write-up published 2026-03-28  ·  **Axes:** A

Chain:
    1. `race condition: "two threads bind and unbind the same VBO at the same time" with improper refcounting` → *Basic Memory Object lifetime vs. GPU virtual-address mapping* → **physical pages freed while "still mapping to the GPU virtual memory address space" (UAF)**
    2. `freed physical pages returned to the kernel page pool under low-memory pressure` → *kernel heap allocator* → **heap-spray with attacker-controlled kgsl_mem_entry structures reclaiming the freed pages**
    3. `hijacked kgsl_memdesc physaddr field and ops pointer (redirected to kgsl_contiguous_ops)` → *GPU virtual-to-physical mapping exposed to userspace* → **arbitrary kernel physical memory mapped into userspace -> arbitrary kernel read/write**
    4. `arbitrary kernel R/W` → *SELinux enforcement check (sel_read_enforce)* → **SELinux disabled -> arbitrary kernel code execution / root**

- **Root cause:** "A race condition ... use-after-free of physical pages" when "two threads bind and unbind the same VBO at the same time" without proper synchronization of the reference count.
- **Reported-vs-real impact:** local unprivileged app -> arbitrary kernel read/write -> disabled SELinux enforcement -> full root
- **Source:** https://androidoffsec.withgoogle.com/posts/a-technical-deep-dive-into-cve-2024-23380-exploiting-gpu-memory-corruption-to-android-root/

### [itw-chain] P0-ITW-2021-01-ANDROID-EXPLOITS
**CVE:** CVE-2018-9568 (WrongZone) chained after a Chrome renderer 0-day; framework also carried CVE-2015-1805, CVE-2016-3809, CVE-2016-0820, CVE-2016-5195 as alternate privesc paths  ·  **Product/version:** Android (multi-OEM/kernel) — Chrome renderer + Linux kernel privilege-escalation exploit framework Android devices with kernels unpatched against 2015-2018-era CVEs, targeted circa 2020  ·  **CVSS:** Not applicable as a single vector — multi-CVE privesc framework; component CVEs scored individually  ·  **Disclosed:** 2021-01-12 (P0 writeup); component CVEs originally disclosed/patched 2015-2018  ·  **Axes:** A,C

Chain:
    1. `Chrome renderer 0-day exploit (shared campaign infrastructure with the Windows chains above)` → *Chrome sandbox/process boundary* → **code execution inside the sandboxed renderer process**
    2. `Framework probes device/kernel version and selects a matching bundled public n-day privilege-escalation exploit (e.g. CVE-2018-9568 WrongZone use-after-free)` → *Android kernel/userland privilege boundary* → **root access via a corrupted cred struct**
    3. `Post-exploitation downloader performs system-level reconnaissance using legitimate syscalls and rootkit-like techniques` → *on-device detection/attestation surface* → **device profiling and staged retrieval of further implant components**
    4. `Final implant stage retrieved and executed with root privileges (internals not detailed in this part of the P0 series)` → *not further specified by the source* → **persistent, privileged on-device implant**

- **Root cause:** Not disclosed in technical depth by this P0 post: for the WrongZone stage the writeup states only that the exploit "follows exactly the strategy and flow described in the Baidu Security Lab blog post," without re-deriving the underlying use-after-free mechanism itself. (inferred: kernel UAF via zone/refcount handling per the externally-cited report, not independently re-derived by P0 here — flagged rather than fabricated.)
- **Reported-vs-real impact:** P0 states plainly: "This attacker is using entirely public exploits for their privilege elevations" — the reported profile of a well-resourced 0-day-capable actor is, for the Android privesc stage specifically, actually built from already-patched 2015-2018 public n-days chained together; the sophistication sits in orchestration/probing/detection-evasion tooling, not in the individual escalation bugs.
- **Source:** https://projectzero.google/2021/01/in-wild-series-android-exploits.html

### [itw-chain] P0-ITW-2021-01-WIN-CSRSS
**CVE:** CVE-2020-1027  ·  **Product/version:** Microsoft Windows — CSRSS (Client/Server Runtime Subsystem) Windows 10, all builds through 18363; fixed April 14, 2020  ·  **CVSS:** CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H (7.8, NVD; CWE-787 out-of-bounds write, per NVD)  ·  **Disclosed:** 2021-01-12 (P0 writeup); reported 2020-03-23, patched 2020-04-14  ·  **Axes:** A,B,C

Chain:
    1. `ApplicationName is reused as an output parameter; validation checks the Length field, not the true buffer capacity` → *CSRSS capture-buffer heap bounds* → **controlled memcpy write past the capture buffer into adjacent heap**
    2. `Heap overflow corrupts adjacent XMLParser node structures` → *heap object-layout integrity* → **generalized arbitrary-address write primitive**
    3. `Arbitrary write overwrites the PEB_LDR_DATA module-list pointer` → *process loader data-structure integrity in ntdll.dll* → **attacker-controlled fake module-list entries**
    4. `Fake module entries feed the LdrpInitializeThread notification-callback path` → *Control Flow Guard (CFG) valid-call-target enforcement* → **call an arbitrary function pointer while bypassing CFG**
    5. `Leak stack state and overwrite a return address, then create a shared memory section with winlogon.exe` → *CSRSS → winlogon.exe session/privilege boundary* → **execute the final implant stage with elevated session privileges**

- **Root cause:** "The buffer overflow is used with [the] Length field rather than [the] MaximumLength" for bounds validation, while "the unaudited MaximumLength value" is what actually sizes the destination buffer once ApplicationName is reused as an output parameter (as extracted from the P0 writeup).
- **Reported-vs-real impact:** The chain's fourth stage explicitly defeats a named exploit mitigation (Control Flow Guard) via fabricated loader module-list entries rather than a generic ROP bypass, i.e. the reported 'sandbox escape' understates that a specific CFI control was subverted, not merely absent.
- **Source:** https://projectzero.google/2021/01/in-wild-series-windows-exploits.html

### [itw-chain] P0-BLOG-2021-12-FORCEDENTRY
**CVE:** CVE-2021-30860  ·  **Product/version:** Apple iOS / iMessage (BlastDoor) — CoreGraphics JBIG2 image decoder reached via ImageIO iOS ≤ 14.7 (fixed iOS/iPadOS 14.8, Security Update 2021-005 Catalina, macOS Big Sur 11.6, watchOS 7.6.2)  ·  **CVSS:** CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H (7.8, NVD; not given a score in the P0 post itself)  ·  **Disclosed:** 2021-12-15 (P0 writeup publish date); underlying CVE fixed 2021-09-13  ·  **Axes:** A,B,C

Chain:
    1. `iMessage delivers a file with a spoofed .gif extension, forcing IMTranscoderAgent to run image parsing outside the BlastDoor sandbox` → *BlastDoor sandbox / file-type allow-list* → **exposes 20+ legacy ImageIO/CoreGraphics codecs (incl. the JBIG2 decoder) to attacker-controlled input**
    2. `Integer overflow in JBIG2 symbol-dictionary segment reference collation causes numSyms to wrap to a small controlled value` → *heap allocation sizing for the symbol lookup table* → **undersized heap buffer whose JBIG2Bitmap object pointers can be written out of bounds**
    3. `Corrupted JBIG2Bitmap height/line fields` → *bounds-checking on bitmap pixel read/write operations* → **arbitrary memory read/write primitive driven purely through bitmap operations**
    4. `JBIG2 refinement-region logical operators (AND/OR/XOR/XNOR) chained over attacker-supplied bitmap data` → *declarative image-format execution model treated as computation-free* → **Turing-complete bit-logic 'weird machine' (custom 64-bit arithmetic, memory search) built entirely inside the font/image parser before any native code executes; pivots to native code execution**

- **Root cause:** "By supplying carefully crafted reference segments it's possible for the repeated addition...to cause numSyms to overflow to a controlled, small value", producing an undersized heap allocation later used for out-of-bounds JBIG2Bitmap pointer writes (as extracted from the P0 writeup).
- **Reported-vs-real impact:** Public reporting framed FORCEDENTRY as a uniquely sophisticated zero-click exploit; P0's technical dive confirms the mechanism actually exceeds that framing in one specific way — the attacker built a full logic-gate computer inside the JBIG2 decoder (a supposedly non-Turing-complete image format) rather than relying on classic shellcode staging, i.e. most of the 'exploit logic' runs as declarative bit-operations inside the image decoder.
- **Source:** https://projectzero.google/2021/12/a-deep-dive-into-nso-zero-click.html
- _(also triaged under: P0-BLOG-2021-12-FORCEDENTRY)_

### [kernel-messaging] CVE-2025-54957 (Dolby UDC) + CVE-2025-36934 (BigWave driver UAF)
**CVE:** CVE-2025-54957, CVE-2025-36934  ·  **Product/version:** Google Pixel 9 — Dolby Unified Decoder (libcodec2_soft_ddpdec.so, mediacodec) chained to BigWave AV1 hardware-decoder kernel driver Pixel 9 (Dolby UDC and BigWave driver shipped on Pixel 9); Dolby bug also affects ChromeOS/Samsung/Vivo devices sharing the same Dolby codec  ·  **Disclosed:** CVE-2025-54957 reported 2025-06-26, public disclosure 2025-10-15; CVE-2025-36934 reported 2025-06-20, public disclosure 2025-09-19; Pixel patches 2026-01-05/06; blog published 2026-01-14  ·  **Axes:** A,B,C

Chain:
    1. `Google Messages auto-decodes incoming SMS/RCS audio attachments with zero user interaction` → *attacker (network SMS/RCS) -> mediacodec sandboxed decoder process* → **attacker-controlled Dolby EAC-3/DD+ EMDF payload reaches the decoder**
    2. `EMDF payload-size field (`emdf_payload_size`, via `variable_bits`) has no stated size limit; on 64-bit systems values in 0xFFFFFFFFFFFFFFF9-0xFFFFFFFFFFFFFFFF wrap the allocator to a tiny buffer while the write loop still uses the oversized original value (CVE-2025-54957)` → *mediacodec sandbox heap* → **arbitrary code execution inside the constrained mediacodec SELinux context**
    3. `BigWave driver use-after-free: BIGO_IOCX_PROCESS ioctl's wait_for_completion_timeout(16s) can expire before bigo_worker_thread finishes, letting the caller close the fd and free the `inst` struct that the worker thread still references; attacker sprays kmalloc to reclaim it (CVE-2025-36934)` → *mediacodec userspace -> kernel BigWave driver* → **arbitrary kernel read/write, i.e. full privilege escalation to root/kernel**

- **Root cause:** Quoted (stage2): 'there is no stated limit for the size of emdf_payload_size, meanwhile the output of variable_bits could be very large, essentially any numeric value.' Quoted (stage3): 'An object whose lifetime is inherently bound to a file descriptor is transiently accessed on a separate kernel thread that isn't explicitly synced to the existence of that file descriptor.'
- **Reported-vs-real impact:** The Dolby audio bug was initially rated only 'Moderate' under Android's own severity framework despite enabling code execution in a constrained context; Samsung independently classified the identical issue 'Critical'. Android subsequently revised its severity matrix to rate such bugs 'Critical' going forward, after this blog showed the moderate-rated bug chains directly into full kernel compromise.
- **Source:** https://projectzero.google/2026/01/pixel-0-click-part-1.html
- _(also triaged under: CVE-2025-54957 (Dolby UDC, no discrete P0 issue # located) + CVE-2025-36934 / P0 Issue 426567975 (BigWave driver UAF); CVE-2025-54957 (reused) + P0 Issue 463438263 (VPU driver mmap, CVE not stated)_

### [mobile-ics] ZDI-26-209 (companion: ZDI-26-210, ZDI-26-225)
**CVE:** CVE-2025-21079 (ZDI-26-209 and ZDI-26-210); CVE-2025-58487 (ZDI-26-225, same bug class, different Samsung app)  ·  **Product/version:** Samsung Galaxy S25 Firmware prior to the Samsung SVE update referenced at security.samsungmobile.com (2025-11 bulletin)  ·  **CVSS:** ZDI-26-209: 5.0 CVSS:3.0/AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:L/A:L / ZDI-26-210: 5.4 CVSS:3.0/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N  ·  **Disclosed:** 2026-03-16 (ZDI-26-209/210); 2026-03-23 (ZDI-26-225) — vendor notified 2025-11-18/20  ·  **Axes:** A,B

Chain:
    1. `Forced open redirect within the Samsung Members / Samsung Account application to a site serving malicious content` → *crosses the trust boundary from arbitrary web content into a pre-installed, privileged first-party Android application's execution/navigation context* → **attacker-controlled content now runs inside/derives trust from the privileged app (e.g. opens a WebView with a custom URL per ZDI-26-210)**
    2. `Abuse of that privileged context to start arbitrary Android exported activities ('An attacker can leverage this in conjunction with other vulnerabilities to start arbitrary Android exported activites, leading to further compromise' — ZDI-26-209)` → *crosses the Android inter-component/exported-activity permission boundary, invoking app components the attacker's own app/webpage could not directly reach* → **further compromise of the device beyond the redirect itself (exact end capability not enumerated in the advisory)**

- **Root cause:** ZDI-26-209 (verbatim): "This vulnerability allows remote attackers to bypass security on affected installations of Samsung Galaxy S25. Authentication is not required to exploit this vulnerability. The specific flaw exists within the Samsung Members application. An attacker can force a redirection to a site that serves malicious content. An attacker can leverage this in conjunction with other vulnerabilities to start arbitrary Android exported activites, leading to further compromise." ZDI-26-210 (verbatim, same product/app): "...The issue results from the exposure of a resource to the wrong control sphere."
- **Source:** https://www.zerodayinitiative.com/advisories/ZDI-26-209/

### [mobile-ics] ZDI-26-241 (chained with ZDI-26-237, ZDI-26-239, ZDI-26-240)
**CVE:** CVE-2025-62846 (RCE stage); chain partners CVE-2025-62843 (firewall bypass), CVE-2025-62844/CVE-2025-62845 (auth bypass)  ·  **Product/version:** QNAP QHora-322 router Firmware prior to the QSA-26-12 update  ·  **CVSS:** ZDI-26-241: 8.8 CVSS:3.0/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H / ZDI-26-237: 6.3 CVSS:3.0/AV:A/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L  ·  **Disclosed:** 2026-03-30 (all four advisories; vendor notified 2025-11-18)  ·  **Axes:** A,B

Chain:
    1. `IPv6 firewall rule matching failure on PPPoE connections (ZDI-26-237, CVE-2025-62843)` → *network-adjacent attacker crosses the router's WAN/PPPoE firewall boundary into internally-exposed services with no authentication* → **advisory states attacker 'can leverage this in conjunction with other vulnerabilities to execute arbitrary code in the context of root'**
    2. `qurouter_token / role_type parameter mishandling in login.newAuthMiddleware.Authenticator and QBelt VPN auth (ZDI-26-239 CVE-2025-62844, ZDI-26-240 CVE-2025-62845)` → *crosses the device's authentication boundary, letting an attacker authenticate as an arbitrary QCloud account or bypass QBelt VPN auth* → **obtains an authenticated session/token without valid credentials**
    3. `SQL injection in the qvpn_db_mgr module (ZDI-26-241, CVE-2025-62846) — 'lack of proper validation of a user-supplied string before using it to construct SQL queries'` → *authenticated-but-bypassable endpoint escalates from app-level DB query context to OS command execution* → **arbitrary code execution as root**

- **Root cause:** ZDI-26-237 (verbatim): "This vulnerability allows network-adjacent attackers to bypass firewall rules on affected installations of QNAP QHora-322 routers. Authentication is not required to exploit this vulnerability. The specific flaw exists within the implementation of firewall rules. The issue results from failing to match IPv6 firewall rules on PPPoE connections. An attacker can leverage this in conjunction with other vulnerabilities to execute arbitrary code in the context of root." ZDI-26-241 (verbatim): "This vulnerability allows remote attackers to execute arbitrary code on affected installations of QNAP QHora-322 routers. Authentication is required."
- **Source:** https://www.zerodayinitiative.com/advisories/ZDI-26-241/

### [mobile-ics] ZDI-26-433 (chained with ZDI-26-434)
**CVE:** CVE-2026-13305 (firmware-signature stage); CVE-2026-13306 (auth-bypass stage, ZDI-26-434)  ·  **Product/version:** Autel MaxiCharger AC Elite Home EV charger Firmware prior to V1.40.81  ·  **CVSS:** ZDI-26-433: 6.4 CVSS:3.0/AV:P/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H / ZDI-26-434: 4.3 CVSS:3.0/AV:P/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L  ·  **Disclosed:** 2026-07-15 (both advisories; vendor notified 2026-03-19)  ·  **Axes:** A,B,C

Chain:
    1. `Missing authentication on the exposed USB interface (ZDI-26-434, CVE-2026-13306) — 'the lack of authentication prior to allowing access to functionality'` → *a physically-present attacker crosses the device's local-access authentication boundary via USB without any credentials* → **gains privileged local access/control-functionality on the charger**
    2. `Lack of validation of a user-supplied software update image before installing it (ZDI-26-433, CVE-2026-13305)` → *crosses the firmware trust boundary — an unsigned/unvalidated image is accepted as a legitimate update* → **arbitrary code execution in the context of the device**

- **Root cause:** ZDI-26-434 (verbatim): "This vulnerability allows physically present attackers to bypass authentication on affected installations of Autel MaxiCharger AC Elite Home EV chargers... The flaw resides in an exposed USB interface... The specific flaw exists within the lack of authentication prior to allowing access to functionality." ZDI-26-433 (verbatim): "This vulnerability allows physically present attackers to execute arbitrary code on affected installations of Autel MaxiCharger AC Elite Home EV chargers. Authentication is not required to exploit this vulnerability. The specific flaw exists within the handling of software updates."
- **Source:** https://www.zerodayinitiative.com/advisories/ZDI-26-433/

### [os-kernel] CVE-2025-38236 (Project Zero writeup)
**CVE:** CVE-2025-38236  ·  **Product/version:** Linux Kernel >=6.9; fixed in commit 32ca245464e1479bfea8592b9db227fdc1641705  ·  **Disclosed:** 2025-08-08  ·  **Axes:** A,B,C

Chain:
    1. `AF_UNIX MSG_OOB dangling-pointer bug: manage_oob() takes the !unix_skb_len(skb) branch and skips the skb==u->oob_skb check, leaving oob_skb pointing at an SKB already consumed by the normal receive path` → *socket receive-queue bookkeeping vs. OOB pointer lifetime* → **use-after-free on a freed sk_buff, reachable from an unprivileged Chrome renderer process**
    2. `recv(..., MSG_OOB) on the dangling oob_skb triggering copy_to_user() on attacker-influenced freed memory` → *user/kernel copy boundary via the UAF'd skb* → **semi-arbitrary kernel memory read, used to defeat KASLR via a fixed IDT-entry address leak**
    3. `pipe-buffer allocation, page-table spraying, and SLUB cache observation to groom the heap` → *page allocator / SLUB cache reuse* → **predictable reallocation of a freed slot as a live kernel stack**
    4. `CONFIG_RANDOMIZE_KSTACK_OFFSET-aware sendmsg() placement plus an mprotect()-induced page fault to delay a copy_from_iter() mid-copy` → *kernel stack frame layout under stack-offset randomization* → **controlled single-value increment inside a live kernel stack frame**
    5. `page-table overwrite creating a userspace mapping of physical kernel memory` → *page-table-mediated memory access control* → **arbitrary kernel memory write, demonstrated by modifying kernel UTS (uname) data**

- **Root cause:** "When the receive queue looks like this ... SKB 1: unix_skb_len()=0, SKB 2: unix_skb_len()=1 <-- OOB pointer, and a normal recv() happens, then manage_oob() takes the !unix_skb_len(skb) branch, which deletes the SKB with remaining length 0 and skips forward to the following SKB; but it then doesn't go through the skb == u->oob_skb check ... which means it doesn't clear out the ->oob_skb pointer before the SKB is consumed by the normal receive path, creating a dangling pointer that will lead to UAF on a subsequent recv(..., MSG_OOB)."
- **Reported-vs-real impact:** Underlying bug is a single UAF classed as a privilege-escalation-enabling flaw; the writeup demonstrates the reported UAF is chained into full arbitrary kernel read/write (KASLR defeat, stack corruption, page-table overwrite) achieved entirely from an unprivileged Chrome renderer sandbox on Linux x86-64 -- the disclosed real capability is materially greater than a bare 'UAF' label implies.
- **Source:** https://projectzero.google/2025/08/from-chrome-renderer-code-exec-to-kernel.html
- _(also triaged under: CVE-2025-38236 (Project Zero writeup))_

### [virtualization] projectzero-2021-epyc-escape-kvm
**CVE:** CVE-2021-29657  ·  **Product/version:** QEMU/KVM (Linux kernel, AMD SVM nested virtualization) Linux kernel v5.10-rc1 through v5.12-rc6 (patched in 5.11.12 / 5.10.28 area)  ·  **CVSS:** 7.4 HIGH (CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H) — NVD  ·  **Disclosed:** 2021-06-29 (Project Zero); patched ~2021-03  ·  **Axes:** A,C

Chain:
    1. `TOCTOU double-fetch: guest modifies VMCB12 fields after nested_vmcb_checks validates them but before load_nested_vmcb_control copies them into svm->nested.ctl` → *malicious L1/L2 nested guest races a second vCPU to desynchronize validated vs. used VMCB state inside the host KVM hypervisor* → **corrupted nested host-save area (hsave) lets guest overwrite the MSR permission bitmap pointer, which is later freed/reused, yielding unrestricted host MSR read/write from the guest**
    2. `MSR-bitmap use-after-free / attacker-controlled bitmap reuse` → *guest-controlled MSR access bypasses host isolation of KVM's SVM nested-virt trap configuration* → **IBS (Instruction Based Sampling) MSR abuse gives an information leak that defeats host KASLR**
    3. `host address-space info leak via IBS` → *leaked addresses used to fabricate a fake host-save area and stage a VMSAVE-based write gadget* → **ROP chain disables CR0 write-protection, then shellcode executes with host kernel privileges — full guest-to-host KVM escape**

- **Root cause:** "A malicious guest can modify fields in the VMCB after they are verified in nested_vmcb_checks, but before they are copied to svm->nested.ctl in load_nested_vmcb_control" — a TOCTOU race condition associated with a VMCB12 double fetch (Project Zero writeup / NVD paraphrase of the same root cause).
- **Reported-vs-real impact:** Escalates from guest-VM-controlled nested-SVM configuration input to arbitrary host kernel code execution (ring 0 on the host), i.e. full hypervisor breakout — not merely an in-guest privilege escalation.
- **Source:** https://projectzero.google/2021/06/an-epyc-escape-case-study-of-kvm.html

### [virtualization] google-security-research-ghsa-virtualbox-vmsvga3d
**CVE:** CVE-2025-30712  ·  **Product/version:** Oracle VM VirtualBox (VMSVGA 3D device, vmsvga3d_dx / MOB object handling) VirtualBox 7.1.6  ·  **CVSS:** 8.1 HIGH (CVSS:3.1/AV:L/AC:L/PR:H/UI:N/S:C/C:H/I:H/A:L)  ·  **Disclosed:** 2025-05-15 (GHSA timeline); NVD published 2025-04-15  ·  **Axes:** A,B

Chain:
    1. `integer overflow in vmsvga3dSurfaceMipBufferSize lets a guest-created 3D surface report a nonzero tracked size while its backing malloc() actually allocates 0 bytes` → *guest-controlled SVGA_3D_CMD_DX_BUFFER_COPY / UPDATE_SUBRESOURCE commands reach the host-side VMSVGA 3D device emulation with only guest-supplied dimension checks* → **linear out-of-bounds read then write against host heap memory adjacent to the zero-sized allocation**
    2. `leak of the VMSVGAMOB pfnCommandClear function pointer via the OOB read` → *leaked pointer value crosses back into the guest, revealing host process layout* → **defeats host ASLR by disclosing VBoxDD.so / VBoxRT.so base addresses**
    3. `corruption of cbTotal / pvHost fields inside MOB objects via vmsvga3dDXReadbackCOTable / GrowCOTable` → *guest now controls arbitrary offsets into host process memory* → **arbitrary host memory read/write primitive**
    4. `shellcode planted via heap grooming + ROP chain disabling memory protections, overwrite of pfnCommandClear` → *hijacked function pointer redirects host VBoxDD execution flow* → **arbitrary code execution in the host VirtualBox process — full guest-to-host escape**

- **Root cause:** Integer overflow in `vmsvga3dSurfaceMipBufferSize` permits an attacker to "manipulate a malloc call such that 0 bytes are allocated while VirtualBox tracks the size of the buffer as a value greater than 0," per the GHSA advisory (Google Security Research / google/security-research repo).
- **Reported-vs-real impact:** Guest-controlled 3D-acceleration command stream escalates to unauthorized host memory read/write and ultimately arbitrary code execution on the VirtualBox host process — a full guest-to-host VM escape, not a guest-local bug.
- **Source:** https://github.com/google/security-research/security/advisories/GHSA-qx2m-rcpc-v43v

### [virtualization] ret2-parallels-megasmash-2021
**CVE:** —  ·  **Product/version:** Parallels Desktop (QtCore usage in prl_vm_app; OTG protocol handler; drag-and-drop handler) Parallels Desktop pre-build 49187 (fixed in 49187)  ·  **Disclosed:** 2022-05-19 (RET2 Systems writeup of a Pwn2Own Vancouver 2021, $40,000 entry)  ·  **Axes:** A,C

Chain:
    1. `uninitialized-heap info leak: OTG opcode 10 handler resizes an output QByteArray to 0x90 bytes but only populates the first 0x20, leaving 0x70 bytes of stale heap content exposed to the guest` → *guest-triggerable OTG protocol request reads host process heap memory back into the guest response* → **leaks function-pointer values, disclosing prl_vm_app and QtCore base addresses (ASLR defeat)**
    2. `stack buffer overflow in the drag-and-drop handler: guest-supplied string lacking null-termination validation overflows a fixed stack buffer` → *guest DnD message corrupts a stack-resident worker pointer inside the host DnD handler* → **corruption of the exception handler's pointer to the original exception port**
    3. `'Megasmash': integer overflow in QtCore's QByteArray constructor lets a guest request allocate a zero-sized array while claiming a 0xffffffff length, so a subsequent memcpy writes far past the allocation` → *unbounded memcpy corrupts the Qt data section of the host process* → **overwrite of the qt_signal_spy_callback_set function pointer**
    4. `corrupted exception-handler pointer causes EXC_BAD_ACCESS that stalls one thread while another thread dereferences the corrupted qt_signal_spy_callback_set pointer` → *hijacked function pointer redirects execution in the host prl_vm_app process* → **stack-pivot ROP chain executes system("open -a Calculator") — arbitrary host code execution, full guest-to-host escape**

- **Root cause:** Three chained bugs quoted from the RET2 Systems writeup: an OTG handler that "resizes the output QByteArray to size 0x90, then proceeds to populate the first 0x20 bytes" (info leak); a DnD stack overflow from an unterminated guest string; and a QtCore QByteArray integer overflow where "memcpy(QtCore_data_section, controlled_data, 0xffffffff)" corrupts adjacent memory.
- **Reported-vs-real impact:** A three-bug chain (info leak -> stack corruption -> heap/global corruption) escalates from ordinary guest-VM protocol messages (OTG + drag-and-drop) to arbitrary command execution on the host — canonical genuine multi-stage guest-to-host escape, independently confirmed reliable (100%) by the researcher.
- **Source:** https://blog.ret2.io/2022/05/19/pwn2own-2021-parallels-desktop-exploit/

### [virtualization] trenchant-l3harris-parallels-virtio-vga-2021
**CVE:** —  ·  **Product/version:** Parallels Desktop (emulated virtio VGA device, CommonCfg MMIO region) Parallels Desktop as targeted at Pwn2Own Vancouver 2021 (exact build not stated in source)  ·  **Disclosed:** 2025-01-14 (writeup of a Pwn2Own Vancouver 2021 entry, Trenchant/L3Harris team)  ·  **Axes:** A,C

Chain:
    1. `missing bounds check on guest-supplied EBX value written into the virtio 'Driver feature select' global register` → *guest MMIO write to the virtio VGA device's CommonCfg settings region reaches unchecked host emulation code* → **relative out-of-bounds read/write against host process memory**
    2. `OOB access reaches the port-I/O handler array located in the host binary's __bss section` → *guest-influenced index overwrites entries in that handler array* → **instruction-pointer control (arbitrary code execution primitive) in the hypervisor process**
    3. `initial shellcode execution upgraded to an absolute read/write primitive` → *host process memory now fully addressable/writable from the guest exploit* → **arbitrary command execution on the macOS host via system(), demonstrated by launching TextEdit**

- **Root cause:** "The code stores guest supplied data (EBX) in the 'Driver feature select' register (a global variable)...without any bounds checking" — quoted from the Trenchant/L3Harris researcher writeup describing the virtio VGA CommonCfg MMIO handler.
- **Reported-vs-real impact:** A guest-writable MMIO register with no bounds validation escalates directly to host code execution via port-handler-array corruption — full guest-to-host escape, publicly detailed for the first time in this 2025 writeup of the 2021 contest bug.
- **Source:** https://www.l3harris.com/newsroom/editorial/2025/01/pwn2own-2021-parallels-desktop-guest-host-escape

### [wireless-proximity] p0-awdl-radio-proximity-2020
**CVE:** CVE-2020-3843  ·  **Product/version:** Apple iOS / macOS - AWDL (Apple Wireless Direct Link) kernel component iOS <= 13.5, macOS <= 10.15.3 (demonstrated on iPhone 11 Pro, A13)  ·  **CVSS:** 8.8 (CVSS 3.1 AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H, per NVD)  ·  **Disclosed:** Reported to Apple 2019-11-29; fixed as CVE-2020-3843 2020-01-28; P0 writeup published 2020-12-01  ·  **Axes:** A

Chain:
    1. `Linear heap buffer overflow in the AWDL SyncTree TLV parser (kernel C++ code) via a memmove whose size parameter is not bounds-checked against the destination allocation` → *Untrusted AWDL protocol frame parsed directly in-kernel with no sandbox/process boundary in front of it* → **Corruption of adjacent kalloc.6144-zone IO80211AWDLPeer / Service-Response-Descriptor objects (steering_msg_blob pointer+size fields)**
    2. `Attacker triggers peer timeout on the corrupted peer object` → *Kernel heap allocator (kalloc zone) trusts the corrupted size/pointer fields it was handed* → **Arbitrary-address kfree() (attacker-controlled pointer and size) -> heap grooming primitive**
    3. `BSS Steering state machine echoes corrupted data back over the air in AWDL Master Indication frames` → *No re-validation of steering-message contents before retransmission* → **Remote memory disclosure, used to build a stable arbitrary kernel read/write primitive and defeat Pointer Authentication Codes (PAC), yielding native code execution with zero user interaction**

- **Root cause:** "A fairly trivial buffer overflow programming error in C++ code in the kernel parsing untrusted data" where the memmove size parameter lacks proper bounds validation despite being logically separated from the length-checking code.
- **Reported-vs-real impact:** "remotely gain native code execution and kernel memory read and write" over Wi-Fi/AWDL proximity alone with zero user interaction, sufficient to "access ... all the photos, read all the email, copy all the private messages" -- full device compromise with no click, no pairing, no auth.
- **Source:** https://projectzero.google/2020/12/an-ios-zero-click-radio-proximity.html

### [wireless-proximity] p0-over-the-air-vol2-pt3-2017
**CVE:** Not assigned a CVE in the cited text -- tracked as Project Zero issue tracker bugs #1302, #1305, #1312, #1313, #1314, #1317, #1318  ·  **Product/version:** Broadcom Wi-Fi SoC firmware + Apple XNU kernel / DART IOMMU (iOS devices) Broadcom Wi-Fi chips used in iPhones circa 2017 (continuation of the 'Over the Air Vol. 2' Apple-focused series)  ·  **CVSS:** Not stated in source  ·  **Disclosed:** 2017-10-11  ·  **Axes:** A

Chain:
    1. `Prior-stage Wi-Fi firmware compromise (from earlier posts in the same series) gives the attacker arbitrary code execution on the Broadcom Wi-Fi SoC` → *Wi-Fi SoC firmware sits behind the DART (Apple's IOMMU) which is meant to confine its DMA to an IO-Space region, isolating it from host kernel memory* → **Malicious firmware can manipulate DMA descriptor ring indices from the compromised chip side**
    2. `getIndices() validates ring indices only against 'a fixed maximal value: 0x10000' rather than the true, ring-specific bound, and the ring indices are 'mapped into IO-Space as both readable and writable'` → *Host-side DMA ring-index validation logic is the only thing standing between firmware and host memory once DART confinement is bypassed* → **Out-of-bounds DMA writes from the Wi-Fi chip into host kernel memory, used to corrupt adjacent DART L2 translation tables**
    3. `Attacker shapes memory so DART L2 translation tables sit adjacent to the exploitable ring structures, then overwrites translation-table entries` → *DART translation tables are the final gate restricting which physical addresses the Wi-Fi chip's DMA engine can reach* → **Firmware gains direct DMA access to arbitrary host physical memory, i.e. full XNU kernel code execution/control originating purely from the Wi-Fi radio**

- **Root cause:** "When fetching the ring indices, the getIndices function attempts to validate their values" but does so only against a fixed maximal value (0x10000) instead of the ring's real bound, and ring indices are "mapped into IO-Space as both readable and writable," letting compromised firmware rewrite them.
- **Reported-vs-real impact:** Escalates a Wi-Fi-chip-only compromise into remote kernel code execution on the host application processor -- "unrestricted access to the device's physical memory and complete control over the XNU kernel" -- purely via Wi-Fi proximity, no user interaction.
- **Source:** https://projectzero.google/2017/10/over-air-vol-2-pt-3-exploiting-wi-fi.html

---

## Axis B — root-cause / severity re-derivation → `skills/ajar-falsify/SKILL.md` & `skills/ajar-report/SKILL.md` (22)

Published root-cause paired with a real severity/scope correction or a clean severity anchor — primary-source calibration evidence for falsification and severity scoring.

| Domain | Source | CVE | CVSS | Root cause / delta | Disclosed |
| --- | --- | --- | --- | --- | --- |
| browser-renderer | ZDI-26-329 / ZDI-26-330 / ZDI-26-331 | CVE-2026-45492 (ZDI-26-329), CVE-2026-45494 (ZDI-26-330), CVE-2026-45495 (ZDI-26-331) | ZDI-26-329: CVSS:3.0/AV:N/AC:L/PR:N/UI:R/S:U/C:N/I:L/A:N (4.3); ZDI-26-330: CVSS:3.0/AV:N/AC:H/PR:N/UI:R/S:U/C:H/I:N/A:N (5.0); ZDI-26-331: CVSS:3.0/AV:N/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H (7.5) | ZDI's Pwn2Own Berlin writeup reports a full renderer sandbox escape via chained logic bugs (CWE-20, CWE-79, CWE-35), while the 3 disclosed CVEs individually carry 4.3, 5.0, and 7.5 base scores. | 2026-06-04 (reported 2026-05-20) |
| browser-renderer | ZDI-26-252 | CVE-2026-4698 | CVSS:3.0/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H (8.8) | IonMonkey switch-statement optimization lacks proper input validation (CWE-843 / type confusion), enabling renderer-context code execution. | 2026-04-02 |
| browser-sandbox | P0-blog-in-wild-ios-exploit-chain-4-2019 | CVE-2019-7286 (cfprefsd sandbox escape); CVE-2019-7287 (IOKit kernel EoP) | Not stated in P0 post (NVD: CVE-2019-7286 CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:H 8.6; CVE-2019-7287 CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H 7.8) | Real-world iOS watering-hole chain: XPC object-lifetime reference-drop bug (`CVE-2019-7286`, CWE-416) paired with an unbounded IOKit `memmove` (`CVE-2019-7287`, CWE-787) forcing emergency iOS 12.1.4 patch. | 2019-08-29 |
| browser-sandbox | P0-blog-in-wild-series-windows-exploits-2021 | CVE-2020-6418 (Chrome V8); CVE-2020-0938, CVE-2020-1020 (atmfd.dll); CVE-2020-1027 (CSRSS EoP) | Not stated in P0 post (NVD CVE-2020-6418: CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H 8.8; CVE-2020-1027: CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H 7.8) | V8 TurboFan type confusion (`CVE-2020-6418`, CWE-843) paired with either ATM Type-1 font stack write (`CVE-2020-0938`/`CVE-2020-1020`, CWE-787) on Windows 8.1 or CSRSS length-field confusion (`CVE-2020-1027`, CWE-787) on Windows 10. | 2021-01-12 |
| enterprise-server | ZDI-21-821 / ZDI-21-822 / ZDI-21-815 (ZDI-CAN-13611 / ZDI-CAN-13614 / ZDI-CAN-13690) | CVE-2021-34473 (ACL bypass) -> CVE-2021-34523 (PowerShell EoP) -> CVE-2021-31207 / ZDI-21-815 (File Write RCE) | ZDI-21-821: 10.0 / CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H; ZDI-21-822: 9.8 / CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H; ZDI-21-815: 7.2 / CVSS:3.0/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H | Canonical 3-stage ProxyShell chain: pre-auth ExplicitLogon URI ACL bypass (`CVE-2021-34473`, CWE-918) -> Exchange PowerShell `X-Rps-CAT` token EoP (`CVE-2021-34523`, CWE-269) -> `New-MailboxExportRequest` arbitrary `.aspx` write RCE (`CVE-2021-31207`, CWE-22/CWE-434). | 2021-07-19 |
| enterprise-server | ZDI-26-194 (ZDI-CAN-28462) | CVE-2026-21527 | 5.3 / CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:N | Scored as a standalone Security Feature Bypass (`C:N/I:L/A:N`, CWE-284, CVSS 5.3) rather than code execution or data compromise — single-primitive contrast against full multi-stage RCE chains. | 2026-03-16 |
| enterprise-server | ZDI-26-355 (ZDI-CAN-28816) | CVE-2026-27220 | 7.8 / CVSS:3.0/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H | Advisory title reads "Remote Code Execution" but the CVSS vector is `AV:L/UI:R` and requires opening a malicious file locally (CWE-787) — local file-open vector, not network pre-auth RCE. | 2026-06-10 |
| enterprise-server | ZDI-26-412 / ZDI-26-413 (ZDI-CAN-31490 / ZDI-CAN-31491) | CVE-2026-50522 | 8.1 / CVSS:3.0/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H | SharePoint chain combining session-token cryptographic signature bypass (`ZDI-26-413`, CWE-347) with `SessionSecurityTokenHandler` untrusted deserialization (`ZDI-26-412`, CWE-502) under a single shared CVE. | 2026-07-15 |
| gpu-tee | p0-0day-cve-2023-33106 | CVE-2023-33106 | 7.8 HIGH / CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H (NVD) | Qualcomm Adreno GPU kernel driver local app-to-kernel memory corruption (CWE-416 / CWE-787) yielding code execution; confirmed exploited in the wild per CISA KEV. | 2023-10-02 |
| itw-chain | P0-ITW-2021-01-WIN-CSRSS | CVE-2020-1027 | 7.8 HIGH / CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H (NVD, CWE-787) | CSRSS `sxssrv.dll` `Length` vs `MaximumLength` bounds bug (CWE-787) whose 4th stage fabricates `PEB_LDR_DATA` module-list entries to bypass Control Flow Guard (CFG) and reach SYSTEM. | 2021-01-12 |
| itw-chain | P0-BLOG-2021-12-FORCEDENTRY | CVE-2021-30860 | 7.8 HIGH / CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H (NVD, CWE-190) | CoreGraphics JBIG2 integer overflow (`numSyms`, CWE-190) chained after a `.gif` extension BlastDoor sandbox bypass to construct a Turing-complete bit-logic machine inside the image decoder. | 2021-12-15 |
| kernel-messaging | CVE-2025-54957 (Dolby UDC) + CVE-2025-36934 (BigWave driver UAF) | CVE-2025-54957, CVE-2025-36934 | Not assigned single chain score (Dolby `CVE-2025-54957` CWE-190/CWE-787; BigWave `CVE-2025-36934` CWE-416) | Dolby `emdf_payload_size` wraparound (`CVE-2025-54957`) was initially rated Moderate by Android before chaining directly with BigWave `BIGO_IOCX_PROCESS` fd-lifetime UAF (`CVE-2025-36934`) for 0-click Pixel 9 kernel R/W. | 2026-01-14 |
| kernel-messaging | P0 blog: 'Defeating KASLR by Doing Nothing at All' | None assigned (classified as intended behavior by kernel maintainers) | Not applicable | Non-randomized linear map and fixed decompression address on Pixel/arm64 kernels eliminate KASLR work without a separate info-leak bug; treated as works-as-intended by maintainers despite material exploit facilitation. | 2025-11-03 |
| mobile-ics | ZDI-26-209 / ZDI-26-210 / ZDI-26-225 | CVE-2025-21079 (ZDI-26-209, ZDI-26-210); CVE-2025-58487 (ZDI-26-225) | ZDI-26-209: 5.0 CVSS:3.0/AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:L/A:L; ZDI-26-210: 5.4 CVSS:3.0/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N | Forced open redirect in Samsung Members (`CVE-2025-21079`, CWE-601 / CWE-20) crosses into privileged first-party WebView context to launch arbitrary exported Android activities. | 2026-03-16 |
| mobile-ics | ZDI-26-241 (chained with ZDI-26-237, ZDI-26-239, ZDI-26-240) | CVE-2025-62846 (ZDI-26-241); CVE-2025-62843 (ZDI-26-237); CVE-2025-62844 (ZDI-26-239); CVE-2025-62845 (ZDI-26-240) | ZDI-26-241: 8.8 CVSS:3.0/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H; ZDI-26-237: 6.3 CVSS:3.0/AV:A/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L | QNAP QHora-322 PPPoE IPv6 firewall rule bypass (`CVE-2025-62843`, CWE-923) -> `qurouter_token`/QBelt auth bypass (`CVE-2025-62844`/`CVE-2025-62845`, CWE-287) -> `qvpn_db_mgr` SQLi (`CVE-2025-62846`, CWE-89) -> root RCE. | 2026-03-30 |
| mobile-ics | ZDI-26-433 (chained with ZDI-26-434) | CVE-2026-13305 (ZDI-26-433); CVE-2026-13306 (ZDI-26-434) | ZDI-26-433: 6.4 CVSS:3.0/AV:P/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H; ZDI-26-434: 4.3 CVSS:3.0/AV:P/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L | Autel MaxiCharger exposed USB missing authentication (`CVE-2026-13306`, CWE-306) chained with unverified firmware update installation (`CVE-2026-13305`, CWE-347) for physical-access root code execution. | 2026-07-15 |
| os-kernel | CVE-2025-38236 (Project Zero writeup) | CVE-2025-38236 | Not stated in P0 post (CWE-416) | Linux kernel >= 6.9 `AF_UNIX` `MSG_OOB` `manage_oob()` dangling `oob_skb` UAF (`CVE-2025-38236`, CWE-416) escalated from unprivileged Chrome renderer sandbox to KASLR leak, kernel stack increment, and page-table arbitrary kernel write. | 2025-08-08 |
| os-kernel | ZDI-26-179 (ZDI-CAN-28557) | CVE-2026-23668 | 8.8 / CVSS:3.0/AV:L/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H | Missing object locking in Windows `win32kfull` (CWE-362) enables local privilege escalation to SYSTEM. | 2026-03-10 |
| os-kernel | ZDI-26-443 (ZDI-CAN-31467) | None assigned at publication | 8.8 / CVSS:3.0/AV:L/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H | Integer overflow before buffer allocation in `vmwgfx` surface allocation handling (CWE-190) enables privilege escalation. | 2026-07-15 |
| virtualization | google-security-research-ghsa-virtualbox-vmsvga3d | CVE-2025-30712 (GHSA-qx2m-rcpc-v43v) | 8.1 HIGH / CVSS:3.1/AV:L/AC:L/PR:H/UI:N/S:C/C:H/I:H/A:L | VirtualBox 7.1.6 `vmsvga3dSurfaceMipBufferSize` integer overflow (`malloc(0)` with nonzero tracked size, CWE-190/CWE-787) escalates guest 3D commands to host ASLR leak and host process code execution. | 2025-05-15 |
| virtualization | ZDI-26-189 (ZDI-CAN-27157) | CVE-2025-41236 | 8.2 / CVSS:3.0/AV:L/AC:L/PR:H/UI:N/S:C/C:H/I:H/A:H | Integer overflow before buffer allocation in VMware VMXNET3 virtual network device implementation (CWE-190), enabling guest-to-host code execution. | 2026-03-16 |
| wireless-proximity | exodusintel-broadpwn-2017 | CVE-2017-9417 | 9.8 CRITICAL / CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H (NVD, CWE-119) | Zero-click over-the-air Wi-Fi chipset buffer overflow (`CVE-2017-9417`, CWE-119) requiring no authentication or user interaction within radio proximity. | 2017-07-26 |

---

## Axis C — mechanism-fidelity / impact-delta → `skills/ajar-reproduce/SKILL.md` (17)

The primitive executed, or was framed broadly, while primary technical analysis established the exact boundary and mechanism.

| Domain | Source | CVE | CVSS | Root cause / delta | Disclosed |
| --- | --- | --- | --- | --- | --- |
| enterprise-server | ZDI-26-194 (ZDI-CAN-28462) | CVE-2026-21527 | 5.3 / CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:N | Scored strictly as a Security Feature Bypass (`C:N/I:L/A:N`, CWE-284) rather than code execution or data disclosure. | 2026-03-16 |
| enterprise-server | ZDI-26-355 (ZDI-CAN-28816) | CVE-2026-27220 | 7.8 / CVSS:3.0/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H | Titled "Remote Code Execution" while vector `AV:L/UI:R` requires local user interaction opening a crafted file (CWE-787). | 2026-06-10 |
| gpu-tee | p0-attacking-adreno-gpu-2020 | CVE-2020-11179 (incomplete fix for CVE-2019-10567) | 7.0 HIGH / CVSS:3.1/AV:L/AC:H/PR:L/UI:N/S:U/C:H/I:H/A:H (NVD, CWE-787) | Incomplete ringbuffer scratch-memory fix for `CVE-2019-10567` in Qualcomm Adreno GPU driver (`CVE-2020-11179`): app-context GPU shared-mapping race overwrites ringbuffer commands for arbitrary physical memory access and kernel code execution. | 2020-09-08 |
| gpu-tee | p0-0day-cve-2023-33107 | CVE-2023-33107 | 7.8 HIGH / CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H (CWE-416) | Qualcomm Adreno GPU dangling IOMMU page-table entries mapping freed kernel memory allow local app to gain arbitrary kernel read/write. | 2023-10-02 |
| gpu-tee | p0-trust-issues-trustzone-2017 | Not assigned single CVE in post (Qualcomm QSEE trustlet bugs) | Not stated in post | Normal-world app exploitation of a Qualcomm QSEE trustlet vulnerability escalates via physical memory mapping to arbitrary code execution inside TrustZone Secure World. | 2017-07-24 |
| gpu-tee | sigma-star-optee-tzasc-alias-2026 | None assigned at publication | Not assigned | System TZASC memory-aliasing misconfiguration lets normal-world privileged physical-memory access read OP-TEE Secure World memory (including fTPM secrets); config-dependent hardware integration defect. | 2026-06-11 |
| itw-chain | P0-ITW-2021-01-ANDROID-EXPLOITS | CVE-2018-9568 (WrongZone) + CVE-2015-1805, CVE-2016-3809, CVE-2016-0820, CVE-2016-5195 | Component CVEs scored individually | Attacker combined a Chrome renderer 0-day with entirely public 2015–2018 Android kernel n-day privilege-escalation exploits (`CVE-2018-9568`, CWE-416); novelty sat in orchestration rather than kernel 0-days. | 2021-01-12 |
| itw-chain | P0-ITW-2021-01-WIN-CSRSS | CVE-2020-1027 | 7.8 HIGH / CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H (NVD, CWE-787) | Fourth stage defeats Control Flow Guard (CFG) specifically by fabricating `PEB_LDR_DATA` loader module-list entries rather than generic ROP. | 2021-01-12 |
| itw-chain | P0-BLOG-2021-12-FORCEDENTRY | CVE-2021-30860 | 7.8 HIGH / CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H (NVD, CWE-190) | Exploit constructs a full bit-logic computer out of JBIG2 refinement-region operators (`CVE-2021-30860`, CWE-190) before transferring control to native code. | 2021-12-15 |
| kernel-messaging | CVE-2025-54957 (Dolby UDC) + CVE-2025-36934 (BigWave driver UAF) | CVE-2025-54957, CVE-2025-36934 | Not assigned single chain score | Constrained-process codec memory corruption (`CVE-2025-54957`, initially rated Moderate) chains directly into kernel driver fd-lifetime UAF (`CVE-2025-36934`) for 0-click root compromise. | 2026-01-14 |
| kernel-messaging | P0 blog: 'Defeating KASLR by Doing Nothing at All' | None assigned | Not applicable | Architectural absence of arm64 linear-map randomization removes the need for a dedicated KASLR info-leak stage without being classified as a kernel CVE. | 2025-11-03 |
| mobile-ics | ZDI-26-433 (chained with ZDI-26-434) | CVE-2026-13305 (ZDI-26-433); CVE-2026-13306 (ZDI-26-434) | ZDI-26-433: 6.4 CVSS:3.0/AV:P/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H; ZDI-26-434: 4.3 CVSS:3.0/AV:P/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L | Physical USB authentication absence (`CVE-2026-13306`, CWE-306) unlocks unverified firmware image installation (`CVE-2026-13305`, CWE-347). | 2026-07-15 |
| os-kernel | CVE-2025-38236 (Project Zero writeup) | CVE-2025-38236 | Not stated in P0 post (CWE-416) | Single `AF_UNIX` `MSG_OOB` UAF (`CVE-2025-38236`) achieves both KASLR bypass and arbitrary physical kernel memory write via page-table reclamation from inside the Chrome renderer sandbox. | 2025-08-08 |
| virtualization | projectzero-2021-epyc-escape-kvm | CVE-2021-29657 | 7.4 HIGH / CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H (NVD, CWE-367) | Nested AMD SVM VMCB12 TOCTOU double-fetch (`CVE-2021-29657`, CWE-367) escalates guest VM state to ring-0 host kernel code execution (full guest-to-host escape, even though NVD scored `S:U`). | 2021-06-29 |
| virtualization | ZDI-26-416 (ZDI-CAN-28769) | CVE-2026-54129 | 7.8 / CVSS:3.0/AV:L/AC:H/PR:L/UI:N/S:C/C:H/I:H/A:H | Product is Microsoft Hyper-V with `S:C`, which looks like guest-to-host escape from metadata alone, whereas advisory details restrict impact to the specific component boundary (CWE-362). | 2026-07-15 |
| virtualization | ret2-parallels-megasmash-2021 | None assigned in writeup | Not assigned | Three-bug guest-to-host Parallels Desktop escape combining OTG uninitialized heap leak (CWE-908), DnD stack overflow (CWE-121), and `QByteArray` 32-bit integer overflow (`Megasmash`, CWE-190). | 2022-05-19 |
| virtualization | trenchant-l3harris-parallels-virtio-vga-2021 | None assigned in writeup | Not assigned | Unbounded guest EBX index write in Parallels virtio VGA CommonCfg MMIO handler (CWE-787) corrupts host `__bss` port-I/O handler table for direct host code execution. | 2025-01-14 |

---

## Contested (4)

Real disclosure, but the chain linkage or per-stage mechanism is withheld or inferred — recorded for reference, not asserted as verified multi-stage handoffs.

| Item | Reason |
| --- | --- |
| CVE-2023-24033, CVE-2023-26496, CVE-2023-26497, CVE-2023-26498 (Project Zero Exynos baseband post) | Project Zero explicitly withheld the per-CVE SDP/RTP baseband exploit mechanism; stage handoffs remain inferred reachability claims rather than disclosed exploit stages. |
| vmware-vmxnet3-geekpwn2018 (VMSA-2018-0027: CVE-2018-6981, CVE-2018-6982) | Real dual-CVE VMware ESXi/Workstation escape (`CVE-2018-6981` 8.8 HIGH uninitialized memory + `CVE-2018-6982` 6.5 MEDIUM), but public chain assembly combines two separate advisories without a single primary stage-by-stage writeup. |
| vmware-xhci-backdoor-pwn2own2017 (VMSA-2017-0006: CVE-2017-4904, CVE-2017-4905) | Real dual-CVE VMware XHCI/backdoor escape (`CVE-2017-4904` 8.8 HIGH write-what-where + `CVE-2017-4905` 5.5 MEDIUM info leak), with partial public chain detail. |
| google-bleedingtooth-badkarma-2020 (CVE-2020-12351, CVE-2020-12352) | `CVE-2020-12351` (BadKarma, CWE-843) is a heap type-confusion primitive; pairing it with `CVE-2020-12352` (BadChoice, GHSA-7mh3-gq28-gfrq stack info leak) for KASLR bypass was inferred across sibling advisories. |

---

## Known coverage gaps

Reviewers dropped single-primitive advisories from Axis A and deduplicated repeated chain shapes. Remaining structural gaps for future corpus passes:
- macOS desktop (non-iOS) local-to-kernel chains.
- Cloud metadata SSRF-to-container/orchestrator breakout chains with full primary postmortems.
- Fully quotable cellular baseband RCE chains where per-stage memory primitives were not withheld.
