#!/usr/bin/env python3
"""
LGU Research Output Harvester
ORIC, Lahore Garrison University

Pulls every publication carrying a Lahore Garrison University affiliation
and writes docs/data.json, which the portal (docs/index.html) reads.

Sources, merged by DOI (then by normalised title):
  1. OpenAlex  - free, no login. Indexes Scopus/WoS journals, conferences,
                 Crossref DOIs. Always runs.
  2. Scopus    - optional. Runs when SCOPUS_API_KEY is set (free key from
                 dev.elsevier.com; works on the LGU network / HEC access).
                 Marks which papers are really Scopus-indexed and adds any
                 Scopus papers OpenAlex missed.
  3. ORIC data - optional data/oric_records.csv exported from the current
                 ORIC system. Nothing already recorded is lost.

Classification inputs ORIC maintains (plain CSV, edit in Excel):
  data/journals.csv  issn, journal_title, hjrs_category (W/X/Y/Z), year, wos (Y/N), scopus (Y/N)
  data/faculty.csv   name, department, designation, aliases, orcid, openalex_id, scholar_url

Usage:  python harvest.py            (all sources)
        python harvest.py --offline  (rebuild from cached raw files, no network)
Env:    OPENALEX_MAILTO, OPENALEX_API_KEY, SCOPUS_API_KEY, SCOPUS_INSTTOKEN,
        SCOPUS_AFID, START_YEAR (default 2012)
"""
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "cache")
OUT = os.path.join(ROOT, "docs", "data.json")

LGU_OPENALEX = "I4210105419"   # https://openalex.org/I4210105419
LGU_ROR = "01j4ba358"          # https://ror.org/01j4ba358
START_YEAR = int(os.environ.get("START_YEAR", "2012"))
MAILTO = os.environ.get("OPENALEX_MAILTO", "oric@lgu.edu.pk")
OFFLINE = "--offline" in sys.argv


# ---------------------------------------------------------------- helpers
def http_json(url, headers=None, tries=6):
    hdr = {"User-Agent": f"LGU-ORIC-research-portal (mailto:{MAILTO})", "Accept": "application/json"}
    hdr.update(headers or {})
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(min(60, 3 * 2 ** i))
                continue
            body = e.read()[:300].decode("utf8", "replace")
            raise SystemExit(f"HTTP {e.code} for {url}\n{body}")
        except urllib.error.URLError:
            if i < tries - 1:
                time.sleep(min(60, 3 * 2 ** i))
                continue
            raise


def norm_doi(d):
    if not d:
        return ""
    d = d.strip().lower()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d)
    return d


def norm_issn(s):
    s = re.sub(r"[^0-9Xx]", "", s or "").upper()
    return f"{s[:4]}-{s[4:]}" if len(s) == 8 else ""


