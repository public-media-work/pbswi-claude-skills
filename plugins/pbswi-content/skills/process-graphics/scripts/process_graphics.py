#!/usr/bin/env python3
"""process-graphics — prep a PBS Wisconsin Education show's raw graphics into
web-ready outputs.

This is a Pillow-only port of the original bash + compiled-image-tool skill, so
it runs anywhere Python runs — including Claude Desktop's code sandbox — with
no Homebrew, no external binaries. The one dependency is Pillow
(``pip install Pillow``), which the sandbox already has.

Pipeline (all steps idempotent — safe to re-run; only missing pieces are made):
  1. detect layout: ``<show>/IMAGES`` (canonical) or ``<show>/graphics`` (legacy)
  2. migrate ``graphics/`` -> ``IMAGES/`` if legacy (needs --allow-migrate)
  3. scaffold ``IMAGES/Originals`` + ``IMAGES/Optimized/{JPG,WebP}``
  4. collect any loose top-level images into ``Originals/``
  5. per Original: resize to ``resize_percent`` %, write lossless WebP + quality JPG
  6. per Original whose name matches a thumbnail pattern: NxN centered square WebP
  7. print a summary + the ``/alt-text`` next step

── Per-show configuration ──────────────────────────────────────────────────────
Every knob that varies between shows is a setting, not a constant. Settings
resolve in this order (each layer overrides the one before):

  1. built-in defaults        (The Look Back's values: 50% / q90 / 144px / host,guest)
  2. <show-folder>/show-config.json   (per-show file that travels with the show)
  3. --config FILE            (an explicitly chosen config)
  4. individual CLI flags     (--resize-percent, --jpg-quality, --thumb-size, ...)

So The Look Back works with zero configuration. A different show either drops a
``show-config.json`` in its folder or passes ``--config path/to/that-show.json``.

Config file schema (all keys optional; omitted keys inherit the layer below):
  {
    "show": "The Look Back",
    "resize_percent": 50,
    "jpg_quality": 90,
    "thumbnail": { "size": 144, "match": ["host", "guest"], "suffix": "-small" }
  }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Pillow is required. Install it with:  python3 -m pip install Pillow")

# Newer Pillow (>= 9.1) moved resampling filters under Image.Resampling.
try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:  # older Pillow
    RESAMPLE = Image.LANCZOS

# Raster formats Pillow can decode. SVG is intentionally excluded — it is vector
# art and cannot be rasterized by Pillow.
RASTER_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

# ── built-in defaults (layer 1) — these are The Look Back's settings ────────────
DEFAULT_CONFIG = {
    "show": "The Look Back",
    "resize_percent": 50,
    "jpg_quality": 90,
    "thumbnail": {"size": 144, "match": ["host", "guest"], "suffix": "-small"},
}


# ── config resolution ──────────────────────────────────────────────────────────
def _merge(base: dict, override: dict) -> dict:
    """Shallow-merge, recursing one level into the 'thumbnail' sub-dict."""
    out = dict(base)
    for key, val in override.items():
        if key == "thumbnail" and isinstance(val, dict):
            out["thumbnail"] = {**base.get("thumbnail", {}), **val}
        else:
            out[key] = val
    return out


def _read_json_config(path: Path) -> dict:
    """Parse a config file, turning a malformed one into a friendly
    ``sys.exit`` naming the file instead of a raw traceback — config errors
    are read by non-technical producers, not developers."""
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"invalid config in {path}: {exc}")


def _validate_thumbnail(cfg: dict, path: Path) -> None:
    """A 'thumbnail' key that isn't an object would otherwise surface as a
    raw TypeError the first time the code indexes into it. Catch it right
    after the layer that introduced it so the message names the file."""
    if not isinstance(cfg.get("thumbnail"), dict):
        sys.exit(
            f"invalid config in {path}: 'thumbnail' must be an object, "
            f"got {type(cfg['thumbnail']).__name__}"
        )


def load_config(show: Path, config_flag: str | None, cli_overrides: dict) -> dict:
    """Resolve settings across all four layers (later layers win)."""
    cfg = dict(DEFAULT_CONFIG)

    show_local = show / "show-config.json"
    if show_local.is_file():
        cfg = _merge(cfg, _read_json_config(show_local))
        _validate_thumbnail(cfg, show_local)

    if config_flag:
        config_path = Path(config_flag).expanduser()
        cfg = _merge(cfg, _read_json_config(config_path))
        _validate_thumbnail(cfg, config_path)

    if cli_overrides:
        cfg = _merge(cfg, cli_overrides)

    return cfg


# ── discovery ──────────────────────────────────────────────────────────────────
def find_images(folder: Path) -> list[Path]:
    """Raster images directly in ``folder`` (non-recursive). Empty if it's absent."""
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file()
        and p.suffix.lower() in RASTER_EXTS
        and not p.name.startswith(".")
    )


