# Promotion Planning Genie Agents — Deployment

This app is a Databricks App (FastAPI backend + prebuilt React frontend) with a Lakebase
(Postgres) write-back store and a Genie space over Unity Catalog data.

The live demo is deployed on the **fevm-serverless** workspace:
`https://promo-planner-7474647755495738.aws.databricksapps.com`

## Prerequisites

- Databricks CLI v0.229+ authenticated to the target workspace (`databricks auth login`)
- Node.js 18+ and Python 3.11+ (for local builds)
- A serverless SQL warehouse
- A Lakebase instance (this demo reuses `lakebase-demo`)

## 1. Data + Genie space (one-time)

```bash
# Generate the RGM demo tables in Unity Catalog
python data/generate_rgm_data.py --profile <profile> --warehouse <warehouse_id>

# Create the Genie space over them
python data/create_genie_space.py --profile <profile> --warehouse <warehouse_id>
```

These write to `serverless_razks1_catalog.promo_planning` (override with `CATALOG`/`SCHEMA`
in the scripts). Create the Lakebase database once:

```bash
databricks psql lakebase-demo -p <profile> -- -c "CREATE DATABASE promo_planner;"
```

## 2. Build the frontend

```bash
cd frontend && npm install && npm run build && cd ..
```

The build output `frontend/dist/` is deployed with the app — do not delete it.

## 3. Create the app + grant the service principal

```bash
databricks apps create promo-planner \
  --description "Promotion Planning Genie Agents" -p <profile>

# Get the app's service principal client id
SP=$(databricks apps get promo-planner -p <profile> --output json | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['service_principal_client_id'])")

# Warehouse
databricks permissions update warehouses <warehouse_id> \
  --json "{\"access_control_list\":[{\"service_principal_name\":\"$SP\",\"permission_level\":\"CAN_USE\"}]}" -p <profile>

# Unity Catalog (read the RGM data)
databricks grants update catalog serverless_razks1_catalog \
  --json "{\"changes\":[{\"principal\":\"$SP\",\"add\":[\"USE_CATALOG\"]}]}" -p <profile>
databricks grants update schema serverless_razks1_catalog.promo_planning \
  --json "{\"changes\":[{\"principal\":\"$SP\",\"add\":[\"USE_SCHEMA\",\"SELECT\"]}]}" -p <profile>

# Genie space (CAN_RUN) — replace <space_id>
curl -s -X PATCH -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  "<host>/api/2.0/permissions/genie/<space_id>" \
  -d "{\"access_control_list\":[{\"service_principal_name\":\"$SP\",\"permission_level\":\"CAN_RUN\"}]}"
```

## 4. Attach Lakebase + grant Postgres role

```bash
databricks apps update promo-planner --json '{
  "resources": [{
    "name": "promo-planner-db",
    "database": {"instance_name": "lakebase-demo", "database_name": "promo_planner", "permission": "CAN_CONNECT_AND_CREATE"}
  }]
}' -p <profile>

# The Postgres role for the SP exists once the resource is attached — grant it:
databricks psql lakebase-demo -p <profile> -- -d promo_planner -c "
GRANT ALL PRIVILEGES ON DATABASE promo_planner TO \"$SP\";
GRANT ALL PRIVILEGES ON SCHEMA public TO \"$SP\";
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"$SP\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO \"$SP\";
"
```

The `promo_plan_state`, `promo_comments` and `promo_activity` tables are created
automatically on first write.

## 5. Sync + deploy

```bash
USERNAME=$(databricks current-user me -p <profile> --output json | python3 -c "import sys,json;print(json.load(sys.stdin)['userName'])")

databricks sync . "/Users/$USERNAME/promo-planner" \
  --exclude node_modules --exclude .venv --exclude __pycache__ --exclude .git \
  --exclude "frontend/src" --exclude "frontend/public" --exclude "frontend/node_modules" \
  --exclude "data" -p <profile>

databricks apps deploy promo-planner \
  --source-code-path "/Workspace/Users/$USERNAME/promo-planner" -p <profile>
```

## Config (app.yaml env)

| Var | Purpose |
|-----|---------|
| `OBO_ENABLED` | `false` = run as service principal (demo default); `true` = on-behalf-of-user |
| `LAKEBASE_INSTANCE`, `PGDATABASE`, `PGHOST` | Lakebase write-back connection |
| `PROMO_CATALOG`, `PROMO_SCHEMA` | Unity Catalog location of the RGM data |
| `PROMO_WAREHOUSE_ID` | SQL warehouse used for all reads |

## Verify

```bash
URL=$(databricks apps get promo-planner -p <profile> --output json | python3 -c "import sys,json;print(json.load(sys.stdin)['url'])")
TOKEN=$(databricks auth token -p <profile> | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -H "Authorization: Bearer $TOKEN" "$URL/api/db-health"      # -> "status":"connected"
curl -s -H "Authorization: Bearer $TOKEN" "$URL/api/promos/kpis"    # -> portfolio KPIs
```
