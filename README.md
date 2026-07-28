# Promo 1YP — Wholesale Pricing Planner

A full-stack Databricks App for **wholesale promo-price planning** (AB InBev-style Revenue
Management). Commercial Directors review and plan recommended prices (REC PPTR) for every
`Wholesaler × Brand × PRC group` across the **52 ISO weeks** of the year, edit them in a
low-latency sandbox, and submit them for CSO approval — replacing a slow Sigma/Palantir workflow.

![Databricks App](https://img.shields.io/badge/Databricks-App-orange)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![React](https://img.shields.io/badge/React-19-61DAFB)

## What it does

- **Calendarized price grid** — rows are grid lines (`Wholesaler × Brand × PRC group`) with
  metadata (Brand Code/Name, PRC Code/Group, QD Min/Max, Deal Description); columns are the 52
  ISO weeks. Each cell shows the weekly value in the current **view**. Promo weeks are tinted by
  discount depth; hover for the week, date range and REC PPTR. The grid is server-paged and
  row-virtualized to stay fast at hundreds of thousands of lines.
- **Three plan tabs** — `2026 Promotions Ran` (committed history), `2027 Plan Builder` (editable
  sandbox), `Final Plan` (CSO-approved).
- **Three views** — `Incremental Discount Plan`, `Absolute Discount Plan`, `REC PPTR Plan` — the
  same grid showing the discount %, the dollars-off, or the resulting price.
- **Mass editing** — select rows (or all), then apply an **incremental** (% off) or **absolute**
  ($ off) discount across a chosen week range in one action. Sandbox edits are ring-highlighted.
- **Budget bar** — always-on roll-up (total discount $, avg incremental discount, lines on promo,
  promo weeks) over the current filter.
- **Sandbox → Submit → Approve** — edits live in Lakebase (private, multi-user, survives reloads);
  **Submit** promotes them into the governed Unity Catalog table as `pending`; **Approve** flips
  them to `approved` in the Final Plan. **Reset** reverts all sandbox edits.
- **Downstream API** — `GET /api/pricing/final` returns the finally-approved pricing as clean
  JSON for another application to pull; the Final Plan's "Push downstream" button previews it.

## Architecture

| Layer | Technology |
|-------|-----------|
| Governed pricing data | **Unity Catalog** (`serverless_razks1_catalog.promo_planning`) |
| Compute for reads/writes | Serverless **SQL warehouse** (Statement API) |
| Front end | **Databricks Apps** — React 19 + TypeScript + Tailwind + Vite |
| Backend | **FastAPI**, httpx, Databricks SDK |
| Low-latency sandbox | **Lakebase** (managed Postgres) via asyncpg |

Production pricing lives in Unity Catalog; in-progress sandbox edits live in Lakebase and are
overlaid on the grid at read time. **Submit** MERGEs the sandbox into UC. The app relies on
Databricks Apps idle auto-stop to **scale to zero** between planning cycles.

## Data model (`promo_planning` schema)

- `dim_iso_week` — 52 ISO weeks (`week_number`, `iso_label`, date range) — the column axis.
- `dim_wholesaler` — wholesaler id / name / region / state.
- `dim_brand` — `brand_code → brand_name`.
- `dim_prc_group` — product/pack group: `prc_code`, `prc_group_name`, `qd_min/max`, `deal_description`.
- `fact_price_plan` — **dense** grid lines: one row per `(plan_year, wholesaler, brand, prc)` with
  `base_pptr` and `curr_max_discount`. This is the "row" users review (the customer counts ~1.3M).
- `fact_promo_week` — **sparse** per-week overrides: one row only where a promo changes the weekly
  price (`incremental_discount`, `absolute_discount`, `rec_pptr`, `approval_status`).

Regenerate the demo data (parameterized by line count):

```bash
python data/generate_rgm_data.py --profile <profile> --warehouse <id> --lines 200000
```

## Local development

```bash
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
databricks auth login --host https://<workspace-url> --profile promo
DATABRICKS_PROFILE=promo uvicorn app:app --reload --port 8000
```

Open http://localhost:8000

## Deploy

See [deployment_docs/DEPLOYMENT.md](deployment_docs/DEPLOYMENT.md). In short: generate the data,
build the frontend, create the app, attach the Lakebase resource, grant the service principal
warehouse + Lakebase + Unity Catalog access, then `databricks apps deploy`.

## License

Internal use.
