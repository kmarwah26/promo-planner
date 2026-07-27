# Promotion Planning Copilot

A full-stack Databricks App for **Revenue Growth Management (RGM)**: plan, compare and
approve trade promotions with granular ROI in view — then act on them without leaving the
app. Built for a beverage portfolio (AB InBev-style brands, markets, channels and packs).

![Databricks App](https://img.shields.io/badge/Databricks-App-orange)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![React](https://img.shields.io/badge/React-19-61DAFB)

## What it does

- **52-Week Planning Calendar** — every promotion laid out across the fiscal year by
  market, channel and brand, each bar color-coded by ROI. Hover for economics; click to
  open a promotion.
- **Promotions Workspace** — a sortable table of every promotion with trade spend,
  incrementality, net profit and ROI. Approve or lock a plan inline.
- **Scenario Comparison** — baseline (no promo) vs proposed plan across the filtered
  portfolio: volume lift, trade spend, incremental margin, net profit and blended ROI,
  with a per-brand net-profit breakdown.
- **RGM Copilot** — a Genie-powered chat over the governed promotion data. Ask
  *"Where are we overspending with low incrementality?"* or *"Which promos should we move
  from Q2 to Q3?"* and get answers with the generated SQL and result table.
- **Write-back actions (Lakebase)** — approve plan, adjust trade-spend budget, assign a
  follow-up, comment, and lock a scenario. All persisted transactionally in Lakebase
  (Postgres), overlaid onto the analytical data and tracked in an activity log.

## Architecture

| Layer | Technology |
|-------|-----------|
| Ingestion / semantics | Lakeflow + **Unity Catalog** (governed RGM tables + comments) |
| Conversational analysis | **Genie** space over the promotion data |
| Front end | **Databricks Apps** — React 19 + TypeScript + Tailwind + Vite |
| Backend | **FastAPI**, httpx, Databricks SDK |
| Transactional write-back | **Lakebase** (managed Postgres) via asyncpg |

The analytical data lives in Unity Catalog (`serverless_razks1_catalog.promo_planning`);
the operational plan state (approvals, budgets, comments, locks) lives in Lakebase and is
merged onto each promotion at read time.

## Data model (`promo_planning` schema)

- `fact_promotions` — one row per promotion (grain = `promotion_id`): market, channel,
  brand, pack, segment, mechanic, 52-week slot, status, and economics (base/promo price,
  discount depth, baseline vs proposed volume, trade spend, incremental margin,
  `net_promo_profit`, `promo_roi`, `incrementality_pct`).
- `fact_weekly_sales` — weekly baseline vs actual volume per promotion.
- `dim_product` — brand / pack / category reference.
- `dim_calendar` — 52-week fiscal calendar (week → quarter / month).

Regenerate the demo data with `python data/generate_rgm_data.py --warehouse <id>` and
(re)create the Genie space with `python data/create_genie_space.py --warehouse <id>`.

## Local development

```bash
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
databricks auth login --host https://<workspace-url> --profile promo
DATABRICKS_PROFILE=promo uvicorn app:app --reload --port 8000
```

Open http://localhost:8000

## Deploy

See [deployment_docs/DEPLOYMENT.md](deployment_docs/DEPLOYMENT.md). In short: build the
frontend, create the app, attach the Lakebase resource, grant the service principal
warehouse + Lakebase + Unity Catalog access, then `databricks apps deploy`.

## License

Internal use.
