# tests/test_main.py
from copy import deepcopy
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers import ai, day90
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


async def test_live_integration_summary_excludes_csv_fallback(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "super-secret-value")
    monkeypatch.setenv("SUPERVITY_WORKFLOW_EXECUTE_URL", "https://workflow.example/execute")
    monkeypatch.setenv("SUPERVITY_API_KEY", "workflow-secret-value")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-secret-value")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "asana-secret-value")
    monkeypatch.setenv("ASANA_PROJECT_GID", "P123")

    registry = day90_integrations.integration_registry({"available": True, "path": "csv", "as_of_date": "today"})
    summary = day90_integrations.live_integration_summary(registry)
    csv_fallback = next(item for item in registry if item["name"] == "Round 2 CSV Mount")

    assert summary["ready_live_integrations"] == 4
    assert summary["total_live_integrations"] == 4
    assert summary["ready_fallbacks"] == 1
    assert csv_fallback["counts_as_live"] is False
    assert csv_fallback["name"] not in summary["live_names"]
    assert summary["meets_round2_minimum"] is True


def _fake_day90_ai_context():
    return {
        "available": True,
        "metrics": {
            "workers": 150,
            "workbench_cases": 12,
            "provisioning_events": 751,
            "policy_evaluations": 119,
            "confidential_cases": 4,
        },
        "routes": [
            {"route": "GREEN", "count": 66, "description": "Safe cohort progress"},
            {"route": "AMBER", "count": 13, "description": "Manager nudge"},
            {"route": "RED", "count": 66, "description": "Human approval"},
            {"route": "CONFIDENTIAL", "count": 4, "description": "Restricted review"},
            {"route": "DATA_QUALITY", "count": 1, "description": "Fix source data"},
        ],
        "outcomes": {
            "workers_in_scope": 150,
            "risky_cases_routed": 84,
            "policy_gate_coverage_pct": 100,
            "workbench_cases_visible": 12,
            "public_text_leakage": 0,
            "retention_lift_claimed": False,
        },
        "integrations_ready": 5,
        "integrations_total": 5,
        "source": {"kind": "supabase", "as_of_date": "2026-08-03"},
        "workbench_cases": [
            {"employee_id": "EMP7005", "route": "CONFIDENTIAL", "status": "restricted_review"},
            {"employee_id": "EMP7041", "route": "RED", "status": "pending_review"},
        ],
        "routing_preview": [],
        "policies": [
            {
                "name": "Amber Manager Nudge",
                "route": "AMBER",
                "threshold": "35 <= risk_score < 85 AND confidential_flag = false",
            }
        ],
        "audit_head": [],
    }


async def test_ai_manager_answers_from_live_day90_context(monkeypatch):
    monkeypatch.setattr(ai, "_safe_day90_context", _fake_day90_ai_context)

    result = ai.chat(ai.ChatRequest(message="What should I show judges?", context={"page": "/"}))

    assert "5/5" in result["response"]
    assert "GREEN 66" in result["response"]
    assert "EMP7005" in result["response"]
    assert result["tool_calls"][0]["name"] == "prepare_demo_path"
    assert result["tool_calls"][0]["result"]["workers"] == 150


async def test_ai_manager_explains_policy_impact_with_counts(monkeypatch):
    monkeypatch.setattr(ai, "_safe_day90_context", _fake_day90_ai_context)

    result = ai.chat(ai.ChatRequest(message="Do policy edits change routing?", context={"page": "/ai/policies"}))

    assert "policy controls are connected" in result["response"]
    assert "AMBER 13" in result["response"]
    assert "Amber Manager Nudge" in result["response"]
    assert result["tool_calls"][0]["name"] == "explain_policy_impact"


async def test_ai_manager_reports_measured_outcomes_without_attrition_lift(monkeypatch):
    monkeypatch.setattr(ai, "_safe_day90_context", _fake_day90_ai_context)

    result = ai.chat(ai.ChatRequest(message="What outcome impact is measured?", context={"page": "/"}))

    assert "leading operational controls" in result["response"]
    assert "84" in result["response"]
    assert "does **not** claim proven retention lift" in result["response"]
    assert result["tool_calls"][0]["name"] == "summarize_outcome_measurement"
    assert result["tool_calls"][0]["result"]["outcomes"]["retention_lift_claimed"] is False


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
    monkeypatch.setenv("SUPERVITY_WORKFLOW_EXECUTE_URL", "https://workflow.example/execute")
    monkeypatch.setenv("SUPERVITY_API_KEY", "test-supervity-token")
    monkeypatch.delenv("DAY90_SUPERVITY_TRIGGER_ENABLED", raising=False)
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
    monkeypatch.setattr(
        day90_integrations.httpx,
        "post",
        lambda *_args, **_kwargs: pytest.fail("Supervity execution should require an explicit enable flag"),
    )

    audit_before = deepcopy(day90.AUDIT_TRAIL)
    try:
        result = day90.trigger_run()

        assert result["ready_for_live_demo"] is True
        assert result["external_actions"] == []
        assert result["orchestrator"]["status"] == "configured_not_executed"
        assert result["orchestrator"]["executed"] is False
        assert "approve" in result["message"].lower()
    finally:
        day90.AUDIT_TRAIL[:] = audit_before


