#!/usr/bin/env python3
"""Tests for process_graphics.py.

Zero-dependency (asserts only), invokes the worker as a subprocess the same
way SKILL.md does, and inspects the final stdout line (the JSON summary) and
the produced image files.

Run with the Pillow venv:
    /tmp/pg-venv/bin/python -m pytest .claude/skills/content/process-graphics/tests/test_process_graphics.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "process_graphics.py"


def check(name, got, want):
    assert got == want, f"{name}: got {got!r}, want {want!r}"


def run_worker(show_dir: Path, *extra_args: str):
    """Invoke the worker as a subprocess and parse the JSON summary it prints
    last on stdout (per SKILL.md: "Its final stdout line is a JSON
    summary — capture it"). The summary is pretty-printed (indent=2), so it
    spans multiple lines — find the last top-level "{" and parse to EOF."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(show_dir), *extra_args],
        capture_output=True, text=True,
    )
    lines = result.stdout.splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.strip() == "{"]
    assert starts, f"no JSON summary found in stdout:\n{result.stdout}\n(stderr: {result.stderr})"
    summary = json.loads("\n".join(lines[starts[-1]:]))
    return result, summary


def test_empty_input_schema_matches_normal_path():
    """A show with an empty IMAGES/Originals/ must still print a JSON summary
    with the SAME shape as the normal (non-empty) path. SKILL.md tells
    callers to do summary["optimized"]["converted"] unconditionally, so a
    schema drift here is a KeyError waiting to happen for any empty show."""
    with tempfile.TemporaryDirectory() as tmp:
        show = Path(tmp) / "empty-show"
        (show / "IMAGES" / "Originals").mkdir(parents=True)

        result, summary = run_worker(show)

        check("returncode", result.returncode, 0)
        check("optimized.converted", summary["optimized"]["converted"], 0)
        check("optimized.skipped", summary["optimized"]["skipped"], 0)
        check("optimized.error", summary["optimized"]["error"], 0)
        check("thumbnails.converted", summary["thumbnails"]["converted"], 0)
        check("thumbnails.skipped", summary["thumbnails"]["skipped"], 0)
        check("thumbnails.error", summary["thumbnails"]["error"], 0)
        assert "output" in summary, f"missing 'output' key: {summary}"
        assert "dry_run" in summary, f"missing 'dry_run' key: {summary}"


def test_jpg_alpha_composited_on_white_not_flattened_to_black():
    """A PNG with a fully-transparent region must not turn black in the JPEG
    export (bare .convert("RGB") flattens alpha to black) — it should
    composite onto a white background instead."""
    with tempfile.TemporaryDirectory() as tmp:
        show = Path(tmp) / "alpha-show"
        graphics = show / "graphics"
        graphics.mkdir(parents=True)

        # Opaque red on the left half, fully transparent on the right half.
        img = Image.new("RGBA", (100, 100), (200, 30, 30, 255))
        for x in range(50, 100):
            for y in range(100):
                img.putpixel((x, y), (200, 30, 30, 0))
        img.save(graphics / "test-title.png")

        # --resize-percent 100 keeps pixel coordinates predictable.
        result, summary = run_worker(
            show, "--allow-migrate", "--resize-percent", "100"
        )
        check("returncode", result.returncode, 0)
        check("optimized.converted", summary["optimized"]["converted"], 1)

        jpg_path = show / "IMAGES" / "Optimized" / "JPG" / "test-title.jpg"
        assert jpg_path.is_file(), f"expected JPG at {jpg_path}"

        out = Image.open(jpg_path).convert("RGB")
        r, g, b = out.getpixel((75, 50))  # was fully-transparent in the source
        assert r > 200 and g > 200 and b > 200, (
            f"transparent region flattened to non-white pixel: {(r, g, b)}"
        )


def test_dry_run_on_legacy_graphics_layout_does_not_crash():
    """Regression (GOTCHAS.md): --dry-run on a legacy graphics/ layout with no
    IMAGES/ yet used to crash — discovery looked in IMAGES/, which a dry run
    never creates. Dry-run must read the current location (graphics/), report
    the image as would-be-converted, and mutate nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        show = Path(tmp) / "legacy-show"
        graphics = show / "graphics"
        graphics.mkdir(parents=True)
        Image.new("RGB", (50, 50), (10, 20, 30)).save(graphics / "legacy-title.png")

        result, summary = run_worker(show, "--dry-run")

        check("returncode", result.returncode, 0)
        assert graphics.is_dir(), "graphics/ should be left intact by --dry-run"
        assert [p.name for p in graphics.iterdir()] == ["legacy-title.png"], (
            "graphics/ contents should be untouched by --dry-run"
        )
        assert not (show / "IMAGES").exists(), "--dry-run must not create IMAGES/"
        check("optimized.converted", summary["optimized"]["converted"], 1)
        check("optimized.error", summary["optimized"]["error"], 0)


def test_invalid_json_config_exits_with_friendly_message():
    """A malformed show-config.json must produce a friendly sys.exit naming
    the offending file, not a raw traceback — config errors are read by
    non-technical producers, not developers."""
    with tempfile.TemporaryDirectory() as tmp:
        show = Path(tmp) / "bad-config-show"
        show.mkdir(parents=True)
        (show / "show-config.json").write_text("{ not valid json ")

        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(show), "--dry-run"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0, "invalid config should exit non-zero"
        assert "show-config.json" in result.stderr, (
            f"error should name the offending file, got stderr: {result.stderr!r}"
        )
        assert "Traceback" not in result.stderr, (
            f"error should be a friendly message, not a traceback:\n{result.stderr}"
        )


def test_non_dict_thumbnail_config_exits_with_friendly_message():
    """A show-config.json with a non-dict 'thumbnail' value must produce a
    friendly sys.exit naming the offending file, not a raw TypeError
    traceback."""
    with tempfile.TemporaryDirectory() as tmp:
        show = Path(tmp) / "bad-thumbnail-show"
        show.mkdir(parents=True)
        (show / "show-config.json").write_text(json.dumps({"thumbnail": "not-an-object"}))

        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(show), "--dry-run"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0, "invalid config should exit non-zero"
        assert "show-config.json" in result.stderr, (
            f"error should name the offending file, got stderr: {result.stderr!r}"
        )
        assert "Traceback" not in result.stderr, (
            f"error should be a friendly message, not a traceback:\n{result.stderr}"
        )


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok  {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
