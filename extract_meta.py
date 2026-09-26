#!/usr/bin/env python3
"""Second pass: recover cover metadata from each issue's OCR text.

Kept separate from the cover download on purpose. The covers are 1.5 GB and
slow; the OCR text is a few KB per issue and cheap to refetch, so the parser
can be tuned and re-run without touching the images.

Yield varies a lot by era and is reported honestly rather than papered over:
early covers often set the headline and credit in small type that the OCR
never resolved, so those rows come back empty and the site hides them.
"""
import json, os, re, sys, threading, time
import requests
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
TEXT = "https://archive.org/download/{i}/{i}_djvu.txt"
_local = threading.local()


def session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        _local.s = s
    return s


JUNK = re.compile(
    r"business\s*week|businessweek|mc\s*graw|graw-hill|publishing|"
    r"company|inc\.?|cents|volume|contents|index|^\W*$|"
    r"jan\.?|feb\.?|mar\.?|apr\.?|jun\.?|jul\.?|aug\.?|sep\.?|oct\.?|nov\.?|dec\.?|"
    r"january|february|march|april|june|july|august|september|october|"
    r"november|december|^\d{4}$|nineteen|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety|year ago|page|^\d+$", re.I)

# "E-Z-Paintr's Touchett: His roller has everyone painting (page 82"
CREDIT = re.compile(
    r"^([A-Z][A-Za-z0-9.'\-]{1,13}(?:[ \-][A-Za-z0-9.'\-]{1,13}){0,2})['’]s\s+"
    r"([A-Z][^:(]{2,34}?)\s*:\s+[^()\n]{6,90}?\(page\s*\d+", re.M)

# a date must never be shown as a headline
DATEISH = re.compile(r"^\W*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
                     r"[a-z]*\.?\s+\d{1,2},?\s*\d{4}\W*$", re.I)
ONLY_DIGITS = re.compile(r"^[\W\d]+$")


def parse(txt):
    if not txt or "<!DOCTYPE html>" in txt[:300]:
        return "", "", ""
    head = txt[:4500]
    raw = [l.strip() for l in head.splitlines()]

    artist = title = ""
    m = CREDIT.search(head)
    if m:
        artist = m.group(1).strip()
        title = m.group(2).strip()

    # the masthead marks where the cover furniture starts
    mast = len(raw)
    for i, l in enumerate(raw[:45]):
        core = l.strip(" ~\\|—_-*")
        if re.fullmatch(r"(business|week|indicator|business\s+week)", core, re.I):
            mast = i
            break

    shouty = []
    for l in raw[:mast]:
        core = l.strip(" ~\\|—_-*")
        if not core or JUNK.search(core) or DATEISH.match(core) or ONLY_DIGITS.match(core):
            continue
        letters = [c for c in core if c.isalpha()]
        if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.8 \
           and 3 < len(core) and len(core.split()) <= 9:
            shouty.append(core)
        if len(shouty) >= 3:
            break

    headline = " ".join(shouty).strip()
    if DATEISH.match(headline) or ONLY_DIGITS.match(headline):
        headline = ""
    if title and len(title) > len(headline):
        headline = title
    return headline, artist, title


def fetch(item, cap):
    ident, date = item["id"], item["date"]
    for attempt in range(3):
        try:
            cap.wait()
            r = session().get(TEXT.format(i=ident), timeout=60,
                              headers={"Range": "bytes=0-9000"})
            if r.status_code in (200, 206):
                h, a, t = parse(r.text)
                return {"date": date, "headline": h, "artist": a, "title": t}
            if r.status_code in (404, 503):
                return {"date": date, "headline": "", "artist": "", "title": ""}
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))
    return {"date": date, "headline": "", "artist": "", "title": ""}


class Cap:
    def __init__(self, rps):
        self.i, self.lk, self.nxt = 1.0 / rps, threading.Lock(), 0.0

    def wait(self):
        with self.lk:
            now = time.time()
            slot = max(now, self.nxt)
            self.nxt = slot + self.i
        if slot - now > 0:
            time.sleep(slot - now)


def main():
    ids = json.load(open(os.path.join(ROOT, "data", "valid_ids.json")))
    if len(sys.argv) > 1 and sys.argv[1] == "--sample":
        import random
        random.seed(4)
        bydec = {}
        for i in ids:
            bydec.setdefault(int(i["date"][:4]) // 10 * 10, []).append(i)
        ids = [x for d in sorted(bydec) for x in random.sample(bydec[d], min(8, len(bydec[d])))]
        print(f"sample of {len(ids)}")
    out = os.path.join(ROOT, "data", "covers-meta.json")
    cap = Cap(6.0)
    t0 = time.time()
    res = list(ThreadPoolExecutor(max_workers=6).map(lambda i: fetch(i, cap), ids))
    json.dump({r["date"]: {"headline": r["headline"], "artist": r["artist"],
                           "title": r["title"]} for r in res if
               r["headline"] or r["artist"] or r["title"]}, open(out, "w"))
    n = len(res)
    print(f"\n{n} issues in {time.time()-t0:.0f}s")
    for k in ("artist", "title", "headline"):
        c = sum(1 for r in res if r[k].strip())
        print(f"  {k:9} {c:3}/{n}  {100*c/n:4.0f}%")
    bydec = {}
    for r in res:
        d = int(r["date"][:4]) // 10 * 10
        b = bydec.setdefault(d, [0, 0])
        b[1] += 1
        if r["artist"].strip():
            b[0] += 1
    print("\n  artist hit rate by decade:")
    for d in sorted(bydec):
        a, t = bydec[d]
        print(f"    {d}s  {a:2}/{t:2}  {100*a/t:3.0f}%")
    print("\n  samples:")
    for r in res[:6]:
        if r["artist"] or r["headline"]:
            print(f"    {r['date']}  artist={r['artist']!r:22} title={r['title']!r:18}")
            print(f"                 headline={r['headline']!r}")


if __name__ == "__main__":
    main()
