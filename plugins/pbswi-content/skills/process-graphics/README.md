# process-graphics — image prep for PBS Education shows

A Claude skill that turns a show's raw graphics into web-ready images: it builds the
`IMAGES/Originals | Optimized` folder tree, makes 50%-resized **JPG + WebP** copies, and
cuts **144×144 square crops** for host/guest portraits. Built for **The Look Back**, and
configurable per show.

It's a portable build — the only dependency is **Pillow** — so it runs inside **Claude
Desktop** with nothing to install on your machine.

## What's in here

```
process-graphics/
  SKILL.md                       ← the skill Claude reads
  GOTCHAS.md
  scripts/process_graphics.py    ← the worker (Pillow only)
  config/
    the-look-back.json           ← documentation/copy-template example (see below)
    _new-show-template.json      ← copy this to set up a different show
```

## Install in Claude Desktop

1. Zip this whole `process-graphics/` folder.
2. In Claude Desktop → **Settings → Capabilities → Skills** → add the skill (upload the zip
   or drop the folder into your skills directory).
3. That's it — Pillow is typically available in Claude's code environment already; if not,
   `pip install Pillow`. Nothing to `brew` install.

> **Using Claude Code instead?** Copy `process-graphics/` into `~/.claude/skills/` and, if
> Pillow isn't present, `python3 -m pip install Pillow`. Everything else is identical.

## Use it (The Look Back)

Point Claude at the show folder — the one that contains `graphics/` or `IMAGES/`:

```
Process the graphics for this show: /path/to/the-look-back-ep3
```

Claude will preview first (a dry run), ask before any folder rename, then produce the
optimized JPG/WebP and the host/guest square crops. Re-running later is safe — it only
fills in what's missing.

You can also run the worker directly:

```bash
# preview — changes nothing
python3 scripts/process_graphics.py /path/to/the-look-back-ep3 --dry-run

# do it (allow the one-time graphics/ -> IMAGES/ rename if needed)
python3 scripts/process_graphics.py /path/to/the-look-back-ep3 --allow-migrate
```

## Settings, and a different show

The Look Back needs **no configuration** — its values are the built-in defaults
(50% resize, JPG quality 90, 144px crops for files with `host` or `guest` in the name).

To check what's in effect:

```bash
python3 scripts/process_graphics.py /path/to/show --print-config
```

For a different show, copy `config/_new-show-template.json` to `show-config.json` **inside
that show's folder** and edit the values — the skill picks it up automatically. Or pass
`--config path/to/that-show.json`. Quick one-offs: `--resize-percent`, `--jpg-quality`,
`--thumb-size`.

## What it does NOT do

- **Alt text** — accessibility descriptions are a separate `/alt-text` skill, not bundled
  here. The web-ready images are complete without it; the script just prints the follow-up
  command if you want it.
- **Video** — image-only.
- **Renaming your files** — filenames are kept as delivered (it handles both `host` and
  `guest` labels).

## Requirements

- Python 3.9+ and Pillow (`pip install Pillow`). Nothing else.
