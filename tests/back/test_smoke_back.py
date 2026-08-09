import pytest

pytestmark = pytest.mark.unit


def test_version_endpoint(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    assert r.get_json()["export"] == 27


def test_create_memo_minimal(client):
    pid = client.post("/api/projects", json={"name": "Smoke"}).get_json()["id"]
    r = client.post("/api/memos", json={"content": "hello", "project_id": pid})
    assert r.status_code == 201, r.data
    assert r.get_json()["content"] == "hello"


def test_create_memo_requires_content_or_title(client):
    r = client.post("/api/memos", json={})
    assert r.status_code == 400
