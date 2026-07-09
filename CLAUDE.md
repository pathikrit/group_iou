# Group IOU — notes for Claude

Zero-backend single-page app: reads a published Google Sheet of net balances and
draws the fewest money transfers to settle up, as an interactive DOT graph.

## ⛔ RULES
- **NEVER run `git commit`, `git push`, `git reset`, `git revert`, or any other git
  write/history command unless the user, in their MOST RECENT message, explicitly
  told you to.** Editing files locally is always fine; touching git is not.
  - An explicit instruction means the current message literally says so (e.g.
    "commit", "commit & push", "push"). If it doesn't, you do NOT have permission —
    finish the edits and STOP, then say the changes are ready and ask whether to commit.
  - **Each git instruction is single-use and applies ONLY to that one turn.** A
    "commit & push" three messages ago (or anywhere earlier in the chat) is NOT
    standing permission — those were one-off checkpoints, not a default workflow.
    Do not infer "they'll probably want this pushed." When unsure, the answer is no.
  - This is the #1 rule. A pattern of prior pushes never overrides it.
- **Only these files may exist:** `index.html` (whole app — HTML+CSS+JS inline,
  all deps from pinned CDNs), `calculator/` (exactly `poker.py`, `odds.json`,
  `Makefile` — see "Odds tab"), `.github/workflows/deploy.yml`, `CLAUDE.md`,
  `.git/`. NO other files.

## Deps (pinned CDNs in `index.html`)
- `bootstrap@5.3.3` (CSS + bundle JS) — UI framework. `<html data-bs-theme="dark">`;
  the tiny `<style>` block is deliberately minimal — a darker palette (via Bootstrap's
  own `--bs-*` CSS variables, its theming hook), the Graphviz SVG internals (no
  Bootstrap equivalent), and the Transactions scroll/sticky-header + graph
  min-height/width. **Font sizes are left to Bootstrap defaults; everything else must
  be Bootstrap components/utilities — do not hand-roll CSS or font sizing.**
