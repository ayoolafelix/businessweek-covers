#!/bin/bash
# One conversion. xargs -n 1 APPENDS the path, so it is the last argument.
set -u
SRC="$1"; DST="$2"; W="$3"; Q="$4"
for f in "$@"; do FILE="$f"; done
rel="${FILE#"$SRC"/}"
y="$(dirname "$rel")"
b="$(basename "$FILE")"; b="${b%.*}"
mkdir -p "$DST/$y"
[ -s "$DST/$y/$b.webp" ] && exit 0
cwebp -quiet -resize "$W" 0 -q "$Q" "$FILE" -o "$DST/$y/$b.webp" 2>/dev/null
