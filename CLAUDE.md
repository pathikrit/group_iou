# Group IOU — notes for Claude

Zero-backend single-page app: reads a published Google Sheet of net balances and
draws the fewest money transfers to settle up, as an interactive DOT graph.

## ⛔ RULES
- **Never `git commit`/`push` without an explicit go-ahead each time.** (Editing
  files freely is fine.)
- **Only these files may exist:** `index.html` (whole app — HTML+CSS+JS inline,
  all deps from pinned CDNs), `.github/workflows/deploy.yml`, `CLAUDE.md`, `.git/`.
  NO other files.

## Deps (pinned CDNs in `index.html`)
- `bootstrap@5.3.3` (CSS + bundle JS) — UI framework. `<html data-bs-theme="dark">`;
  the small `<style>` block only overrides the palette (darker than BS default) and
  styles the graph/chips. Use Bootstrap components/utilities, not hand-rolled CSS.
- `bootstrap-table@1.27.3` (+ its CSS) drives the **Balances table** — sortable
  columns (#, Name chip, Balance), init in `initBalTable`, rows loaded in
  `renderTable` via `bootstrapTable('load', …)`. Requires **`jquery@3.7.1`** (load
  order: jQuery → bootstrap bundle → bootstrap-table). jQuery is ONLY for
  bootstrap-table; use d3 for everything else.
- `d3@7.9.0`, `@hpcc-js/wasm@2.34.2`, `d3-graphviz@5.6.0` (DOT→SVG), `papaparse@5.5.4`.
- Tabs use Bootstrap's tab plugin (`data-bs-toggle="tab"`); switch programmatically
  via `showTab(id)`. Dataset toggle = rounded-pill buttons (`#dsToggle`). Status
  banner = a Bootstrap `.alert` (`setStatus`).

## Data flow (`load` → `applyCsv` → `showDataset`)
- Sheet is the pubhtml URL, entered in the **Input** tab; remembered in
  `localStorage[STORE_KEY]`. First run uses `DEMO`. **No URL params.**
- pubhtml → CSV via `toCsvUrl` (`/pub?...&output=csv`); Google sends
  `Access-Control-Allow-Origin: *` so we fetch directly (no proxy).
  - `file://` (null origin) is blocked by browsers → must serve over http(s); the
    error banner says so. (Can't test CORS in the sandbox — no network for Bash.)
- **Caching = stale-while-revalidate** (`load`): render cached CSV
  (`localStorage['iou_csv:'+csvUrl]`) instantly, then fetch fresh and re-render only
  if the string differs; on network error with a cache, keep the cached view.
  Sheet title cached the same way (`iou_title:`+db). Selected column preserved when
  data is unchanged.
- Parsing (`applyCsv`): col 0 = name; every later column **with a header label**
  (e.g. `Current`, `All Time`, dates) is a selectable dataset → segmented toggle in
  Balances that re-drives table + graph. Labels come from the sheet header (change
  there, not in code). Blank/non-numeric cell = `0`; `Total` row skipped. No labels
  (old format) → single `Balance` column, no toggle.
- Amounts: `$`, commas, `(123)`/`-` negatives, cents. Asserts net `$0` within `EPS`;
  else error + no graph.

## Algorithm (`computeTransfers`) — three constraints, applied strictly in order
The code MUST follow these exactly; keep the matching comment in `computeTransfers`.
1. **Constraint 1 — fewest edges (fewest transfers).** `= n − k`, `k` = max number
   of disjoint zero-sum subgroups (bitmask DP in `maxZeroSumPartition`; exact ≤
   `MAX_EXACT_N`, greedy fallback above). Each atomic subgroup then settles as a
   spanning tree (`size−1` edges); each edge's amount+direction is fixed by its
   subtree balance sum.
2. **Constraint 2 — of those, fewest proxy nodes.** A proxy = a node with *both* an
   incoming and an outgoing edge. Prefer `{A→B; A→C}` over `{A→B→C}` (in the chain B
   just relays A's money to C; rather have A make 2 direct transfers).
   - NB: this is "both in AND out", **not** "any outgoing edge". The latter (counting
     senders) was tried and rejected — it leaves *debtor* proxies in place (a debtor
     is already a sender, so relaying through it is free), e.g. the demo collapsed to
     a `Nate→Rick→Linh→…` chain. Counting proxies avoids that. (User confirmed.)
3. **Constraint 3 — of those, maximize the smallest transfer** (avoid tiny payments).

`bestSpanningTree` enumerates all spanning trees via Prüfer sequences (≤ `MAX_TREE_S`);
`treeAmounts` returns `{detailed, minAmt, proxies}`; selection is lexicographic
(proxies asc, then minAmt desc).

## UI specifics
- **Balances** card is tabbed: **Balances** (table + dataset toggle) / **Input**
  (URL + iframe). **Transfers** card just shows the graph (no tabs); the raw DOT is
  behind a little ⓘ button (`#dotToggle`) at the graph box's bottom-right, which
  toggles a `#dotSource` overlay. No textual transfer list — graph only.
- Amounts (balances + transfers) display in **dollars** (`moneyWhole`).
- Node label = 3 rows (HTML-like DOT label): emoji(s) / name / $amount (`POINT-SIZE 8`).
  Emojis (`emojiFor`): rank 👑/🥈/💩 + magnitude tier 🍾🥳😁😅 / 🤷 / 😓😫😭😱, where
  the tier is chosen by the balance as a **% of the pot** (`totalPot` = sum of
  positive balances) so it scales with stakes; thresholds 5/15/30/50%.
- Click row or node → highlight that node + its edges + neighbors, dim the rest
  (`applyGraphSelection`, `selecting`/`keep`/`hl` classes; edges get DOT `id=edge-N`).
  Click graph blank space → `clearSelection`. Colors keyed by row index (stable
  across columns).
- Heading = sheet name (`fetchSheetTitle`, best-effort, may be CORS-blocked →
  "Group IOU"); heading links to the sheet; GitHub icon top-right.

## Deploy / test
- `deploy.yml`: official Pages flow on push to `main`. **Repo setting:** Settings →
  Pages → Source = **GitHub Actions**. Remote: `github.com/pathikrit/group_iou`.
- Local: `python3 -m http.server` → `http://localhost:8000/` (not `file://`).
- Sanity after JS edits: extract last `<script>` and `node --check` it.
