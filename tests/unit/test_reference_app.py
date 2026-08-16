"""Validate the deterministic reference application contract."""

from fastapi.testclient import TestClient

from vaipex_visual_accessibility.app import app

client = TestClient(app)


def test_readiness_contract() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_default_dashboard_is_byte_for_byte_deterministic() -> None:
    first_response = client.get("/")
    second_response = client.get("/")

    assert first_response.status_code == 200
    assert first_response.content == second_response.content
    assert 'data-render-contract="vaipex-v1"' in first_response.text
    assert 'data-state="ready"' in first_response.text


def test_supported_states_have_explicit_render_identity() -> None:
    for state in ("ready", "empty", "degraded"):
        response = client.get("/", params={"state": state})

        assert response.status_code == 200
        assert f'data-state="{state}"' in response.text


def test_unknown_state_is_rejected() -> None:
    response = client.get("/", params={"state": "random"})

    assert response.status_code == 422


def test_page_uses_local_assets_and_semantic_landmarks() -> None:
    response = client.get("/")

    assert "https://" not in response.text
    assert 'href="http://testserver/static/styles.css"' in response.text
    assert 'src="http://testserver/static/app.js"' in response.text
    assert '<nav aria-label="Primary navigation">' in response.text
    assert '<main id="main-content"' in response.text
    assert "<caption>" in response.text


def test_dialog_state_is_addressable() -> None:
    response = client.get("/", params={"dialog": "true"})

    assert response.status_code == 200
    assert '<dialog id="policy-dialog" data-auto-open="true"' in response.text
