# platform/frontend — adherence audit

Read against `src/app/globals.css` (1325 lines), `src/app/layout.tsx`, `src/components/site-header.tsx`, `site-footer.tsx`, `status-pill.tsx`.

## Already correct — no work needed

The gazette language is implemented. `layout.tsx` loads Bodoni Moda, EB Garamond, Marcellus and Archivo through `next/font` and maps them to `--display / --body / --font-name / --mono` on `body`. The second `:root` (line ~1047) carries the exact system palette: paper `#f7f4ea`, deep paper `#e9e5d7`, ink `#171512`, muted `#5c5648`, hairline `#cfc8b4`, vermillion `#8c2f1d`. Rule weights are right throughout — 3px double on the masthead, footer and page breaks; 2px on section and table heads; 1px hairline on rows. `.directory-row`, `.book-row`, `.allotment-grid`, `.gazette-calendar-event`, `.about-columns`, `.lead-issue` and `.gazette-columns` reproduce the design's grids track-for-track, including the 1px ink column divider. Company names use `--font-name` (Marcellus) in every list. Cover bars are flat ink. Vermillion is used only on kickers, deadlines and `.book-row` change cells.

So the remaining items are consolidation and fidelity, not implementation.

## 1. Legacy layer to delete (~700 lines, lines 1–1045)

The file is two design systems stacked. The first `:root` still declares the pre-gazette palette — `--ink: #18211d`, `--green: #1d6048`, `--orange: #bc542f`, `--display: Georgia`, `--body: var(--font-source-sans)` — and is overridden 1000 lines later. Note `--font-source-sans` is no longer loaded by `layout.tsx`, so that declaration is dead.

Candidates for removal, all superseded or unreferenced by the gazette markup:

- `.offer-structure`, `.application-desk`, `.bid-ticket`, `.investor-lane`, `.market-context` — the old "application workbench".
- `.company-overview` and its rail, `.rhp-analysis`, `.rhp-thesis-grid`, `.growth-case`, `.risk-register`, `.financial-ledger`.
- `.newspaper-trial` — the earlier per-page newspaper experiment, now neutralised to `border: 0; background: transparent` at line ~1300. The whole 120-line block plus its three media-query overrides can go.
- `.hero`, `.stats-strip`, `.paper-panel`, `.editorial-row`, `.section-block`.
- The keyframes: `timeline-draw`, `timeline-progress-in`, `timeline-step-in`, `timeline-today-in`, `timeline-pulse`, `demand-fill`. The system has no motion.

Before deleting, grep each class name across `src/app` and `src/components` — `ipo-timetable.tsx`, `offer-structure.tsx`, `rhp-analysis.tsx` and `subscription-momentum.tsx` still render some of them, so those four components need converting to gazette geometry first (tables and ruled rows, per `ui_kits/gazette/IssueRecord.jsx`).

## 2. Motifs that violate the system, still live in the legacy layer

- Hard offset shadows: `6px 6px 0 var(--orange)` on `.button-primary`, `10px 10px 0` on `.application-desk`, `7px 7px 0` on `.financial-ledger`, `18px 22px 0` on `.newspaper-trial`. The only shadow in the system is the sheet's.
- `border-radius: 50%` on `.desk-step`, `.ticket-marker`, `.live-dot`, `.ipo-timeline-marker`. Radius is 0 everywhere; sequence numbers are Archivo `01`–`06`.
- Gradients: the radial in `.rhp-analysis`, the `repeating-linear-gradient` in `.ticket-price`, the one in `.grain`.
- Colour-tinted panels: `.growth-case { background: #416d5a }`, `.lane-chance { background: var(--green-light) }`.
- `.grain` — still rendered by `layout.tsx` at `opacity: .16`. The system has no texture overlays; delete the rule and the `<div className="grain">`.
- `.status-open / -upcoming / -listed / -closed` keep tinted fills (`--green-light`, `#efe2c9`, `--orange-light`). The system sets status as bare tracked type, Closed and Listed dropping to `--muted`. `status-pill.tsx` needs no prop change — just restyle `.status`.

## 3. Token consolidation

Append `integration/gazette-tokens.css` to the gazette `:root`. It names the greys and the field paper that currently appear as raw hex in ~14 rules (`#3b362c` ×6, `#4a4438` ×3, `#2c2822` ×2, `#fdfbf4`). Then retire `--orange-light`, `--green` and `--green-light` — the system has one accent and tints with `--paper-deep`.

## 4. Type fidelity (the one place values drift)

The system's display and label tokens are weight 400 (700 only on the masthead `GAZETTE`). Your gazette rules set 500 and 600 fairly widely:

| Rule | Current | System |
| --- | --- | --- |
| `.gazette-briefs strong` | `600 30px` | `400 30px` |
| `.gazette-page > h1` | `500 54px` | `400 54px` |
| `.lead-ledger dd` | `600 19px` | `400 20px` |
| `.book-row … strong` | `500 22px` | `400 22px` |
| `.gazette-calendar-day time strong` | `500 38px` | `400 38px` |
| `.site-header .desktop-nav` | `600 10px / .16em` | `400 11px / .18em` |
| `.gazette-filters a` | `500 10px / .16em` | `400 10px / .16em` ✓ size |

Bodoni at 500–600 optically thickens the whole page against the reference. Also `.page-title h1` and `.lead-copy h1` apply `letter-spacing: -.025em`; the system sets none on display type.

## 5. One open decision: the sheet

The design is a sheet floating on a darker desk — `--desk: #ddd6c4`, 1180px max, 1px ink border, `0 26px 60px rgba(0,0,0,.3)`. Your build deliberately went full-bleed instead: `html, body { background: var(--paper) }` and `.page-shell { width: 100%; border: 0; box-shadow: none }`.

That is a defensible web adaptation and I have not "fixed" it. If you want the sheet back:

```css
html, body { background: var(--desk); }
.page-shell {
  width: min(1180px, 100%);
  margin: 26px auto 70px;
  padding: 26px 30px 40px;
  background: var(--paper);
  border: 1px solid var(--ink);
  box-shadow: 0 26px 60px rgba(0,0,0,.3);
}
```

Mobile already collapses it (the 820px query zeroes the padding and border), so the change is desktop-only.

## Order I'd do it in

1. Append the token block; replace the ~14 hardcoded hexes.
2. Type weights 500/600 → 400, drop the negative letter-spacing on display type.
3. Restyle `.status` to bare type; delete `.grain` and its div.
4. Convert `ipo-timetable.tsx`, `offer-structure.tsx`, `rhp-analysis.tsx`, `subscription-momentum.tsx` to gazette tables (reference `ui_kits/gazette/IssueRecord.jsx` and `Subscription.jsx`).
5. Delete lines 1–1045 and the first `:root`, then the keyframes.
6. Decide the sheet.

## Reference in this design system

- `ui_kits/gazette/IssueRecord.jsx` — the target geometry for the detail page's timetable, application sizes, key-details sidebar and pool table.
- `ui_kits/gazette/Subscription.jsx` — cover bars with bids, reserved shares and change.
- `guidelines/type-display.card.html`, `type-label.card.html` — the weights and tracking in point 4.
- `guidelines/rules-borders.card.html` — the four rule weights, for the deletions in point 2.
