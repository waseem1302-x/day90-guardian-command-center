# tests/test_main.py
from copy import deepcopy
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers import day90
from app.services import day90_integrations

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio


async def test_health_check():
    """
    Tests the public health check endpoint.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_check():
    """Tests the public readiness endpoint used by deployment checks."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def _fake_response(payload, status_code=200):
    class FakeResponse:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return payload

    return FakeResponse()


async def test_integration_registry_never_returns_secret_fragments(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "super-secret-value")
    monkeypatch.setenv("SUPERVITY_WORKFLOW_EXECUTE_URL", "https://workflow.example/execute")
    monkeypatch.setenv("SUPERVITY_API_KEY", "workflow-secret-value")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-secret-value")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "asana-secret-value")
    monkeypatch.setenv("ASANA_PROJECT_GID", "P123")

    registry = day90_integrations.integration_registry({"available": True, "path": "csv", "as_of_date": "today"})
    secrets = {
        key: value
        for item in registry
        for key, value in item["safe_config"].items()
        if "KEY" in key or "TOKEN" in key
    }
    assert all(value == "configured" for value in secrets.values())
    assert not any("secret" in value for value in secrets.values())


async def test_route_aware_reviewer_actions(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-secret")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "asana-secret")
    monkeypatch.setenv("ASANA_PROJECT_GID", "P123")

    requests = []

    def fake_post(url, **kwargs):
        requests.append({"url": url, **kwargs})
        if "slack.com" in url:
            return _fake_response({"ok": True})
        return _fake_response({"data": {"gid": "T123", "permalink_url": "https://asana.test/T123"}}, 201)

    monkeypatch.setattr(day90_integrations.httpx, "post", fake_post)
    base = {
        "case_key": "R2|EMP7001|DAY90|hr-default|1",
        "employee_id": "EMP7001",
        "reason": "Synthetic test reason",
        "recommended_action": "Review safely",
    }

    amber = day90_integrations.create_masked_reviewer_actions({**base, "route": "AMBER"}, "TEST-AMBER")
    red = day90_integrations.create_masked_reviewer_actions({**base, "route": "RED"}, "TEST-RED")
    confidential = day90_integrations.create_masked_reviewer_actions({**base, "route": "CONFIDENTIAL"}, "TEST-CONF")
    data_quality = day90_integrations.create_masked_reviewer_actions({**base, "route": "DATA_QUALITY"}, "TEST-DQ")

    assert {action["system"] for action in amber} == {"slack", "asana"}
    assert {action["system"] for action in red} == {"asana"}
    assert confidential == [{"system": "privacy_gate", "ok": True, "detail": "Confidential case blocked from public Slack/Asana notification."}]
    assert data_quality[0]["system"] == "data_quality_gate"

    slack_request = next(request for request in requests if "slack.com" in request["url"])
    asana_requests = [request for request in requests if "asana.com" in request["url"]]
    amber_task = asana_requests[0]["json"]["data"]
    red_task = asana_requests[1]["json"]["data"]

    assert "Employee: EMP7001" in slack_request["json"]["text"]
    assert "No confidential text" in slack_request["json"]["text"]
    assert amber_task["assignee"] == "me"
    assert amber_task["due_on"]
    assert "Route: AMBER" in amber_task["notes"]
    assert red_task["assignee"] == "me"
    assert red_task["due_on"]


async def test_approved_decision_is_idempotent(monkeypatch):
    case = {
        "id": "case-test-amber",
        "case_key": "R2|EMP7001|DAY90|hr-default|1",
        "employee_id": "EMP7001",
        "route": "AMBER",
        "status": "pending_review",
    }
    calls = []
    monkeypatch.setattr(day90, "_profile", lambda: {})
    monkeypatch.setattr(day90, "_workbench_cases_from_profile", lambda _profile: [dict(case)])
    monkeypatch.setattr(
        day90,
        "create_masked_reviewer_actions",
        lambda _case, _tag: calls.append(True) or [{"system": "asana", "ok": True, "detail": "created"}],
    )
    day90.CASE_DECISIONS.clear()
    day90.CASE_ACTIONS.clear()

    audit_before = deepcopy(day90.AUDIT_TRAIL)
    try:
        first = day90.record_decision("case-test-amber", day90.DecisionRequest(decision="approve", note="Approved"))
        second = day90.record_decision("case-test-amber", day90.DecisionRequest(decision="approve", note="Approved again"))

        assert len(calls) == 1
        assert first["actions"] == second["actions"]
        assert sum(event["event"] == "Approved action: asana" for event in day90.AUDIT_TRAIL) == 1
    finally:
        day90.AUDIT_TRAIL[:] = audit_before
        day90.CASE_DECISIONS.clear()
        day90.CASE_ACTIONS.clear()


async def test_manual_trigger_stages_actions_behind_workbench(monkeypatch):
    """A scan may be live-ready, but it must not notify until approval."""
    monkeypatch.setattr(day90, "_profile", lambda: {"source": {"available": True}})
    monkeypatch.setattr(
        day90,
        "_workbench_cases_from_profile",
        lambda _profile: [{"id": "case-1", "route": "AMBER", "employee_id": "EMP7001"}],
    )
    monkeypatch.setattr(day90, "all_required_live_integrations_ready", lambda _source: True)
    monkeypatch.setattr(
        day90,
        "create_masked_reviewer_actions",
        lambda *_args, **_kwargs: pytest.fail("external action bypassed Workbench approval"),
    )

    audit_before = deepcopy(day90.AUDIT_TRAIL)
    try:
        result = day90.trigger_run()

        assert result["ready_for_live_demo"] is True
        assert result["external_actions"] == []
        assert "approve" in result["message"].lower()
    finally:
        day90.AUDIT_TRAIL[:] = audit_before