def gather_originals(images: Path) -> list[Path]:
    """All source images: those already in Originals/ plus any loose at the
    IMAGES/ top level (which a real run moves into Originals/ first, but a
    --dry-run leaves in place — so we count them either way)."""
    return find_images(images / "Originals") + find_images(images)


# ── image operations (Pillow) ──────────────────────────────────────────────────
def load_oriented(path: Path) -> "Image.Image":
    """Open, applying EXIF orientation so rotated photos come out upright."""
    return ImageOps.exif_transpose(Image.open(path))


def resized(img: "Image.Image", percent: int) -> "Image.Image":
    if percent == 100:
        return img.copy()
    w, h = img.size
    nw, nh = max(1, round(w * percent / 100)), max(1, round(h * percent / 100))
    return img.resize((nw, nh), RESAMPLE)


def save_jpg(img: "Image.Image", dest: Path, quality: int) -> None:
    # JPEG has no alpha channel. A bare .convert("RGB") on a transparent
    # source discards the alpha and keeps whatever RGB values sat underneath
    # it — often black, sometimes worse (arbitrary leftover color) — which
    # shows up as fringing on PBS title cards/logos delivered as PNGs with
    # alpha. Composite onto white first so transparent regions come out white.
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        out = background
    else:
        out = img.convert("RGB")
    out.save(dest, "JPEG", quality=quality, optimize=True)


def save_webp_lossless(img: "Image.Image", dest: Path) -> None:
    img.save(dest, "WEBP", lossless=True)


# ── pipeline steps ──────────────────────────────────────────────────────────────
def detect_layout(show: Path) -> str:
    if (show / "IMAGES").is_dir():
        return "IMAGES"
    if (show / "graphics").is_dir():
        return "graphics"
    return "none"


def scaffold(images: Path) -> None:
    (images / "Originals").mkdir(parents=True, exist_ok=True)
    (images / "Optimized" / "JPG").mkdir(parents=True, exist_ok=True)
    (images / "Optimized" / "WebP").mkdir(parents=True, exist_ok=True)


def collect_originals(images: Path, dry_run: bool, log) -> int:
    """Move loose top-level images (dumped at IMAGES/ level) into Originals/."""
    if not images.is_dir():
        return 0
    moved = 0
    for f in find_images(images):
        log(f"  collect loose original: {f.name} -> Originals/")
        if not dry_run:
            f.rename(images / "Originals" / f.name)
        moved += 1
    return moved


def process_one(src: Path, optimized: Path, cfg: dict, dry_run: bool, log) -> str:
    base = src.stem
    jpg_out = optimized / "JPG" / f"{base}.jpg"
    webp_out = optimized / "WebP" / f"{base}.webp"
    if jpg_out.exists() and webp_out.exists():
        log(f"  skip (already optimized): {base}")
        return "skipped"
    if dry_run:
        log(f"  would optimize: {base}")
        return "converted"
    try:
        small = resized(load_oriented(src), cfg["resize_percent"])
        if not webp_out.exists():
            save_webp_lossless(small, webp_out)
        if not jpg_out.exists():
            save_jpg(small, jpg_out, cfg["jpg_quality"])
        log(f"  optimized: {base}")
        return "converted"
    except Exception as exc:  # noqa: BLE001 — report and keep going on the batch
        log(f"  error: {base}: {exc}", err=True)
        return "error"


def thumb_one(src: Path, optimized: Path, cfg: dict, dry_run: bool, log) -> str:
    thumb = cfg["thumbnail"]
    size, suffix = thumb["size"], thumb.get("suffix", "-small")
    dest = optimized / "WebP" / f"{src.stem}{suffix}.webp"
    if dest.exists():
        log(f"  skip square crop (exists): {src.stem}{suffix}")
        return "skipped"
    if dry_run:
        log(f"  would square-crop: {src.stem}{suffix} ({size}x{size})")
        return "converted"
    try:
        square = ImageOps.fit(load_oriented(src), (size, size), RESAMPLE, centering=(0.5, 0.5))
        save_webp_lossless(square, dest)
        log(f"  square crop: {src.stem}{suffix} ({size}x{size})")
        return "converted"
    except Exception as exc:  # noqa: BLE001
        log(f"  error (thumb): {src.stem}: {exc}", err=True)
        return "error"


def wants_thumbnail(name: str, patterns: list[str]) -> bool:
    low = name.lower()
    return any(pat.lower() in low for pat in patterns)


def build_summary(
    cfg: dict,
    optimized: Path,
    images: int,
    counts: dict,
    tcounts: dict,
    dry_run: bool,
) -> dict:
    """The single JSON-summary schema printed on stdout's final line, shared
    by every code path (including the "no source images" early return) so
    they can't drift apart. SKILL.md tells callers to parse this and read
    summary["optimized"]["converted"] unconditionally."""
    return {
        "show": cfg.get("show"),
        "output": str(optimized),
        "images": images,
        "optimized": counts,
        "thumbnails": tcounts,
        "dry_run": dry_run,
    }


