import json
from unittest.mock import patch, MagicMock

from app.auth.security import create_access_token
from app.config import settings
from app.encryption import decrypt


# ── helpers ──────────────────────────────────────────────────────────────────

def _fake_token_response(*args, **kwargs):
    """Fake Google token exchange response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "access_token": "ya29.fake-access-token",
        "refresh_token": "1//fake-refresh-token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    return resp


def _fake_userinfo_response(*args, **kwargs):
    """Fake Google userinfo response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"email": "user@gmail.com", "verified_email": True}
    return resp


def _make_state(auth_header: dict, client) -> str:
    """Get an OAuth state token via the start-oauth endpoint."""
    settings.google_client_id = "fake-client-id"
    settings.google_client_secret = "fake-client-secret"
    r = client.post("/email-accounts/gmail/start-oauth", headers=auth_header)
    assert r.status_code == 200
    auth_url = r.json()["auth_url"]
    state = auth_url.split("state=")[1].split("&")[0]
    return state


# ── start-oauth tests ───────────────────────────────────────────────────────

def test_start_oauth_returns_auth_url(client, auth_header):
    settings.google_client_id = "fake-client-id"
    settings.google_client_secret = "fake-client-secret"
    r = client.post("/email-accounts/gmail/start-oauth", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert "auth_url" in body
    assert "accounts.google.com" in body["auth_url"]
    assert "fake-client-id" in body["auth_url"]
    assert "gmail.modify" in body["auth_url"]
    assert "state=" in body["auth_url"]


def test_start_oauth_requires_auth(client):
    r = client.post("/email-accounts/gmail/start-oauth")
    assert r.status_code in (401, 403)


def test_start_oauth_fails_without_google_config(client, auth_header):
    settings.google_client_id = ""
    settings.google_client_secret = ""
    r = client.post("/email-accounts/gmail/start-oauth", headers=auth_header)
    assert r.status_code == 500


# ── oauth-callback tests ────────────────────────────────────────────────────

@patch("app.routers.email_accounts._get_google_user_info", return_value={"email": "user@gmail.com", "name": None})
@patch("app.routers.email_accounts._exchange_code_for_tokens", return_value={
    "access_token": "ya29.fake-access-token",
    "refresh_token": "1//fake-refresh-token",
    "expires_in": 3600,
})
def test_oauth_callback_creates_account(mock_exchange, mock_userinfo, client, auth_header):
    state = _make_state(auth_header, client)
    r = client.get(
        "/email-accounts/gmail/oauth-callback",
        params={"code": "fake-auth-code", "state": state},
        follow_redirects=False,
    )
    assert r.status_code in (302, 307)

    r2 = client.get("/email-accounts", headers=auth_header)
    assert r2.status_code == 200
    accounts = r2.json()
    assert len(accounts) == 1
    assert accounts[0]["email_address"] == "user@gmail.com"
    assert accounts[0]["provider"] == "gmail"
    assert accounts[0]["status"] == "active"


@patch("app.routers.email_accounts._get_google_user_info", return_value={"email": "user@gmail.com", "name": None})
@patch("app.routers.email_accounts._exchange_code_for_tokens", return_value={
    "access_token": "ya29.fake-access-token",
    "refresh_token": "1//fake-refresh-token",
    "expires_in": 3600,
})
def test_oauth_callback_stores_encrypted_tokens(mock_exchange, mock_userinfo, client, auth_header):
    state = _make_state(auth_header, client)
    client.get(
        "/email-accounts/gmail/oauth-callback",
        params={"code": "fake-auth-code", "state": state},
        follow_redirects=False,
    )

    from tests.conftest import TestSession
    from app.models.email_account import EmailAccount

    db = TestSession()
    account = db.query(EmailAccount).first()
    assert account is not None

    # oauth_encrypted should not be plain JSON
    assert "ya29" not in account.oauth_encrypted

    # but decrypting it should give us the token data
    decrypted = json.loads(decrypt(account.oauth_encrypted))
    assert decrypted["access_token"] == "ya29.fake-access-token"
    assert decrypted["refresh_token"] == "1//fake-refresh-token"
    db.close()


@patch("app.routers.email_accounts._get_google_user_info", return_value={"email": "user@gmail.com", "name": None})
@patch("app.routers.email_accounts._exchange_code_for_tokens", return_value={
    "access_token": "ya29.fake-access-token",
    "refresh_token": "1//fake-refresh-token",
    "expires_in": 3600,
})
def test_oauth_callback_initializes_sync_cursor(mock_exchange, mock_userinfo, client, auth_header):
    state = _make_state(auth_header, client)
    client.get(
        "/email-accounts/gmail/oauth-callback",
        params={"code": "fake-auth-code", "state": state},
        follow_redirects=False,
    )

    from tests.conftest import TestSession
    from app.models.email_account import EmailAccount

    db = TestSession()
    account = db.query(EmailAccount).first()
    cursor = json.loads(account.sync_cursor_json)
    assert cursor["history_id"] is None
    assert cursor["last_polled_at"] is None
    db.close()


def test_oauth_callback_rejects_invalid_state(client):
    r = client.get(
        "/email-accounts/gmail/oauth-callback",
        params={"code": "fake-auth-code", "state": "bogus-state"},
    )
    assert r.status_code == 400


@patch("app.routers.email_accounts._get_google_user_info", return_value={"email": "user@gmail.com", "name": None})
@patch("app.routers.email_accounts._exchange_code_for_tokens", return_value={
    "access_token": "ya29.new-token",
    "refresh_token": "1//new-refresh",
    "expires_in": 3600,
})
def test_oauth_callback_reconnect_updates_existing(mock_exchange, mock_userinfo, client, auth_header):
    """Re-connecting the same Gmail should update tokens, not create a duplicate."""
    state1 = _make_state(auth_header, client)
    client.get(
        "/email-accounts/gmail/oauth-callback",
        params={"code": "code1", "state": state1},
        follow_redirects=False,
    )

    state2 = _make_state(auth_header, client)
    client.get(
        "/email-accounts/gmail/oauth-callback",
        params={"code": "code2", "state": state2},
        follow_redirects=False,
    )

    r = client.get("/email-accounts", headers=auth_header)
    accounts = r.json()
    assert len(accounts) == 1
    assert accounts[0]["status"] == "active"


# ── list accounts tests ─────────────────────────────────────────────────────

def test_list_accounts_empty(client, auth_header):
    r = client.get("/email-accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.json() == []


def test_list_accounts_requires_auth(client):
    r = client.get("/email-accounts")
    assert r.status_code in (401, 403)


@patch("app.routers.email_accounts._get_google_user_info", return_value={"email": "user@gmail.com", "name": None})
@patch("app.routers.email_accounts._exchange_code_for_tokens", return_value={
    "access_token": "ya29.fake", "refresh_token": "1//fake", "expires_in": 3600,
})
def test_list_accounts_never_leaks_tokens(mock_exchange, mock_userinfo, client, auth_header):
    state = _make_state(auth_header, client)
    client.get(
        "/email-accounts/gmail/oauth-callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )

    r = client.get("/email-accounts", headers=auth_header)
    text = r.text
    assert "ya29" not in text
    assert "oauth_encrypted" not in text
    assert "sync_cursor" not in text


# ── disconnect tests ─────────────────────────────────────────────────────────

@patch("app.routers.email_accounts._get_google_user_info", return_value={"email": "user@gmail.com", "name": None})
@patch("app.routers.email_accounts._exchange_code_for_tokens", return_value={
    "access_token": "ya29.fake", "refresh_token": "1//fake", "expires_in": 3600,
})
def test_disconnect_account(mock_exchange, mock_userinfo, client, auth_header):
    state = _make_state(auth_header, client)
    client.get(
        "/email-accounts/gmail/oauth-callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )

    accounts = client.get("/email-accounts", headers=auth_header).json()
    account_id = accounts[0]["id"]

    r = client.post(f"/email-accounts/{account_id}/disconnect", headers=auth_header)
    assert r.status_code == 200
    assert r.json()["status"] == "disconnected"

    accounts_after = client.get("/email-accounts", headers=auth_header).json()
    assert accounts_after[0]["status"] == "disconnected"


def test_disconnect_nonexistent_account(client, auth_header):
    import uuid
    fake_id = str(uuid.uuid4())
    r = client.post(f"/email-accounts/{fake_id}/disconnect", headers=auth_header)
    assert r.status_code == 404


def test_disconnect_requires_auth(client):
    import uuid
    r = client.post(f"/email-accounts/{uuid.uuid4()}/disconnect")
    assert r.status_code in (401, 403)


# ── tenant isolation test ───────────────────────────────────────────────────

@patch("app.routers.email_accounts._get_google_user_info", return_value={"email": "user@gmail.com", "name": None})
@patch("app.routers.email_accounts._exchange_code_for_tokens", return_value={
    "access_token": "ya29.fake", "refresh_token": "1//fake", "expires_in": 3600,
})
def test_tenant_isolation(mock_exchange, mock_userinfo, client):
    """Accounts from tenant A should not be visible to tenant B."""
    # Register tenant A
    r1 = client.post("/auth/register", json={
        "tenant_name": "TenantA", "email": "a@a.com", "password": "pass",
    })
    header_a = {"Authorization": f"Bearer {r1.json()['access_token']}"}

    # Register tenant B
    r2 = client.post("/auth/register", json={
        "tenant_name": "TenantB", "email": "b@b.com", "password": "pass",
    })
    header_b = {"Authorization": f"Bearer {r2.json()['access_token']}"}

    # Connect Gmail for tenant A
    settings.google_client_id = "fake-client-id"
    settings.google_client_secret = "fake-client-secret"
    state_a = client.post("/email-accounts/gmail/start-oauth", headers=header_a).json()["auth_url"]
    state_a = state_a.split("state=")[1].split("&")[0]
    client.get(
        "/email-accounts/gmail/oauth-callback",
        params={"code": "code", "state": state_a},
        follow_redirects=False,
    )

    # Tenant A sees account, Tenant B does not
    assert len(client.get("/email-accounts", headers=header_a).json()) == 1
    assert len(client.get("/email-accounts", headers=header_b).json()) == 0
