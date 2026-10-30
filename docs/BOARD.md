# The board: one snapshot, three renderings

The desk produces one board snapshot per scan and renders it three ways. They must agree; when they do not, the
snapshot is wrong, not the renderer.

| Surface | Where | Produced by | Freshness |
| --- | --- | --- | --- |
| **Card** | chat, one fenced block | `SOUL.md` rules, or `rgtriage board` for the exact copy | the scan it was built from |
| **Page** | `board.html`, self-contained | `rgtriage board --html`; every scan writes it too | static, stamped with snapshot and generation time |
| **Dashboard tab** | `/board` in the Hermes dashboard | `rg-board` plugin serving the page file | polls the scan time; **Refresh now** forces a scan |

## The card

46 columns, one fenced block, in this order:

```
● LIVE  REMEDIGENIUS · <installation>
as of HH:MM UTC · <age>
──────────────────────────────────────────────
OPEN   <n> P1 · <n> P2 · <n> P3 · <n> P4
P1  <n>  <bar>
P2  <n>  <bar>
P3  <n>  <bar>
P4  <n>  <bar>
──────────────────────────────────────────────
CHANGE <+N new · M urgent · K cleared>
──────────────────────────────────────────────
COVERAGE  <read>/<known> accounts · <read>/<enabled> regions
          <the gap that matters>
──────────────────────────────────────────────
FIXES     <fixes in flight>            (omitted when there are none)
──────────────────────────────────────────────
NEXT      <one item> (<priority>)
          "why <ref>" · "fix <ref>"
```

Rules that are not cosmetic:

- **Every number is copied from the scan.** A value that is not available drops its line; nothing is estimated.
- **The bars are scaled, and the number is the count.** `P3  44  ████████████` — not 44 blocks, and not 12 written
  in the number column.
- **`COVERAGE a/b` is read over known**, where `b` includes accounts the desk cannot read. One readable account and
  three not covered is `1/4`, never `1/1`.
- **The state word is a claim.** `● LIVE` inside six hours, `○ STALE` after it (and then the card says
  `NOT CURRENT OPERATIONAL STATE.` with the age), `◌ DAY ONE` when there is no scan.
- **No score.** P1–P4, verified fixes and coverage are facts; a 0–100 number would hide both coverage and staleness.

The prompt version lives in `SOUL.md`; `rg-triage` defers to it. The exact version is `rgtriage board`, which is what
`/triage` should call once the command is registered with the desk.

## The page

`rgtriage board --html [PATH]` writes a single self-contained HTML file: KPI tiles, severity distribution,
needs-a-decision, verified fixes, and the coverage matrix. It has no external assets, no scripts and a print
stylesheet. Every scan writes `board.html` next to `report.html`.

It is **static on purpose**. The header carries the snapshot id and the scan time; the footer says "static snapshot"
and when it was generated. A page that says when it was true cannot pretend to be live.

## The Dashboard tab

`profiles/remedigenius/dashboard-plugins/rg-board` is a dashboard plugin:

- `dashboard/plugin_api.py` serves `/api/plugins/rg-board/page` (the page file, `Cache-Control: no-store`),
  `/status` (scan time and age from `status.json`) and `POST /refresh`.
- `dashboard/dist/index.js` registers the tab, frames the page, shows the scan age and a **Refresh now** button.
- `POST /refresh` asks the desk over its Unix socket for `scan --quiet` — a real collection run of every configured
  account, region and source — and refuses to report success unless `scanned_at` moved. A concurrent request gets 409.

Freshness has two sources:

1. `remedigenius-scan.timer` scans every six hours (the interval is the installation's).
2. **Refresh now** runs the same scan immediately; the open tab also polls `/status` every 60 seconds and swaps the
   iframe when the snapshot changes.

The button can sit in "Scanning all sources…" for minutes because the scan is AWS-bound (measured ~4 minutes on
`rgce-private` against scheduled runs of ~45 seconds). It is not a page reload.

## Limits

- The page is a snapshot; only the tab's status poll makes it feel live, and only between scans.
- A campaign lifecycle, a trend sparkline and a shareable PDF are not part of this surface yet.
- The dashboard process holds no AWS credentials: it reads a file the desk wrote and asks the desk to scan. That is the
  boundary, and it should stay that way.
- The workstation path needs the desk paths in `local.json`; the host and workstation installers write them.