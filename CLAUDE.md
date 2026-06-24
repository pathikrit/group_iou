# Group IOU — project notes for Claude

A zero-backend single-page app that reads a publicly-published Google Sheet of net
balances and computes the **fewest money transfers** needed to settle everyone up,
rendered as a graph.

## ⛔ RULES (must follow)
- **DO NOT COMMIT OR PUSH until the user explicitly says so.** Make file changes
  freely, but never run `git commit` / `git push` without an explicit go-ahead.
- **Only these files may exist — NO OTHER FILES:**
  - `index.html` — the entire app (HTML + CSS + JS in one file, all deps inline
    from CDN with pinned versions).
  - `.github/workflows/deploy.yml` — GitHub Pages deploy.
  - `CLAUDE.md` — this file.
  - (plus the `.git/` repo itself)

## How it works
- Input is a Google Sheet **published to the web** (its `pubhtml` URL). The URL is
  entered in the **Input** tab; it is remembered in `localStorage` (`STORE_KEY`)
  across reloads. First-ever load falls back to the `DEMO` constant. **No URL
  params** — `load(db)` re-fetches in place when the user clicks Load.
- The `pubhtml` URL is converted to a CSV endpoint (`/pub?...&output=csv`), which
  Google serves with `Access-Control-Allow-Origin: *`, so the page `fetch()`es it
  directly — **no CORS proxy**.
  - Caveat: opening `index.html` via `file://` gives an opaque (null) origin and
    browsers block the fetch ("Failed to fetch"). Must be served over http(s)
    (localhost or the deployed Pages URL). The error banner says so.
- Column **0 is the name**. Every later column that has a **header label**
  (e.g. `Current`, `All Time`, dated snapshots) becomes a selectable dataset.
  A segmented toggle in the **Balances** tab switches which column drives both
  the table and the graph (labels come straight from the sheet header — change
  them in the sheet, not the code). Defaults to the first labeled column.
  Blank/non-numeric cells in a column count as `0`; a `Total` row is skipped.
  If no header labels exist (old single-column format), it falls back to one
  `Balance` column and shows no toggle.
- Amounts support `$`, commas, `(123)` and `-` negatives, and cents.
- Asserts the balances net to `$0` within `EPS` (< 1 cent); otherwise shows an
  error and suppresses the graph.

## Algorithm (in `computeTransfers`) — strict lexicographic objective
1. **Fewest transfers** = `n − k`, where `k` = max number of disjoint zero-sum
   subgroups. Found with a bitmask DP over subsets (exact up to `MAX_EXACT_N`
   active people; greedy fallback above that). Each atomic subgroup then settles
   with exactly `size−1` edges = a spanning tree; each tree edge's amount and
   direction are fully determined by the subtree balance sum.
2. **Fewest pass-through nodes**: among all spanning trees, prefer ones with the
   fewest nodes that have *both* an incoming and an outgoing edge (a node that is
   just a money proxy, e.g. `A→B→C`). We'd rather `A→B, A→C`.
3. **Largest minimum transfer**: tie-break by maximizing the smallest edge amount.
   Enumerated over all spanning trees via Prüfer sequences (up to `MAX_TREE_S`);
   `treeAmounts` returns `{detailed, minAmt, passThrough}` and `bestSpanningTree`
   selects lexicographically (passThrough asc, then minAmt desc).

## Dependencies (pinned CDNs, inline in `index.html`)
- `d3@7.9.0` — DOM/selection, colors, interactivity.
- `@hpcc-js/wasm@2.34.2` — Graphviz WASM engine.
- `d3-graphviz@5.6.0` — renders **DOT → SVG** (this is the DOT rendering library).
- `papaparse@5.5.4` — CSV parsing.

## UI
- **Balances** card with tabs: **Balances** (pretty table; each name has a
  deterministic Tableau10 color shown as a dot) and **Input** (URL field + Load
  button + Open link + the live sheet `<iframe>`).
- **Transfers** card with tabs: **Graph** (DOT digraph via d3-graphviz) and
  **DOT** (the raw DOT source). Clicking a table row or a graph node highlights
  the matching node. There is no textual transfer list — the graph is it.
- Page heading + `document.title` use the sheet's name, read best-effort from the
  pubhtml `<title>` (`fetchSheetTitle`, strips the `- Google Drive`/`Sheets`
  suffix). Separate fetch from the CSV; may be CORS-blocked → falls back to
  "Group IOU". Non-blocking, never delays the data render.
- Minimal chrome: no success banner, no Net row (net is only checked internally).
- Mobile-friendly: responsive layout, scrollable table, fluid SVG.

## Deploy
- `.github/workflows/deploy.yml` uses the official Pages flow
  (`configure-pages` → `upload-pages-artifact` → `deploy-pages`) on push to `main`.
- **Repo setting required:** Settings → Pages → Source = **GitHub Actions**.
- Remote: `https://github.com/pathikrit/group_iou`.

## Local testing
- Serve over HTTP (not `file://`, which breaks fetch/CORS):
  `python3 -m http.server` then open `http://localhost:8000/`.
