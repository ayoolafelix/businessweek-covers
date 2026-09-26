# Businessweek Cover Archive, 1931–1961

**1,592 covers**, every Businessweek issue available from the Internet
Archive's `pub_business-week` microfilm collection, as an infinite draggable
WebGL grid.

## Provenance

Businessweek has no public issue-page pattern the way The New Yorker does, and
`bloomberg.com/businessweek` returns 403 to scripted requests. The archive.org
microfilm donation is the only bulk source:

- Covers are page 1 of each scan, served individually by archive.org's
  BookReader page service — the 23–58 MB PDFs are never downloaded whole.
- OCR text is pulled with a `Range` request for the first few KB, which is all
  the cover text occupies. The full `_djvu.txt` is ~466 KB per issue, so this
  saves roughly 750 MB of transfer.
- The source is `_djvu.txt`-derived and therefore noisy; the grid uses the
  `contain()` path in its fragment shader so no cover is ever cropped.

### Known limits, stated rather than hidden

- **Coverage stops at 1961-12-30.** The microfilm run was donated up to that
  point. 1962–2008 (McGraw-Hill) and 2009 onward (Bloomberg L.P.) are not
  available from it.
- **4 of 1,596 validated issues have no renderable files** and are absent, so
  the archive holds 1,592.
- **No cover credits.** The `_djvu.txt` OCR does contain the printed credit
  line, and a parser recovered it on some issues, but the text is too degraded
  to ship: 1950s covers yield "E-Z-Paintr's Touchett" (really E.Z. Paint'r)
  while others return rotated masthead noise like "HOIN HOEUY NNVY". The
  pane shows cover and date only rather than guessed attributions.

## Grid

Ported from the New Yorker archive build. Rigid lattice, one offset drives
every cell, so row alignment, uniform spacing and full-bleed coverage are
structural rather than tuned. Parallax is a bounded per-column lead/lag capped
at 30% of a row, with luminance and saturation falling across the field for
atmospheric depth.

`verify-grid.mjs` checks 1,440 scroll positions across 10 viewports: gap
deviation 3.7e-13px, zero bare patches on either axis, row skew 60% (exactly
the design bound). It reads `PARALLAX_SPAN`, `PERIOD` and `ROW_SPARE` from
`src/main.js` so the harness cannot drift from the source.

## Commands

```bash
python3 scrape_covers.py 6 5    # covers, resumable
python3 build_manifest.py        # -> site/public/covers.json
./scripts/thumbs.sh              # WebP grid textures
npm install && npm run build
```

## Copyright

These are copyrighted covers published by McGraw-Hill (1931–1961), a
trademark now owned by Bloomberg L.P. This is a personal research archive.
The Internet Archive items carry no explicit rights statement, but the
underlying artwork is not public domain. Commercial reuse would need a
license from the current rights holder.
