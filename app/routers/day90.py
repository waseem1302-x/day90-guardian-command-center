from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.day90_integrations import (
    all_required_live_integrations_ready,
    create_masked_reviewer_actions,
    execute_supervity_orchestrator,
    integration_registry,
    live_integration_summary,
    seed_supabase_source_records,
)
from app.services.day90_data import DATASET_DIR, compute_day90_profile

router = APIRouter(prefix="/day90", tags=["Day90 Guardian"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


OPERATORS = [
    {
        "name": "HR Data Quality and Lifecycle Operator",
        "role": "Validates worker cohort, lifecycle stage, manager links, location, and data completeness before any risk decision runs.",
        "mode": "sequential gate",
        "status": "ready",
        "last_result": "150 workers checked; 3 manager-reference exceptions isolated.",
    },
    {
        "name": "Onboarding Task and Access Reconciliation Operator",
        "role": "Compares onboarding tasks with provisioning evidence so only trustworthy access/task recoveries move forward.",
        "mode": "parallel fan-out",
        "status": "ready",
        "last_result": "75 blocked provisioning events; badge and system access are the top bottlenecks.",
    },
    {
        "name": "Engagement and Confidentiality Guard Operator",
        "role": "Reads pulse/non-response signals and separates confidential disclosures from normal cohort reporting.",
        "mode": "parallel fan-out",
        "status": "ready",
        "last_result": "38 low non-confidential engagement signals; 4 confidential cases restricted.",
    },
    {
        "name": "Retention Risk and Policy Evaluation Operator",
        "role": "Applies editable Day90 policies to merged evidence and assigns Green, Amber, Red, Confidential, or Data Quality routes.",
        "mode": "fan-in policy gate",
        "status": "ready",
        "last_result": "Policy v1 evaluated; Amber manager-nudge and Red compliance routes active.",
    },
    {
        "name": "Intervention Execution and Outcome Operator",
        "role": "Creates only safe or approved Slack/Asana interventions, verifies evidence, and records outcome state.",
        "mode": "approved action",
        "status": "ready",
        "last_result": "Slack and Asana proof generated for EMP7002 Amber review.",
    },
]


POLICIES = [
    {
        "id": "policy-confidential-isolation",
        "name": "Confidential Disclosure Isolation",
        "description": "Any confidential pulse or sensitive disclosure must leave normal dashboards and route only to the restricted People Ops queue.",
        "is_active": True,
        "threshold": "confidential_flag = true",
        "route": "CONFIDENTIAL",
        "owner": "People Ops restricted reviewer",
        "last_evaluated_at": "2026-08-03T07:02:15+00:00",
        "evaluations": 4,
    },
    {
        "id": "policy-red-compliance",
        "name": "Red Compliance and Payroll Gate",
        "description": "Overdue work authorization, missing compliance, payroll failure, or day-one blocking dependency requires human approval before any external action.",
        "is_active": True,
        "threshold": "compliance_overdue >= 1 OR payroll_error = true OR severity_score >= 85",
        "route": "RED",
        "owner": "HR operations lead",
        "last_evaluated_at": "2026-08-03T07:02:15+00:00",
        "evaluations": 26,
    },
    {
        "id": "policy-amber-manager-nudge",
        "name": "Amber Manager Nudge",
        "description": "Low engagement, overdue manager follow-up, or blocked onboarding without confidential text creates Slack notice and Asana task.",
        "is_active": True,
        "threshold": "35 <= risk_score < 85 AND confidential_flag = false",
        "route": "AMBER",
        "owner": "HR business partner",
        "last_evaluated_at": "2026-08-03T07:02:15+00:00",
        "evaluations": 41,
    },
    {
        "id": "policy-data-quality-stop",
        "name": "Data Quality Stop",
        "description": "Unsafe joins, missing manager ownership, or chronology conflicts are quarantined instead of auto-completing tasks.",
        "is_active": True,
        "threshold": "manager_missing = true OR chronology_invalid = true",
        "route": "DATA_QUALITY",
        "owner": "People data steward",
        "last_evaluated_at": "2026-08-03T07:02:15+00:00",
        "evaluations": 48,
    },
]


DATASET_COVERAGE_TABLES = [
    {
        "key": "workers",
        "table": "Workers",
        "domain": "People and lifecycle",
        "purpose": "Employee cohort, lifecycle, manager, role, and location context.",
    },
    {
        "key": "tasks",
        "table": "Onboarding_Tasks",
        "domain": "Readiness and access",
        "purpose": "Task completion, overdue status, evidence, and Day90 blockers.",
    },
    {
        "key": "provisioning",
        "table": "Provisioning_Integration",
        "domain": "Readiness and access",
        "purpose": "Laptop, badge, VPN, email, and system access status.",
    },
    {
        "key": "engagement",
        "table": "Peakon_Engagement",
        "domain": "Risk and governance",
        "purpose": "Non-confidential engagement signals and confidential disclosure flags.",
    },
    {
        "key": "managers",
        "table": "Manager_Directory",
        "domain": "People and lifecycle",
        "purpose": "Manager ownership and data-quality validation.",
    },
    {
        "key": "locations",
        "table": "Locations_Entities",
        "domain": "People and lifecycle",
        "purpose": "Jurisdiction, country, timezone, and employing-entity context.",
    },
    {
        "key": "compliance",
        "table": "Compliance_Items",
        "domain": "Risk and governance",
        "purpose": "Work authorization and jurisdiction-specific compliance deadlines.",
    },
    {
        "key": "payroll",
        "table": "Payroll_Records",
        "domain": "Risk and governance",
        "purpose": "First payroll readiness, bank validation, tax, and cost-center issues.",
    },
    {
        "key": "learning",
        "table": "Learning_Milestones",
        "domain": "Readiness and access",
        "purpose": "Training and ramp milestone completion.",
    },
    {
        "key": "attrition_history",
        "table": "Attrition_History",
        "domain": "Risk and governance",
        "purpose": "Historical job-family context only; not a proven retention-lift claim.",
    },
    {
        "key": "cross_team_dependencies",
        "table": "Cross_Team_Dependencies",
        "domain": "Readiness and access",
        "purpose": "Security, facilities, IT, payroll, and manager dependency blocks.",
    },
]


INSIGHTS = [
    {
        "id": "insight-provisioning-bottleneck",
        "type": "pattern",
        "severity": "critical",
        "title": "Provisioning blockers are concentrated in access and badge work",
        "description": "75 provisioning events are blocked. Badge, system access, and VPN issues are delaying day-one readiness across multiple cohorts.",
        "data": {"blocked_events": 75, "top_blockers": "Badge, System Access, VPN", "affected_area": "onboarding readiness"},
        "suggested_action": "Open Workbench queue for Red and Amber provisioning cases",
        "action_type": "open_workbench",
        "confidence": 0.94,
        "created_at": "2026-08-03T07:02:15+00:00",
    },
    {
        "id": "insight-confidential-routing",
        "type": "anomaly",
        "severity": "critical",
        "title": "Confidential disclosures are isolated from normal reporting",
        "description": "4 confidential pulse records were detected and routed away from dashboard text, cohort summaries, Slack, and public Asana descriptions.",
        "data": {"confidential_cases": 4, "public_text_leakage": 0, "route": "CONFIDENTIAL"},
        "suggested_action": "Restricted reviewer should approve or modify next action",
        "action_type": "open_workbench",
        "confidence": 0.98,
        "created_at": "2026-08-03T07:02:15+00:00",
    },
    {
        "id": "insight-manager-accountability",
        "type": "recommendation",
        "severity": "warning",
        "title": "Manager follow-up delay is increasing Day90 risk",
        "description": "19 manager follow-ups are older than 5 days, and several overlap with low engagement or incomplete learning milestones.",
        "data": {"manager_followups_over_5d": 19, "low_engagement": 38, "learning_incomplete": 177},
        "suggested_action": "Trigger Amber manager nudge policy for non-confidential cases",
        "action_type": "trigger_policy",
        "confidence": 0.89,
        "created_at": "2026-08-03T07:02:15+00:00",
    },
    {
        "id": "insight-compliance-payroll",
        "type": "anomaly",
        "severity": "warning",
        "title": "Compliance and first payroll need a governed hold",
        "description": "28 compliance records are missing, 22 are overdue, and 4 payroll errors require review before broad intervention.",
        "data": {"missing_compliance": 28, "overdue_compliance": 22, "payroll_errors": 4},
        "suggested_action": "Keep Red cases in Workbench until approved",
        "action_type": "open_workbench",
        "confidence": 0.91,
        "created_at": "2026-08-03T07:02:15+00:00",
    },
]


WORKBENCH_CASES = [
    {
        "id": "case-emp7002-amber",
        "case_key": "76d367ca-8ae6-4a05-8346-bbff700f5f1a|EMP7002|DAY90|hr-default|1",
        "employee_id": "EMP7002",
        "route": "AMBER",
        "risk_band": "Amber",
        "summary": "Manager nudge and HR review required for Day90 onboarding/retention follow-up.",
        "reason": "Non-confidential follow-up: delayed manager response plus onboarding recovery evidence.",
        "recommended_action": "Approve Slack notice and Asana task to HR business partner.",
        "assignee": "HR business partner",
        "status": "pending_review",
        "security": "Synthetic hackathon data only. No confidential text exposed.",
        "evidence": ["Slack message proof exists", "Asana task proof exists", "Policy v1 evaluated"],
        "updated_at": "2026-08-03T07:02:15+00:00",
    },
    {
        "id": "case-emp7062-red",
        "case_key": "R2-BATCH-20260803|EMP7062|DAY90|hr-default|1",
        "employee_id": "EMP7062",
        "route": "RED",
        "risk_band": "Red",
        "summary": "Compliance, payroll, badge, and security dependency overlap requires human approval.",
        "reason": "Payroll bank validation failed and salary was not disbursed; compliance and access evidence also need review.",
        "recommended_action": "Approve restricted HR Ops task; do not send broad Slack message.",
        "assignee": "HR operations lead",
        "status": "pending_review",
        "security": "No raw payroll detail in public dashboard; reviewer receives safe summary only.",
        "evidence": ["Payroll error count included", "Compliance gate triggered", "External action withheld"],
        "updated_at": "2026-08-03T07:02:15+00:00",
    },
    {
        "id": "case-emp7090-confidential",
        "case_key": "R2-BATCH-20260803|EMP7090|DAY90|hr-default|1",
        "employee_id": "EMP7090",
        "route": "CONFIDENTIAL",
        "risk_band": "Confidential",
        "summary": "Confidential disclosure detected and isolated from normal reporting.",
        "reason": "Sensitive pulse content exists; only restricted People Ops reviewer can decide the next step.",
        "recommended_action": "Route to confidential queue; hide raw text and block Slack/Asana public content.",
        "assignee": "Restricted People Ops reviewer",
        "status": "restricted_review",
        "security": "Raw confidential text intentionally not loaded into this UI.",
        "evidence": ["Confidential policy gate fired", "Dashboard masking active", "Public action blocked"],
        "updated_at": "2026-08-03T07:02:15+00:00",
    },
]

CASE_DECISIONS: dict[str, dict] = {}
CASE_ACTIONS: dict[str, list[dict]] = {}

AUDIT_TRAIL = [
    {"time": "2026-08-03T07:01:34+00:00", "event": "Run input accepted", "actor": "Day90 Guardian Orchestrator", "detail": "Batch R2-BATCH-20260803, policy profile hr-default v1"},
    {"time": "2026-08-03T07:01:41+00:00", "event": "Data quality gate", "actor": OPERATORS[0]["name"], "detail": "Manager reference exceptions isolated before route evaluation"},
    {"time": "2026-08-03T07:01:49+00:00", "event": "Parallel fan-out started", "actor": "Day90 Guardian Orchestrator", "detail": "Onboarding/access and engagement/confidentiality operators called in parallel"},
    {"time": "2026-08-03T07:02:03+00:00", "event": "Fan-in merge complete", "actor": "Day90 Guardian Orchestrator", "detail": "Evidence merged with policy version and case keys"},
    {"time": "2026-08-03T07:02:15+00:00", "event": "Human gates created", "actor": OPERATORS[3]["name"], "detail": "Amber, Red, Confidential, and Data Quality routes visible in Workbench"},
]


class DecisionRequest(BaseModel):
    decision: Literal["approve", "modify", "reject"]
    note: str = ""


class PolicyUpdateRequest(BaseModel):
    is_active: bool | None = None
    threshold: str | None = None
    route: str | None = None


ROUTES = {"GREEN", "AMBER", "RED", "CONFIDENTIAL", "DATA_QUALITY"}


def _policy_by_id(policy_id: str) -> dict:
    return next(policy for policy in POLICIES if policy["id"] == policy_id)


def _policy_active(policy_id: str) -> bool:
    return bool(_policy_by_id(policy_id).get("is_active", True))


def _policy_route(policy_id: str, fallback: str) -> str:
    route = str(_policy_by_id(policy_id).get("route") or fallback).upper()
    return route if route in ROUTES else fallback


def _policy_number(policy_id: str, field: str, operator: str, fallback: int) -> int:
    threshold = str(_policy_by_id(policy_id).get("threshold") or "")
    patterns = [
        rf"{re.escape(field)}\s*{re.escape(operator)}\s*(\d+)",
        rf"(\d+)\s*{re.escape(operator)}\s*{re.escape(field)}",
    ]
    for pattern in patterns:
        match = re.search(pattern, threshold)
        if match:
            return int(match.group(1))
    return fallback


def _route_case_with_policies(case: dict) -> str:
    signals = case.get("signals", {})
    score = int(case.get("score") or 0)

    # Privacy fails closed. Confidential text must never become an Amber/Slack
    # style public route because of a no-code policy experiment.
    if signals.get("confidential"):
        return "CONFIDENTIAL"

    if signals.get("missing_manager") and _policy_active("policy-data-quality-stop"):
        return _policy_route("policy-data-quality-stop", "DATA_QUALITY")

    red_floor = _policy_number(
        "policy-red-compliance",
        "severity_score",
        ">=",
        _policy_number("policy-red-compliance", "risk_score", ">=", 85),
    )
    if _policy_active("policy-red-compliance") and (
        signals.get("pay_errors") or signals.get("comp_overdue") or score >= red_floor
    ):
        return _policy_route("policy-red-compliance", "RED")

    amber_floor = _policy_number(
        "policy-amber-manager-nudge",
        "risk_score",
        "<=",
        _policy_number("policy-amber-manager-nudge", "risk_score", ">=", 55),
    )
    amber_ceiling = _policy_number("policy-amber-manager-nudge", "risk_score", "<", red_floor)
    if _policy_active("policy-amber-manager-nudge") and amber_floor <= score < amber_ceiling:
        return _policy_route("policy-amber-manager-nudge", "AMBER")

    return "GREEN"


def _apply_policy_routing(profile: dict) -> dict:
    routed = deepcopy(profile)
    route_counts: Counter[str] = Counter()
    for case in routed.get("candidate_cases", []):
        case["route"] = _route_case_with_policies(case)
        route_counts[case["route"]] += 1

    workers = routed.get("counts", {}).get("workers", 0)
    non_green = sum(count for route, count in route_counts.items() if route != "GREEN")
    routed["route_counts"] = {
        "GREEN": max(workers - non_green, 0),
        "AMBER": route_counts["AMBER"],
        "RED": route_counts["RED"],
        "CONFIDENTIAL": route_counts["CONFIDENTIAL"],
        "DATA_QUALITY": route_counts["DATA_QUALITY"],
    }
    routed["policy_effect"] = {
        "profile": "hr-default",
        "version": 1,
        "editable_routes_applied": True,
        "confidential_route_locked": True,
    }
    return routed


def _profile() -> dict:
    return _apply_policy_routing(compute_day90_profile())


def _route_counts(profile: dict) -> list[dict]:
    counts = profile.get("route_counts") or {
        route: 0 for route in ["GREEN", "AMBER", "RED", "CONFIDENTIAL", "DATA_QUALITY"]
    }
    return [
        {"route": "GREEN", "count": counts["GREEN"], "description": "Safe cohort progress; no action needed"},
        {"route": "AMBER", "count": counts["AMBER"], "description": "Manager nudge or HR review"},
        {"route": "RED", "count": counts["RED"], "description": "Compliance/payroll/access risk requiring approval"},
        {"route": "CONFIDENTIAL", "count": counts["CONFIDENTIAL"], "description": "Restricted People Ops review only"},
        {"route": "DATA_QUALITY", "count": counts["DATA_QUALITY"], "description": "Unsafe joins or chronology conflicts"},
    ]


def _safe_int(mapping: dict | None, key: str) -> int:
    return int((mapping or {}).get(key, 0) or 0)


def _outcome_metrics(profile: dict, cases: list[dict]) -> dict:
    route_counts = profile.get("route_counts") or {}
    workers = _safe_int(profile.get("counts"), "workers")
    routed_review_cases = sum(
        _safe_int(route_counts, route)
        for route in ["AMBER", "RED", "CONFIDENTIAL", "DATA_QUALITY"]
    )
    signal_volume = (
        _safe_int(profile.get("provisioning"), "blocked")
        + _safe_int(profile.get("compliance"), "missing")
        + _safe_int(profile.get("compliance"), "overdue")
        + _safe_int(profile.get("payroll"), "errors")
        + _safe_int(profile.get("engagement"), "low_nonconf")
        + _safe_int(profile.get("engagement"), "confidential")
    )
    approved_action_receipts = sum(len(actions) for actions in CASE_ACTIONS.values())

    return {
        "measurement_mode": "leading_operational_controls",
        "measurement_note": (
            "Measured from the current Day90 batch as risk detection, governed routing, privacy isolation, "
            "and approval-gated execution. This is not a claimed measured attrition lift."
        ),
        "retention_lift_claimed": False,
        "workers_in_scope": workers,
        "risk_signals_detected": signal_volume,
        "risky_cases_routed": routed_review_cases,
        "policy_gate_coverage_pct": 100 if routed_review_cases else 0,
        "workbench_cases_visible": len(cases),
        "approval_gated_receipts": approved_action_receipts,
        "public_text_leakage": 0,
        "confidential_cases_masked": _safe_int(profile.get("engagement"), "confidential"),
        "cards": [
            {
                "label": "Risk cases routed",
                "value": str(routed_review_cases),
                "detail": "Non-green employees assigned to Amber, Red, Confidential, or Data Quality gates.",
            },
            {
                "label": "Governance coverage",
                "value": "100%" if routed_review_cases else "0%",
                "detail": "Every routed review case has an explicit policy route before action.",
            },
            {
                "label": "Confidential leakage",
                "value": "0",
                "detail": "Confidential pulse text remains out of dashboard summaries and public artifacts.",
            },
            {
                "label": "Approval-gated receipts",
                "value": str(approved_action_receipts),
                "detail": "Slack/Asana artifacts are counted only after Workbench approval.",
            },
        ],
    }


def _dataset_coverage(profile: dict) -> dict:
    counts = profile.get("counts") or {}
    tables = [
        {
            **table,
            "rows": _safe_int(counts, table["key"]),
            "loaded": _safe_int(counts, table["key"]) > 0,
        }
        for table in DATASET_COVERAGE_TABLES
    ]
    loaded_tables = sum(1 for table in tables if table["loaded"])
    total_rows = sum(table["rows"] for table in tables)
    domain_summaries = []
    for domain in ["People and lifecycle", "Readiness and access", "Risk and governance"]:
        domain_tables = [table for table in tables if table["domain"] == domain]
        domain_summaries.append(
            {
                "name": domain,
                "tables": [table["table"] for table in domain_tables],
                "rows": sum(table["rows"] for table in domain_tables),
            }
        )

    return {
        "expected_operational_tables": len(DATASET_COVERAGE_TABLES),
        "loaded_operational_tables": loaded_tables,
        "total_operational_rows": total_rows,
        "cohorts_covered": _safe_int(counts, "cohorts"),
        "field_dictionary": {
            "included_in_source_workbook": True,
            "role": "Semantic reference for table fields; not counted as an operational HR table.",
        },
        "domains": domain_summaries,
        "tables": tables,
        "coverage_note": (
            "Round 2 coverage spans workers, onboarding tasks, provisioning/access, engagement, managers, "
            "locations/entities, compliance, payroll, learning, attrition history, and cross-team dependencies."
        ),
    }


def _signals_text(signals: dict) -> str:
    labels = {
        "overdue_tasks": "overdue onboarding tasks",
        "blocked_prov": "blocked provisioning events",
        "comp_overdue": "overdue compliance items",
        "comp_missing": "missing compliance items",
        "pay_errors": "payroll errors",
        "low_engagement": "low engagement signals",
        "confidential": "confidential disclosure flags",
        "manager_slow": "slow manager follow-ups",
        "learning_incomplete": "incomplete learning milestones",
        "day1_blocks": "open day-one dependencies",
        "missing_manager": "missing manager references",
    }
    parts = [f"{value} {labels.get(key, key)}" for key, value in signals.items() if value]
    return ", ".join(parts) or "No major signals"


def _workbench_cases_from_profile(profile: dict) -> list[dict]:
    generated = []
    selected_cases = []
    seen_employee_ids = set()
    for route in ["CONFIDENTIAL", "RED", "AMBER", "DATA_QUALITY"]:
        route_case = next(
            (case for case in profile["candidate_cases"] if case["route"] == route),
            None,
        )
        if route_case:
            selected_cases.append(route_case)
            seen_employee_ids.add(route_case["employee_id"])
    for case in profile["candidate_cases"]:
        if len(selected_cases) >= 12:
            break
        if case["route"] == "GREEN":
            continue
        if case["employee_id"] not in seen_employee_ids:
            selected_cases.append(case)
            seen_employee_ids.add(case["employee_id"])

    for case in selected_cases:
        employee_id = case["employee_id"]
        route = case["route"]
        signals = case["signals"]
        is_confidential = route == "CONFIDENTIAL"
        risk_band = route.title().replace("_", " ")
        reason = _signals_text(signals)
        generated.append(
            {
                "id": f"case-{employee_id.lower()}-{route.lower()}",
                "case_key": f"R2-BATCH-20260803|{employee_id}|DAY90|hr-default|1",
                "employee_id": employee_id,
                "route": route,
                "risk_band": risk_band,
                "summary": f"{risk_band} Day90 review for {employee_id}.",
                "reason": reason,
                "recommended_action": (
                    "Route only to restricted People Ops reviewer; do not expose raw pulse text."
                    if is_confidential
                    else "Review evidence in Workbench, then approve a masked Slack/Asana action only if safe."
                ),
                "assignee": "Restricted People Ops reviewer" if is_confidential else "HR operations lead",
                "status": "restricted_review" if is_confidential else "pending_review",
                "security": (
                    "Raw confidential text intentionally not loaded into this UI."
                    if is_confidential
                    else "Synthetic hackathon data only. No confidential text exposed."
                ),
                "evidence": [
                    f"Risk score {case['score']}",
                    reason,
                    "Policy profile hr-default v1 evaluated",
                ],
                "updated_at": "2026-08-03T07:02:15+00:00",
            }
        )
    cases = generated or deepcopy(WORKBENCH_CASES)
    return [{**case, **CASE_DECISIONS.get(case["id"], {})} for case in cases]


def _insights_from_profile(profile: dict) -> list[dict]:
    blocked_resources = ", ".join(
        item[0] for item in profile["provisioning"]["blocked_by_resource"][:3]
    )
    return [
        {
            "id": "insight-provisioning-bottleneck",
            "type": "pattern",
            "severity": "critical",
            "title": "Provisioning blockers are concentrated in access and badge work",
            "description": f"{profile['provisioning']['blocked']} provisioning events are blocked. {blocked_resources} are the strongest repeated blockers.",
            "data": {
                "blocked_events": profile["provisioning"]["blocked"],
                "top_blockers": blocked_resources,
                "affected_area": "onboarding readiness",
            },
            "suggested_action": "Open Workbench queue for Red and Amber provisioning cases",
            "action_type": "open_workbench",
            "confidence": 0.94,
            "created_at": "2026-08-03T07:02:15+00:00",
        },
        {
            "id": "insight-confidential-routing",
            "type": "anomaly",
            "severity": "critical",
            "title": "Confidential disclosures are isolated from normal reporting",
            "description": f"{profile['engagement']['confidential']} confidential pulse records were detected and routed away from dashboard text, cohort summaries, Slack, and public Asana descriptions.",
            "data": {
                "confidential_cases": profile["engagement"]["confidential"],
                "public_text_leakage": 0,
                "route": "CONFIDENTIAL",
            },
            "suggested_action": "Restricted reviewer should approve or modify next action",
            "action_type": "open_workbench",
            "confidence": 0.98,
            "created_at": "2026-08-03T07:02:15+00:00",
        },
        {
            "id": "insight-manager-accountability",
            "type": "recommendation",
            "severity": "warning",
            "title": "Manager follow-up delay is increasing Day90 risk",
            "description": f"{profile['engagement']['manager_slow_ge_5d']} manager follow-ups are older than 5 days and overlap with low engagement or incomplete learning milestones.",
            "data": {
                "manager_followups_over_5d": profile["engagement"]["manager_slow_ge_5d"],
                "low_engagement": profile["engagement"]["low_nonconf"],
                "learning_incomplete": profile["learning"]["incomplete"],
            },
            "suggested_action": "Trigger Amber manager nudge policy for non-confidential cases",
            "action_type": "trigger_policy",
            "confidence": 0.89,
            "created_at": "2026-08-03T07:02:15+00:00",
        },
        {
            "id": "insight-compliance-payroll",
            "type": "anomaly",
            "severity": "warning",
            "title": "Compliance and first payroll need a governed hold",
            "description": f"{profile['compliance']['missing']} compliance records are missing, {profile['compliance']['overdue']} are overdue, and {profile['payroll']['errors']} payroll errors require review before broad intervention.",
            "data": {
                "missing_compliance": profile["compliance"]["missing"],
                "overdue_compliance": profile["compliance"]["overdue"],
                "payroll_errors": profile["payroll"]["errors"],
            },
            "suggested_action": "Keep Red cases in Workbench until approved",
            "action_type": "open_workbench",
            "confidence": 0.91,
            "created_at": "2026-08-03T07:02:15+00:00",
        },
    ]


def dashboard_payload() -> dict:
    profile = _profile()
    cases = _workbench_cases_from_profile(profile)
    registry = integration_registry(profile["source"])
    return {
        "run": {
            "name": "Day90 Guardian Command Center",
            "batch_id": "R2-BATCH-20260803",
            "policy_profile": "hr-default",
            "policy_version": 1,
            "mode": "approved_test",
            "last_run_at": "2026-08-03T07:02:15+00:00",
        },
        "metrics": {
            "workers": profile["counts"]["workers"],
            "cohorts": profile["counts"]["cohorts"],
            "onboarding_tasks": profile["counts"]["tasks"],
            "provisioning_events": profile["counts"]["provisioning"],
            "blocked_provisioning": profile["provisioning"]["blocked"],
            "missing_compliance": profile["compliance"]["missing"],
            "overdue_compliance": profile["compliance"]["overdue"],
            "payroll_errors": profile["payroll"]["errors"],
            "low_engagement": profile["engagement"]["low_nonconf"],
            "confidential_cases": profile["engagement"]["confidential"],
            "workbench_cases": len(cases),
            "policy_evaluations": sum(policy["evaluations"] for policy in POLICIES),
        },
        "routes": _route_counts(profile),
        "outcomes": _outcome_metrics(profile, cases),
        "operators": OPERATORS,
        "integrations": registry,
        "integration_summary": live_integration_summary(registry),
        "audit": AUDIT_TRAIL,
        "source": profile["source"],
    }


@router.get("/dashboard")
def get_dashboard():
    return dashboard_payload()


@router.get("/data-profile")
def get_data_profile():
    profile = _profile()
    return {**profile, "dataset_coverage": _dataset_coverage(profile)}


@router.get("/outcomes")
def get_outcomes():
    profile = _profile()
    cases = _workbench_cases_from_profile(profile)
    return {"outcomes": _outcome_metrics(profile, cases)}


@router.get("/integrations")
def get_integrations():
    profile = _profile()
    registry = integration_registry(profile["source"])
    return {
        "ready_for_live_demo": all_required_live_integrations_ready(profile["source"]),
        "integrations": registry,
        "integration_summary": live_integration_summary(registry),
        "required_live_integrations": ["Supabase", "Supervity Auto", "Slack", "Asana"],
        "safe_note": "Secrets are never returned; only masked/configured status is exposed.",
    }


@router.post("/supabase/seed")
def seed_supabase():
    result = seed_supabase_source_records(str(DATASET_DIR))
    timestamp = utc_now()
    AUDIT_TRAIL.insert(
        0,
        {
            "time": timestamp,
            "event": "Supabase source seed",
            "actor": "Data Manager",
            "detail": (
                f"Seeded {result.get('inserted', 0)} Round 2 source records into Supabase."
                if result.get("ok")
                else f"Supabase seed failed: {result.get('error')}"
            ),
        },
    )
    return {"result": result, "audit": deepcopy(AUDIT_TRAIL[0])}


@router.get("/policies")
def get_policies():
    return {"policies": deepcopy(POLICIES), "routing_preview": _route_counts(_profile())}


@router.patch("/policies/{policy_id}")
def update_policy(policy_id: str, request: PolicyUpdateRequest):
    for policy in POLICIES:
        if policy["id"] == policy_id:
            if request.is_active is not None:
                policy["is_active"] = request.is_active
            if request.threshold is not None:
                policy["threshold"] = request.threshold
            if request.route is not None:
                route = request.route.upper()
                if route not in ROUTES:
                    raise HTTPException(status_code=400, detail="Unsupported Day90 route")
                if policy_id == "policy-confidential-isolation" and route != "CONFIDENTIAL":
                    raise HTTPException(
                        status_code=400,
                        detail="Confidential disclosure policy is locked to the confidential route.",
                    )
                policy["route"] = route
            policy["last_evaluated_at"] = utc_now()
            policy["evaluations"] += 1
            AUDIT_TRAIL.insert(
                0,
                {
                    "time": policy["last_evaluated_at"],
                    "event": "Policy updated and evaluated",
                    "actor": "Policy Manager",
                    "detail": f"{policy['name']} now routes to {policy['route']} with active={policy['is_active']}",
                },
            )
            return {
                "policy": deepcopy(policy),
                "routing_preview": _route_counts(_profile()),
                "audit": deepcopy(AUDIT_TRAIL[0]),
            }
    raise HTTPException(status_code=404, detail="Policy not found")


@router.get("/insights")
def get_insights():
    profile = _profile()
    return {
        "insights": _insights_from_profile(profile) if profile["source"]["available"] else deepcopy(INSIGHTS),
        "patterns": [
            {"name": "Access bottleneck cluster", "frequency": "daily", "confidence": 0.94, "sample_size": profile["counts"]["provisioning"], "description": "Provisioning delays repeat across badge, VPN, and system access queues."},
            {"name": "Manager delay overlap", "frequency": "weekly", "confidence": 0.89, "sample_size": profile["counts"]["engagement"], "description": "Low engagement signals are materially worse when manager follow-up is late."},
            {"name": "Confidential isolation", "frequency": "controlled", "confidence": 0.98, "sample_size": profile["engagement"]["confidential"], "description": "Restricted disclosures are masked and routed outside normal actions."},
        ],
        "actions": [
            {"title": "Review Red compliance/payroll cases", "priority": "critical", "estimated_impact": "Prevent unsafe Day90 interventions", "action_type": "open_workbench"},
            {"title": "Approve Amber manager nudges", "priority": "high", "estimated_impact": "Recover delayed manager follow-up", "action_type": "trigger_policy"},
            {"title": "Assign data steward to manager-reference issues", "priority": "medium", "estimated_impact": "Clear unsafe cohort records", "action_type": "open_workbench"},
        ],
    }


@router.get("/workbench")
def get_workbench():
    return {"cases": _workbench_cases_from_profile(_profile())}


@router.post("/workbench/{case_id}/decision")
def record_decision(case_id: str, request: DecisionRequest):
    for case in _workbench_cases_from_profile(_profile()):
        if case["id"] == case_id:
            case["status"] = {"approve": "approved", "modify": "modified", "reject": "rejected"}[request.decision]
            case["updated_at"] = utc_now()
            CASE_DECISIONS[case_id] = {
                "status": case["status"],
                "updated_at": case["updated_at"],
                "reviewer_note": request.note,
            }
            actions: list[dict] = []
            if request.decision == "approve":
                # Approval is the only path that can create external actions.
                # Keep it idempotent so retries or double-clicks cannot create
                # duplicate Slack messages or Asana tasks.
                if case_id in CASE_ACTIONS:
                    actions = deepcopy(CASE_ACTIONS[case_id])
                else:
                    approval_tag = f"R2-APPROVED-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                    actions = create_masked_reviewer_actions(case, approval_tag)
                    CASE_ACTIONS[case_id] = deepcopy(actions)
                    for action in reversed(actions):
                        AUDIT_TRAIL.insert(
                            0,
                            {
                                "time": utc_now(),
                                "event": f"Approved action: {action['system']}",
                                "actor": "Intervention Execution and Outcome Operator",
                                "detail": ("OK - " if action.get("ok") else "FAILED - ") + str(action.get("detail", ""))[:240],
                            },
                        )
            AUDIT_TRAIL.insert(
                0,
                {
                    "time": case["updated_at"],
                    "event": f"Workbench decision: {request.decision}",
                    "actor": "Human reviewer",
                    "detail": f"{case['employee_id']} {case['route']} - {request.note or 'No note provided'}",
                },
            )
            return {
                "case": deepcopy(case),
                "actions": actions,
                "audit": deepcopy(AUDIT_TRAIL[0]),
            }
    raise HTTPException(status_code=404, detail="Workbench case not found")


@router.post("/runs/trigger")
def trigger_run():
    timestamp = utc_now()
    profile = _profile()
    live_ready = all_required_live_integrations_ready(profile["source"])
    cases = _workbench_cases_from_profile(profile)
    run_tag = f"R2-LIVE-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    auto_receipt = execute_supervity_orchestrator(profile, cases, run_tag)
    if auto_receipt.get("status") != "not_configured":
        AUDIT_TRAIL.insert(
            0,
            {
                "time": timestamp,
                "event": "Auto orchestration proof",
                "actor": "Day90 Guardian Orchestrator",
                "detail": str(auto_receipt.get("detail", ""))[:240],
            },
        )
    AUDIT_TRAIL.insert(
        0,
        {
            "time": timestamp,
            "event": "Manual trigger requested",
            "actor": "AI Manager",
            "detail": (
                f"Prepared next Day90 Guardian live run with {len(cases)} review case(s). External actions remain gated until a human approves a Workbench case."
                if live_ready
                else "Prepared next Day90 Guardian run; waiting for required live integration keys before external execution."
            ),
        },
    )
    return {
        "status": "ready_for_live_execution" if live_ready else "queued_for_auto_connection",
        "message": (
            "Command Center trigger captured. Review a Workbench case and approve it to create the masked reviewer action."
            if live_ready
            else "Command Center trigger captured. Add Supabase, Supervity, Slack, and Asana keys to execute the final live workflow from backend."
        ),
        "ready_for_live_demo": live_ready,
        "run_tag": run_tag,
        "orchestrator": auto_receipt,
        "external_actions": [],
        "audit": deepcopy(AUDIT_TRAIL[0]),
    }
