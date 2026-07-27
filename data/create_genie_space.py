"""Create a Genie space over the promotion-planning RGM data on fevm.

Usage: python data/create_genie_space.py --profile fevm-serverless --warehouse <id>
"""
import argparse
import json
import uuid
from databricks.sdk import WorkspaceClient

CATALOG = "serverless_razks1_catalog"
SCHEMA = "promo_planning"
TABLES = [f"{CATALOG}.{SCHEMA}.{t}" for t in
          ["fact_promotions", "fact_weekly_sales", "dim_product", "dim_calendar"]]

INSTRUCTIONS = """This Genie space answers Revenue Growth Management (RGM) and trade-promotion
planning questions for a beverage portfolio (AB InBev-style brands).

Key facts:
- fact_promotions: one row per planned promotion. Grain = promotion_id. Columns include
  brand, pack, category, market, channel, customer_segment, promo_mechanic, start_week/end_week
  (1-52 fiscal weeks), quarter, status (Draft/Proposed/Approved/Locked), base_price, promo_price,
  discount_depth, baseline_volume_total, proposed_volume_total, incremental_volume, trade_spend,
  incremental_margin, net_promo_profit, promo_roi, incrementality_pct.
- fact_weekly_sales: weekly baseline vs actual volume per promotion (promotion_id x week_number).
- dim_product: brand / pack / category reference.
- dim_calendar: 52-week fiscal calendar mapping week_number -> quarter and month.

Definitions:
- promo_roi = (incremental_margin - trade_spend) / trade_spend. Negative ROI = the promotion
  loses money. "Overspending with low incrementality" = high trade_spend with low
  incrementality_pct or negative promo_roi.
- incrementality_pct = (proposed_volume_total - baseline_volume_total) / baseline_volume_total.
- Trade spend is the promotional investment; net_promo_profit is incremental margin minus trade spend.

When users ask about "moving promos between quarters", use the quarter column and compare
promo_roi / net_promo_profit. Always prefer showing brand, market, ROI and trade spend together."""

SAMPLE_QUERIES = [
    {"question": "Which promotions have the lowest ROI and highest trade spend?",
     "sql": f"SELECT promotion_code, brand, market, channel, trade_spend, promo_roi, incrementality_pct FROM {CATALOG}.{SCHEMA}.fact_promotions ORDER BY promo_roi ASC, trade_spend DESC LIMIT 20"},
    {"question": "What is total trade spend and net promo profit by market?",
     "sql": f"SELECT market, round(sum(trade_spend)) AS trade_spend, round(sum(net_promo_profit)) AS net_profit, round(sum(incremental_margin)/nullif(sum(trade_spend),0),3) AS roi FROM {CATALOG}.{SCHEMA}.fact_promotions GROUP BY market ORDER BY net_profit DESC"},
    {"question": "Which brands deliver the best promotion ROI?",
     "sql": f"SELECT brand, round(sum(incremental_margin)/nullif(sum(trade_spend),0),3) AS roi, round(sum(net_promo_profit)) AS net_profit FROM {CATALOG}.{SCHEMA}.fact_promotions GROUP BY brand ORDER BY roi DESC"},
    {"question": "Show Q2 promotions with negative net profit we could move to Q3",
     "sql": f"SELECT promotion_code, brand, market, quarter, net_promo_profit, promo_roi FROM {CATALOG}.{SCHEMA}.fact_promotions WHERE quarter='Q2' AND net_promo_profit < 0 ORDER BY net_promo_profit ASC"},
]


def build_serialized_space():
    space = {
        "version": 2,
        "data_sources": {"tables": [{"identifier": t} for t in sorted(TABLES)]},
        "instructions": {
            "text_instructions": [{"id": uuid.uuid4().hex, "content": [INSTRUCTIONS]}],
            "example_question_sqls": sorted(
                [{"id": uuid.uuid4().hex, "question": [q["question"]], "sql": [q["sql"]]} for q in SAMPLE_QUERIES],
                key=lambda x: x["id"],
            ),
        },
    }
    return json.dumps(space)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="fevm-serverless")
    ap.add_argument("--warehouse", required=True)
    args = ap.parse_args()
    w = WorkspaceClient(profile=args.profile)
    host = w.config.host.rstrip("/")
    headers = w.config.authenticate()

    import urllib.request
    body = {
        "title": "Promotion Planning RGM Copilot",
        "description": "Trade-promotion planning & Revenue Growth Management analytics over the promo_planning dataset.",
        "serialized_space": build_serialized_space(),
        "warehouse_id": args.warehouse,
    }
    req = urllib.request.Request(
        f"{host}/api/2.0/genie/spaces",
        data=json.dumps(body).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print("ERROR", e.code, e.read().decode())
        raise SystemExit(1)
    sid = data.get("space_id") or data.get("id")
    print("✅ Created Genie space:", sid)
    print("   Title:", data.get("title"))
    print(f"   URL: {host}/genie/rooms/{sid}")


if __name__ == "__main__":
    main()
