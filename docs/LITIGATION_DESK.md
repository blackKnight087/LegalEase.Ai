# Litigation Desk — Full SaaS Module

Route: `/litigation` (Practice → Litigation)

## Tabs

| Tab | Capability |
|-----|------------|
| **Court Day** | Paste or PDF cause list → parse (rules + Ollama) → match matters → import hearings → today's board → AI prep pack → export `.ics` calendar |
| **Court Sync** | One-shot eCourts-ready sync with optional auto-import |
| **Evidence** | Firm-wide contradictions, scan all matters, export markdown report |
| **Limitation** | Indian limitation presets → calculate → save to matter deadlines |
| **Watchlist** | Hearings, gazette, sections, custom legal watches |

## APIs (`/api/v1/practice/`)

- `POST court-day/parse`, `parse-file`, `import`
- `GET court-day/today`, `prep/{matter_id}?use_ai=1`, `calendar.ics`
- `GET court-sync/status`, `POST court-sync`
- `GET evidence-desk`, `POST evidence-desk/scan`, `scan-all`, `GET export`
- `GET limitation/presets`, `POST limitation/calculate`, `add-to-matter`

Watchlist: `/api/v1/engines/watchlist`

## Environment

| Variable | Purpose |
|----------|---------|
| `LITIGATION_LLM_PARSE=1` | Ollama fallback when regex finds no rows |
| `LITIGATION_PREP_AI=1` | AI brief section in prep pack |
| `EVIDENCE_DESK_SCAN_MAX=50` | Max matters per full scan |
| `ECOURTSINDIA_API_KEY` | eCourtsIndia partner API (optional — or save key in Court Sync UI) |
| `ECOURTS_API_ENABLED=1` | Legacy government eCourts stub |

## Sync modes

| Mode | Cost | When to use |
|------|------|-------------|
| **Paste / PDF** | Free | Daily cause lists, demos, saving API credits |
| **eCourtsIndia API** | ~₹3/call PAYG | Live fetch by date/state/case without copying text |

User chooses mode on the **Court Sync** tab. Search-engine APIs (Google/Bing) are not supported for cause lists.
