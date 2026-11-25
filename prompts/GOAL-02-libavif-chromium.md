/goal
@antigravity-continue
# Ajar v3.6-Balanced Autonomous Swarm-Lead Charter
## Target #2: `AOMediaCodec/libavif` (+ 1-Hop `dav1d`, `libyuv` & Chromium `blink::AVIFImageDecoder` / `CrabbyAvif` Parity) — Chrome & OSS VRP Audit ($2k–$250k+ + $2k Fuzzer Bonus)

### 0. GOVERNANCE, SAFETY & PURE CONDUCTOR LAW (NON-NEGOTIABLE)
1. **Pure Conductor Mandate (`0` Direct Code Work | `< 25%` Lead Context)**:
   - You are the **Swarm Lead**. Never read raw C/C++/Rust source files, run raw `grep`/`rg`, write harnesses, or invoke compilers/fuzzers in your own context.
   - Coordinate **8 concurrent specialized workers** (`W1`–`W8`) strictly through `.ajar/REALITY.md`, `.ajar/WHITEBOARD.md`, `.ajar/STATUS.md`, `chain_weaver`, `autobuild` + Python `Input Encoder`, and Ring-0 `verify.py` (`C3`).
2. **Clean-Room Defensive Sanitizer Verification**:
   - Prove memory-safety or heap pixel-disclosure defects strictly via `ASan`, `UBSan`, or `MSan` stacktraces / canary-buffer checks in local test harnesses (`<= 64 KB` `.avif` inputs).

---

### 1. DOWNSTREAM ARCHITECTURE REALITY & BUILD PROFILES (PRE-SEED `.ajar/REALITY.md`)
1. **Chromium `blink::AVIFImageDecoder` Ground Truth (Chrome M131–M157+)**:
   - Chrome parses ISO-BMFF via `third_party/crabbyavif` (`google/CrabbyAvif` 1:1 Rust port of `libavif`), decodes AV1 OBUs via C/ASM **`dav1d`**, and converts/scales planes via C++/SIMD **`libyuv`**.
   - **Exact Shipped Chrome Flags**:
     - `decoder->ignoreXMP = AVIF_TRUE` and `decoder->ignoreExif = AVIF_TRUE` (**`src/exif.c` is UNREACHABLE in Chrome!**)
     - `decoder->strictFlags &= ~(AVIF_STRICT_CLAP_VALID | AVIF_STRICT_PIXI_REQUIRED)` (**Chrome disables strict `clap` & `pixi` checks, exposing paths rejected by default `avifdec`!**)
     - Incremental `avifIO` returning `AVIF_RESULT_WAITING_ON_IO` at arbitrary network chunk boundaries.
   - **Routing Tiers**:
     - **Tier-1A (Chrome Renderer VRP `$2k–$250k+`)**: Defects in 1-hop `dav1d`, 1-hop `libyuv`, or cross-seam/incremental/FFI logic reproduced in both `blink_avif_shim` (`libavif`) and `CrabbyAvif`.
     - **Tier-1B (Android `SkAvifCodec` / Python `Pillow >= 12.x` `_avif.c` / PHP `ext/gd` / `gdk-pixbuf`)**: Pure C memory-safety defects in `AOMediaCodec/libavif` (`src/{read,gainmap,sampletransform,reformat,scale,alpha,stream}.c`).
2. **Three Sanitizer Build Profiles (`W1` `autobuild`)**:
   - **Profile 1 (`asan-ubsan-blink-shim`)**: `clang`/`clang++` `-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer` linking local `dav1d` + `libyuv` + `blink_avif_shim.cc` (replicating exact `AVIFImageDecoder` flags + `WAITING_ON_IO` chunk cuts).
   - **Profile 2 (`msan`)**: `-fsanitize=memory -fsanitize-memory-track-origins=2` (`dav1d` `-Denable_asm=false`, `libyuv` `-DLIBYUV_DISABLE_X86=1`) to catch uninitialized heap pixel leaks (`CVE-2026-47247` class!).
   - **Profile 3 (`crabbyavif-asan` + `Pillow` downstream)**: Cross-language ASan parity check for Chrome Tier-1A + `Pillow` `Image.open().load()` check for Tier-1B.

---

