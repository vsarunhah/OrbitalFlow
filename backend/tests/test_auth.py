def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_register(client):
    r = client.post("/auth/register", json={
        "tenant_name": "Acme Corp",
        "email": "alice@acme.com",
        "password": "secret123",
    })
    assert r.status_code == 201
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_register_duplicate_email(client):
    payload = {
        "tenant_name": "Acme Corp",
        "email": "alice@acme.com",
        "password": "secret123",
    }
    client.post("/auth/register", json=payload)
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 409


def test_login_success(client):
    client.post("/auth/register", json={
        "tenant_name": "Acme Corp",
        "email": "alice@acme.com",
        "password": "secret123",
    })
    r = client.post("/auth/login", json={
        "email": "alice@acme.com",
        "password": "secret123",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password(client):
    client.post("/auth/register", json={
        "tenant_name": "Acme Corp",
        "email": "alice@acme.com",
        "password": "secret123",
    })
    r = client.post("/auth/login", json={
        "email": "alice@acme.com",
        "password": "wrong",
    })
    assert r.status_code == 401


def test_me_requires_auth(client):
    r = client.get("/auth/me")
    assert r.status_code in (401, 403)


def test_me_with_valid_token(client):
    reg = client.post("/auth/register", json={
        "tenant_name": "Acme Corp",
        "email": "alice@acme.com",
        "password": "secret123",
    })
    token = reg.json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "alice@acme.com"
    assert "user_id" in body
    assert "tenant_id" in body


def test_me_with_bad_token(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_refresh_with_valid_token(client):
    reg = client.post("/auth/register", json={
        "tenant_name": "Acme Corp",
        "email": "alice@acme.com",
        "password": "secret123",
    })
    token = reg.json()["access_token"]
    r = client.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    # new token works for /me
    r2 = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert r2.status_code == 200
    assert r2.json()["email"] == "alice@acme.com"


def test_refresh_without_token(client):
    r = client.post("/auth/refresh")
    assert r.status_code in (401, 403)


def test_forgot_password_returns_204(client):
    r = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 204


def test_reset_password_invalid_token(client):
    r = client.post(
        "/auth/reset-password",
        json={"token": "invalid-token", "new_password": "newsecret123"},
    )
    assert r.status_code == 400


def test_reset_password_success(client):
    client.post(
        "/auth/register",
        json={
            "tenant_name": "Acme Corp",
            "email": "alice@acme.com",
            "password": "secret123",
        },
    )
    from app.auth.security import create_password_reset_token
    from app.models.user import User

    from tests.conftest import TestSession

    db = TestSession()
    try:
        user = db.query(User).filter(User.email == "alice@acme.com").first()
        assert user is not None
        token = create_password_reset_token(str(user.id))
    finally:
        db.close()

    r = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "newsecret456"},
    )
    assert r.status_code == 204

    r = client.post(
        "/auth/login",
        json={"email": "alice@acme.com", "password": "newsecret456"},
    )
    assert r.status_code == 200
    assert "access_token" in r.json()