async def test_policy_route_edit_changes_next_routing_preview(monkeypatch):
    """Editable policy routes must change the next route evaluation, not just the card text."""
    profile = {
        "source": {"available": True},
        "counts": {"workers": 3},
        "candidate_cases": [
            {
                "employee_id": "EMP9001",
                "route": "RED",
                "score": 90,
                "signals": {"pay_errors": 0, "comp_overdue": 0, "confidential": 0, "missing_manager": 0},
            },
            {
                "employee_id": "EMP9002",
                "route": "AMBER",
                "score": 60,
                "signals": {"pay_errors": 0, "comp_overdue": 0, "confidential": 0, "missing_manager": 0},
            },
            {
                "employee_id": "EMP9003",
                "route": "DATA_QUALITY",
                "score": 40,
                "signals": {"pay_errors": 0, "comp_overdue": 0, "confidential": 0, "missing_manager": 1},
            },
        ],
    }
    policies_before = deepcopy(day90.POLICIES)
    audit_before = deepcopy(day90.AUDIT_TRAIL)
    monkeypatch.setattr(day90, "compute_day90_profile", lambda: deepcopy(profile))
    try:
        before_counts = {row["route"]: row["count"] for row in day90._route_counts(day90._profile())}
        assert before_counts["RED"] == 1
        assert before_counts["AMBER"] == 1
        assert before_counts["DATA_QUALITY"] == 1

        result = day90.update_policy(
            "policy-amber-manager-nudge",
            day90.PolicyUpdateRequest(route="RED"),
        )
        after_counts = {row["route"]: row["count"] for row in result["routing_preview"]}
        workbench = day90.get_workbench()["cases"]

        assert after_counts["RED"] == 2
        assert after_counts["AMBER"] == 0
        assert any(case["employee_id"] == "EMP9002" and case["route"] == "RED" for case in workbench)
    finally:
        day90.POLICIES[:] = policies_before
        day90.AUDIT_TRAIL[:] = audit_before


async def test_confidential_policy_route_is_locked():
    """Confidential signals must remain fail-closed even when policy controls are editable."""
    policies_before = deepcopy(day90.POLICIES)
    try:
        with pytest.raises(Exception) as exc_info:
            day90.update_policy(
                "policy-confidential-isolation",
                day90.PolicyUpdateRequest(route="AMBER"),
            )
        assert getattr(exc_info.value, "status_code", None) == 400
    finally:
        day90.POLICIES[:] = policies_before


async def test_outcome_metrics_are_measured_without_retention_lift_claim():
    profile = {
        "counts": {"workers": 10},
        "route_counts": {"GREEN": 6, "AMBER": 2, "RED": 1, "CONFIDENTIAL": 1, "DATA_QUALITY": 0},
        "provisioning": {"blocked": 3},
        "compliance": {"missing": 1, "overdue": 2},
        "payroll": {"errors": 1},
        "engagement": {"low_nonconf": 2, "confidential": 1},
    }

    outcomes = day90._outcome_metrics(profile, [{"id": "case-1"}, {"id": "case-2"}])

    assert outcomes["retention_lift_claimed"] is False
    assert outcomes["risky_cases_routed"] == 4
    assert outcomes["policy_gate_coverage_pct"] == 100
    assert outcomes["workbench_cases_visible"] == 2
    assert outcomes["public_text_leakage"] == 0
    assert outcomes["cards"][0]["value"] == "4"


async def test_manual_trigger_can_call_supervity_with_approval_gated_payload(monkeypatch):
    """When explicitly enabled, the backend calls Auto without bypassing Workbench approval."""
    monkeypatch.setenv("SUPERVITY_WORKFLOW_EXECUTE_URL", "https://workflow.example/execute")
    monkeypatch.setenv("SUPERVITY_API_KEY", "test-supervity-token")
    monkeypatch.setenv("DAY90_SUPERVITY_TRIGGER_ENABLED", "true")
    monkeypatch.setattr(
        day90,
        "_profile",
        lambda: {
            "source": {"available": True},
            "route_counts": {"GREEN": 1, "AMBER": 1, "RED": 0, "CONFIDENTIAL": 0, "DATA_QUALITY": 0},
        },
    )
    monkeypatch.setattr(
        day90,
        "_workbench_cases_from_profile",
        lambda _profile: [
            {
                "id": "case-1",
                "case_key": "R2|EMP7001|DAY90|hr-default|1",
                "route": "AMBER",
                "risk_band": "Amber",
                "status": "pending_review",
                "employee_id": "EMP7001",
            }
        ],
    )
    monkeypatch.setattr(day90, "all_required_live_integrations_ready", lambda _source: True)
    monkeypatch.setattr(
        day90,
        "create_masked_reviewer_actions",
        lambda *_args, **_kwargs: pytest.fail("external action bypassed Workbench approval"),
    )

    requests = []

    class FakeResponse:
        status_code = 202
        content = b'{"run_id":"RUN-123","status":"queued"}'

        def json(self):
            return {"run_id": "RUN-123", "status": "queued"}

    def fake_post(url, **kwargs):
        requests.append({"url": url, **kwargs})
        return FakeResponse()

    monkeypatch.setattr(day90_integrations.httpx, "post", fake_post)

    audit_before = deepcopy(day90.AUDIT_TRAIL)
    try:
        result = day90.trigger_run()

        assert result["external_actions"] == []
        assert result["orchestrator"]["ok"] is True
        assert result["orchestrator"]["executed"] is True
        assert result["orchestrator"]["run_id"] == "RUN-123"
        assert len(requests) == 1
        assert requests[0]["headers"]["Authorization"].startswith("Bearer ")
        assert requests[0]["json"]["external_actions_allowed"] is False
        assert requests[0]["json"]["workbench_approval_required"] is True
        assert requests[0]["json"]["cases"][0]["employee_id"] == "EMP7001"
    finally:
        day90.AUDIT_TRAIL[:] = audit_before
