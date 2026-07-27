"""Generate synthetic ABI-style Revenue Growth Management (RGM) / promotion-planning
data in Unity Catalog for the Promotion Planning Genie Agents demo.

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

# Trimmed to a full-factorial 3 x 3 x 3 = 27 promotions for a succinct demo.
MARKETS = ["USA-Northeast", "USA-Midwest", "USA-West"]
CHANNELS = ["Off-Premise Grocery", "Club/Warehouse", "On-Premise Bar"]
SEGMENTS = ["National Chains", "Regional Grocers", "On-Premise Accounts"]
# promo_mechanic -> volume elasticity to discount depth (lift = 1 + elasticity * discount).
# Display/Multi-Buy drive the most incremental volume per point of discount; low-elasticity
# mechanics (Loyalty, Price Reduction) turn unprofitable as discount deepens, which is the
# whole point of the demo — find the promos that overspend for too little lift.
MECHANIC_ELASTICITY = {
    "Display + Feature": 9,
    "Multi-Buy (2-for)": 8,
    "Bonus Pack": 6,
    "Price Reduction": 4,
    "Loyalty Coupon": 3,
}
MECHANICS = list(MECHANIC_ELASTICITY.keys())
# brand -> (category, pack). One representative pack per brand keeps the grid readable.
BRANDS = {
    "Corona Extra": ("Premium Import", "12pk Can"),
    "Michelob Ultra": ("Premium Light", "12pk Can"),
    "Bud Light": ("Core Light", "18pk Can"),
}

MARGIN_RATE = 0.38  # gross margin as a fraction of base price


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
    for brand, (cat, pack) in BRANDS.items():
        pid += 1
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

    # ── fact_promotions ── full-factorial brand x market x channel (27 rows) ──
    #
    # Economics follow an explicit elasticity model so the app's scenario grid can
    # recompute every metric live from a changed discount and match these stored values:
    #   lift_multiplier      = 1 + elasticity * discount_depth
    #   proposed_volume      = baseline_volume * lift_multiplier * duration_weeks
    #   incremental_volume   = baseline_volume * (lift_multiplier - 1) * duration_weeks
    #   trade_spend          = base_price * discount_depth * proposed_volume + fixed_fee
    #   incremental_margin   = incremental_volume * margin_per_case
    #   net_promo_profit     = incremental_margin - trade_spend
    #   promo_roi            = net_promo_profit / trade_spend
    exec_sql(w, wid, f"DROP TABLE IF EXISTS {FQ}.fact_promotions", "drop fact_promotions")
    market_list = ",".join(f"'{m}'" for m in MARKETS)
    channel_list = ",".join(f"'{c}'" for c in CHANNELS)
    segment_arr = "array(" + ",".join(f"'{s}'" for s in SEGMENTS) + ")"
    status_arr = "array('Draft','Proposed','Approved')"
    # SQL CASE mapping mechanic -> elasticity
    elast_case = " ".join(
        f"WHEN promo_mechanic = '{m}' THEN {e}" for m, e in MECHANIC_ELASTICITY.items()
    )
    mechanic_arr = "array(" + ",".join(f"'{m}'" for m in MECHANICS) + ")"

    exec_sql(w, wid, f"""
        CREATE TABLE {FQ}.fact_promotions
        COMMENT 'One row per planned promotion (brand x market x channel). Economics follow an elasticity model: lift = 1 + elasticity*discount. Grain: promotion_id.'
        AS
        WITH base AS (
          SELECT
            p.product_id, p.brand, p.pack, p.category,
            m.market, c.channel,
            abs(hash(concat(p.brand, m.market, c.channel))) AS h
          FROM {FQ}.dim_product p
          CROSS JOIN (SELECT explode(array({market_list})) AS market) m
          CROSS JOIN (SELECT explode(array({channel_list})) AS channel) c
        ),
        assigned AS (
          SELECT
            row_number() OVER (ORDER BY brand, market, channel) AS promotion_id,
            brand, pack, category, market, channel, h,
            {segment_arr}[pmod(h, 3)] AS customer_segment,
            {mechanic_arr}[pmod(h, 5)] AS promo_mechanic,
            (pmod(h, 40) + 4) AS start_week,
            (pmod(h, 40) + 4 + 2) AS end_week,
            3 AS duration_weeks,
            concat('Q', cast(least(4, ceil((pmod(h,40)+4)/13.0)) AS int)) AS quarter,
            {status_arr}[pmod(h, 3)] AS status,
            round(5.0 + pmod(h, 45) * 0.10, 2) AS base_price,
            round((0.08 + pmod(h, 15) * 0.01), 3) AS discount_depth,   -- 8%-22% off
            (2000 + pmod(h, 6000)) AS baseline_volume
          FROM base
        ),
        model AS (
          SELECT *,
            concat('PROMO-', lpad(cast(promotion_id AS string), 4, '0')) AS promotion_code,
            (CASE {elast_case} ELSE 8 END) AS elasticity,
            (CASE WHEN promo_mechanic IN ('Display + Feature','Bonus Pack') THEN 5000 ELSE 1500 END) AS fixed_fee,
            round(base_price * {MARGIN_RATE}, 4) AS margin_per_case
          FROM assigned
        ),
        derived AS (
          SELECT *,
            round(1 + elasticity * discount_depth, 4) AS lift_multiplier
          FROM model
        )
        SELECT
          promotion_id, promotion_code, brand, pack, category, market, channel,
          customer_segment, promo_mechanic, start_week, end_week, duration_weeks, quarter, status,
          base_price, discount_depth, baseline_volume, elasticity, fixed_fee, margin_per_case,
          lift_multiplier,
          round(base_price * (1 - discount_depth), 2) AS promo_price,
          cast(round(baseline_volume * duration_weeks) AS bigint) AS baseline_volume_total,
          cast(round(baseline_volume * lift_multiplier * duration_weeks) AS bigint) AS proposed_volume_total,
          cast(round(baseline_volume * (lift_multiplier - 1) * duration_weeks) AS bigint) AS incremental_volume,
          round(base_price * discount_depth * (baseline_volume * lift_multiplier * duration_weeks) + fixed_fee, 2) AS trade_spend,
          round(baseline_volume * (lift_multiplier - 1) * duration_weeks * margin_per_case, 2) AS incremental_margin,
          round(baseline_volume * (lift_multiplier - 1) * duration_weeks * margin_per_case
                - (base_price * discount_depth * (baseline_volume * lift_multiplier * duration_weeks) + fixed_fee), 2) AS net_promo_profit,
          round((baseline_volume * (lift_multiplier - 1) * duration_weeks * margin_per_case
                 - (base_price * discount_depth * (baseline_volume * lift_multiplier * duration_weeks) + fixed_fee))
                / nullif(base_price * discount_depth * (baseline_volume * lift_multiplier * duration_weeks) + fixed_fee, 0), 3) AS promo_roi,
          round(lift_multiplier - 1, 3) AS incrementality_pct
        FROM derived
    """, "fact_promotions (elasticity model)")

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
