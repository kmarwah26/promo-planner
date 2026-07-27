"""Generate synthetic ABI-style Revenue Growth Management (RGM) / promotion-planning
data in Unity Catalog for the Promotion Planning Copilot demo.

Runs entirely in SQL against a serverless SQL warehouse via the Databricks SDK, so it
needs no local Spark. Produces four Genie-friendly, denormalized tables in
``fevm_shared_catalog.promo_planning``:

  * dim_product        — brand / pack / category reference
  * fact_promotions    — one row per promotion (market, channel, brand, pack, segment,
                         52-week calendar slot) with baseline vs proposed volume, margin,
                         trade spend and computed ROI / incrementality.
  * fact_weekly_sales  — weekly baseline vs promoted volume per promotion (for the
                         52-week calendar heatmap and post-promo learning).
  * dim_calendar       — 52-week fiscal calendar (week -> quarter/month) for the year.

Usage:
    python data/generate_rgm_data.py --profile fevm-serverless --warehouse <id>
"""
import argparse
import time
from databricks.sdk import WorkspaceClient

CATALOG = "serverless_razks1_catalog"
SCHEMA = "promo_planning"
FQ = f"{CATALOG}.{SCHEMA}"

MARKETS = ["USA-Northeast", "USA-Southeast", "USA-Midwest", "USA-West", "Canada", "Mexico"]
CHANNELS = ["Off-Premise Grocery", "Off-Premise Convenience", "On-Premise Bar", "Club/Warehouse", "Mass Merchant"]
SEGMENTS = ["National Chains", "Regional Grocers", "Independent Retailers", "On-Premise Accounts"]
MECHANICS = ["Price Reduction", "Multi-Buy (2-for)", "Display + Feature", "Loyalty Coupon", "Bonus Pack"]
# brand -> (category, [packs])
BRANDS = {
    "Corona Extra": ("Premium Import", ["6pk Bottle", "12pk Can", "24pk Case"]),
    "Michelob Ultra": ("Premium Light", ["6pk Bottle", "12pk Can", "18pk Can"]),
    "Bud Light": ("Core Light", ["12pk Can", "18pk Can", "30pk Can"]),
    "Budweiser": ("Core Lager", ["12pk Can", "18pk Can", "24pk Case"]),
    "Stella Artois": ("Premium Import", ["6pk Bottle", "12pk Bottle"]),
    "Busch Light": ("Value Light", ["18pk Can", "30pk Can"]),
}


