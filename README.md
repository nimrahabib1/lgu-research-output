# LGU Research Output Portal

ORIC, Lahore Garrison University

A public, link-based register of every publication carrying an LGU affiliation since 2012.
Anyone with the link can type a faculty member's name and see all their papers, with live
counts by HJRS category (W / X / Y / Z), Scopus, Web of Science, year, type and department.
The data refreshes itself every week. No server, no hosting cost.

## How it works

```
OpenAlex API (free, every LGU-affiliated paper) ─┐
Scopus API   (optional, LGU's key)               ├─> harvest.py ─> docs/data.json ─> docs/index.html (public link)
ORIC's existing system (CSV export)              ┘          ▲
                                                            │
data/journals.csv  (HJRS category, WoS, Scopus per ISSN)  ──┤  maintained by ORIC in Excel
data/faculty.csv   (names, departments, name variants)    ──┘
```

GitHub Actions runs `harvest.py` every Monday 02:17 PKT, and again whenever ORIC edits a file in `data/`.
Duplicates found in more than one source are merged by DOI, then by title + year.

## One-time setup (about 20 minutes)

1. **Create the repository.** On GitHub, create a new repository (e.g. `lgu-research-output`) under the ORIC/LGU account and upload every file in this folder, keeping the folder structure (`.github/workflows/update.yml` included).
2. **Turn on the public link.** Repository → Settings → Pages → Source: *Deploy from a branch* → Branch `main`, folder `/docs` → Save. The portal link appears there, e.g. `https://<account>.github.io/lgu-research-output/`.
3. **Contact email.** Settings → Secrets and variables → Actions → *Variables* → New: `OPENALEX_MAILTO` = the ORIC email. (OpenAlex asks for one; it gives faster, more reliable access.)
4. **First run.** Actions tab → *Refresh LGU publication data* → *Run workflow*. After 2–5 minutes the portal shows the full LGU list.

### Optional: Scopus (recommended)
OpenAlex already covers almost all Scopus and WoS journals, but it cannot say *which* papers Scopus indexes.
With a Scopus key the portal marks Scopus-indexed papers exactly and adds any Scopus paper OpenAlex missed.

1. On the LGU campus network, sign in at <https://dev.elsevier.com> → *Create API Key*.
2. In Scopus (via HEC Digital Library), search *Affiliations* → "Lahore Garrison University" → open it; the number in the URL is the **Affiliation ID**.
3. Repository → Settings → Secrets and variables → Actions:
   - Secret `SCOPUS_API_KEY` = the key
   - Secret `SCOPUS_INSTTOKEN` = institutional token (only if Elsevier issues one for off-campus use)
   - Variable `SCOPUS_AFID` = the Affiliation ID
   GitHub's servers are off-campus, so if Scopus refuses the key, ask Elsevier/HEC for an institutional token.

## The three files ORIC maintains (`data/`)

Open in Excel, edit, save as CSV, upload to the repository. The portal updates within minutes.

**`journals.csv`** — the source of the W/X/Y/Z, WoS and Scopus labels.

| issn | journal_title | hjrs_category | year | wos | scopus |
|---|---|---|---|---|---|
| 1234-5678 | Example Journal of Computing | X | 2024 | Y | Y |

- `hjrs_category`: W, X, Y or Z from <https://hjrs.hec.gov.pk>.
- `year`: the HJRS year that category applies to. HJRS re-rates journals, so add one row per year; each paper takes the rating for its publication year (or the latest earlier one). Leave blank if not tracked by year.
- `wos`: Y if the journal is in Web of Science (check at <https://mjl.clarivate.com>).
- `scopus`: Y if indexed in Scopus (used only when no Scopus key is set).
- Quickest start: filter the portal by *HJRS category → Not mapped*, export CSV, and add the journals that appear there.

**`faculty.csv`** — links papers to people and departments.

| name | department | designation | aliases | orcid | openalex_id | scholar_url |
|---|---|---|---|---|---|---|
| Dr. Example Name | Computer Science | Assistant Professor | E. Name;Name E | 0000-0000-0000-0000 | A5000000000 | https://scholar.google.com/citations?user=… |

- `aliases`: other spellings the person publishes under, separated by `;`.
- `orcid` / `openalex_id`: optional, but make matching exact. A person's OpenAlex ID is shown at <https://openalex.org> when you search their name.
- Faculty who are not in this file still appear in search under the name printed on their papers.

**`oric_records.csv`** — export from ORIC's current system, so nothing already recorded is lost.
Columns: `title, authors, year, journal, issn, doi, hjrs_category, type, volume, issue, pages, publisher` (authors separated by `;`).

## Why each source is used the way it is

| Source | Used for | Limitation |
|---|---|---|
| OpenAlex | Full automatic list of LGU-affiliated papers, citations, co-authors | Cannot label Scopus/WoS indexing per paper |
| Scopus API | Exact Scopus-indexed list and count | Needs LGU's key; subscription network |
| Web of Science | WoS label via journal list | No free API. MJL (mjl.clarivate.com) checks journals, not paper counts. Exact WoS counts need a WoS login (HEC Digital Library) |
| Google Scholar | Profile link per faculty | No API; automated collection is against its terms. Scholar profiles are faculty-maintained |
| HJRS | W/X/Y/Z category | No public API, so ORIC keeps `journals.csv` |

## Running it on a computer instead

```
python harvest.py          # needs Python 3.9+, internet; no packages to install
cd docs && python -m http.server 8000   # open http://localhost:8000
```
