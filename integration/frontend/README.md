# Drop-in files for platform/frontend

Copy each file to the path below, then `npm run build` (or restart the dev server).

| Copy this | To |
| --- | --- |
| `globals.css` | `src/app/globals.css` (full replacement) |
| `app/layout.tsx` | `src/app/layout.tsx` |
| `app/ipo/-slug-/page.tsx` | `src/app/ipo/[slug]/page.tsx` (the folder is named `-slug-` here because this project can't hold `[` in a path) |
| `components/ipo-timetable.tsx` | `src/components/ipo-timetable.tsx` |
| `components/offer-structure.tsx` | `src/components/offer-structure.tsx` |
| `components/rhp-analysis.tsx` | `src/components/rhp-analysis.tsx` |

## What changed

**globals.css** — rewritten from 1325 lines to ~430. The legacy palette and the entire pre-gazette layer are gone (`.offer-structure`, `.application-desk`, `.bid-ticket`, `.company-overview`, `.rhp-analysis`, `.financial-ledger`, `.risk-register`, `.ipo-timeline`, `.newspaper-trial`, `.hero`, `.stats-strip`, `.demand-*`, all keyframes, the `.grain` texture, every offset shadow, every `border-radius`, both gradients, the tinted status pills, the second accent). Every class the surviving pages use is kept with the same name and the same geometry, retuned to the design system: display type back to weight 400, labels to Archivo at 9–11px / .10–.20em, one accent, four rule weights.

**layout.tsx** — drops the `<div className="grain">` overlay. Fonts unchanged.

**ipo/[slug]/page.tsx** — rebuilt as the design's issue record, in this order: breadcrumb → name + status/listing with price-band aside (3px double rule) → company-at-a-glance panel on deep paper → two columns (timetable + valid application sizes | key details, filed documents, source trail, disclaimer) split by a 1px ink rule → "Shares reserved for you" pool table → prospectus dossier (financials reversed on ink, use of funds | growth case, risk rows) → "The book, in motion" strip with the overall cover figure and a link to the subscription page.

Removed from that page: the market-edition strip, the `newspaper-deck` three-up, the hero illustration, the `live-book` section and the `SubscriptionMomentum` chart. The design carries live demand as the closing strip plus the dedicated subscription page — no chart on the record.

**ipo-timetable.tsx** — six numbered rows (`01`–`06`, label, date, vermillion "Estimated" tag). No progress bar, no today marker, no animation, so it is now a server component; the `initialToday` prop is gone.

**offer-structure.tsx** — exports `ApplicationSizes` (left-column table) and `ReservedPools` (full-width pool table) instead of `OfferStructure`. All allotment-estimate maths is unchanged, including the bid-volume floor.

**rhp-analysis.tsx** — same two exports, same props. `CompanyOverview` is now the glance panel (profile / products / two figures); `RhpAnalysis` is the dossier.

## Files now unused

- `src/components/subscription-momentum.tsx` and `src/components/charts/` — the design has no line charts. Delete when you're ready; nothing imports them after this change.
- `src/components/ipo-market-illustration.tsx`, `src/components/illustrations.tsx`, `public/illustrations/` — the system runs no imagery.
- `src/components/ipo-card.tsx` — the home page uses its own `IssueRow`; the directory uses `.directory-row`.
- `src/components/shimmering-text.tsx` — animation.

Check with `grep -r "SubscriptionMomentum\|IpoMarketIllustration\|ShimmeringText\|IpoCard" src` before deleting.

## Two things to confirm

1. **The sheet.** The design floats a 1180px sheet on a `#ddd6c4` desk with `0 26px 60px rgba(0,0,0,.3)`. Your build is full-bleed, and I kept that. To restore it, change `.page-shell` to `width: min(1180px, 100%); margin: 26px auto 70px; background: var(--paper); border: 1px solid var(--ink); box-shadow: 0 26px 60px rgba(0,0,0,.3);` and set `html, body { background: var(--desk) }`.
2. **The refresh stamp.** `site-header.tsx` prints a static "Last refresh · exchange record". The design always shows a real timestamp; pass one through when you have it.