def exec_sql(w: WorkspaceClient, warehouse_id: str, sql: str, label: str = ""):
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=sql, wait_timeout="50s"
    )
    state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"
    # poll if still running
    stmt_id = resp.statement_id
    while state in ("PENDING", "RUNNING") and stmt_id:
        time.sleep(2)
        resp = w.statement_execution.get_statement(stmt_id)
        state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"
    if state != "SUCCEEDED":
        err = resp.status.error.message if resp.status and resp.status.error else "unknown"
        raise RuntimeError(f"[{label}] SQL failed ({state}): {err}\nSQL: {sql[:400]}")
    print(f"  ✓ {label} ({state})")
    return resp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="fevm-serverless")
    ap.add_argument("--warehouse", required=True)
    args = ap.parse_args()

    w = WorkspaceClient(profile=args.profile)
    wid = args.warehouse

    print(f"Creating schema {FQ} ...")
    exec_sql(w, wid, f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA} COMMENT 'ABI Revenue Growth Management promotion-planning demo data'", "create schema")

    # ── dim_calendar: 52-week fiscal calendar for FY2026 ──
    exec_sql(w, wid, f"DROP TABLE IF EXISTS {FQ}.dim_calendar", "drop dim_calendar")
    exec_sql(w, wid, f"""
        CREATE TABLE {FQ}.dim_calendar
        COMMENT 'Fiscal 52-week calendar. One row per ISO week of the planning year, mapped to quarter and month.'
        AS
        SELECT
          wk AS week_number,
          date_add('2026-01-05', (wk-1)*7) AS week_start_date,
          concat('Q', cast(least(4, ceil(wk/13.0)) as int)) AS quarter,
          date_format(date_add('2026-01-05', (wk-1)*7), 'MMMM') AS month
        FROM (SELECT explode(sequence(1, 52)) AS wk)
    """, "dim_calendar")

    # ── dim_product ──
    prod_rows = []
    pid = 0
    prod_lookup = {}  # (brand,pack) -> product_id
    for brand, (cat, packs) in BRANDS.items():
        for pack in packs:
            pid += 1
            prod_lookup[(brand, pack)] = pid
            prod_rows.append(f"({pid}, '{brand}', '{pack}', '{cat}')")
    exec_sql(w, wid, f"DROP TABLE IF EXISTS {FQ}.dim_product", "drop dim_product")
    exec_sql(w, wid, f"""
        CREATE TABLE {FQ}.dim_product (
          product_id INT COMMENT 'Surrogate key for a brand + pack combination',
          brand STRING COMMENT 'Beer brand name',
          pack STRING COMMENT 'Pack configuration (e.g. 12pk Can)',
          category STRING COMMENT 'Brand price/category tier'
        )
        COMMENT 'Product dimension: brand, pack size and category tier for the ABI portfolio.'
    """, "dim_product ddl")
    exec_sql(w, wid, f"INSERT INTO {FQ}.dim_product VALUES {', '.join(prod_rows)}", "dim_product insert")

    # ── fact_promotions ── generated deterministically in SQL ──
    exec_sql(w, wid, f"DROP TABLE IF EXISTS {FQ}.fact_promotions", "drop fact_promotions")
    # Build a cross of markets x channels x brand/pack, assign a plausible promo per row.
    market_list = ",".join(f"'{m}'" for m in MARKETS)
    channel_list = ",".join(f"'{c}'" for c in CHANNELS)
    segment_arr = "array(" + ",".join(f"'{s}'" for s in SEGMENTS) + ")"
    mechanic_arr = "array(" + ",".join(f"'{m}'" for m in MECHANICS) + ")"
    status_arr = "array('Draft','Proposed','Approved','Locked')"
    exec_sql(w, wid, f"""
        CREATE TABLE {FQ}.fact_promotions
        COMMENT 'One row per planned promotion. Baseline vs proposed volume/margin/trade-spend with computed ROI and incrementality. Grain: promotion_id.'
        AS
        WITH base AS (
          SELECT
            p.product_id, p.brand, p.pack, p.category,
            m.market,
            c.channel,
            -- deterministic pseudo-random via hash
            abs(hash(concat(p.brand, p.pack, m.market, c.channel))) AS h
          FROM {FQ}.dim_product p
          CROSS JOIN (SELECT explode(array({market_list})) AS market) m
          CROSS JOIN (SELECT explode(array({channel_list})) AS channel) c
          -- keep the dataset focused: ~1 in 3 combinations gets a promo
          WHERE pmod(abs(hash(concat(p.brand, p.pack, m.market, c.channel))), 3) = 0
        )
        SELECT
          row_number() OVER (ORDER BY h) AS promotion_id,
          concat('PROMO-', lpad(cast(row_number() OVER (ORDER BY h) AS string), 4, '0')) AS promotion_code,
          brand, pack, category, market, channel,
          {segment_arr}[pmod(h, 4)] AS customer_segment,
          {mechanic_arr}[pmod(h, 5)] AS promo_mechanic,
          (pmod(h, 52) + 1) AS start_week,
          (pmod(h, 52) + 1 + (pmod(h, 3) + 1)) AS end_week,
          (pmod(h, 3) + 1) AS duration_weeks,
          concat('Q', cast(least(4, ceil((pmod(h,52)+1)/13.0)) as int)) AS quarter,
          {status_arr}[pmod(h, 4)] AS status,
          -- economics ----------------------------------------------------
          round(5.0 + pmod(h, 45) * 0.10, 2) AS base_price,
          round((0.08 + pmod(h, 15) * 0.01), 3) AS discount_depth,   -- 8%-22% off
          -- baseline (no promo) weekly volume in cases
          (2000 + pmod(h, 8000)) AS baseline_volume,
          -- lift multiplier: driven mostly by mechanic effectiveness + a spread factor,
          -- decoupled from discount so ROI ranges from clearly-losing to clearly-winning.
          round(1.30 + pmod(h, 7) * 0.12
                + (case when promo_mechanic in ('Display + Feature','Multi-Buy (2-for)') then 0.35
                        when promo_mechanic = 'Bonus Pack' then 0.20 else 0.05 end), 3) AS lift_multiplier
        FROM base
    """, "fact_promotions base")

    # Add derived economics as a second pass (proposed volume, spend, margin, ROI, incrementality)
    exec_sql(w, wid, f"""
        CREATE OR REPLACE TABLE {FQ}.fact_promotions AS
        SELECT
          *,
          cast(round(baseline_volume * duration_weeks) AS bigint) AS baseline_volume_total,
          cast(round(baseline_volume * lift_multiplier * duration_weeks) AS bigint) AS proposed_volume_total,
          cast(round(baseline_volume * (lift_multiplier - 1) * duration_weeks) AS bigint) AS incremental_volume,
          round(base_price * (1 - discount_depth), 2) AS promo_price,
          -- trade spend = discount per case * proposed volume + fixed display/feature fee
          round(base_price * discount_depth * (baseline_volume * lift_multiplier * duration_weeks)
                + (case when promo_mechanic in ('Display + Feature','Bonus Pack') then 5000 else 1500 end), 2) AS trade_spend,
          -- gross margin per case ~ 38% of base price
          round(base_price * 0.38, 2) AS margin_per_case
        FROM {FQ}.fact_promotions
    """, "fact_promotions economics 1")

    exec_sql(w, wid, f"""
        CREATE OR REPLACE TABLE {FQ}.fact_promotions AS
        SELECT
          *,
          round(incremental_volume * margin_per_case, 2) AS incremental_margin,
          round(incremental_volume * margin_per_case - trade_spend, 2) AS net_promo_profit,
          round((incremental_volume * margin_per_case - trade_spend) / nullif(trade_spend, 0), 3) AS promo_roi,
          round((proposed_volume_total - baseline_volume_total) / nullif(baseline_volume_total, 0), 3) AS incrementality_pct
        FROM {FQ}.fact_promotions
    """, "fact_promotions economics 2")

    # ── fact_weekly_sales: expand each promo across its active weeks + surrounding baseline ──
    exec_sql(w, wid, f"DROP TABLE IF EXISTS {FQ}.fact_weekly_sales", "drop fact_weekly_sales")
    exec_sql(w, wid, f"""
        CREATE TABLE {FQ}.fact_weekly_sales
        COMMENT 'Weekly volume per promotion across the 52-week calendar: baseline vs actual/promoted volume. Grain: promotion_id x week_number.'
        AS
        SELECT
          f.promotion_id, f.promotion_code, f.brand, f.pack, f.market, f.channel,
          f.customer_segment, f.promo_mechanic, f.status,
          cal.week_number,
          cal.quarter,
          f.baseline_volume AS baseline_volume,
          CASE
            WHEN cal.week_number BETWEEN f.start_week AND f.end_week
              THEN cast(round(f.baseline_volume * f.lift_multiplier) AS bigint)
            ELSE f.baseline_volume
          END AS actual_volume,
          CASE WHEN cal.week_number BETWEEN f.start_week AND f.end_week THEN true ELSE false END AS is_promo_week
        FROM {FQ}.fact_promotions f
        JOIN {FQ}.dim_calendar cal
          ON cal.week_number BETWEEN greatest(1, f.start_week - 2) AND least(52, f.end_week + 2)
    """, "fact_weekly_sales")

    # counts
    for t in ["dim_calendar", "dim_product", "fact_promotions", "fact_weekly_sales"]:
        r = exec_sql(w, wid, f"SELECT count(*) AS n FROM {FQ}.{t}", f"count {t}")
        n = r.result.data_array[0][0] if r.result and r.result.data_array else "?"
        print(f"    {t}: {n} rows")

    print("\n✅ RGM demo data ready in", FQ)


if __name__ == "__main__":
    main()
