#!/bin/bash
# WebP thumbnails for the Businessweek grid.
# Same reasoning as the New Yorker build: a 3192x4212 RGBA texture is ~53 MB,
# so rendering the full-res scans would need gigabytes of VRAM for a screenful.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-$HERE/../../archive}"
DST="${2:-$HERE/../public/covers}"
W="${3:-300}"
Q="${4:-62}"
mkdir -p "$DST"
find "$SRC" -type f -name '*.jpg' -print0 \
  | xargs -0 -n 1 -P 8 "$HERE/one.sh" "$SRC" "$DST" "$W" "$Q"
echo "thumbs: $(find "$DST" -name '*.webp' | wc -l | tr -d ' ')"
du -sh "$DST"
