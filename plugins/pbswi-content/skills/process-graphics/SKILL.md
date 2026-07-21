---
name: process-graphics
description: Prep a PBS Wisconsin Education show's raw graphics into web-ready outputs — scaffolds the IMAGES/Originals|Optimized folder tree, generates resized JPG + lossless WebP, and creates square crops for host/guest portraits. Settings (resize %, JPG quality, crop size, which files get cropped) are per-show and default to The Look Back. Pillow-only, so it runs in Claude Desktop with no extra installs. Triggers on "process graphics", "prep show images", "optimize the graphics pack", "make web-ready images for <show>".
---

Prep a PBS Wisconsin Education show's raw graphics into web-ready outputs.

The heavy lifting (folder scaffolding, resize, format conversion, square cropping) is done by `scripts/process_graphics.py`, which needs only **Pillow** — no compiled image-conversion binaries, no macOS-native tools — so it runs anywhere, including Claude Desktop's sandbox.

## When to use

- Raw PNGs are sitting in `<show>/graphics/` or `<show>/IMAGES/Originals/` and need to become web-ready
- You need to regenerate just the square crops or re-run after adding a few images (the pipeline is idempotent — re-running only makes missing pieces)

## What it produces

```
<show-folder>/
  IMAGES/
    Originals/          ← raw PNGs (input; never modified)
    Optimized/
      JPG/              ← resized, quality 90
      WebP/             ← resized, lossless
        *-small.webp    ← 144×144 square crops for host/guest portraits
```

## Per-show configuration

Every value that varies between shows is a **setting**, not a hardcoded constant. Settings resolve in this order (each layer overrides the one before):

1. **Built-in defaults** — The Look Back's values: 50% resize, JPG quality 90, 144px crops for `host`/`guest` files
2. **`<show-folder>/show-config.json`** — a per-show file that travels with the show folder
3. **`--config FILE`** — an explicitly chosen config
4. **Individual CLI flags** — `--resize-percent`, `--jpg-quality`, `--thumb-size`

So **The Look Back works with zero configuration.** A different show either drops a `show-config.json` in its folder (copy `config/_new-show-template.json`) or is run with `--config`. See `config/the-look-back.json` for the canonical example.

Preview the effective settings any time with `--print-config`.

## Steps

1. **Determine the show folder** from `$ARGUMENTS`. If empty, ask the user. If the path points at a subfolder (e.g. `.../the-look-back-ep3/graphics`), use its parent as the show folder.

2. **Preview first (recommended).** Run with `--dry-run` and show the user what will happen — nothing is changed:

   ```bash
   python3 scripts/process_graphics.py "<show-folder>" --dry-run
   ```

   (`scripts/process_graphics.py` is relative to this skill's own directory.)

3. **Confirm destructive moves.** If the output says it will migrate a legacy `graphics/` → `IMAGES/`, surface that to the user before proceeding — that rename needs the `--allow-migrate` flag.

4. **Run the pipeline.**

   ```bash
   python3 scripts/process_graphics.py "<show-folder>" [--allow-migrate]
   ```

   The script detects layout, scaffolds folders, collects loose originals, resizes each Original (→ lossless WebP + q90 JPG, skipping any already done), and makes a 144×144 square crop for each `host`/`guest` file. Its final stdout line is a JSON summary — capture it.

5. **Report to the user:** N originals processed (converted vs skipped), N square crops, output path, any errors.

6. **(Optional) Alt text.** Accessibility descriptions are a *separate* skill (`/alt-text`) and are not required to produce the web-ready images. If it's available, the script prints the exact follow-up command. Do not reimplement alt text here.

## Arguments

| Input / flag | Behavior |
|---|---|
| `<show-folder>` | The folder containing `IMAGES/` or `graphics/`. |
| `<show-folder>/graphics` | Tolerated — the script uses the parent. |
| `--dry-run` | Preview only; change nothing. |
| `--allow-migrate` | Permit renaming legacy `graphics/` → `IMAGES/`. |
| `--config FILE` | Use this show-config.json. |
| `--resize-percent N` / `--jpg-quality N` / `--thumb-size N` | One-off overrides. |
| `--print-config` | Print the resolved settings and exit. |
| *(empty)* | Ask the user for the show folder. |

## Idempotency

Re-running on a finished show is safe: an `Optimized/JPG` + `Optimized/WebP` pair that already exists is not re-converted, and a `*-small.webp` that exists is not regenerated. Originals are never moved (except the one-time legacy `graphics/`→`IMAGES/` migration) or modified.

## Notes

- SVGs are skipped (vector art can't be rasterized).
- EXIF orientation is respected, so rotated photos come out upright.
- This is the portable, config-driven build of the internal `process-graphics` skill. The PBS folder convention and host/guest cropping are intentionally preserved; only the hardcoded path and the compiled image-conversion dependency were removed for Claude Desktop portability.
