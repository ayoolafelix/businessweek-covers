#!/usr/bin/env python3
"""Validate the archive.org identifier list.

The advancedsearch index still lists items that have since been removed, so a
search result is not proof the item exists. This HEADs the derivative file for
every id and keeps only the ones that answer 200. Without this step the plan
was built on ~1,618 issues of which an unknown share are ghosts.
"""
import json, re, sys, time
import requests
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
_local_id = __import__("threading").local()


def session():
    s = getattr(_local_id, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        _local_id.s = s
    return s


def check(item):
    ident, date = item["id"], item["date"]
    url = f"https://archive.org/download/{ident}/{ident}_djvu.txt"
    for attempt in range(3):
        try:
            r = session().head(url, timeout=40, allow_redirects=True)
            if r.status_code == 200:
                return {"id": ident, "date": date, "ok": True,
                        "bytes": r.headers.get("content-length")}
            if r.status_code in (404, 503):
                return {"id": ident, "date": date, "ok": False, "code": r.status_code}
            time.sleep(1.5 * (attempt + 1))
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return {"id": ident, "date": date, "ok": False, "code": "err"}


def main():
    items = json.load(open(sys.argv[1]))
    print(f"validating {len(items)} identifiers from the search index")
    out, done = [], 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(check, items):
            out.append(res)
            done += 1
            if done % 150 == 0:
                ok = sum(1 for r in out if r["ok"])
                el = time.time() - t0
                print(f"  {done}/{len(items)}  live={ok}  {done/el:.1f}/s "
                      f"eta={(len(items)-done)/(done/el)/60:.0f}m", flush=True)
    live = [r for r in out if r["ok"]]
    json.dump(live, open(sys.argv[2], "w"))
    print(f"live items: {len(live)} of {len(items)} "
          f"({100*len(live)/len(items):.1f}%)  -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
