from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.routers import day90 as day90_router

router = APIRouter(prefix="/ai", tags=["AI Manager"])


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)
    context: dict = Field(default_factory=dict)


def _safe_day90_context() -> dict:
    try:
        dashboard = day90_router.dashboard_payload()
        workbench = day90_router.get_workbench()
        policies = day90_router.get_policies()
    except Exception as exc:  # pragma: no cover - protects chat from data-source outages
        return {"available": False, "error": str(exc)[:180]}

    cases = workbench.get("cases", [])
    metrics = dashboard.get("metrics", {})
    routes = dashboard.get("routes", [])
    outcomes = dashboard.get("outcomes", {})
    integrations = dashboard.get("integrations", [])
    integration_summary = dashboard.get("integration_summary", {})
    return {
        "available": True,
        "metrics": metrics,
        "routes": routes,
        "outcomes": outcomes,
        "integrations_ready": integration_summary.get(
            "ready_live_integrations",
            sum(1 for item in integrations if item.get("status") == "ready"),
        ),
        "integrations_total": integration_summary.get("total_live_integrations", len(integrations)),
        "fallbacks_ready": integration_summary.get("ready_fallbacks", 0),
        "fallbacks_total": integration_summary.get("total_fallbacks", 0),
        "source": dashboard.get("source", {}),
        "workbench_cases": cases,
        "routing_preview": policies.get("routing_preview", []),
        "policies": policies.get("policies", []),
        "audit_head": dashboard.get("audit", [])[:3],
    }


def _route_counts(context: dict) -> dict:
    return {item["route"]: item["count"] for item in context.get("routes", [])}


def _format_route_counts(context: dict) -> str:
    counts = _route_counts(context)
    return ", ".join(
        f"{route} {counts.get(route, 0)}"
        for route in ["GREEN", "AMBER", "RED", "CONFIDENTIAL", "DATA_QUALITY"]
    )


def _sample_cases(context: dict, limit: int = 4) -> str:
    cases = context.get("workbench_cases", [])[:limit]
    if not cases:
        return "No Workbench cases are currently queued."
    return "; ".join(
        f"{case.get('employee_id')} -> {case.get('route')} ({case.get('status')})"
        for case in cases
    )


def _policy_summary(context: dict) -> str:
    policies = context.get("policies", [])
    if not policies:
        return "No Day90 policies were returned."
    return "; ".join(
        f"{policy.get('name')}: {policy.get('route')} when `{policy.get('threshold')}`"
        for policy in policies[:4]
    )


def _tool_result(context: dict) -> dict:
    if not context.get("available"):
        return {"status": "unavailable", "detail": context.get("error")}
    metrics = context.get("metrics", {})
    return {
        "status": "ready",
        "workers": metrics.get("workers"),
        "workbench_cases": metrics.get("workbench_cases"),
        "route_counts": _route_counts(context),
        "outcomes": context.get("outcomes", {}),
        "integrations": f"{context.get('integrations_ready')}/{context.get('integrations_total')}",
        "fallbacks": f"{context.get('fallbacks_ready')}/{context.get('fallbacks_total')}",
        "source": context.get("source", {}).get("kind"),
    }


