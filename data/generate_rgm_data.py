"""Generate synthetic wholesale promo-pricing data in Unity Catalog for the
Promo 1YP planning app (AB InBev-style Revenue Management).

The app is a calendarized pricing workspace: rows are a **grid line**
(plan year x wholesaler x brand x PRC group) and columns are the 52 ISO weeks
of the year. Each cell is the weekly REC PPTR (recommended price to retailer),
optionally overridden by a promotion that runs for several contiguous weeks.

Everything is generated in SQL against a serverless SQL warehouse via the
Databricks SDK, so no local Spark is needed. Produces six tables in
``serverless_razks1_catalog.promo_planning``:

  * dim_iso_week      — 52 ISO weeks (week_number -> label + date range).
  * dim_wholesaler    — distributor/wholesaler reference (id, name, region, state).
  * dim_brand         — brand code -> brand name.
  * dim_prc_group     — product/pack "PRC group" (prc_code, pack, QD min/max, deal desc).
  * fact_price_plan   — DENSE grid lines: one row per (plan_year, wholesaler, brand, prc)
                        with the base REC PPTR and current max discount. This is the
                        "row" users review (target ~100-300K+; the customer counts ~1.3M).
  * fact_promo_week   — SPARSE per-week promo overrides: one row only where a promo
                        changes the price in a given week. plan_year 2026 = committed
                        history ("2026 Promotions Ran"); plan_year 2027 approved rows
                        seed the "Final Plan".

Usage:
    python data/generate_rgm_data.py --profile fevm-serverless --warehouse <id> --lines 200000
"""
import argparse
import json
import math
import time

CATALOG = "serverless_razks1_catalog"
SCHEMA = "promo_planning"
FQ = f"{CATALOG}.{SCHEMA}"

# ── Brand catalog (code -> name). Codes/names mirror the customer screenshots. ──
BRANDS = [
    ("STA", "STELLA ARTOIS"),
    ("MUL", "MICHELOB ULTRA"),
    ("P6F", "FRANZISKANER HEFE WEISS"),
    ("BU4", "BUD LIGHT SELTZER MANGO"),
    ("RWL", "CUTWATER RANCH WATER LIME"),
    ("RMJ", "CUTWATER MINT AND LIME MOJITO"),
    ("BHI", "BUSCH LIGHT LIME"),
    ("GMB", "GOLDEN ROAD BLOOMIN BLONDE ALE"),
    ("SA2", "STARBOVICH"),
    ("BLR", "BITSA LIMB-A-RITA"),
    ("MF2", "NUTRL FRUIT VARIETY PACK"),
    ("BDL", "BUD LIGHT"),
    ("BUD", "BUDWEISER"),
    ("HGA", "HOOP TEA HALF AND HALF A"),
    ("COR", "CORONA EXTRA"),
]

# ── Pack / PRC-group configurations and the deal descriptions from the screenshots. ──
PACKS = [
    "24/12 CAN 4/6", "1/6 BBL DFT", "24/12 NRLN 4/6", "24/12 NRLN 2/12",
    "15/25 CAN", "24/12 CAN 4/4 (LQ)", "24/12 CAN", "24/12 CAN 2/12",
    "1/2 BBL", "24/16 CAN", "12/24 CAN", "24/16 ALU",
]
DEAL_DESCRIPTIONS = ["General Market", "Retail - Military", "Licensed Home 3", "CLARION"]

# ── Wholesaler name generation fragments. ──
CITIES = [
    "ARKANSAS", "EAGLE ROCK", "ATLANTA", "UNITED", "ORANGE COUNTY", "KABRICK",
    "SENECA", "ASHLAND", "STARBOVICH", "REPUBLIC", "MASON CITY", "COLORADO",
    "JACKSONVILLE", "STANHOPE", "HEBGARDEN", "TRISTAR", "SUNRISE", "SAVANNAH",
    "PIEDMONT", "GREAT LAKES", "CASCADE", "LONE STAR", "GULF COAST", "BAY AREA",
]
WS_SUFFIX = ["BEVERAGE SALES INC", "DIST CO", "DISTRIBUTORS INC", "WHOLESALE CO",
             "BEVERAGE CO", "PDI OF", "DIST CO", "BEVERAGE LLC"]
REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]
STATES = ["AR", "CO", "GA", "TX", "CA", "IL", "OH", "FL", "NY", "WA", "AZ", "MA"]


def _sql_str_array(values):
    return "array(" + ",".join(f"'{v}'" for v in values) + ")"


def build_statements(lines: int = 200_000, prc_per_brand: int = 4) -> list[tuple[str, str]]:
    """Build the ordered list of (label, sql) statements that create the pricing schema.

    Pure function — no SDK / warehouse needed — so the SQL can be executed via the SDK,
    emitted for the CLI Statement API, or unit-tested. TABLES: dim_iso_week, dim_brand,
    dim_prc_group, dim_wholesaler, fact_price_plan (dense grid lines), fact_promo_week
    (sparse per-week overrides).
    """
    n_products = len(BRANDS) * prc_per_brand              # distinct (brand, prc) product lines
    n_wholesalers = max(1, math.ceil(lines / n_products))
    stmts: list[tuple[str, str]] = []

    stmts.append(("create schema",
        f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA} "
        "COMMENT 'AB InBev-style wholesale promo-pricing (Promo 1YP) demo data'"))

    # ── dim_iso_week: 52 ISO weeks anchored at 2026-12-29 (matches the customer screenshot). ──
    stmts.append(("drop dim_iso_week", f"DROP TABLE IF EXISTS {FQ}.dim_iso_week"))
    stmts.append(("dim_iso_week", f"""
        CREATE TABLE {FQ}.dim_iso_week
        COMMENT 'Planning calendar: one row per ISO week (1-52) with label and date range.'
        AS
        SELECT
          wk AS week_number,
          concat('WK', lpad(cast(wk AS string), 2, '0')) AS iso_label,
          date_add('2026-12-29', (wk-1)*7) AS week_start_date,
          date_add('2026-12-29', (wk-1)*7 + 6) AS week_end_date,
          concat(date_format(date_add('2026-12-29', (wk-1)*7), 'MM/dd'), '-',
                 date_format(date_add('2026-12-29', (wk-1)*7 + 6), 'MM/dd')) AS date_range_label
        FROM (SELECT explode(sequence(1, 52)) AS wk)
    """))

    # ── dim_brand ──
    stmts.append(("drop dim_brand", f"DROP TABLE IF EXISTS {FQ}.dim_brand"))
    stmts.append(("dim_brand ddl", f"""
        CREATE TABLE {FQ}.dim_brand (
          brand_code STRING COMMENT 'Short brand code (e.g. STA)',
          brand_name STRING COMMENT 'Full brand name'
        ) COMMENT 'Brand dimension.'
    """))
    brand_vals = ", ".join(f"('{c}', '{n}')" for c, n in BRANDS)
    stmts.append(("dim_brand insert", f"INSERT INTO {FQ}.dim_brand VALUES {brand_vals}"))

    # ── dim_prc_group: prc-per-brand product/pack lines per brand. ──
    stmts.append(("drop dim_prc_group", f"DROP TABLE IF EXISTS {FQ}.dim_prc_group"))
    stmts.append(("dim_prc_group", f"""
        CREATE TABLE {FQ}.dim_prc_group
        COMMENT 'Product "PRC group": a brand + pack configuration with QD thresholds and deal type.'
        AS
        WITH b AS (SELECT brand_code, brand_name FROM {FQ}.dim_brand),
        expanded AS (
          SELECT b.brand_code, b.brand_name, seq AS prc_seq,
                 abs(hash(concat(b.brand_code, cast(seq AS string)))) AS h
          FROM b LATERAL VIEW explode(sequence(1, {prc_per_brand})) t AS seq
        )
        SELECT
          concat(brand_code, lpad(cast(prc_seq AS string), 2, '0')) AS prc_code,
          brand_code, brand_name,
          {_sql_str_array(PACKS)}[pmod(h, {len(PACKS)})] AS prc_group_name,
          (pmod(h, 20) + 1) AS qd_min,
          CASE WHEN pmod(h, 3) = 0 THEN 9999 ELSE pmod(h, 90) + 10 END AS qd_max,
          {_sql_str_array(DEAL_DESCRIPTIONS)}[pmod(h, {len(DEAL_DESCRIPTIONS)})] AS deal_description
        FROM expanded
    """))

    # ── dim_wholesaler: n_wholesalers distributors with id/name/region/state. ──
    stmts.append(("drop dim_wholesaler", f"DROP TABLE IF EXISTS {FQ}.dim_wholesaler"))
    stmts.append(("dim_wholesaler", f"""
        CREATE TABLE {FQ}.dim_wholesaler
        COMMENT 'Wholesaler/distributor dimension (id, name, region, state).'
        AS
        WITH ids AS (SELECT explode(sequence(1, {n_wholesalers})) AS n)
        SELECT
          lpad(cast(n AS string), 5, '0') AS wholesaler_id,
          concat(
            {_sql_str_array(CITIES)}[pmod(abs(hash(n)), {len(CITIES)})], ' ',
            {_sql_str_array(WS_SUFFIX)}[pmod(abs(hash(n * 7)), {len(WS_SUFFIX)})]
          ) AS wholesaler_name,
          {_sql_str_array(REGIONS)}[pmod(abs(hash(n * 13)), {len(REGIONS)})] AS region,
          {_sql_str_array(STATES)}[pmod(abs(hash(n * 17)), {len(STATES)})] AS state
        FROM ids
    """))

    # ── fact_price_plan: DENSE grid lines for both plan years. ──
    # base_pptr ~ $18-$130 (matches screenshot price range); curr_max_discount is a $ cap.
    stmts.append(("drop fact_price_plan", f"DROP TABLE IF EXISTS {FQ}.fact_price_plan"))
    stmts.append(("fact_price_plan", f"""
        CREATE TABLE {FQ}.fact_price_plan
        COMMENT 'Dense grid lines: one row per (plan_year, wholesaler, brand, prc group) with base REC PPTR. Grain the customer counts (~1.3M in prod).'
        AS
        WITH lines AS (
          SELECT
            yr.plan_year,
            ws.wholesaler_id, ws.wholesaler_name, ws.region, ws.state,
            pg.brand_code, pg.brand_name, pg.prc_code, pg.prc_group_name,
            pg.qd_min, pg.qd_max, pg.deal_description,
            abs(hash(concat(ws.wholesaler_id, pg.prc_code, cast(yr.plan_year AS string)))) AS h
          FROM (SELECT explode(array(2026, 2027)) AS plan_year) yr
          CROSS JOIN {FQ}.dim_wholesaler ws
          CROSS JOIN {FQ}.dim_prc_group pg
        )
        SELECT
          plan_year, wholesaler_id, wholesaler_name, region, state,
          brand_code, brand_name, prc_code, prc_group_name, qd_min, qd_max, deal_description,
          round(18.0 + pmod(h, 112) + (pmod(h, 100) / 100.0), 2) AS base_pptr,
          round(1.0 + pmod(h, 40) * 0.10, 2) AS curr_max_discount
        FROM lines
    """))

    # ── fact_promo_week: SPARSE per-week promo overrides. ──
    # Each line gets up to two contiguous promo windows (derived from its hash). A week is
    # in-promo when it falls inside a window; only those weeks are materialized.
    #   window 1: start s1 = pmod(h,40)+3, length l1 = pmod(h,4)+2
    #   window 2: start s2 = pmod(h,20)+30, length l2 = pmod(h,3)+2 (only when pmod(h,2)=0)
    # 2026 rows = 'committed'; 2027 rows = 'approved' (Final Plan seed) except ~1/4 'pending'.
    stmts.append(("drop fact_promo_week", f"DROP TABLE IF EXISTS {FQ}.fact_promo_week"))
    stmts.append(("fact_promo_week", f"""
        CREATE TABLE {FQ}.fact_promo_week
        COMMENT 'Sparse per-week promo overrides. One row only where a promo changes the weekly price. Grain: plan_year x line x week_number.'
        AS
        WITH lines AS (
          SELECT plan_year, wholesaler_id, brand_code, prc_code, base_pptr,
                 abs(hash(concat(wholesaler_id, prc_code, cast(plan_year AS string)))) AS h
          FROM {FQ}.fact_price_plan
          WHERE pmod(abs(hash(concat(wholesaler_id, prc_code))), 5) < 4   -- ~80% of lines run a promo
        ),
        params AS (
          SELECT *,
            pmod(h, 40) + 3 AS s1, pmod(h, 4) + 2 AS l1,
            pmod(h, 20) + 30 AS s2, pmod(h, 3) + 2 AS l2,
            (pmod(h, 2) = 0) AS has_second,
            round(0.05 + pmod(h, 20) * 0.01, 3) AS disc1,   -- 5%-24%
            round(0.05 + pmod(h, 15) * 0.01, 3) AS disc2
          FROM lines
        ),
        exploded AS (
          SELECT p.*, cal.week_number
          FROM params p
          JOIN {FQ}.dim_iso_week cal
            ON (cal.week_number BETWEEN p.s1 AND p.s1 + p.l1 - 1)
            OR (p.has_second AND cal.week_number BETWEEN p.s2 AND p.s2 + p.l2 - 1)
        )
        SELECT
          plan_year, wholesaler_id, brand_code, prc_code, week_number,
          CASE WHEN week_number >= s2 THEN disc2 ELSE disc1 END AS incremental_discount,
          CAST(NULL AS DOUBLE) AS absolute_discount,
          round(base_pptr * (1 - CASE WHEN week_number >= s2 THEN disc2 ELSE disc1 END), 2) AS rec_pptr,
          CASE
            WHEN plan_year = 2026 THEN 'committed'
            WHEN pmod(h, 4) = 0 THEN 'pending'
            ELSE 'approved'
          END AS approval_status
        FROM exploded
    """))
    return stmts