- `bootstrap-table@1.27.3` (+ its CSS) drives the **Balances table** — sortable
  columns (#, Name chip, Balance), init in `initBalTable`, rows loaded in
  `renderTable` via `bootstrapTable('load', …)`. Requires **`jquery@3.7.1`** (load
  order: jQuery → bootstrap bundle → bootstrap-table). jQuery is ONLY for
  bootstrap-table; use d3 for everything else.
- `d3@7.9.0`, `@hpcc-js/wasm@2.34.2`, `d3-graphviz@5.6.0` (DOT→SVG), `papaparse@5.5.4`.
- `nouislider@15.8.1` (CSS + JS) — ONLY for the Odds-tab player-count slider (value
  shown on the thumb, which Bootstrap's `form-range` can't do).
- Tabs use Bootstrap's tab plugin (`data-bs-toggle="tab"`); switch programmatically
  via `showTab(id)`. **Tab deep-links:** the URL *hash* selects a tab
  (`#balances`/`#transactions`/`#odds`/`#input`, `TAB_BY_HASH`/`HASH_BY_TAB`) so a tab
  is directly linkable. Showing a tab writes the hash back (`history.replaceState` — no
  history spam / no `hashchange` loop); `pendingHash` is applied via `applyPendingHash`
  as soon as the target tab is *visible* (retried from `renderTable` once `tableCard`
  shows, and from `setPokerMode` once the Odds tab appears). This is nav state only —
  **not** a data-source param (the hash is separate from the "No URL params" rule below).
  Dataset toggle (`#dsToggle`, `renderDatasetToggle`): IOUs/All
  Time as `btn-lg rounded-pill` CTA buttons, then dated columns rightmost-first in a
  Bootstrap `.btn-group`, overflow (> `MAX_DATED_PILLS`) in a **nested `.btn-group`
  dropdown** ("More"); active state via `markActiveDataset`. Status banner = a
  Bootstrap `.alert` (`setStatus`). Net toggle = a Bootstrap `.form-switch`.

## Data flow (`load` → `applyCsv` → `showDataset`)
- Sheet is the pubhtml URL, entered in the **Input** tab; remembered in
  `localStorage[STORE_KEY]`. First run uses `DEMO`. **No URL params** for the data
  source (the URL *hash* is used only for tab deep-links — see Tabs above).
- pubhtml → CSV via `toCsvUrl` (`/pub?...&output=csv`); Google sends
  `Access-Control-Allow-Origin: *` so we fetch directly (no proxy).
  - `file://` (null origin) is blocked by browsers → must serve over http(s); the
    error banner says so. (Can't test CORS in the sandbox — no network for Bash.)
- **Caching = stale-while-revalidate** (`load`): render cached CSV
  (`localStorage['iou_csv:'+csvUrl]`) instantly, then fetch fresh and re-render only
  if the string differs; on network error with a cache, keep the cached view.
  Sheet title cached the same way (`iou_title:`+db). Selected column preserved when
  data is unchanged.
- Parsing (`applyCsv`): the sheet may stack **two tables** in one tab — a balances
  block on top, then a settlement **ledger** whose header row is
  `From, To, Date, Amount` (blank separator rows are already dropped by
  `skipEmptyLines`). Split at the first `from`/`to` header row; everything above =
  balances, below = ledger.
  - Balances block: col 0 = name; every later column **with a header label**
    (dated snapshots like `9-Jun`) is a dataset. Labels come from the sheet header
    (change there, not in code). Blank/non-numeric cell = `null` (absent that
    column → hidden); `Total` row skipped. No labels (old format) → single
    `Balance` column, no toggle.
  - Ledger → `transactions` `[{from, to, date, amount}]`. **When a ledger exists**,
    two **virtual datasets are prepended**: **`All Time`** = per-person sum of the
    dated columns (base owed, ignoring settlements), and **`IOUs`** = All Time
    after applying the ledger (each transfer: payer `+amount`, payee `−amount`) =
    what's still outstanding. Both are unshifted onto every
    `rawPeople[i].values[]` so the index-based `showDataset(idx)` is unchanged.
    **`All Time` is the default selected column** until the user clicks a pill
    (`userPicked` flag; then their choice persists across revalidation). A name
    only in the ledger (not in any dated column) still gets a row (`All Time` = 0).
    Toggle order: `IOUs | All Time | <dates…>` (`IOUs`/`All Time` render as larger
    CTA pills). No ledger → legacy behavior (no computed columns, no Transactions
    tab).
- Amounts: `$`, commas, `(123)`/`-` negatives, cents. Asserts net `$0` within `EPS`;
  else error + no graph. (Both base and ledger are net-zero, so `IOUs`/`All Time`
  stay net-zero.)

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
- **Balances** card is tabbed: **Balances** (table + dataset toggle) /
  **Transactions** (the parsed ledger — a second bootstrap-table `#txnTable`,
  `initTxnTable`/`renderTxnTable`; From/To name chips colored per-person via
  `colorForName`/`nameChip`; tab hidden via `d-none` when no ledger) / **Input**
  (URL + iframe). **Transfers** card just shows the graph (no tabs) — no textual
  transfer list, graph only. It's **never shown while the Input tab is active**: the
  `shown.bs.tab` on `#tab-input` hides it (`d-none`), and every reveal goes through
  `showGraphCard()` which no-ops when `#tab-input` is `.active` — so re-renders (e.g.
  toggling poker mode) can't pop it back open. The bal/txn tabs re-render & re-show.
- **The Transfers graph follows the active tab** (`graphMode`, switched by
  `shown.bs.tab` on `#tab-bal`/`#tab-txn`): on **Balances** it's the *settlement*
  graph (`renderBalGraph` → `computeTransfers`, name+balance+emoji nodes); on
  **Transactions** it's the *raw ledger* graph (`renderTxnGraph`/`txnGraphData`) —
  **no settlement algorithm**, just the ledger summed per directed `(from,to)` pair
  (a dense all-pairs graph is fine), `$0` edges dropped, name-only nodes.
  `buildDot`/`applyGraphSelection` operate on `graphNodes` (the nodes currently
  drawn) so highlight/selection work in both modes.
- **Net toggle** (`#netToggle`, `txnNet`, shown only in the txn graph via
  `#netToggleWrap`): on (default) collapses each pair to a single edge in the
  surplus direction (`A→B` minus `B→A`); off keeps both directions (≤2 edges/pair).
  Edges are always positive `from→to`; a pair that evens out shows no edge.
- **Balances table medals** (`renderTable`, suffixed after the name chip): each
  dated column ranks its people and tags 🥇 #1 / 🥈 #2 / 💩 last (`tableMedal`); IOUs
  gets none. **All Time** instead shows each person's medals *accumulated* across all
  dated columns (`accumulatedMedals`/`medalString`, sorted 🥇→🥈→💩, a kind with >5
  collapsed to e.g. `🥇×11`). All Time also adds an **Average** column (balance ÷
  `seenCount` = #dated columns the person appears in; shown via bootstrap-table
  `showColumn`/`hideColumn`), and the **highest-average person gets a 👑** prefixed
  to their medal suffix.
- **Poker mode** (`pokerMode`, `#pokerToggle` 🃏 `.form-switch` next to Load in the
  **Input** tab): a win/loss framing, on by default when the **sheet
  title matches `/poker/i`** (`setTitle`); manual toggle sticks via `pokerUserSet`
  (mirrors `userPicked`), and `setPokerMode` syncs the switch + re-renders the table
  & balance graph. When **off**: (1) **no ranking emojis** (🥇/🥈/💩 medals + 👑
  crown) anywhere — the single gate is **`rankEmoji(rank,count,gold)`** (returns ''
  unless poker; `gold` = 👑 in the graph, 🥇 in the table), which both `emojiFor` and
  `tableMedal` delegate to, so no caller branches on `pokerMode`; magnitude/👻/🤷
  emojis stay; (2) no Average column and All Time sorts by balance like a dated
  column (`showAverage = isAllTime && pokerMode`); (3) `moneySigned` shows plain
  `+`/`-` signs instead of the triangles. Conversely, **when on**, `renderGraph`
  calls `decoratePokerChips(svg)` to overlay each node circle with **poker-chip edge
  spots** — 8 chunky contrasting arcs (a wide `stroke-dasharray` circle) just inside
  the rim + a thin inner "face" ring, both `stroke=textOn(fill)`. Drawn in raw SVG
  (Graphviz can't do chunky segments — its `dashed` looks like fine stitching),
  inserted between the ellipse and the text so name/amount stay readable; re-applied
  on every render since the SVG is regenerated.
- Amounts (balances + transfers + Average) display in whole **dollars**
  (`moneyWhole`, rounded, no cents); Average keeps full precision for sorting.
  Signed balances (table Balance/Average + graph node $) use `moneySigned`: in poker
  mode a **text-glyph ▲/▼** prefix (not emoji, so it inherits the number's color —
  green up / red down in the table); otherwise `+`/`-` (positives get a `+`). Exact
  $0 gets no prefix. Transfer/ledger amounts stay unsigned (`moneyWhole`).
- Node label = 3 rows (HTML-like DOT label): emoji(s) / name / $amount (`POINT-SIZE 8`).
  Emojis (`emojiFor`): rank 👑/🥈/💩 + magnitude tier 🍾🥳😁😅 / 🤷 / 😓😫😭😱, where
  the tier is chosen by the balance as a **% of the pot** (`totalPot` = sum of
  positive balances) so it scales with stakes; thresholds 5/15/30/50%. **Exact $0**
  (present, evened out) → 👻 (distinct from near-zero nonzero 🤷). **Missing** people
  (empty cell, not in `people`) show nothing.
- Graph shows everyone present, incl. exact-$0 nodes (no transfer edges). $0 nodes
  are pushed to the bottom by an invisible edge from a creditor to each (plain
  `rank=sink` doesn't work — they're disconnected). Missing people aren't drawn.
- Click row or node → highlight that node + its edges + neighbors, dim the rest
  (`applyGraphSelection`, `selecting`/`keep`/`hl` classes; edges get DOT `id=edge-N`).
  Click graph blank space → `clearSelection`. Colors keyed by row index (stable
  across columns).
- Heading = sheet name (`fetchSheetTitle`, best-effort, may be CORS-blocked →
  "Group IOU"); heading links to the sheet; GitHub icon top-right.

- **Odds tab** (`#tab-odds`/`#pane-odds`, in the Balances-card tab bar; `d-none`
  unless poker mode — gated in `setPokerMode`, which kicks back to Balances if the
  tab was active when the mode turns off): pre-flop win % of the 169 canonical
  hold'em starting hands vs N−1 random opponents. Data = `calculator/odds.json`
  (`{ "AKs": [p2..p10], … }` in percent), generated ONCE by `calculator/poker.py`
  (uv single-file script, 1M Monte-Carlo deals/cell ≈ ±0.1pp, `make odds` in
  `calculator/`, ~15 min) and checked in — the tab lazy-fetches it on first show
  (`showOdds`). UI (`buildOddsDom`/`renderOdds`): 13×13 grid (pairs on the
  diagonal, suited upper-right, offsuit lower-left, A→2 header row/col) + a
  rank-ordered table (Rank/Hand/Win %) in a left panel exactly as tall as the grid
  (absolute + `overflow-y:auto`); noUiSlider for player count (2–10, value on the
  thumb); color-scale pill = Bootstrap `btn-check` radio group — **Relative**
  (percentile rank among the 169 hands → hue 0° red…120° green) vs **Break-even**
  (log₂-scaled vs the 1/players fair share, yellow at exactly break-even; the pill
  label shows the current break-even %). Plain-English hovers everywhere
  ("Pair of 7s", "Ace-King Suited") via ONE delegated `bootstrap.Tooltip`
  (`animation:false, delay:0` — instant, per user demand). Like Input, showing the
  tab hides the Transfers graph card. No text slop: no captions, footers, or legends.
  **Font:** `#pane-odds` is pinned to **Inter** even in poker mode — the Special Elite
  casino face is too hard to read for a dense grid of numbers.

## TODO / future ideas
- **Link heading to the editable sheet when possible.** Today `appTitle.href = db`
  (the pubhtml URL). For a *normal* `/spreadsheets/d/<ID>/…` link we could extract
  `<ID>` (regex `/spreadsheets/d/(?!e/)<ID>/`) and point the heading at
  `…/d/<ID>/edit#gid=<gid>`. NOT derivable for the "publish to web"
  `/d/e/2PACX-1v…/pubhtml` form (incl. the DEMO): that `2PACX-1v…` token is an
  opaque, one-way publish ID with no client-side mapping to the real doc ID — so
  for publish-form links keep linking to the published view. (Going further would
  mean accepting `/d/<ID>/` URLs as a data source via `export?format=csv`/`gviz`,
  but those have flakier CORS than `pub?output=csv` and need link-sharing.)

## Deploy / test
- `deploy.yml`: official Pages flow on push to `main`. **Repo setting:** Settings →
  Pages → Source = **GitHub Actions**. Remote: `github.com/pathikrit/group_iou`.
  - It's a **pure static upload** (`upload-pages-artifact` with `path: .`) — it does
    **NOT** build anything, so `calculator/odds.json` (checked in) is served as-is at
    `<site>/calculator/odds.json` (the Odds tab fetches that relative path). CI never
    runs `poker.py`; regenerating `odds.json` is a **one-time local** `make odds` in
    `calculator/` (~15 min), then commit the new JSON.
- Local: `python3 -m http.server` → `http://localhost:8000/` (not `file://`).
- Sanity after JS edits: extract last `<script>` and `node --check` it.
