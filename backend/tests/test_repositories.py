"""Repository CRUD API tests on isolated SQLite (never real Supabase)."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import use_owner

LOCAL = {"name": "my-project", "source_type": "local", "local_path": "/tmp/my-project"}
GIT = {
    "name": "web-app",
    "source_type": "git",
    "source_url": "https://example.com/org/web-app.git",
}


def test_create_local_repository(client: TestClient) -> None:
    use_owner("owner-A")
    response = client.post("/api/v1/repositories", json=LOCAL)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "my-project"
    assert body["owner_id"] == "owner-A"
    assert body["status"] == "pending"
    assert body["id"]


def test_create_rejects_invalid_source_type(client: TestClient) -> None:
    use_owner("owner-A")
    response = client.post(
        "/api/v1/repositories",
        json={"name": "x", "source_type": "svn", "local_path": "/tmp/x"},
    )
    assert response.status_code == 422


def test_create_local_requires_path(client: TestClient) -> None:
    use_owner("owner-A")
    response = client.post(
        "/api/v1/repositories", json={"name": "x", "source_type": "local"}
    )
    assert response.status_code == 422


def test_create_git_requires_url(client: TestClient) -> None:
    use_owner("owner-A")
    response = client.post(
        "/api/v1/repositories", json={"name": "x", "source_type": "git"}
    )
    assert response.status_code == 422


def test_create_rejects_blank_name(client: TestClient) -> None:
    use_owner("owner-A")
    response = client.post(
        "/api/v1/repositories",
        json={"name": "   ", "source_type": "local", "local_path": "/tmp/x"},
    )
    assert response.status_code == 422


def test_get_repository(client: TestClient) -> None:
    use_owner("owner-A")
    created = client.post("/api/v1/repositories", json=LOCAL).json()
    response = client.get(f"/api/v1/repositories/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_missing_repository_is_404(client: TestClient) -> None:
    use_owner("owner-A")
    response = client.get("/api/v1/repositories/123e4567-e89b-12d3-a456-426614174000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REPOSITORY_NOT_FOUND"


def test_get_invalid_uuid_is_422(client: TestClient) -> None:
    use_owner("owner-A")
    assert client.get("/api/v1/repositories/not-a-uuid").status_code == 422


def test_owner_cannot_access_other_owner_repository(client: TestClient) -> None:
    use_owner("owner-A")
    created = client.post("/api/v1/repositories", json=LOCAL).json()
    use_owner("owner-B")
    response = client.get(f"/api/v1/repositories/{created['id']}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REPOSITORY_NOT_FOUND"


def test_list_returns_only_own_repositories(client: TestClient) -> None:
    use_owner("owner-A")
    client.post("/api/v1/repositories", json=LOCAL)
    client.post("/api/v1/repositories", json=GIT)
    use_owner("owner-B")
    client.post("/api/v1/repositories", json={**LOCAL, "name": "b-repo"})
    use_owner("owner-A")
    body = client.get("/api/v1/repositories").json()
    assert body["total"] == 2
    assert {item["owner_id"] for item in body["items"]} == {"owner-A"}
    use_owner("owner-B")
    body = client.get("/api/v1/repositories").json()
    assert body["total"] == 1


def test_update_allowed_fields(client: TestClient) -> None:
    use_owner("owner-A")
    created = client.post("/api/v1/repositories", json=GIT).json()
    response = client.patch(
        f"/api/v1/repositories/{created['id']}",
        json={"name": "renamed", "default_branch": "main"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"
    assert response.json()["default_branch"] == "main"


def test_update_rejects_protected_fields(client: TestClient) -> None:
    use_owner("owner-A")
    created = client.post("/api/v1/repositories", json=GIT).json()
    for field in ("status", "owner_id", "current_commit_sha", "error_message"):
        response = client.patch(
            f"/api/v1/repositories/{created['id']}", json={field: "indexed"}
        )
        assert response.status_code == 422, field


def test_update_other_owner_repository_is_404(client: TestClient) -> None:
    use_owner("owner-A")
    created = client.post("/api/v1/repositories", json=GIT).json()
    use_owner("owner-B")
    response = client.patch(
        f"/api/v1/repositories/{created['id']}", json={"name": "hijack"}
    )
    assert response.status_code == 404


def test_delete_repository(client: TestClient) -> None:
    use_owner("owner-A")
    created = client.post("/api/v1/repositories", json=LOCAL).json()
    assert client.delete(f"/api/v1/repositories/{created['id']}").status_code == 204
    assert client.get(f"/api/v1/repositories/{created['id']}").status_code == 404


def test_delete_missing_repository_is_404(client: TestClient) -> None:
    use_owner("owner-A")
    response = client.delete(
        "/api/v1/repositories/123e4567-e89b-12d3-a456-426614174000"
    )
    assert response.status_code == 404


def test_duplicate_name_rejected(client: TestClient) -> None:
    use_owner("owner-A")
    assert client.post("/api/v1/repositories", json=LOCAL).status_code == 201
    response = client.post("/api/v1/repositories", json=LOCAL)
    assert response.status_code == 400
    assert "already exists" in response.json()["error"]["message"]


def test_create_rejects_unsafe_source_urls(client: TestClient) -> None:
    use_owner("owner-A")
    for bad_url in (
        "file:///etc/passwd",
        "ftp://example.com/repo.git",
        "javascript:alert(1)",
        "https://user:secret@example.com/org/repo.git",
        "/tmp/local-escape",
        "not-a-url",
    ):
        response = client.post(
            "/api/v1/repositories",
            json={"name": "x", "source_type": "git", "source_url": bad_url},
        )
        assert response.status_code == 422, bad_url


def test_create_accepts_git_and_scp_urls(client: TestClient) -> None:
    use_owner("owner-A")
    for index, good_url in enumerate(
        (
            "https://example.com/org/repo.git",
            "http://example.com/org/repo.git",
            "ssh://git@example.com/org/repo.git",
            "git@github.com:org/repo.git",
        )
    ):
        response = client.post(
            "/api/v1/repositories",
            json={
                "name": f"r-{index}",
                "source_type": "git",
                "source_url": good_url,
            },
        )
        assert response.status_code == 201, good_url


def test_update_rejects_unsafe_source_url(client: TestClient) -> None:
    use_owner("owner-A")
    created = client.post("/api/v1/repositories", json=GIT).json()
    response = client.patch(
        f"/api/v1/repositories/{created['id']}",
        json={"source_url": "file:///etc/passwd"},
    )
    assert response.status_code == 422


def test_production_refuses_dev_owner(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gap #5: DEV_OWNER_ID must never silently serve production traffic."""
    from app.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "production")
    response = client.get("/api/v1/repositories")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"