# ── main ─────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Prep a PBS Education show's raw graphics into web-ready JPG + WebP (Pillow only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("show", nargs="?", help="the show folder (contains IMAGES/ or graphics/)")
    ap.add_argument("--config", help="path to a show-config.json (overrides <show>/show-config.json)")
    ap.add_argument("--resize-percent", type=int, help="override: resize to this percent")
    ap.add_argument("--jpg-quality", type=int, help="override: JPEG quality 1-100")
    ap.add_argument("--thumb-size", type=int, help="override: square crop size in px")
    ap.add_argument("--allow-migrate", action="store_true",
                    help="permit renaming legacy graphics/ -> IMAGES/ (a destructive move)")
    ap.add_argument("--dry-run", action="store_true", help="print what would happen; change nothing")
    ap.add_argument("--print-config", action="store_true",
                    help="resolve + print the effective settings for the show, then exit")
    args = ap.parse_args()

    if not args.show:
        ap.error("a show folder is required (the folder containing IMAGES/ or graphics/)")
    show = Path(args.show.rstrip("/")).expanduser().resolve()
    if not show.is_dir():
        sys.exit(f"not a directory: {show}")

    cli_overrides: dict = {}
    if args.resize_percent is not None:
        cli_overrides["resize_percent"] = args.resize_percent
    if args.jpg_quality is not None:
        cli_overrides["jpg_quality"] = args.jpg_quality
    if args.thumb_size is not None:
        cli_overrides["thumbnail"] = {"size": args.thumb_size}

    cfg = load_config(show, args.config, cli_overrides)

    if args.print_config:
        print(json.dumps(cfg, indent=2))
        return

    def log(msg: str, err: bool = False) -> None:
        print(msg, file=sys.stderr if err else sys.stdout)

    log(f"show: {cfg.get('show', '(unnamed)')}")
    log(f"settings: resize={cfg['resize_percent']}%  jpg_q={cfg['jpg_quality']}  "
        f"thumb={cfg['thumbnail']['size']}px match={cfg['thumbnail']['match']}")

    # 1-2. layout detect / migrate. `images` is where the show's images live now:
    # a real run migrates legacy graphics/ -> IMAGES/ first; a --dry-run reads the
    # current location (graphics/) so the preview still finds the files.
    layout = detect_layout(show)
    if layout == "graphics":
        if (show / "IMAGES").is_dir():
            sys.exit("both graphics/ and IMAGES/ exist — refusing to migrate, resolve manually")
        if not args.allow_migrate and not args.dry_run:
            sys.exit("legacy graphics/ found — re-run with --allow-migrate to rename it to IMAGES/")
        log(f"migrate: {show}/graphics -> {show}/IMAGES")
        if args.dry_run:
            images = show / "graphics"
        else:
            (show / "graphics").rename(show / "IMAGES")
            images = show / "IMAGES"
    else:
        if layout == "none":
            log("no IMAGES/ or graphics/ found — creating IMAGES/ scaffold")
        images = show / "IMAGES"

    if not args.dry_run:
        scaffold(images)
    collect_originals(images, args.dry_run, log)

    optimized = images / "Optimized"
    originals = gather_originals(images)
    if not originals:
        log(f"no source images in {images}/Originals — nothing to do")
        empty_counts = {"converted": 0, "skipped": 0, "error": 0}
        print(json.dumps(
            build_summary(cfg, optimized, 0, empty_counts, dict(empty_counts), args.dry_run),
            indent=2,
        ))
        return

    log(f"\nfound {len(originals)} source image(s) in Originals/\n\n── resize + convert ──")
    counts = {"converted": 0, "skipped": 0, "error": 0}
    for src in originals:
        counts[process_one(src, optimized, cfg, args.dry_run, log)] += 1

    log("\n── square crops (portraits) ──")
    tcounts = {"converted": 0, "skipped": 0, "error": 0}
    for src in originals:
        if wants_thumbnail(src.name, cfg["thumbnail"]["match"]):
            tcounts[thumb_one(src, optimized, cfg, args.dry_run, log)] += 1

    log("\n── summary ──")
    log(f"resize/convert: {counts['converted']} converted, {counts['skipped']} skipped, {counts['error']} errors")
    log(f"square crops:   {tcounts['converted']} created, {tcounts['skipped']} skipped, {tcounts['error']} errors")
    log(f"\noutput: {optimized}")
    log(f"next: run /alt-text on {optimized}/WebP with --source-dir {images}/Originals  (optional, separate skill)")

    # machine-readable summary on stdout's final line
    print(json.dumps(
        build_summary(cfg, optimized, len(originals), counts, tcounts, args.dry_run),
        indent=2,
    ))

    if counts["error"] or tcounts["error"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
