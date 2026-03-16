def test_check_no_key_configured(client, auth_header):
    r = client.get("/llm-keys", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["provider"] is None


def test_set_key(client, auth_header):
    r = client.put("/llm-keys", json={
        "api_key": "sk-test-key-123",
        "provider": "openai",
    }, headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["provider"] == "openai"
    assert "sk-test-key-123" not in r.text


def test_check_after_set(client, auth_header):
    client.put("/llm-keys", json={
        "api_key": "sk-test-key-123",
    }, headers=auth_header)
    r = client.get("/llm-keys", headers=auth_header)
    assert r.status_code == 200
    assert r.json()["configured"] is True
    assert r.json()["provider"] == "openai"


def test_update_key(client, auth_header):
    client.put("/llm-keys", json={
        "api_key": "sk-old-key",
    }, headers=auth_header)
    r = client.put("/llm-keys", json={
        "api_key": "sk-new-key",
    }, headers=auth_header)
    assert r.status_code == 200
    assert r.json()["configured"] is True


def test_key_never_returned(client, auth_header):
    client.put("/llm-keys", json={
        "api_key": "sk-super-secret",
    }, headers=auth_header)

    r_check = client.get("/llm-keys", headers=auth_header)
    assert "sk-super-secret" not in r_check.text


def test_requires_auth(client):
    r = client.get("/llm-keys")
    assert r.status_code in (401, 403)
    r = client.put("/llm-keys", json={"api_key": "sk-x"})
    assert r.status_code in (401, 403)


def test_different_providers(client, auth_header):
    client.put("/llm-keys", json={
        "api_key": "sk-openai",
        "provider": "openai",
    }, headers=auth_header)
    client.put("/llm-keys", json={
        "api_key": "sk-anthropic",
        "provider": "anthropic",
    }, headers=auth_header)

    r1 = client.get("/llm-keys?provider=openai", headers=auth_header)
    assert r1.json()["configured"] is True

    r2 = client.get("/llm-keys?provider=anthropic", headers=auth_header)
    assert r2.json()["configured"] is True

    r3 = client.get("/llm-keys?provider=gemini", headers=auth_header)
    assert r3.json()["configured"] is False