def _contextual_response(message: str, page: str, context: dict) -> tuple[str, str]:
    if not context.get("available"):
        return (
            "I could not load the live Day90 context for this answer, so I would not rely on AI Manager proof until the data endpoint is healthy.",
            "read_day90_context",
        )

    metrics = context["metrics"]
    source = context.get("source", {})
    route_line = _format_route_counts(context)
    sample_cases = _sample_cases(context)
    outcomes = context.get("outcomes", {})
    lower = message.lower()

    if any(word in lower for word in ["confidential", "privacy", "leak", "mask"]):
        return (
            "Confidential routing is active and fail-closed.\n\n"
            f"- Current confidential cases: **{metrics.get('confidential_cases', 0)}**\n"
            f"- Workbench proof: {sample_cases}\n"
            "- Raw confidential pulse text is not loaded into the dashboard, Slack text, or public Asana descriptions.\n"
            "- The confidential policy route is locked to `CONFIDENTIAL`, so a policy edit cannot accidentally turn it into an Amber/public action.",
            "explain_confidential_gate",
        )

    if any(word in lower for word in ["policy", "threshold", "route", "routing", "gate"]):
        return (
            "The policy controls are connected to the next Day90 route evaluation.\n\n"
            f"- Current routing preview: **{route_line}**\n"
            f"- Active gates: {_policy_summary(context)}\n"
            "- If a reviewer changes a non-confidential policy route or threshold, the routing preview and next Workbench queue update from the same evaluation path.\n"
            "- Confidential disclosure isolation remains locked fail-closed for privacy.",
            "explain_policy_impact",
        )

    if any(word in lower for word in ["outcome", "impact", "measure", "measured", "retention", "attrition", "roi"]):
        return (
            "The outcome proof is measured as leading operational controls, not as a claimed attrition lift.\n\n"
            f"- Workers in scope: **{outcomes.get('workers_in_scope', metrics.get('workers'))}**\n"
            f"- Risk cases routed through policy gates: **{outcomes.get('risky_cases_routed', 0)}**\n"
            f"- Governance coverage for routed review cases: **{outcomes.get('policy_gate_coverage_pct', 0)}%**\n"
            f"- Confidential public-text leakage: **{outcomes.get('public_text_leakage', 0)}**\n"
            f"- Workbench cases visible for human review: **{outcomes.get('workbench_cases_visible', metrics.get('workbench_cases', 0))}**\n\n"
            "The operational claim is: Day90 Guardian detects and governs early risk in the current batch; it does **not** claim proven retention lift from this dataset.",
            "summarize_outcome_measurement",
        )

    if any(word in lower for word in ["workbench", "case", "approve", "review", "human"]):
        return (
            "The human gate is populated from the live Day90 profile, not a static slide.\n\n"
            f"- Workbench cases queued: **{metrics.get('workbench_cases', 0)}**\n"
            f"- Route mix: **{route_line}**\n"
            f"- Sample queue: {sample_cases}\n"
            "- Approval is the only path that can create route-safe Slack/Asana artifacts; trigger alone keeps `external_actions` empty.",
            "summarize_workbench_queue",
        )

    if any(word in lower for word in ["integration", "asana", "slack", "supervity", "supabase", "source", "data"]):
        return (
            "The connected-system layer is live and source-aware.\n\n"
            f"- Source: **{source.get('kind')}** / {source.get('as_of_date')}\n"
            f"- Primary operational integrations ready: **{context.get('integrations_ready')}/{context.get('integrations_total')}**\n"
            f"- Resilience fallback ready: **{context.get('fallbacks_ready')}/{context.get('fallbacks_total')}**\n"
            f"- Workers: **{metrics.get('workers')}**, provisioning events: **{metrics.get('provisioning_events')}**, policy evaluations: **{metrics.get('policy_evaluations')}**\n"
            "- Slack/Asana are still approval-gated; Supervity auto execution reports proof status without bypassing Workbench.",
            "summarize_connected_systems",
        )

    if any(word in lower for word in ["trigger", "run", "demo", "proof", "workflow", "operating"]):
        return (
            "The strongest live operating path is already visible from this Command Center.\n\n"
            f"1. Show the source of record and **{context.get('integrations_ready')}/{context.get('integrations_total')}** primary integrations ready.\n"
            f"2. Show route counts: **{route_line}**.\n"
            f"3. Open Workbench and show queued cases: {sample_cases}.\n"
            "4. Run Guardian Review to create an audit event while keeping external actions gated.\n"
            "5. Approve only a safe Amber/Red case when you intentionally want Slack/Asana proof.",
            "prepare_demo_path",
        )

    return (
        f"On `{page}`, I’m reading the live Day90 context.\n\n"
        f"- Source: **{source.get('kind')}**\n"
        f"- Primary integrations: **{context.get('integrations_ready')}/{context.get('integrations_total')} ready**\n"
        f"- Route counts: **{route_line}**\n"
        f"- Workbench queue: **{metrics.get('workbench_cases', 0)} cases**\n\n"
        "Ask me about policies, confidential routing, Workbench approvals, integrations, or the live operating path and I’ll answer from these current signals.",
        "summarize_day90_context",
    )


@router.post("/chat")
def chat(request: ChatRequest):
    page = request.context.get("page", "the current page")
    context = _safe_day90_context()
    response, tool_name = _contextual_response(request.message, page, context)

    return {
        "response": response,
        "tool_calls": [
            {
                "id": "day90-manager-001",
                "name": tool_name,
                "args": {"page": page},
                "result": _tool_result(context),
            }
        ],
    }
