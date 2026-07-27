"""Read-side routes for promotion planning: calendar, promotion list, filters,
scenario comparison, and portfolio KPIs — all sourced from Unity Catalog.
"""
from fastapi import APIRouter, Request, Query
from server.routes.sql_exec import run_query, FQ

router = APIRouter(tags=["promos"])


def _num(v):
    """Coerce a SQL Statement API string value to float, or None."""
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return v


@router.get("/promos/filters")
async def get_filters(request: Request):
    """Distinct values for the filter controls (markets, channels, brands, segments, statuses)."""
    rows = await run_query(request, f"""
        SELECT 'market' AS dim, market AS val FROM {FQ}.fact_promotions GROUP BY market
        UNION ALL SELECT 'channel', channel FROM {FQ}.fact_promotions GROUP BY channel
        UNION ALL SELECT 'brand', brand FROM {FQ}.fact_promotions GROUP BY brand
        UNION ALL SELECT 'customer_segment', customer_segment FROM {FQ}.fact_promotions GROUP BY customer_segment
        UNION ALL SELECT 'status', status FROM {FQ}.fact_promotions GROUP BY status
        UNION ALL SELECT 'promo_mechanic', promo_mechanic FROM {FQ}.fact_promotions GROUP BY promo_mechanic
        ORDER BY dim, val
    """)
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["dim"], []).append(r["val"])
    return out


def _where(market, channel, brand, segment, status):
    clauses = []
    if market:
        clauses.append(f"market = '{market}'")
    if channel:
        clauses.append(f"channel = '{channel}'")
    if brand:
        clauses.append(f"brand = '{brand}'")
    if segment:
        clauses.append(f"customer_segment = '{segment}'")
    if status:
        clauses.append(f"status = '{status}'")
    return ("WHERE " + " AND ".join(clauses)) if clauses else ""


@router.get("/promos")
async def list_promos(
    request: Request,
    market: str | None = None,
    channel: str | None = None,
    brand: str | None = None,
    segment: str | None = None,
    status: str | None = None,
):
    """List promotions with economics, filtered. Overlaid with any Lakebase write-back state."""
    where = _where(market, channel, brand, segment, status)
    rows = await run_query(request, f"""
        SELECT promotion_id, promotion_code, brand, pack, category, market, channel,
               customer_segment, promo_mechanic, start_week, end_week, duration_weeks,
               quarter, status, base_price, promo_price, discount_depth,
               baseline_volume_total, proposed_volume_total, incremental_volume,
               trade_spend, incremental_margin, net_promo_profit, promo_roi, incrementality_pct
        FROM {FQ}.fact_promotions
        {where}
        ORDER BY promotion_id
    """)
    for r in rows:
        for k in ("base_price", "promo_price", "discount_depth", "baseline_volume_total",
                  "proposed_volume_total", "incremental_volume", "trade_spend",
                  "incremental_margin", "net_promo_profit", "promo_roi", "incrementality_pct",
                  "start_week", "end_week", "duration_weeks", "promotion_id"):
            r[k] = _num(r.get(k))
    # Overlay write-back state (approved/locked/budget/comments) from Lakebase
    from server.routes.planning import get_plan_state_map
    state_map = await get_plan_state_map()
    for r in rows:
        st = state_map.get(str(int(r["promotion_id"])))
        r["plan_state"] = st  # None or {status, adjusted_budget, locked, ...}
    return {"promos": rows}


@router.get("/promos/kpis")
async def portfolio_kpis(
    request: Request,
    market: str | None = None,
    channel: str | None = None,
    brand: str | None = None,
    segment: str | None = None,
    status: str | None = None,
):
    """Portfolio-level roll-up for the header KPI tiles."""
    where = _where(market, channel, brand, segment, status)
    rows = await run_query(request, f"""
        SELECT
          count(*) AS n_promos,
          round(sum(trade_spend), 0) AS total_trade_spend,
          round(sum(incremental_volume), 0) AS total_incremental_volume,
          round(sum(net_promo_profit), 0) AS total_net_profit,
          round(sum(incremental_margin) / nullif(sum(trade_spend), 0), 3) AS blended_roi,
          round(avg(incrementality_pct), 3) AS avg_incrementality,
          sum(CASE WHEN promo_roi < 0 THEN 1 ELSE 0 END) AS n_negative_roi
        FROM {FQ}.fact_promotions
        {where}
    """)
    r = rows[0] if rows else {}
    return {k: _num(v) for k, v in r.items()}


