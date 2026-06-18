# LegalEase.AI — Design System

Source of truth: `web/tailwind.config.ts`, `web/app/globals.css`, shadcn-style components under `web/components/ui/`.

## Color palette

| Token | Usage |
|-------|--------|
| Primary navy (`#1e3a5f`) | Headers, KB mode, brand |
| Blue (`#2563eb`) | Open Law, links, CTAs |
| Purple (`#7c3aed`) | Hybrid mode |
| Green (`#059669`) | Success, positive feedback |
| Red (`#dc2626`) | Errors, negative feedback |
| Slate scale | Backgrounds, borders, body text |

## Typography

- **Font:** System UI stack via Tailwind `font-sans`
- **Page titles:** `PageHeader` component — semibold, responsive scale
- **Body:** 14–16px; legal content in `prose` where markdown rendered

## Components

| Component | Path |
|-----------|------|
| Buttons | `web/components/ui/` |
| Page layout | `PageHeader`, `(app)/layout.tsx` sidebar |
| Charts | `AnalyticsPieChart.tsx` (SVG pies) |
| Chat | `web/components/chat/` |
| Matters | `web/components/matters/` |

## Layout patterns

- **App shell:** Fixed sidebar + scrollable main (`le-scroll`, `le-page-body`)
- **Dashboard:** KPI cards grid → detail sections
- **Matter workspace:** Tabbed sub-routes under `/matters/[matterId]/`

## Accessibility

- Target WCAG 2.1 AA for new UI
- Focus rings on interactive elements
- `lang="en"` on root HTML
- Mobile: responsive grids, `viewportFit: cover` for notched devices

## Mobile

- 46 routes use responsive Tailwind breakpoints (`sm:`, `md:`)
- Native app deferred; PWA enhancements on roadmap Phase 3