def norm_text(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def name_key(s):
    """'Dr. Muhammad  Asif Khan' -> 'asif khan muhammad' (order-insensitive)."""
    s = norm_text(s)
    s = re.sub(r"\b(dr|prof|professor|engr|mr|mrs|ms|miss|sir)\b", " ", s)
    return " ".join(sorted(s.split()))


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def yes(v):
    return (v or "").strip().lower() in ("y", "yes", "true", "1")


# ---------------------------------------------------------------- OpenAlex
def harvest_openalex():
    raw_path = os.path.join(CACHE, "openalex_raw.json")
    if OFFLINE:
        with open(raw_path, encoding="utf8") as f:
            return json.load(f)
    params = {
        "filter": f"authorships.institutions.lineage:{LGU_OPENALEX},from_publication_date:{START_YEAR}-01-01",
        "select": "id,doi,display_name,publication_year,publication_date,type,primary_location,"
                  "authorships,cited_by_count,open_access,biblio,ids",
        "per_page": "200",
        "mailto": MAILTO,
    }
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    works, cursor = [], "*"
    while cursor:
        params["cursor"] = cursor
        page = http_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
        works.extend(page.get("results", []))
        cursor = page.get("meta", {}).get("next_cursor")
        print(f"  OpenAlex: {len(works)} / {page.get('meta', {}).get('count')}", flush=True)
        time.sleep(0.15)
    os.makedirs(CACHE, exist_ok=True)
    with open(raw_path, "w", encoding="utf8") as f:
        json.dump(works, f)
    return works


def from_openalex(w):
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    issns = [norm_issn(x) for x in (src.get("issn") or [])]
    if src.get("issn_l"):
        issns.insert(0, norm_issn(src["issn_l"]))
    authors = []
    for a in w.get("authorships") or []:
        au = a.get("author") or {}
        insts = a.get("institutions") or []
        lgu = any((i.get("id") or "").endswith(LGU_OPENALEX) or (i.get("ror") or "").endswith(LGU_ROR)
                  or LGU_OPENALEX in (i.get("lineage") or []) for i in insts)
        authors.append({
            "n": au.get("display_name") or a.get("raw_author_name") or "",
            "id": (au.get("id") or "").rsplit("/", 1)[-1],
            "orcid": (au.get("orcid") or "").rsplit("/", 1)[-1],
            "lgu": lgu,
        })
    b = w.get("biblio") or {}
    pages = "-".join(x for x in (b.get("first_page"), b.get("last_page")) if x)
    return {
        "id": w["id"].rsplit("/", 1)[-1],
        "doi": norm_doi(w.get("doi")),
        "t": w.get("display_name") or "",
        "y": w.get("publication_year"),
        "d": w.get("publication_date") or "",
        "ty": w.get("type") or "",
        "j": src.get("display_name") or "",
        "jt": src.get("type") or "",
        "pub": src.get("host_organization_name") or "",
        "issn": [x for x in dict.fromkeys(issns) if x],
        "vol": b.get("volume") or "", "iss": b.get("issue") or "", "pg": pages,
        "c": w.get("cited_by_count") or 0,
        "oa": (w.get("open_access") or {}).get("oa_status") or "",
        "au": authors,
        "src": ["OpenAlex"],
        "scopus": None, "wos": None, "hjrs": "",
    }


# ---------------------------------------------------------------- Scopus
def harvest_scopus():
    key = os.environ.get("SCOPUS_API_KEY")
    if not key:
        return None, None
    hdr = {"X-ELS-APIKey": key}
    if os.environ.get("SCOPUS_INSTTOKEN"):
        hdr["X-ELS-Insttoken"] = os.environ["SCOPUS_INSTTOKEN"]
    afid = os.environ.get("SCOPUS_AFID")
    q = f"AF-ID({afid})" if afid else 'AFFIL("Lahore Garrison University")'
    q += f" AND PUBYEAR > {START_YEAR - 1}"
    view = os.environ.get("SCOPUS_VIEW", "STANDARD")
    entries, cursor, total = [], "*", None
    while cursor:
        url = "https://api.elsevier.com/content/search/scopus?" + urllib.parse.urlencode(
            {"query": q, "cursor": cursor, "count": "25" if view == "COMPLETE" else "200", "view": view})
        res = http_json(url, hdr).get("search-results", {})
        total = int(res.get("opensearch:totalResults") or 0)
        batch = [e for e in res.get("entry", []) if "error" not in e]
        if not batch:
            break
        entries.extend(batch)
        nxt = (res.get("cursor") or {}).get("@next")
        cursor = nxt if nxt and nxt != cursor else None
        print(f"  Scopus: {len(entries)} / {total}", flush=True)
        time.sleep(0.2)
    return entries, total


def from_scopus(e):
    authors = [{"n": a.get("authname", ""), "id": "", "orcid": "", "lgu": True}
               for a in (e.get("author") or [])] or [{"n": e.get("dc:creator", ""), "id": "", "orcid": "", "lgu": False}]
    return {
        "id": "S" + (e.get("dc:identifier", "").split(":")[-1]),
        "doi": norm_doi(e.get("prism:doi")),
        "t": e.get("dc:title", ""),
        "y": int((e.get("prism:coverDate") or "0")[:4]) or None,
        "d": e.get("prism:coverDate", ""),
        "ty": {"ar": "article", "cp": "conference paper", "re": "review", "ch": "book-chapter",
               "bk": "book"}.get(e.get("subtype", ""), e.get("subtypeDescription", "").lower()),
        "j": e.get("prism:publicationName", ""), "jt": "journal", "pub": "",
        "issn": [x for x in (norm_issn(e.get("prism:issn")), norm_issn(e.get("prism:eIssn"))) if x],
        "vol": e.get("prism:volume", ""), "iss": e.get("prism:issueIdentifier", ""),
        "pg": e.get("prism:pageRange") or "",
        "c": int(e.get("citedby-count") or 0), "oa": "",
        "au": authors, "src": ["Scopus"], "scopus": True, "wos": None, "hjrs": "",
    }


# ---------------------------------------------------------------- ORIC's own records
def from_oric(r):
    names = [n.strip() for n in re.split(r";|\band\b", r.get("authors", "")) if n.strip()]
    yr = re.sub(r"\D", "", r.get("year", ""))[:4]
    return {
        "id": "O" + str(abs(hash(r.get("title", "") + yr)) % 10 ** 9),
        "doi": norm_doi(r.get("doi")),
        "t": r.get("title", ""), "y": int(yr) if yr else None, "d": "",
        "ty": (r.get("type") or "article").lower(),
        "j": r.get("journal", ""), "jt": "journal", "pub": r.get("publisher", ""),
        "issn": [x for x in (norm_issn(r.get("issn")),) if x],
        "vol": r.get("volume", ""), "iss": r.get("issue", ""), "pg": r.get("pages", ""),
        "c": 0, "oa": "",
        "au": [{"n": n, "id": "", "orcid": "", "lgu": True} for n in names],
        "src": ["ORIC record"], "scopus": None, "wos": None,
        "hjrs": (r.get("hjrs_category") or r.get("category") or "").upper()[:1],
    }


# ---------------------------------------------------------------- merge
def merge(records):
    by_doi, by_title, out = {}, {}, []
    for r in records:
        tk = norm_text(r["t"])[:120]
        hit = (by_doi.get(r["doi"]) if r["doi"] else None) or (by_title.get((tk, r["y"])) if len(tk) > 25 else None)
        if hit is None:
            out.append(r)
            if r["doi"]:
                by_doi[r["doi"]] = r
            if len(tk) > 25:
                by_title[(tk, r["y"])] = r
            continue
        for s in r["src"]:
            if s not in hit["src"]:
                hit["src"].append(s)
        if r["scopus"]:
            hit["scopus"] = True
        if r["hjrs"] and not hit["hjrs"]:
            hit["hjrs"] = r["hjrs"]
        for k in ("doi", "j", "vol", "iss", "pg", "pub"):
            if not hit[k] and r[k]:
                hit[k] = r[k]
        hit["issn"] = list(dict.fromkeys(hit["issn"] + r["issn"]))
        hit["c"] = max(hit["c"], r["c"])
        if r["doi"] and r["doi"] not in by_doi:
            by_doi[r["doi"]] = hit
    return out


# ---------------------------------------------------------------- classification
def load_journals():
    rows = read_csv(os.path.join(DATA, "journals.csv"))
    idx = {}
    for r in rows:
        issn = norm_issn(r.get("issn"))
        if not issn:
            continue
        yr = re.sub(r"\D", "", r.get("year", ""))[:4]
        idx.setdefault(issn, []).append({
            "year": int(yr) if yr else None,
            "cat": (r.get("hjrs_category") or "").upper()[:1],
            "wos": r.get("wos", ""), "scopus": r.get("scopus", ""),
        })
    for v in idx.values():
        v.sort(key=lambda x: x["year"] or 0)
    return idx, len(rows)


def classify(rec, jidx):
    rows = [row for i in rec["issn"] for row in jidx.get(i, [])]
    if not rows:
        return
    same = [r for r in rows if r["year"] == rec["y"]]
    before = [r for r in rows if r["year"] and rec["y"] and r["year"] <= rec["y"]]
    pick = (same or before or rows)[-1]
    if pick["cat"] in "WXYZ" and pick["cat"] and not rec["hjrs"]:
        rec["hjrs"] = pick["cat"]
    if pick["wos"]:
        rec["wos"] = yes(pick["wos"])
    if pick["scopus"] and rec["scopus"] is None:
        rec["scopus"] = yes(pick["scopus"])


def load_faculty():
    fac = []
    for r in read_csv(os.path.join(DATA, "faculty.csv")):
        if not r.get("name"):
            continue
        keys = {name_key(r["name"])} | {name_key(a) for a in r.get("aliases", "").split(";") if a.strip()}
        fac.append({
            "name": r["name"], "dept": r.get("department", ""), "desig": r.get("designation", ""),
            "orcid": r.get("orcid", "").rsplit("/", 1)[-1], "oa": r.get("openalex_id", "").rsplit("/", 1)[-1],
            "scholar": r.get("scholar_url", ""), "keys": sorted(k for k in keys if k),
        })
    return fac


def tag_faculty(records, fac):
    by_id, by_orcid, by_key = {}, {}, {}
    for i, f in enumerate(fac):
        if f["oa"]:
            by_id[f["oa"]] = i
        if f["orcid"]:
            by_orcid[f["orcid"]] = i
        for k in f["keys"]:
            by_key.setdefault(k, i)
    for r in records:
        for a in r["au"]:
            i = by_id.get(a["id"]) if a["id"] else None
            if i is None and a["orcid"]:
                i = by_orcid.get(a["orcid"])
            if i is None:
                i = by_key.get(name_key(a["n"]))
            if i is not None:
                a["f"] = i
                a["lgu"] = True


# ---------------------------------------------------------------- main
def main():
    print("Harvesting LGU publications from", START_YEAR)
    records = [from_openalex(w) for w in harvest_openalex()]
    sources = {"OpenAlex": len(records)}

    sc, sc_total = (None, None) if OFFLINE else harvest_scopus()
    if sc is not None:
        records += [from_scopus(e) for e in sc]
        sources["Scopus"] = sc_total

    oric = read_csv(os.path.join(DATA, "oric_records.csv"))
    if oric:
        records += [from_oric(r) for r in oric if r.get("title")]
        sources["ORIC records"] = len(oric)

    records = merge(records)
    records = [r for r in records if r["y"] is None or r["y"] >= START_YEAR]

    jidx, jrows = load_journals()
    for r in records:
        classify(r, jidx)
    if sc is not None:
        for r in records:
            if r["scopus"] is None:
                r["scopus"] = False

    fac = load_faculty()
    tag_faculty(records, fac)

    records.sort(key=lambda r: (r["d"] or str(r["y"] or ""), r["t"]), reverse=True)
    out = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start_year": START_YEAR,
        "institution": {"name": "Lahore Garrison University", "openalex": LGU_OPENALEX, "ror": LGU_ROR},
        "sources": sources,
        "scopus_live": sc is not None,
        "journal_rows": jrows,
        "faculty": [{k: v for k, v in f.items() if k != "keys"} | {"keys": f["keys"]} for f in fac],
        "works": records,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {len(records)} publications -> {OUT}")


if __name__ == "__main__":
    main()
