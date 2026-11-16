# PBS Wisconsin — Claude Skills Marketplace

> [!WARNING]
> **Sunsetting. Don't add new work here.** This marketplace is being replaced by the PBS Wisconsin domain marketplace (pbswi-ops#90). It still delivers `pbswi-content` and `process-graphics` until the cutover in skill-ops#484. Use **[`pbswi-skills`](https://github.com/public-media-work/pbswi-skills)** instead.
> See the [sunset registry](https://github.com/mriechers/skill-ops/blob/master/docs/sunset-registry.md) and [skill-ops ADR 0014](https://github.com/mriechers/skill-ops/blob/master/docs/adr/0014-one-domain-marketplace-per-domain.md).

Proven [Claude Code](https://claude.com/claude-code) skills for digital production work at PBS Wisconsin, vetted and tested by us and shared openly for the public media ecosystem.

## Add this marketplace

```
claude plugin marketplace add public-media-work/pbswi-claude-skills
```

Then browse and install bundles with `claude plugin install`.

## Contents

- **pbswi-content** — content-production skills.
  - **process-graphics** — turn a show's raw graphics into web-ready outputs: scaffolds the `IMAGES/{Originals,Optimized}` tree, generates resized JPG + lossless WebP, and cuts square portrait crops. Pillow-only (no ImageMagick), so it runs anywhere Claude runs, including Claude Desktop. Per-show configurable.

More skills graduate here over time.
