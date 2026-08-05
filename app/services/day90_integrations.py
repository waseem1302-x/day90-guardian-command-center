from __future__ import annotations

import os
import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx


def _configured(*names: str) -> bool:
    return all(bool(os.getenv(name, "").strip()) for name in names)


def _secret_status(name: str) -> str:
    """Return configuration state without exposing any part of a secret."""
    return "configured" if os.getenv(name, "").strip() else "missing"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _business_due_date(days: int) -> str:
    """Return a weekday deadline, skipping Saturday and Sunday."""
    due_date = date.today()
    remaining_days = max(0, days)
    while remaining_days:
        due_date += timedelta(days=1)
        if due_date.weekday() < 5:
            remaining_days -= 1
    return due_date.isoformat()


def _asana_owner(route: str) -> tuple[str, str]:
    """Select a safe owner without hard-coding a personal account ID."""
    route_owner = os.getenv(f"ASANA_{route}_ASSIGNEE_GID", "").strip()
    default_owner = os.getenv("ASANA_ASSIGNEE_GID", "").strip()
    if route_owner:
        return route_owner, "route-specific reviewer"
    if default_owner:
        return default_owner, "default reviewer"
    # Asana's documented value assigns the task to the token holder.
    return "me", "token owner"


def _asana_due_date(route: str) -> str:
    configured_days = os.getenv(f"ASANA_{route}_DUE_DAYS", "").strip()
    if configured_days.isdigit():
        return _business_due_date(int(configured_days))
    # Red cases are urgent; Amber gets the next business day by default.
    return _business_due_date(0 if route == "RED" else 1)


