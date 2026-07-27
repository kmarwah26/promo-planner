import os
from databricks.sdk import WorkspaceClient

IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

# On-behalf-of-user master switch. OBO requires each user's forwarded token to
# carry the requested OAuth scopes (sql, dashboards.genie, catalog.catalogs, …),
# which only happens once the user consents to that exact scope set. When scopes
# are added to an already-consented app, the delta scopes don't reliably activate
# for existing users, so OBO calls 403. Default OFF: all calls use the service
# principal (which has the app's mirrored UC/Genie/warehouse grants). Set
# OBO_ENABLED=true in app.yaml once user-authorization consent is confirmed.
OBO_ENABLED = os.environ.get("OBO_ENABLED", "false").lower() in ("1", "true", "yes", "on")

# Reuse a single service-principal WorkspaceClient to avoid repeated SDK init.
_workspace_client: WorkspaceClient | None = None


def _get_sp_client() -> WorkspaceClient:
    """Cached service-principal (or local profile) WorkspaceClient.

    Used for background/shared work that isn't tied to a user request, and as the
    fallback whenever no user OAuth token is available.
    """
    global _workspace_client
    if _workspace_client is None:
        if IS_DATABRICKS_APP:
            _workspace_client = WorkspaceClient()
        else:
            profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
            _workspace_client = WorkspaceClient(profile=profile)
    return _workspace_client


def get_user_token(request) -> str | None:
    """The logged-in user's OAuth token, forwarded by Databricks Apps.

    Present only when running as a Databricks App with `user_authorization`
    scopes declared in app.yaml. Returns None in local dev or if the header is
    absent, so callers can fall back to the service principal.
    """
    if not OBO_ENABLED or request is None or not IS_DATABRICKS_APP:
        return None
    return request.headers.get("X-Forwarded-Access-Token") or None


def get_workspace_client(request=None) -> WorkspaceClient:
    """Return a WorkspaceClient for Databricks SDK calls.

    On-behalf-of-user: when `request` carries the user's forwarded OAuth token,
    return a client authenticated as that user so the call runs with their Unity
    Catalog / workspace permissions. Otherwise (local dev, missing header, or no
    request) return the cached service-principal client.
    """
    token = get_user_token(request)
    if token:
        # auth_type="pat" pins bearer-token auth so the SDK doesn't also pick up
        # the service principal's OAuth client_id/secret from the Apps environment,
        # which would raise "more than one authorization method configured".
        return WorkspaceClient(host=get_workspace_host(), token=token, auth_type="pat")
    return _get_sp_client()


def get_workspace_host() -> str:
    if IS_DATABRICKS_APP:
        host = os.environ.get("DATABRICKS_HOST", "")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        return host
    return _get_sp_client().config.host


def get_auth_headers(request=None) -> dict:
    """Return REST Authorization headers.

    On-behalf-of-user: prefer the user's forwarded OAuth token so REST calls run
    with their permissions. Falls back to the service principal when no user
    token is available (local dev or missing header).
    """
    token = get_user_token(request)
    if token:
        return {"Authorization": f"Bearer {token}"}
    return _get_sp_client().config.authenticate()


def get_user_auth_headers(request) -> dict | None:
    """User-only OBO headers, or None when no user token is available.

    Kept for callers that need to distinguish OBO from SP explicitly. Most code
    should prefer get_auth_headers(request), which falls back to the SP.
    """
    token = get_user_token(request)
    return {"Authorization": f"Bearer {token}"} if token else None


# Message shown when an OBO call is rejected for lack of scope. A 403 here almost
# always means the app's user_api_scopes changed after this user last consented,
# so their forwarded token predates the scope and can't be fixed in code — the
# user must re-authorize. Surfacing this verbatim beats a raw "403 Forbidden".
OBO_REAUTH_MESSAGE = (
    "Access denied (403): your session is missing the required permission. "
    "Sign out and reopen the app to re-authorize (accept the permissions "
    "prompt). If it persists, ask an admin to confirm the app's user "
    "authorization scopes include Genie and SQL warehouse access."
)
