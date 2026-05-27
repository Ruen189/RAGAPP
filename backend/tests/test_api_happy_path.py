from fastapi.testclient import TestClient

from app.main import app


def test_health_like_flow():
    # Minimal integration smoke test for route registration.
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_available():
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "paths" in response.json()