### 2. EIGHT-WORKER SWARM TOPOLOGY (`W1`–`W8`)
- **`W1` (Sanitizer & Blink-Shim Steward)**: Builds Profiles 1–3, `blink_avif_shim.cc`, `.ajar/REALITY.md`, and runs `verify.py`.
- **`W2` (ISO-BMFF Container, Grid & Incremental `avifIO`)**: Audits `src/{read,stream,io,obu,properties}.c` (`iloc`, `ipco`/`ipma`, `iref` [`dimg`, `auxl`, `prem`, `sato`, `tmap`], `WAITING_ON_IO` resume).
- **`W3` (GainMap `tmap`, Sample Transforms `sato` & Crop/Orient)**: Audits `src/{gainmap,sampletransform,colr,colrconvert,scale}.c` (`clap` signed math, `irot`, `imir`).
- **`W4` (1-Hop `dav1d` Codec Seam & Tile Copy)**: Audits `src/codec_dav1d.c` <-> `dav1d` (`Dav1dPicture` 128-byte/`+64` stride alignment, `use_superres`, spatial layers, `avifDecoderCopyGridTile`).
- **`W5` (1-Hop `libyuv` SIMD Reformat, Alpha & `CrabbyAvif` Parity)**: Audits `src/{reformat,reformat_libyuv,alpha}.c` <-> `libyuv` row kernels <-> `CrabbyAvif` `src/decoder/` & `src/reformat/`.
- **`W6` (Backward Sink Abductor & `chain_weaver`)**: Posts backward `WISH` obligations (`buffer_geometry_mismatch`, `parser_offset_disagreement`, `lifetime_escape`, `residual_error_state`, `uninitialized_or_sentinel_propagation`).
- **`W7` (Python `Input Encoder` ISO-BMFF + AV1 OBU Microfuzzer)**: Authors deterministic bitpacking encoders (`emit(rng) -> bytes`) feeding `blink_avif_shim` under ASan/UBSan/MSan.
- **`W8` (Clean-Context Critic, Downstream Prover & Patch Author)**: Executes 5-stage `C3` proof + `CrabbyAvif`/`Pillow` downstream reachability + `gtest`/`FuzzTest` regression patch.

---

### 3. FIVE CROSS-SEAM HYPOTHESES (`L1`–`L5`) & `INPUT ENCODER` SPECS
1. **`L1` — Incremental `AVIF_RESULT_WAITING_ON_IO` State-Loss, Stale Plane Pointers & Heterogeneous Grid Tiles**: Suspension mid-grid or between progressive `a1lx`/`lsel` layers leaving uninitialized rows (MSan heap-pixel leak) or mismatched tile `depth`/`yuvFormat` in `avifDecoderCopyGridTile` (`enc_l1_incremental_grid.py`).
2. **`L2` — Chrome-Relaxed `~AVIF_STRICT_PIXI_REQUIRED & ~AVIF_STRICT_CLAP_VALID` vs. OBU Header Divergence & `tmap` GainMap**: `ispe`/`av1C` vs. decoded `dav1d` frame header mismatch across primary, `auxl` alpha, and ISO 21496-1 `tmap` items (`enc_l2_relaxed_strict_tmap.py`).
3. **`L3` — 1-Hop `dav1d` Stride Padding (`1024`-width `+64` pad), `use_superres` & `DecodeToYUV` Plane Copy**: Odd dimensions (`1x1`, `3x5`, `1024x1`) + `10`/`12`-bit stride discrepancies between `dav1d`, `libavif`, and Blink's `DecodedYUVWidthBytes` (`enc_l3_dav1d_stride.py`).
4. **`L4` — 1-Hop `libyuv` Bilinear Upsampling, `YCgCo_Re`/`YCgCo_Ro`, `16`-Bit & Alpha Premultiply Row OOB**: Odd-width SIMD row over-reads in `reformat_libyuv.c` / `libyuv` (`enc_l4_libyuv_matrix.py`).
5. **`L5` — `sato` 16-Bit Postfix Sample-Transform Evaluator (`src/sampletransform.c`) & `avifDecoderReset()` Lifetime**: Postfix stack/operator overflow, `INT32_MIN` shift/divide UB, mismatched `sato` input item grids, and stale state across `avifDecoderReset()` (`enc_l5_sato_reset.py`).

---

### 4. AUTONOMOUS STOPPING CRITERION (`TWO-TIER PINCER EXHAUSTION`)
Run autonomously (`@antigravity-continue`) until **EITHER**:
- **(A) `C3` Crown-Jewel Victory + Queue Drain**: At least one High/Critical ASan/MSan/UBSan memory-safety defect passes all **5 Ring-0 `verify.py` `C3` gates** (`3/3` pre-patch sanitizer reproduction on `blink_avif_shim`/`CrabbyAvif` [Tier-1A] or `Pillow`/`avifdec` [Tier-1B], minimal C/Rust patch + mandatory post-patch rebuild, `3/3` post-patch pass + `ctest` 100% green, and Cross-Family Critic approval) **AND** all high-priority chains on `.ajar/WHITEBOARD.md` are drained; **OR**
- **(B) `100%` Two-Tier Pincer Exhaustion**: `100%` of in-scope ISO-BMFF boxes/entrypoints mapped forward **AND** `100%` of allocation, lifetime, and pixel-copy sinks in `libavif` + 1-hop `dav1d`/`libyuv` seams backward-abduced with `file:line` `INVARIANT` or `DEAD_END` proofs in `.ajar/WHITEBOARD.md`.
