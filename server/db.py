import os
import uuid
import asyncpg
from typing import Optional
from server.config import get_workspace_client, IS_DATABRICKS_APP


LAKEBASE_INSTANCE = os.environ.get("LAKEBASE_INSTANCE", "lakebase-demo")


class DatabasePool:
    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def get_pool(self) -> Optional[asyncpg.Pool]:
        host = os.environ.get("PGHOST", "")
        if not host:
            # Fall back to SDK lookup so the app works even when the Apps resource
            # injection isn't populating PGHOST. We look up the read_write_dns of
            # the configured Lakebase instance.
            host = _lookup_lakebase_host(LAKEBASE_INSTANCE)
            if not host:
                print("[db] PGHOST not set and SDK lookup failed — skipping Lakebase")
                return None
            print(f"[db] PGHOST resolved via SDK: {host}")

        # Try existing pool first
        if self._pool is not None:
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute("SELECT 1")
                return self._pool
            except Exception:
                # Token likely expired — close and recreate
                print("[db] Pool health check failed, refreshing token...")
                try:
                    await self._pool.close()
                except Exception:
                    pass
                self._pool = None

        port = int(os.environ.get("PGPORT", "5432"))
        database = os.environ.get("PGDATABASE", "promo_planner")
        user = _get_user()
        password = _get_token()

        print(f"[db] Connecting to Lakebase: host={host}, port={port}, db={database}, user={user}, has_password={bool(password)}")
        try:
            self._pool = await asyncpg.create_pool(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                ssl="require",
                min_size=1,
                max_size=5,
            )
            print("[db] Lakebase pool created successfully")
            return self._pool
        except Exception as e:
            print(f"[db] Lakebase connection failed: {e}")
            return None

    async def refresh_token(self):
        """Refresh OAuth token by recreating the pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
        return await self.get_pool()

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None


_cached_host: Optional[str] = None


def _lookup_lakebase_host(instance_name: str) -> str:
    """Look up the read_write_dns for a Lakebase instance via SDK. Cached.

    Tries `get_database_instance` first; falls back to scanning `list_database_instances`.
    """
    global _cached_host
    if _cached_host:
        return _cached_host
    try:
        w = get_workspace_client()
        try:
            inst = w.database.get_database_instance(name=instance_name)
            host = getattr(inst, "read_write_dns", "") or ""
            if host:
                _cached_host = host
                return host
        except Exception as e1:
            print(f"[db] get_database_instance failed ({e1}), trying list scan…")
        for inst in w.database.list_database_instances():
            if inst.name == instance_name:
                host = getattr(inst, "read_write_dns", "") or ""
                if host:
                    _cached_host = host
                    return host
    except Exception as e:
        print(f"[db] _lookup_lakebase_host failed for {instance_name}: {e}")
    return ""


def _get_user() -> str:
    """Get the Postgres username for Lakebase.

    For Databricks Apps, this is the service principal's client ID (UUID).
    For local dev, it's the user's email from the workspace client.
    """
    # If PGUSER env var looks like a valid user (not a hostname), use it
    pg_user = os.environ.get("PGUSER", "")
    if pg_user and not pg_user.startswith("ep-") and "database" not in pg_user:
        return pg_user
    # Get user from SDK
    try:
        w = get_workspace_client()
        me = w.current_user.me()
        user = me.user_name or ""
        print(f"[db] Resolved PGUSER from SDK: {user}")
        return user
    except Exception as e:
        print(f"[db] Failed to get user from SDK: {e}")
    return pg_user


def _get_token() -> str:
    """Get OAuth token for Lakebase.

    Uses the Databricks SDK to generate a database credential token,
    which is the correct auth mechanism for Lakebase (not workspace tokens).
    Falls back to PGPASSWORD env var if set, then workspace token as last resort.
    """
    # 1. Try PGPASSWORD env var (may be injected by Databricks Apps)
    pg_password = os.environ.get("PGPASSWORD", "")
    if pg_password:
        print("[db] Using PGPASSWORD env var")
        return pg_password

    # 2. Generate a Lakebase-specific database credential via SDK
    try:
        w = get_workspace_client()
        cred = w.database.generate_database_credential(
            request_id=str(uuid.uuid4()),
            instance_names=[LAKEBASE_INSTANCE],
        )
        if cred and cred.token:
            print("[db] Generated Lakebase database credential token")
            return cred.token
    except Exception as e:
        print(f"[db] Database credential generation failed: {e}")

    # 3. Last resort: workspace OAuth token
    try:
        w = get_workspace_client()
        headers = w.config.authenticate()
        if headers and "Authorization" in headers:
            print("[db] Falling back to workspace OAuth token")
            return headers["Authorization"].replace("Bearer ", "")
    except Exception as e:
        print(f"[db] Workspace token generation failed: {e}")

    return ""


db = DatabasePool()
