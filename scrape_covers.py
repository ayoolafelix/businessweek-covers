#!/usr/bin/env python3
"""Pull Businessweek covers and cover credits from the Internet Archive.

Source: the pub_business-week microfilm collection (sim_microfilm). Each issue
is a 23-58 MB PDF; the cover is page n0, served individually by archive.org's
BookReader page service, so we never download the whole scan.

The _djvu.txt derivative is ~466 KB of OCR for a whole issue, but the cover
text is in the first few KB, so it is pulled with a Range request instead.
That text contains the cover headline and the printed credit line
("E-Z Paint'r's Touchett: ... (page 82)"), which is the only artist
attribution available anywhere for these issues.

Resumable: existing cover files are skipped. Polite: concurrency is low and
each request is rate limited.
"""
import csv, json, os, re, sys, threading, time
import requests
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(ROOT, "site", "public", "archive")
MANIFEST = os.path.join(ROOT, "data", "manifest.csv")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
COVER = "https://archive.org/download/{i}/page/n0.jpg"
TEXT = "https://archive.org/download/{i}/{i}_djvu.txt"

# cover boilerplate that OCR throws up and that is never a headline
JUNK = re.compile(
    r"business\s*week|mc\s*graw|publishing|company|inc\.?|cents|volume|"
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december|index|contents|^a$|^~$|^—$|^\W+$|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|businessweek|"
    r"the business week|year ago|no\.|page$|^\d+$", re.I)
# "E-Z-Paintr's Touchett: His roller ... (page 82"  ->  artist + title
CREDIT = re.compile(
    r"^([A-Z][A-Za-z0-9.'\-]{1,14}(?:[ \-][A-Za-z0-9.'\-]{1,14}){0,2})['’]s\s+"
    r"([A-Z][^:(]{2,34}?)\s*:\s*[^()]{6,90}?\(page\s*\d+", re.M)
_local = threading.local()
_lock = threading.Lock()


def session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        _local.s = s
    return s


def parse_cover_text(txt):
    """Pull the headline and the printed credit out of the cover OCR.

    OCR of a 1950s cover is rough: the headline wraps across several lines and
    the masthead is interleaved with it, so a "pick the longest shouty line"
    heuristic returns fragments like "UP COMPETITIVELY". Consecutive shouty
    lines before the masthead are joined instead, and when the credit line
    yields a title we prefer that, since it is the one field the typesetter
    set deliberately.
    """
    if not txt or "<!DOCTYPE html>" in txt[:200]:
        return "", "", ""
    head = txt[:4000]

    artist = credit_title = ""
    m = CREDIT.search(head)
    if m:
        artist = m.group(1).strip()
        credit_title = m.group(2).strip()

    # split into lines, drop boilerplate, and note where the masthead sits
    raw = [l.strip() for l in head.splitlines()]
    masthead_at = len(raw)
    for i, l in enumerate(raw):
        if re.match(r"^[\s~\\|—_-]*(business|week)[\s~\\|—_-]*$", l, re.I) and i < 40:
            masthead_at = i
            break

    shouty = []
    for l in raw[:masthead_at]:
        core = l.strip(" ~\\|—_-*")
        if not core or JUNK.search(core):
            continue
        # shouty = mostly capitals, and OCR noise is rarely shouty
        letters = [c for c in core if c.isalpha()]
        if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.8 \
           and len(core) > 3 and len(core.split()) <= 8:
            shouty.append(core)
        if len(shouty) >= 3:
            break

    headline = " ".join(shouty).strip() if shouty else ""
    if credit_title and len(credit_title) >= len(headline):
        headline = credit_title
    return headline, artist, credit_title


def fetch(item, workers_rps):
    ident, date = item["id"], item["date"]
    y, m, d = date.split("-")
    out = os.path.join(ARCHIVE, y, f"{date}.jpg")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    row = {"date": date, "year": y, "headline": "", "artist": "", "title": "",
           "file": f"archive/{y}/{date}.jpg", "bytes": 0, "status": ""}
    have_cover = os.path.exists(out) and os.path.getsize(out) > 10_000

    # credit (cheap, ranged)
    if not have_cover or True:
        try:
            workers_rps.wait()
            r = session().get(TEXT.format(i=ident), timeout=60,
                              headers={"Range": "bytes=0-8000"})
            if r.status_code in (200, 206):
                hl, ar, ti = parse_cover_text(r.text)
                row["headline"], row["artist"], row["title"] = hl, ar, ti
        except Exception:
            pass

    if have_cover:
        row["bytes"] = os.path.getsize(out)
        row["status"] = "ok"
        return row

    for attempt in range(4):
        try:
            workers_rps.wait()
            r = session().get(COVER.format(i=ident), timeout=120)
            if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
                with open(out, "wb") as f:
                    f.write(r.content)
                row["bytes"] = len(r.content)
                row["status"] = "ok"
                return row
            if r.status_code in (404, 503):
                row["status"] = f"dead_{r.status_code}"
                return row
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    row["status"] = "err"
    return row


class RPS:
    """Global rate cap so we do not hammer archive.org."""
    def __init__(self, rps):
        self.i = 1.0 / rps
        self.lk = threading.Lock()
        self.nxt = 0.0

    def wait(self):
        with self.lk:
            now = time.time()
            slot = max(now, self.nxt)
            self.nxt = slot + self.i
        if slot - now > 0:
            time.sleep(slot - now)


def main():
    ids = json.load(open(os.path.join(ROOT, "data", "valid_ids.json")))
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    rps = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
    print(f"issues={len(ids)} workers={workers} rps={rps}")

    done = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("status") == "ok":
                    done[r["date"]] = r
    todo = [i for i in ids if i["date"] not in done]
    print(f"already ok={len(done)} todo={len(todo)}")

    newfile = not os.path.exists(MANIFEST)
    fh = open(MANIFEST, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=["date", "year", "headline", "artist", "title",
                                      "file", "bytes", "status"])
    if newfile:
        w.writeheader()
        fh.flush()

    cap = RPS(rps)
    t0, n, ok = time.time(), 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for row in ex.map(lambda i: fetch(i, cap), todo):
            w.writerow(row)
            fh.flush()
            n += 1
            if row["status"] == "ok":
                ok += 1
            if n % 50 == 0:
                el = time.time() - t0
                print(f"  {n}/{len(todo)} ok={ok} {n/el:.2f}/s "
                      f"eta={(len(todo)-n)/(n/el)/60:.0f}m", flush=True)
    fh.close()
    print(f"done: {n} processed, {ok} ok, {(time.time()-t0)/60:.1f}m")


if __name__ == "__main__":
    main()