def integration_registry(source: dict) -> list[dict]:
    supabase_ready = _configured("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
    supervity_ready = _configured("SUPERVITY_WORKFLOW_EXECUTE_URL", "SUPERVITY_API_KEY")
    slack_ready = _configured("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID")
    asana_ready = _configured("ASANA_ACCESS_TOKEN", "ASANA_PROJECT_GID")

    return [
        {
            "name": "Supabase",
            "category": "system of record",
            "proof_role": "judged_live_integration",
            "counts_as_live": True,
            "status": "ready" if supabase_ready else "needs_api_key",
            "detail": (
                "Configured as final live data source."
                if supabase_ready
                else "Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for final live proof. CSV fallback remains active for local dev."
            ),
            "configured": supabase_ready,
            "safe_config": {
                "SUPABASE_URL": "configured" if os.getenv("SUPABASE_URL") else "missing",
                "SUPABASE_SERVICE_ROLE_KEY": _secret_status("SUPABASE_SERVICE_ROLE_KEY"),
            },
        },
        {
            "name": "Round 2 CSV Mount",
            "category": "source data fallback",
            "proof_role": "controlled_fallback_not_judged_live",
            "counts_as_live": False,
            "status": "ready" if source.get("available") else "missing",
            "detail": f"Controlled fallback only; not counted as a judged live integration. {source.get('path')} as of {source.get('as_of_date')}",
            "configured": bool(source.get("available")),
            "safe_config": {"DAY90_DATASET_DIR": source.get("path")},
        },
        {
            "name": "Supervity Auto",
            "category": "orchestration",
            "proof_role": "judged_live_integration",
            "counts_as_live": True,
            "status": "ready" if supervity_ready else "needs_api_key",
            "detail": (
                "Workflow execute endpoint and API key configured."
                if supervity_ready
                else "Add SUPERVITY_WORKFLOW_EXECUTE_URL and SUPERVITY_API_KEY to trigger the live operator workflow from this app."
            ),
            "configured": supervity_ready,
            "safe_config": {
                "SUPERVITY_WORKFLOW_EXECUTE_URL": "configured" if os.getenv("SUPERVITY_WORKFLOW_EXECUTE_URL") else "missing",
                "SUPERVITY_API_KEY": _secret_status("SUPERVITY_API_KEY"),
            },
        },
        {
            "name": "Slack",
            "category": "channel",
            "proof_role": "judged_live_integration",
            "counts_as_live": True,
            "status": "ready" if slack_ready else "needs_api_key",
            "detail": (
                "Bot token and target channel configured for masked case notifications."
                if slack_ready
                else "Add SLACK_BOT_TOKEN and SLACK_CHANNEL_ID for live reviewer notifications."
            ),
            "configured": slack_ready,
            "safe_config": {
                "SLACK_BOT_TOKEN": _secret_status("SLACK_BOT_TOKEN"),
                "SLACK_CHANNEL_ID": "configured" if os.getenv("SLACK_CHANNEL_ID") else "missing",
            },
        },
        {
            "name": "Asana",
            "category": "work system",
            "proof_role": "judged_live_integration",
            "counts_as_live": True,
            "status": "ready" if asana_ready else "needs_api_key",
            "detail": (
                "Access token and project configured; new review tasks receive an owner and route-based due date."
                if asana_ready
                else "Add ASANA_ACCESS_TOKEN and ASANA_PROJECT_GID for live review task creation."
            ),
            "configured": asana_ready,
            "safe_config": {
                "ASANA_ACCESS_TOKEN": _secret_status("ASANA_ACCESS_TOKEN"),
                "ASANA_PROJECT_GID": "configured" if os.getenv("ASANA_PROJECT_GID") else "missing",
                "ASANA_TASK_OWNER": "configured" if os.getenv("ASANA_ASSIGNEE_GID") else "token owner (me)",
            },
        },
    ]


def live_integration_summary(registry: list[dict]) -> dict:
    live_items = [item for item in registry if item.get("counts_as_live")]
    fallback_items = [item for item in registry if not item.get("counts_as_live")]
    ready_live = [item for item in live_items if item.get("status") == "ready" and item.get("configured")]
    ready_fallbacks = [item for item in fallback_items if item.get("status") == "ready" and item.get("configured")]
    categories = sorted({item["category"] for item in live_items})

    return {
        "ready_live_integrations": len(ready_live),
        "total_live_integrations": len(live_items),
        "ready_fallbacks": len(ready_fallbacks),
        "total_fallbacks": len(fallback_items),
        "live_names": [item["name"] for item in live_items],
        "fallback_names": [item["name"] for item in fallback_items],
        "live_categories": categories,
        "meets_round2_minimum": len(ready_live) >= 3 and "channel" in categories and "system of record" in categories,
        "judge_note": "CSV is retained as a controlled fallback and is not counted toward the judged live integration total.",
    }


def all_required_live_integrations_ready(source: dict) -> bool:
    registry = integration_registry(source)
    required = {"Supabase", "Supervity Auto", "Slack", "Asana"}
    return all(item["configured"] for item in registry if item["name"] in required)


def supervity_trigger_enabled() -> bool:
    return os.getenv("DAY90_SUPERVITY_TRIGGER_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def execute_supervity_orchestrator(profile: dict, cases: list[dict], run_tag: str) -> dict:
    """Call the Auto Orchestrator when explicitly enabled.

    The default is proof-safe: report configuration without executing the
    external workflow. Enabling execution is a deployment choice because Auto
    workflows can be connected to real downstream systems.
    """

    workflow_url = os.getenv("SUPERVITY_WORKFLOW_EXECUTE_URL", "").strip()
    api_key = os.getenv("SUPERVITY_API_KEY", "").strip()
    if not workflow_url or not api_key:
        return {
            "system": "supervity_auto",
            "ok": False,
            "executed": False,
            "status": "not_configured",
            "detail": "Supervity workflow URL or API key is missing.",
        }

    if not supervity_trigger_enabled():
        return {
            "system": "supervity_auto",
            "ok": True,
            "executed": False,
            "status": "configured_not_executed",
            "detail": "Supervity is configured; execution is disabled by DAY90_SUPERVITY_TRIGGER_ENABLED.",
        }

    payload = {
        "source": "day90_command_center",
        "mode": "approval_gated",
        "run_tag": run_tag,
        "batch_id": "R2-BATCH-20260803",
        "policy_profile": "hr-default",
        "policy_version": 1,
        "external_actions_allowed": False,
        "workbench_approval_required": True,
        "route_counts": profile.get("route_counts", {}),
        "case_count": len(cases),
        "cases": [
            {
                "case_id": case.get("id"),
                "case_key": case.get("case_key"),
                "employee_id": case.get("employee_id"),
                "route": case.get("route"),
                "risk_band": case.get("risk_band"),
                "status": case.get("status"),
            }
            for case in cases[:12]
        ],
    }

    try:
        timeout_seconds = int(os.getenv("DAY90_SUPERVITY_TIMEOUT_SECONDS", "20"))
        response = httpx.post(
            workflow_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=timeout_seconds,
        )
        response_payload = response.json() if response.content else {}
        run_id = (
            response_payload.get("run_id")
            or response_payload.get("id")
            or response_payload.get("data", {}).get("id")
        )
        status_text = response_payload.get("status") or response_payload.get("state")
        return {
            "system": "supervity_auto",
            "ok": response.status_code < 400,
            "executed": True,
            "status": status_text or ("accepted" if response.status_code < 400 else "failed"),
            "status_code": response.status_code,
            "run_id": run_id,
            "detail": (
                f"Auto Orchestrator accepted run {run_id}."
                if response.status_code < 400 and run_id
                else "Auto Orchestrator execution request completed."
                if response.status_code < 400
                else f"Auto Orchestrator execution failed with HTTP {response.status_code}."
            ),
        }
    except Exception as exc:  # pragma: no cover - network dependent
        return {
            "system": "supervity_auto",
            "ok": False,
            "executed": True,
            "status": "error",
            "detail": str(exc)[:240],
        }


def create_masked_reviewer_actions(case: dict, run_tag: str) -> list[dict]:
    """Create safe, route-aware reviewer artifacts.

    Amber may use the broad reviewer channel plus a task. Red is restricted to
    the task system, while Confidential and Data Quality never create public
    external artifacts.
    """
    route = case.get("route")
    if route == "CONFIDENTIAL":
        return [
            {
                "system": "privacy_gate",
                "ok": True,
                "detail": "Confidential case blocked from public Slack/Asana notification.",
            }
        ]
    if route == "DATA_QUALITY":
        return [
            {
                "system": "data_quality_gate",
                "ok": True,
                "detail": "Unsafe data-quality case quarantined; no external action created.",
            }
        ]

    actions: list[dict] = []
    slack_token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    slack_channel = os.getenv("SLACK_CHANNEL_ID", "").strip()
    asana_token = os.getenv("ASANA_ACCESS_TOKEN", "").strip()
    asana_project = os.getenv("ASANA_PROJECT_GID", "").strip()

    safe_text = "\n".join(
        [
            f"[{run_tag}] DAY90 GUARDIAN - AMBER REVIEW",
            f"Employee: {case['employee_id']} | Lifecycle: DAY90",
            f"Recommended action: {case['recommended_action']}",
            f"Case key: {case['case_key']}",
            "Safety: Synthetic hackathon test only. No confidential text. Privacy masking active.",
        ]
    )

    # Red cases are restricted to the HR task queue and never go to a broad
    # Slack channel. Amber is the only route eligible for Slack notification.
    if route == "AMBER" and slack_token and slack_channel:
        try:
            response = httpx.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {slack_token}"},
                json={"channel": slack_channel, "text": safe_text},
                timeout=12,
            )
            payload = response.json()
            actions.append(
                {
                    "system": "slack",
                    "ok": bool(payload.get("ok")),
                    "detail": payload.get("error") or "Masked Slack reviewer message sent.",
                }
            )
        except Exception as exc:  # pragma: no cover - network dependent
            actions.append({"system": "slack", "ok": False, "detail": str(exc)})

    if asana_token and asana_project:
        try:
            asana_owner, owner_source = _asana_owner(route)
            due_on = _asana_due_date(route)
            response = httpx.post(
                "https://app.asana.com/api/1.0/tasks",
                headers={"Authorization": f"Bearer {asana_token}"},
                json={
                    "data": {
                        "name": f"[{run_tag}] {case['employee_id']} - {route} Day90 review",
                        "notes": "\n".join(
                            [
                                "Day90 Guardian human-review task",
                                f"Case key: {case['case_key']}",
                                f"Route: {route}",
                                f"Review owner: {case.get('assignee', owner_source)}",
                                f"Reason: {case['reason']}",
                                f"Required action: {case['recommended_action']}",
                                f"Due date: {due_on}",
                                "Security: synthetic hackathon data only, no confidential raw text.",
                                "Audit: generated by Day90 Guardian Command Center.",
                            ]
                        ),
                        "projects": [asana_project],
                        "assignee": asana_owner,
                        "due_on": due_on,
                    }
                },
                timeout=12,
            )
            payload = response.json()
            data = payload.get("data") or {}
            actions.append(
                {
                    "system": "asana",
                    "ok": response.status_code < 400 and bool(data.get("gid")),
                    "detail": data.get("permalink_url") or payload.get("errors") or "Masked Asana reviewer task created.",
                    "assignment": owner_source,
                    "due_on": due_on,
                }
            )
        except Exception as exc:  # pragma: no cover - network dependent
            actions.append({"system": "asana", "ok": False, "detail": str(exc)})

    return actions


def seed_supabase_source_records(dataset_dir: str, load_id: str = "R2-20260803") -> dict:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return {"ok": False, "error": "Supabase URL/service key not configured."}

    csv_dir = Path(dataset_dir)
    if not csv_dir.exists():
        return {"ok": False, "error": f"Dataset directory not found: {dataset_dir}"}

    endpoint = f"{url}/rest/v1/round2_day90_source_records"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    files = sorted(
        path
        for path in csv_dir.glob("*.csv")
        if path.name not in {"00_INDEX.csv", "Field_Dictionary.csv"}
    )

    with httpx.Client(timeout=30) as client:
        delete_response = client.delete(
            endpoint,
            params={"load_id": f"eq.{load_id}"},
            headers={**headers, "Prefer": "return=minimal"},
        )
        if delete_response.status_code >= 400:
            return {
                "ok": False,
                "error": f"Delete existing load failed: {delete_response.status_code}",
                "detail": delete_response.text[:240],
            }

        inserted = 0
        per_table = []
        for path in files:
            table_name = path.stem
            with path.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            per_table.append({"table": table_name, "rows": len(rows)})
            for start in range(0, len(rows), 500):
                payload = [
                    {
                        "load_id": load_id,
                        "source_table": table_name,
                        "row_index": start + offset,
                        "payload": row,
                    }
                    for offset, row in enumerate(rows[start : start + 500])
                ]
                response = client.post(
                    endpoint,
                    headers={**headers, "Prefer": "return=minimal"},
                    json=payload,
                )
                if response.status_code >= 400:
                    return {
                        "ok": False,
                        "error": f"Insert failed for {table_name}: {response.status_code}",
                        "detail": response.text[:240],
                        "inserted_before_failure": inserted,
                    }
                inserted += len(payload)

    return {
        "ok": True,
        "load_id": load_id,
        "tables": len(files),
        "inserted": inserted,
        "per_table": per_table,
    }
