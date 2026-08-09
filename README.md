# Munich District Colormap

A clickable map of Munich's **110 Stadtbezirksteile** (official sub-districts), colored by a shortlist you keep in a Notion database. Use it while deciding where to live.

## Features

- **110 sub-districts** (e.g. borough *Neuhausen-Nymphenburg* is split into `09.1 Neuhausen`, `09.2 Nymphenburg`, `09.3 Oberwiesenfeld Süd`, `09.4 St. Vinzenz-Viertel`, `09.5 Kasernenviertel`, `09.6 Ebenau`), each with real OSM neighborhood names where they exist.
- Hover shows the district code + name; each row links to its Google Maps location.
- **Liked-area marks**: draw circles ("+ Mark area") for spots you like, name + note them. Marks are saved in the browser (`localStorage`), survive reloads, and remember which sub-district they fall in.
- Side panel list with sort by **number / name / rating**.
- Locate button (uses geolocation).

## Colors

| Color | Meaning            |
| ----- | ------------------ |
| 🔴 Red    | No go              |
| 🟡 Yellow | Compromise         |
| 🟢 Green  | Like               |
| ⚪ Grey   | Explore / unset    |

## Two sources of truth

| Data | Owned by | Location |
| ---- | -------- | -------- |
| Rating (`Color`) and personal `Notes` | **Notion** — edit these by hand | database "Munich Sub-Districts (110)" |
| Geometry, `bt_nummer` codes, borough, area, centroids, OSM names | **Repo** — regenerated from official data | `munich_bezirksteile_named.geojson` |

Both are joined by the official code `bt_nummer` (e.g. `"09.1"`). The sync scripts write metadata repo→Notion and **never overwrite `Color`/`Notes`**, so your ratings are safe.

> **Migration note.** Ratings were previously kept in the 25-row "Munich Districts Colors" table. It is now superseded (still present, not deleted); its borough colors were carried down to the sub-districts as starting values (borough `9` = Green → all `09.x` start Green). It is no longer used by the map.

## How it works

```
               ┌──────────────────── Notion ────────────────────┐
               │  "Munich Sub-Districts (110)"  (Color + Notes) │
               └───────────────────────┬────────────────────────┘
                                       │  read by bake.py (ratings only)
                                       ▼
GeodatenService München WFS ─┐         repo data (committed)
  vablock_bezirksteil (poly) ─┼─► fetch_districts.py ─► munich_bezirksteile_named.geojson
OpenStreetMap (named places) ─┘    (run locally, on demand)    munich_districts_detail.md
                                                             │
                                                             ▼  bake.py
                                                        index.html ──► gh-pages ──► GitHub Pages
```

1. **`fetch_districts.py`** pulls the official 110 sub-district polygons from the GeodatenService München WFS (reprojected server-side to WGS84) and the named suburb/quarter/neighbourhood centroids from OpenStreetMap. Each OSM name is attached to the official polygon that contains its centroid (priority: suburb > quarter > neighbourhood). Output: `munich_bezirksteile_named.geojson` + a human-readable `munich_districts_detail.md`. **Run it locally, on demand** (the OSM endpoint is rate-limited and flaky from CI), and commit the result. It falls back to the previously committed OSM names if Overpass is unreachable.
2. **`sync_notion_districts.py`** makes the Notion database match the committed repo data. First run creates "Munich Sub-Districts (110)" under the "Munich Districts Map" page and seeds all 110 rows (carrying down the archived borough colors). Later runs are idempotent upserts keyed by `Code` — metadata is refreshed, `Color`/`Notes` untouched.
3. **`bake.py`** embeds the committed GeoJSON and the current colors from Notion into a single static `index.html`.
4. A GitHub Actions workflow publishes `index.html` to the `gh-pages` branch, which GitHub Pages serves. `main` stays clean (source only). The live page can be embedded in Notion.

## Setup

- Repo: `munich-district-colormap`
- Enable **GitHub Pages**: Settings → Pages → Deploy from branch → `gh-pages`, folder `/ (root)`.
- **Actions secret** `NOTION_TOKEN`: a Notion integration token that can read/write the databases under "Munich Districts Map".
- The Notion database is found by title (`"Munich Sub-Districts (110)"`), so no DB ID variable is required.

The Notion database schema (created automatically by the sync):

| Property | Type | Notes |
| -------- | ---- | ----- |
| Name | title | e.g. `Neuhausen (09.1)` |
| Code | rich text | the `bt_nummer`, join key (e.g. `09.1`) |
| Borough | rich text | the parent Stadtbezirk name |
| Color | select | Red / Yellow / Green / Grey — **edit by hand** |
| Notes | rich text | **edit by hand** |
| Area km² | number | derived |
| Centroid Lat / Lng | number | derived |
| Map | url | link to Google Maps |

## Local usage

```sh
# regenerate the district data (needs internet; writes the .geojson + .md)
python3 fetch_districts.py

# sync the data to Notion (needs NOTION_TOKEN; creates/updates the DB)
NOTION_TOKEN=secret_... python3 sync_notion_districts.py

# render the map (colors from Notion if NOTION_TOKEN is set)
python3 bake.py
open index.html
```

## Structure

- `fetch_districts.py` — official WFS polygons + OSM names → `munich_bezirksteile_named.geojson`, `munich_districts_detail.md`
- `sync_notion_districts.py` — creates/seeds + idempotently syncs the Notion database
- `bake.py` — fetches colors from Notion and renders `index.html` (includes the marks feature)
- `.github/workflows/sync.yml` — rebuild + deploy the map (every 10 min, on push, or via **Run workflow**)
- `.github/workflows/sync-notion.yml` — sync repo metadata to the Notion database (weekly or via **Run workflow**)
- `munich_bezirksteile_named.geojson` — generated district data (committed)
- `munich_districts_detail.md` — generated district table (committed)
- `paths.json`, `stadtbezirke.geojson` — legacy 25-district assets, superseded by the sub-district data
- `index.html` — generated map (lives on the `gh-pages` branch, not committed to `main`)