@router.get("/promos/calendar")
async def calendar(
    request: Request,
    market: str | None = None,
    channel: str | None = None,
    brand: str | None = None,
    segment: str | None = None,
    status: str | None = None,
):
    """52-week calendar grid: for each promotion, the weeks it is active, plus economics
    for cell coloring. Returns promotions and the week/quarter reference axis."""
    where = _where(market, channel, brand, segment, status)
    promos = await run_query(request, f"""
        SELECT promotion_id, promotion_code, brand, pack, market, channel, customer_segment,
               promo_mechanic, status, start_week, end_week, quarter, promo_roi, trade_spend,
               incremental_volume, net_promo_profit
        FROM {FQ}.fact_promotions
        {where}
        ORDER BY start_week, brand
    """)
    for r in promos:
        for k in ("promotion_id", "start_week", "end_week", "promo_roi", "trade_spend",
                  "incremental_volume", "net_promo_profit"):
            r[k] = _num(r.get(k))
    weeks = await run_query(request, f"""
        SELECT week_number, week_start_date, quarter, month
        FROM {FQ}.dim_calendar ORDER BY week_number
    """)
    for wk in weeks:
        wk["week_number"] = _num(wk["week_number"])
    from server.routes.planning import get_plan_state_map
    state_map = await get_plan_state_map()
    for r in promos:
        r["plan_state"] = state_map.get(str(int(r["promotion_id"])))
    return {"promos": promos, "weeks": weeks}


@router.get("/promos/{promotion_id}")
async def promo_detail(promotion_id: int, request: Request):
    """Full detail for one promotion incl. weekly baseline-vs-actual series and write-back state."""
    rows = await run_query(request, f"""
        SELECT * FROM {FQ}.fact_promotions WHERE promotion_id = {promotion_id}
    """)
    if not rows:
        return {"promo": None}
    promo = rows[0]
    for k, v in promo.items():
        promo[k] = _num(v)
    weekly = await run_query(request, f"""
        SELECT week_number, quarter, baseline_volume, actual_volume, is_promo_week
        FROM {FQ}.fact_weekly_sales
        WHERE promotion_id = {promotion_id}
        ORDER BY week_number
    """)
    for wk in weekly:
        wk["week_number"] = _num(wk["week_number"])
        wk["baseline_volume"] = _num(wk["baseline_volume"])
        wk["actual_volume"] = _num(wk["actual_volume"])
        wk["is_promo_week"] = str(wk.get("is_promo_week")).lower() == "true"
    from server.routes.planning import get_plan_state, list_comments
    promo["plan_state"] = await get_plan_state(str(promotion_id))
    promo["comments"] = await list_comments(str(promotion_id))
    return {"promo": promo, "weekly": weekly}


@router.get("/promos/scenario/compare")
async def scenario_compare(
    request: Request,
    market: str | None = None,
    channel: str | None = None,
    brand: str | None = None,
    segment: str | None = None,
):
    """Baseline vs proposed roll-up across the filtered promotion set, plus per-brand breakdown."""
    where = _where(market, channel, brand, segment, None)
    totals = await run_query(request, f"""
        SELECT
          round(sum(baseline_volume_total), 0) AS baseline_volume,
          round(sum(proposed_volume_total), 0) AS proposed_volume,
          round(sum(incremental_volume), 0) AS incremental_volume,
          round(sum(trade_spend), 0) AS trade_spend,
          round(sum(incremental_margin), 0) AS incremental_margin,
          round(sum(net_promo_profit), 0) AS net_profit,
          round(sum(incremental_margin) / nullif(sum(trade_spend), 0), 3) AS roi
        FROM {FQ}.fact_promotions {where}
    """)
    by_brand = await run_query(request, f"""
        SELECT brand,
          round(sum(baseline_volume_total), 0) AS baseline_volume,
          round(sum(proposed_volume_total), 0) AS proposed_volume,
          round(sum(trade_spend), 0) AS trade_spend,
          round(sum(net_promo_profit), 0) AS net_profit,
          round(sum(incremental_margin) / nullif(sum(trade_spend), 0), 3) AS roi
        FROM {FQ}.fact_promotions {where}
        GROUP BY brand ORDER BY net_profit DESC
    """)
    return {
        "totals": {k: _num(v) for k, v in (totals[0] if totals else {}).items()},
        "by_brand": [{k: _num(v) for k, v in r.items()} for r in by_brand],
    }
