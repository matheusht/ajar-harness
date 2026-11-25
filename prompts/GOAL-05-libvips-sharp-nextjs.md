/goal
@antigravity-continue
# Ajar v3.6-Balanced Flagship Autonomous Swarm-Lead Charter
## Target #5 (Tier 3 Flagship): `libvips` (+ 1-Hop `sharp-libvips` Codecs) -> `lovell/sharp` -> `Next.js` (`/_next/image` & `next/og`) / Vercel / Cloudflare Pipeline

### 0. GOVERNANCE, SAFETY & PURE CONDUCTOR LAW (NON-NEGOTIABLE)
1. **Pure Conductor Mandate (`0` Direct Code Work | `< 25%` Lead Context)**:
   - You are the **Swarm Lead**. Never edit source files, compile binaries, or run raw `grep`/`rg` searches in your own context.
   - Coordinate **8 concurrent specialist workers** (`W1`–`W8`, including dedicated `W8` `DOWNSTREAM_PROVER`) strictly via `.ajar/REALITY.md`, `.ajar/WHITEBOARD.md`, `.ajar/STATUS.md`, `chain_weaver`, `autobuild` + Python `Input Encoder`, and Ring-0 `verify.py` (`C3`).
2. **Clean-Room Sanitizer & Local Conformance Verification**:
   - All testing runs offline locally under `ASan`/`UBSan`, `MSan` (for heap-memory pixel disclosure into transcoded `.webp`/`.avif`/`.png` outputs!), and `TSan` (`VipsThreadpool` concurrency), using minimal spec-structured fixtures (`<= 64x64` nominal geometry unless testing header dimension guards).

---

### 1. BUILD-PROFILE TRUTH GATE (PRE-SEED `.ajar/REALITY.md` — CRITICAL!)
Default npm deployments (`Next.js 15.5.28+ / 16.4.1+` -> `sharp 0.35.5` -> `@img/sharp-libvips v1.3.4` / `libvips 8.18.x`) ship a specific compiled loader set:
- **IN-SCOPE FOR DEFAULT `sharp` / `Next.js` STAGE B PROOF**:
  - `libvips` core (`foreign.c`, `region.c`, `sinkdisc.c`, `threadpool.c`, `sequential.c`, `colour/icc_transform.c`, `foreign/exif.c`).
  - **PNG**: `pngload_buffer` (`libpng` + `zlib-ng` + `libimagequant` — migrated off `libspng`).
  - **JPEG + UltraHDR GainMap**: `jpegload_buffer` (`mozjpeg`) + **`uhdrload_buffer` (`libultrahdr` ISO 21496-1 gain-map decoder!)**.
  - **AVIF / HEIF**: `heifload_buffer` (`libheif` + **`libaom` AV1 ONLY**; container boxes parsed for all `heif_magic` brands, **no `dav1d`**, **no `libde265` HEVC** in prebuilt npm `sharp`).
  - **WebP**: `webpload_buffer` (`libwebp` + `libwebpdemux`).
  - **GIF**: `gifload_buffer` (in-tree `libnsgif` + `cgif`).
  - **TIFF**: `tiffload_buffer` (`libtiff` nesting Deflate, `mozjpeg`, and `libwebp` strip/tile sub-codecs!).
  - **SVG / SVGZ**: `svgload_buffer` (`librsvg` + `libxml2` + `cairo`/`pango` — note: `/_next/image` blocks `image/svg+xml` via `BYPASS_TYPES` by default, whereas **`next/og` (`ImageResponse` on Node)** passes SVG directly to `sharp()`, and any sniffer divergence between Next.js `detectContentType()` and `vips_foreign_find_load_buffer()` bypasses `BYPASS_TYPES`!).
  - **Color / EXIF / SIMD**: `lcms2`, `libexif`, `highway`.
- **MARK `DISTRO_ONLY` (Excluded from Default `sharp` npm Prebuilds)**:
  - `magickload`, `pdfload` (`poppler`/`pdfium`), `openslideload`, `jp2kload`, `jxlload`, `exrload`, `libde265`. (Track `DISTRO_ONLY` only if verifying Docker/Debian `apt install libvips42` deployments; Stage B requires an IN-SCOPE `sharp-libvips` path!)

---

