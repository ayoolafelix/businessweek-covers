#!/usr/bin/env python3
"""Build the site manifest from the scrape, and report what is actually there."""
import csv, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "site")
PUB = os.path.join(SITE, "public")


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True).stdout.decode()


def dims(p):
    out = sh(f"sips -g pixelWidth -g pixelHeight {p!r} 2>/dev/null")
    w = re.search(r"pixelWidth:\s*(\d+)", out)
    h = re.search(r"pixelHeight:\s*(\d+)", out)
    return (int(w.group(1)), int(h.group(1))) if w and h else (0, 0)


def main():
    rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "data", "manifest_final.csv")))
            if r.get("status") == "ok"]
    rows.sort(key=lambda r: r["date"])
    out, ars = [], []
    for r in rows:
        # the CSV path is relative to site/public already; strip the prefix so
        # it is not doubled when we prepend our own
        rel = r["file"]
        if rel.startswith("archive/"):
            rel = rel[len("archive/"):]
        stem = os.path.splitext(rel)[0]
        out.append({
            "d": r["date"], "y": int(r["year"]),
            "t": f"{r['date'][8:10]} {r['date'][5:7]} {r['date'][:4]}",
            "thumb": f"covers/{stem}.webp",
            "full": f"archive/{stem}.jpg",
            "src": f"https://archive.org/details/sim_business-week_{r['date'].replace('-', '-')}",
        })
    os.makedirs(PUB, exist_ok=True)
    json.dump(out, open(os.path.join(PUB, "covers.json"), "w"), separators=(",", ":"))
    print(f"covers.json: {len(out)} entries")

    # most common page geometry, so the grid can size cells to the art
    sample = rows[:: max(1, len(rows) // 60)][:60]
    with ThreadPoolExecutor(max_workers=8) as ex:
        sizes = list(ex.map(lambda r: dims(os.path.join(SITE, "public", r["file"])), sample))
    good = [s for s in sizes if s[0] and s[1]]
    if good:
        ratios = sorted(w / h for w, h in good)
        ar = round(ratios[len(ratios) // 2], 4)
        print(f"aspect from {len(good)} samples: median {ar} "
              f"(min {ratios[0]:.3f} max {ratios[-1]:.3f})")
    total = sum(int(r["bytes"]) for r in rows if r.get("bytes"))
    print(f"full-res: {total/2**30:.2f} GB over {len(rows)} covers")


if __name__ == "__main__":
    main()
