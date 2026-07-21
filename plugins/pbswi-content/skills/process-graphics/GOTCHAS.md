# Gotchas — process-graphics (portable build)

Running log of mistakes this skill has made. Each entry should be specific enough that a future session can spot the pattern and avoid it.

---

- **`--dry-run` on a legacy `graphics/` layout used to crash.** Discovery looked in `IMAGES/`, which a dry run never creates. Fixed: dry-run reads the current location (`graphics/`) and `find_images` tolerates a missing directory. Don't reintroduce an unconditional `IMAGES/` assumption.