### 2. THREE-LAYER LOCAL SANITIZER ENVIRONMENT & 8-WORKER TOPOLOGY
- **`W1` (`SANDBOX_BUILDER` & `REALITY_MAPPER`)**: Builds (1) `libvips` + 1-hop `sharp-libvips` deps with `ASan+UBSan` (and a second tree with `TSan` / `MSan`), (2) `lovell/sharp --build-from-source` linked against instrumented `libvips`, and (3) isolated local `Next.js` `imageOptimizerTransform()` (`failOn: 'none'`, `.rotate().resize().webp()/.avif()`) + `wasm-vips` Cloudflare/Edge worker harness.
- **`W2` (`FOREIGN_SNIFFER_AUDITOR`)**: Audits Next.js `detectContentType` + `BYPASS_TYPES` vs. `libvips/foreign/foreign.c` (`vips_foreign_find_load_buffer`, `vips_foreign_load_iscompat` header-vs-load `Xsize`/`Ysize`/`Bands`/`BandFmt` check) and `svgload.c` (`SVG_HEADER_SIZE = 1000` gzip/UTF-8 window).
- **`W3` (`CONTAINER_CODEC_AUDITOR`)**: Audits `heifload.c` + `libheif`/`libaom` (grid/alpha `m_storage` channel views, `8`-bit `UCHAR` vs `>8`-bit `USHORT` promotion, thumbnail switching, 4-byte Exif `memmove`) and `uhdrload.c` + `libultrahdr`.
- **`W4` (`STRIP_TILE_AUDITOR`)**: Audits `tiff2vips.c` + `libtiff` (nested JPEG/WebP/Deflate strip/tile geometry vs `VIPS_REGION_LSKIP`), `pngload.c`, `jpeg2vips.c`, `webpload.c`, and `libnsgif`.
- **`W5` (`CONCURRENCY_COLOR_AUDITOR`)**: Audits `iofuncs/{region,sinkdisc,threadpool,sequential}.c` under `failOn: 'none'` mid-stream errors + `icc_transform.c` (`lcms2`) & `vips_autorot` (`exif.c`) dimension transposes.
- **`W6` (Backward Sink Abductor & `chain_weaver`)**: Pairs canonical `EffectType`s (`parser_offset_disagreement`, `buffer_geometry_mismatch`, `lifetime_escape`, `residual_error_state`, `uninitialized_or_sentinel_propagation`, `policy_alias_divergence`) across all 3 layers.
- **`W7` (Python `Input Encoder` Microfuzzer)**: Builds deterministic `emit(rng) -> bytes` encoders for ISO-BMFF/AVIF grid+alpha, UltraHDR JPEG, nested-codec multi-strip TIFF, SVG/SVGZ 1000-byte boundary, and ICC+EXIF carriers.
- **`W8` (`DOWNSTREAM_PROVER` & `C3` Patch Engineer)**: Executes mandatory **Two-Stage `C3` Verification** + authors minimal C/Rust patch.

---

### 3. MANDATORY TWO-STAGE `C3` CROWN-JEWEL PROOF
No finding reaches `C3` unless **BOTH Stage A and Stage B** pass deterministically:
1. **Stage A (Native `libvips`/Codec Root Cause + Rebuild Patch)**: `3/3` deterministic `ASan`/`UBSan`/`MSan`/`TSan` failure (including heap-memory pixel leak check in output image bytes!) on unpatched `libvips`/codec -> minimal upstream C/Rust patch -> mandatory `.ajar/build.sh` rebuild -> `3/3` pass + `meson test` green + Cross-Family Critic approval.
2. **Stage B (End-to-End `sharp` + `Next.js` / Edge Default-Config Proof)**: Exact same image payload fed into unmodified `Next.js` `imageOptimizerTransform()` (`/_next/image` default `NextConfig`: `dangerouslyAllowSVG: false`, `limitInputPixels: 268402689`, `failOn: 'none'`) and/or `sharp(buf).rotate().resize(640).webp()` triggers the defect pre-patch and produces clean output (`0` sanitizer errors) when rebuilt against the Stage A patch!

---

### 4. AUTONOMOUS STOPPING CRITERION (`TWO-TIER PINCER EXHAUSTION`)
Run autonomously (`@antigravity-continue`) until **EITHER**:
- **(A) Two-Stage `C3` Crown-Jewel Victory + Queue Drain**: At least one High/Critical memory-safety or heap-pixel-disclosure defect passes **both Stage A and Stage B `C3` gates** **AND** all high-priority cross-layer chains on `.ajar/WHITEBOARD.md` are drained; **OR**
- **(B) `100%` Two-Tier Pincer Exhaustion**: `100%` of `sharp-libvips`-enabled `VipsForeignLoad` entrypoints x Next.js `detectContentType` gates mapped forward **AND** `100%` of `VIPS_REGION_ADDR`, codec buffer, `lcms2`, and `VipsThreadpool` sinks backward-abduced with verified `file:line` `INVARIANT` or `DEAD_END` proofs in `.ajar/WHITEBOARD.md`.