TABLES = ["dim_iso_week", "dim_brand", "dim_prc_group", "dim_wholesaler",
          "fact_price_plan", "fact_promo_week"]


def _run_with_sdk(profile: str, warehouse_id: str, lines: int, prc_per_brand: int):
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient(profile=profile)

    def exec_sql(sql: str, label: str = ""):
        resp = w.statement_execution.execute_statement(
            warehouse_id=warehouse_id, statement=sql, wait_timeout="50s")
        state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"
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

    for label, sql in build_statements(lines, prc_per_brand):
        exec_sql(sql, label)
    for t in TABLES:
        r = exec_sql(f"SELECT count(*) AS n FROM {FQ}.{t}", f"count {t}")
        n = r.result.data_array[0][0] if r.result and r.result.data_array else "?"
        print(f"    {t}: {n} rows")
    print("\n✅ Promo 1YP demo data ready in", FQ)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="fevm-serverless")
    ap.add_argument("--warehouse", default="")
    ap.add_argument("--lines", type=int, default=200_000,
                    help="Approx. number of grid lines PER plan year (default 200000).")
    ap.add_argument("--prc-per-brand", type=int, default=4,
                    help="PRC groups generated per brand (default 4).")
    ap.add_argument("--emit", action="store_true",
                    help="Print the statements as JSON [{label, sql}, ...] instead of executing "
                         "them (run via the databricks CLI Statement API when the SDK is unavailable).")
    args = ap.parse_args()

    if args.emit:
        out = [{"label": label, "sql": sql}
               for label, sql in build_statements(args.lines, args.prc_per_brand)]
        out.append({"label": "counts", "sql": " UNION ALL ".join(
            f"SELECT '{t}' AS tbl, count(*) AS n FROM {FQ}.{t}" for t in TABLES)})
        print(json.dumps(out))
        return

    if not args.warehouse:
        ap.error("--warehouse is required unless --emit is used")
    n_products = len(BRANDS) * args.prc_per_brand
    n_wholesalers = max(1, math.ceil(args.lines / n_products))
    print(f"Target ~{args.lines:,} lines/year → {n_wholesalers:,} wholesalers × "
          f"{n_products} products ({len(BRANDS)} brands × {args.prc_per_brand} PRC groups).")
    _run_with_sdk(args.profile, args.warehouse, args.lines, args.prc_per_brand)


if __name__ == "__main__":
    main()
