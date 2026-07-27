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
               baseline_volume, elasticity, fixed_fee, margin_per_case, lift_multiplier,
               baseline_volume_total, proposed_volume_total, incremental_volume,
               trade_spend, incremental_margin, net_promo_profit, promo_roi, incrementality_pct
        FROM {FQ}.fact_promotions
        {where}
        ORDER BY promotion_id
    """)
    for r in rows:
        for k in ("base_price", "promo_price", "discount_depth", "baseline_volume", "elasticity",
                  "fixed_fee", "margin_per_case", "lift_multiplier", "baseline_volume_total",
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


def _econ(base_price, baseline_volume, duration_weeks, elasticity, fixed_fee, margin_per_case, discount):
    """Recompute promotion economics from a discount depth. Mirrors the SQL elasticity
    model in data/generate_rgm_data.py and the frontend computeEcon() exactly."""
    lift = 1 + elasticity * discount
    proposed = baseline_volume * lift * duration_weeks
    incremental = baseline_volume * (lift - 1) * duration_weeks
    trade = base_price * discount * proposed + fixed_fee
    margin = incremental * margin_per_case
    net = margin - trade
    return {
        "baseline_volume": baseline_volume * duration_weeks,
        "proposed_volume": proposed,
        "incremental_volume": incremental,
        "trade_spend": trade,
        "incremental_margin": margin,
        "net_profit": net,
        "roi": (net / trade) if trade else 0.0,
        "incrementality_pct": lift - 1,
    }


def _agg(econs: list[dict]) -> dict:
    """Sum a list of per-promo econ dicts into a totals block (with blended ROI)."""
    keys = ["baseline_volume", "proposed_volume", "incremental_volume", "trade_spend",
            "incremental_margin", "net_profit"]
    out = {k: sum(e[k] for e in econs) for k in keys}
    # ROI must match the per-promo definition: net profit / trade spend.
    out["roi"] = (out["net_profit"] / out["trade_spend"]) if out["trade_spend"] else 0.0
    return {k: round(v, 3) for k, v in out.items()}


@router.get("/promos/scenario/compare")
async def scenario_compare(
    request: Request,
    market: str | None = None,
    channel: str | None = None,
    brand: str | None = None,
    segment: str | None = None,
):
    """Compare the CURRENT committed plan against the SAVED scenario.

    Current = each promotion's committed discount_depth. Scenario = the discount saved
    in Lakebase (adjusted_discount), falling back to the committed discount where no
    scenario has been saved. Economics for both are recomputed with the elasticity model,
    then aggregated overall and by market / channel / brand, with ROI winners/losers and
    the best/worst promotion callouts.
    """
    where = _where(market, channel, brand, segment, None)
    rows = await run_query(request, f"""
        SELECT promotion_id, promotion_code, brand, market, channel, promo_mechanic,
               base_price, baseline_volume, duration_weeks, elasticity, fixed_fee,
               margin_per_case, discount_depth
        FROM {FQ}.fact_promotions {where}
    """)
    numeric = ("base_price", "baseline_volume", "duration_weeks", "elasticity",
               "fixed_fee", "margin_per_case", "discount_depth", "promotion_id")
    for r in rows:
        for k in numeric:
            r[k] = _num(r.get(k))

    # Overlay saved scenario discounts from Lakebase.
    from server.routes.planning import get_plan_state_map
    state_map = await get_plan_state_map()

    per_promo = []
    for r in rows:
        st = state_map.get(str(int(r["promotion_id"])))
        cur_disc = r["discount_depth"]
        scen_disc = st["adjusted_discount"] if st and st.get("adjusted_discount") is not None else cur_disc
        args = (r["base_price"], r["baseline_volume"], r["duration_weeks"],
                r["elasticity"], r["fixed_fee"], r["margin_per_case"])
        cur = _econ(*args, cur_disc)
        scen = _econ(*args, scen_disc)
        per_promo.append({
            "promotion_id": int(r["promotion_id"]),
            "promotion_code": r["promotion_code"],
            "brand": r["brand"], "market": r["market"], "channel": r["channel"],
            "promo_mechanic": r["promo_mechanic"],
            "current_discount": round(cur_disc, 4),
            "scenario_discount": round(scen_disc, 4),
            "has_scenario": bool(st and st.get("adjusted_discount") is not None and abs(scen_disc - cur_disc) > 1e-9),
            "current": cur, "scenario": scen,
            "roi_delta": round(scen["roi"] - cur["roi"], 4),
            "profit_delta": round(scen["net_profit"] - cur["net_profit"], 2),
        })

    def breakdown(dim: str):
        groups: dict[str, dict] = {}
        for p in per_promo:
            g = groups.setdefault(p[dim], {"cur": [], "scen": []})
            g["cur"].append(p["current"]); g["scen"].append(p["scenario"])
        out = []
        for name, g in groups.items():
            cur, scen = _agg(g["cur"]), _agg(g["scen"])
            out.append({
                "name": name,
                "current": cur, "scenario": scen,
                "profit_delta": round(scen["net_profit"] - cur["net_profit"], 2),
                "roi_delta": round(scen["roi"] - cur["roi"], 4),
            })
        return sorted(out, key=lambda x: x["scenario"]["net_profit"], reverse=True)

    n_scenarios = sum(1 for p in per_promo if p["has_scenario"])
    winners = sorted([p for p in per_promo], key=lambda p: p["scenario"]["roi"], reverse=True)[:5]
    losers = sorted([p for p in per_promo], key=lambda p: p["scenario"]["roi"])[:5]

    def slim(p):
        return {
            "promotion_id": p["promotion_id"], "promotion_code": p["promotion_code"],
            "brand": p["brand"], "market": p["market"], "channel": p["channel"],
            "promo_mechanic": p["promo_mechanic"],
            "scenario_discount": p["scenario_discount"], "has_scenario": p["has_scenario"],
            "roi": round(p["scenario"]["roi"], 4),
            "trade_spend": round(p["scenario"]["trade_spend"], 2),
            "net_profit": round(p["scenario"]["net_profit"], 2),
            "roi_delta": p["roi_delta"], "profit_delta": p["profit_delta"],
        }

    return {
        "n_promos": len(per_promo),
        "n_scenarios": n_scenarios,
        "current_totals": _agg([p["current"] for p in per_promo]) if per_promo else {},
        "scenario_totals": _agg([p["scenario"] for p in per_promo]) if per_promo else {},
        "by_market": breakdown("market"),
        "by_channel": breakdown("channel"),
        "by_brand": breakdown("brand"),
        "winners": [slim(p) for p in winners],
        "losers": [slim(p) for p in losers],
        "movers": [slim(p) for p in sorted(
            [p for p in per_promo if p["has_scenario"]],
            key=lambda p: abs(p["profit_delta"]), reverse=True)[:8]],
    }
