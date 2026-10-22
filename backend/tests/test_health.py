def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_capabilities_exposes_configuration_without_credentials(client, monkeypatch):
    monkeypatch.setenv("CODEATLAS_GENERATION_URL", "https://model.example/v1")
    monkeypatch.setenv("CODEATLAS_GENERATION_MODEL", "model-name")
    monkeypatch.setenv("CODEATLAS_GENERATION_KEY", "never-return-this-key")
    response = client.get("/capabilities")
    assert response.status_code == 200
    assert response.json()["generation_configured"] is True
    assert response.json()["schema"] == "005_pull_requests"
    assert "never-return-this-key" not in response.text and "model.example" not in response.text
