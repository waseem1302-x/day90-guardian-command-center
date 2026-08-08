from __future__ import annotations

import re

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
        insights = day90_router.get_insights()
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
        "insights": insights.get("insights", []),
        "patterns": insights.get("patterns", []),
        "actions": insights.get("actions", []),
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


def _cases_for_route(context: dict, route: str, limit: int = 5) -> list[dict]:
    return [
        case
        for case in context.get("workbench_cases", [])
        if str(case.get("route", "")).upper() == route
    ][:limit]


def _format_cases(cases: list[dict]) -> str:
    if not cases:
        return "No matching Workbench cases are currently queued."
    return "; ".join(
        " / ".join(
            str(value)
            for value in [
                case.get("employee_id"),
                case.get("route"),
                case.get("status"),
                case.get("recommended_action"),
            ]
            if value
        )
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


def _audit_summary(context: dict) -> str:
    events = context.get("audit_head", [])
    if not events:
        return "No recent audit events were returned."
    return "; ".join(
        f"{event.get('event')} by {event.get('actor')}: {event.get('detail')}"
        for event in events[:4]
    )


def _insight_summary(context: dict) -> str:
    insights = context.get("insights", [])
    if not insights:
        return "No computed insights were returned."
    return "; ".join(
        f"{insight.get('severity', 'info')}: {insight.get('title')} -> {insight.get('suggested_action')}"
        for insight in insights[:3]
    )


def _confidence_percent(value: object) -> int:
    try:
        return round(float(value or 0) * 100)
    except (TypeError, ValueError):
        return 0


def _capability_menu(page: str, context: dict) -> str:
    return (
        "I am a guided Day90 command-center assistant, not a general free-text LLM. "
        "Use one of these supported commands and I will answer from the current Day90 data.\n\n"
        "- `Run Guardian Review`: start the approval-gated Supervity Guardian run.\n"
        "- `Show readiness proof`: explain the live operating proof path.\n"
        "- `Summarize Workbench`: show queue counts, route mix, and sample cases.\n"
        "- `Show Red cases`, `Show Amber cases`, `Show Confidential cases`, or `Show Data Quality cases`: filter Workbench by route.\n"
        "- `Explain policy gates`: summarize active policy thresholds and routing impact.\n"
        "- `Check integrations`: summarize Supabase, Supervity, Slack, Asana, and fallback readiness.\n"
        "- `Summarize outcomes`: explain measured operational outcomes without claiming attrition lift.\n"
        "- `Show AI insights`: summarize computed insights, patterns, and recommended actions.\n"
        "- `Check privacy controls`: explain confidential routing, masking, and public-action blocking.\n"
        "- `Show recent activity`: summarize audit events and receipts.\n"
        "- `Explain this page`: summarize what I can read for the current page.\n\n"
        f"Current page: `{page}`. Current snapshot: **{context.get('integrations_ready')}/{context.get('integrations_total')}** primary integrations ready, "
        f"**{context.get('metrics', {}).get('workbench_cases', 0)}** Workbench cases, route mix **{_format_route_counts(context)}**."
    )


def _recent_history_text(history: list[dict], limit: int = 4) -> str:
    messages = []
    for item in history[-limit:]:
        content = str(item.get("content", "")).strip()
        if content:
            messages.append(content)
    return " ".join(messages)


def _is_followup(message: str) -> bool:
    lower = message.lower().strip()
    followup_starters = ("what about", "show me those", "show those", "them", "those", "these", "and", "also")
    return lower.startswith(followup_starters)


def _history_mentions_route_context(history: list[dict]) -> bool:
    lower = _recent_history_text(history).lower()
    return any(word in lower for word in ["workbench", "case", "route", "queue", "human approval"])


def _requested_route(message: str) -> str | None:
    lower = message.lower()
    route_terms = {
        "CONFIDENTIAL": ["confidential", "privacy"],
        "DATA_QUALITY": ["data quality", "data_quality", "source data", "hris"],
        "AMBER": ["amber"],
        "RED": ["red"],
        "GREEN": ["green"],
    }
    for route, terms in route_terms.items():
        if any(re.search(rf"\b{re.escape(term)}\b", lower) for term in terms):
            return route
    return None


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
        "insights": len(context.get("insights", [])),
        "recent_audit_events": len(context.get("audit_head", [])),
    }


def _contextual_response(message: str, page: str, context: dict, history: list[dict] | None = None) -> tuple[str, str]:
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
    lower = message.lower().strip()
    recent_history = history or []
    requested_route = _requested_route(message)
    route_query_words = ["case", "workbench", "route", "queue", "what about", "show", "those", "these"]
    wants_capability_menu = (
        lower in {"help", "commands", "capabilities", "options", "menu"}
        or "what can you help" in lower
        or "explain this page" in lower
    )

    if requested_route and (
        any(word in lower for word in route_query_words)
        or (_is_followup(message) and _history_mentions_route_context(recent_history))
    ):
        cases = _cases_for_route(context, requested_route)
        counts = _route_counts(context)
        return (
            f"Here is the current `{requested_route}` route view from Workbench and route counts.\n\n"
            f"- Route count: **{counts.get(requested_route, 0)}**\n"
            f"- Matching Workbench cases: {_format_cases(cases)}\n"
            "- This is read-only context; AI Manager is not approving or creating external actions from this answer.",
            "summarize_route_cases",
        )

    if wants_capability_menu:
        return (_capability_menu(page, context), "show_supported_commands")

    if any(word in lower for word in ["confidential", "privacy", "leak", "mask"]):
        return (
            "Confidential routing is active and fail-closed.\n\n"
            f"- Current confidential cases: **{metrics.get('confidential_cases', 0)}**\n"
            f"- Workbench proof: {sample_cases}\n"
            "- Raw confidential pulse text is not loaded into the dashboard, Slack text, or public Asana descriptions.\n"
            "- The confidential policy route is locked to `CONFIDENTIAL`, so a policy edit cannot accidentally turn it into an Amber/public action.",
            "explain_confidential_gate",
        )

    if any(word in lower for word in ["policy", "policies", "threshold", "route", "routing", "gate"]):
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

    if any(word in lower for word in ["insight", "signal", "pattern", "recommendation", "recommended action"]):
        patterns = context.get("patterns", [])
        actions = context.get("actions", [])
        pattern_line = "; ".join(
            f"{pattern.get('name')} ({_confidence_percent(pattern.get('confidence'))}%)"
            for pattern in patterns[:3]
        ) or "No patterns returned."
        action_line = "; ".join(
            f"{action.get('priority')}: {action.get('title')}"
            for action in actions[:3]
        ) or "No recommended actions returned."
        return (
            "The AI Insights view is grounded in the current Day90 profile and Workbench-safe actions.\n\n"
            f"- Computed insights: {_insight_summary(context)}\n"
            f"- Detected patterns: {pattern_line}\n"
            f"- Recommended actions: {action_line}\n"
            "- These are analysis summaries only; use Workbench for human approval before any external artifact.",
            "summarize_ai_insights",
        )

    if any(word in lower for word in ["audit", "activity", "recent", "history", "receipt"]):
        return (
            "Recent Day90 activity is available from the audit trail.\n\n"
            f"- Latest events: {_audit_summary(context)}\n"
            "- Guardian run receipts and Workbench decisions are recorded as audit events without exposing secrets.",
            "summarize_recent_activity",
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

    return (_capability_menu(page, context), "show_supported_commands")


@router.post("/chat")
def chat(request: ChatRequest):
    page = request.context.get("page", "the current page")
    context = _safe_day90_context()
    response, tool_name = _contextual_response(request.message, page, context, request.history)

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
