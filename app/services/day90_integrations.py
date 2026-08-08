from __future__ import annotations

import csv
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import httpx


DEFAULT_SUPERVITY_WORKFLOW_ID = "019f7b16-6fc0-7000-923b-f6ebf9317c02"
DEFAULT_SUPERVITY_ACTIVE_ORG = ""
DEFAULT_SUPERVITY_RUN_MODE = "dry_run"
DEFAULT_SUPERVITY_SCOPE_TYPE = "all"
DEFAULT_SUPERVITY_BATCH_ID = "R2-BATCH-20260803"
DEFAULT_SUPERVITY_POLICY_PROFILE = "hr-default"
DEFAULT_SUPERVITY_POLICY_VERSION = 1
DEFAULT_SUPERVITY_SLACK_CHANNEL_NAME = "day90-test"
DEFAULT_SUPERVITY_ASANA_PROJECT_NAME = "D90TEST — Day90 Guardian"
DEFAULT_SUPERVITY_ASANA_WORKSPACE_NAME = "My Workspace"
SUPERVITY_STREAM_PATH = "/api/v1/workflow-runs/execute/stream"
SUPERVITY_FAILED_STATUSES = {"failed", "cancelled"}


def _configured(*names: str) -> bool:
    return all(bool(os.getenv(name, "").strip()) for name in names)


def _secret_status(name: str) -> str:
    """Return configuration state without exposing any part of a secret."""
    return "configured" if os.getenv(name, "").strip() else "missing"


def _is_supervity_stream_url(value: str) -> bool:
    return value.rstrip("/").endswith(SUPERVITY_STREAM_PATH)


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
    supervity_url = os.getenv("SUPERVITY_WORKFLOW_EXECUTE_URL", "").strip()
    supervity_workflow_id = os.getenv("SUPERVITY_WORKFLOW_ID", DEFAULT_SUPERVITY_WORKFLOW_ID).strip()
    supervity_active_org = os.getenv("SUPERVITY_ACTIVE_ORG", DEFAULT_SUPERVITY_ACTIVE_ORG).strip()
    supervity_ready = (
        _configured("SUPERVITY_WORKFLOW_EXECUTE_URL", "SUPERVITY_API_KEY")
        and _is_supervity_stream_url(supervity_url)
        and bool(supervity_workflow_id)
    )
    slack_ready = _configured("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID")
    asana_ready = _configured("ASANA_ACCESS_TOKEN", "ASANA_PROJECT_GID")

    return [
        {
            "name": "Supabase",
            "category": "system of record",
            "proof_role": "primary_operational_integration",
            "counts_as_live": True,
            "status": "ready" if supabase_ready else "needs_api_key",
            "detail": (
                "Configured as final live data source."
                if supabase_ready
                else "Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for the live source of record. CSV fallback remains active for local recovery."
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
            "proof_role": "resilience_fallback",
            "counts_as_live": False,
            "status": "ready" if source.get("available") else "missing",
            "detail": f"Resilience fallback for local recovery and source validation. {source.get('path')} as of {source.get('as_of_date')}",
            "configured": bool(source.get("available")),
            "safe_config": {"DAY90_DATASET_DIR": source.get("path")},
        },
        {
            "name": "Supervity Auto",
            "category": "orchestration",
            "proof_role": "primary_operational_integration",
            "counts_as_live": True,
            "status": "ready" if supervity_ready else "needs_api_key",
            "detail": (
                "Streaming workflow endpoint, workflow ID, and API key configured."
                if supervity_ready
                else "Configure the Supervity streaming endpoint, workflow ID, and API key to trigger Auto from this app."
            ),
            "configured": supervity_ready,
            "safe_config": {
                "SUPERVITY_WORKFLOW_EXECUTE_URL": "configured" if os.getenv("SUPERVITY_WORKFLOW_EXECUTE_URL") else "missing",
                "SUPERVITY_API_KEY": _secret_status("SUPERVITY_API_KEY"),
                "SUPERVITY_WORKFLOW_ID": "configured" if supervity_workflow_id else "missing",
                "SUPERVITY_ACTIVE_ORG": "configured" if supervity_active_org else "not required for personal scope",
            },
        },
        {
            "name": "Slack",
            "category": "channel",
            "proof_role": "primary_operational_integration",
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
            "proof_role": "primary_operational_integration",
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
        "operational_note": "CSV is retained as a resilience fallback; primary operations run through Supabase, Supervity Auto, Slack, and Asana.",
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


def _iter_supervity_sse_events(lines: Iterable[str]) -> Iterable[tuple[str, dict]]:
    """Parse complete SSE events without retaining streamed reasoning content."""
    event_name = "message"
    data_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if line == "":
            if data_lines:
                payload = json.loads("\n".join(data_lines))
                if not isinstance(payload, dict):
                    raise ValueError("Supervity SSE data must be a JSON object.")
                yield event_name, payload
            event_name = "message"
            data_lines = []
        elif line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if data_lines:
        payload = json.loads("\n".join(data_lines))
        if not isinstance(payload, dict):
            raise ValueError("Supervity SSE data must be a JSON object.")
        yield event_name, payload


def _supervity_event_receipt(event_name: str, payload: dict) -> tuple[str | None, str | None]:
    content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    workflow_run = payload.get("workflowRun") if isinstance(payload.get("workflowRun"), dict) else {}
    run_id = content.get("workflowRunId") or workflow_run.get("id") or payload.get("workflowRunId")
    status = content.get("status") or workflow_run.get("status") or payload.get("status")
    if event_name == "result" and payload.get("success") is True and not status:
        status = "completed"
    return run_id, status


def _supervity_contract_inputs(profile: dict) -> dict:
    """Build the exact Auto workflow input names observed from the v12 workflow metadata."""
    source = profile.get("source") if isinstance(profile.get("source"), dict) else {}
    as_of_date = os.getenv("SUPERVITY_AS_OF_DATETIME", "").strip()
    if not as_of_date:
        as_of_date = f"{source.get('as_of_date') or '2026-08-03'}T12:00:00+08:00"

    batch_id = os.getenv("SUPERVITY_BATCH_ID", DEFAULT_SUPERVITY_BATCH_ID).strip()

    return {
        "as_of_datetime": as_of_date,
        "scope_type": os.getenv("SUPERVITY_SCOPE_TYPE", DEFAULT_SUPERVITY_SCOPE_TYPE).strip(),
        "scope_value": os.getenv("SUPERVITY_SCOPE_VALUE", "").strip(),
        "policy_profile": os.getenv("SUPERVITY_POLICY_PROFILE", DEFAULT_SUPERVITY_POLICY_PROFILE).strip(),
        "policy_version": int(os.getenv("SUPERVITY_POLICY_VERSION", str(DEFAULT_SUPERVITY_POLICY_VERSION)).strip()),
        "run_mode": os.getenv("SUPERVITY_RUN_MODE", DEFAULT_SUPERVITY_RUN_MODE).strip(),
        "batch_id": batch_id,
        "source_batch_id": os.getenv("SUPERVITY_SOURCE_BATCH_ID", batch_id).strip(),
        "slack_channel_name": os.getenv("SUPERVITY_SLACK_CHANNEL_NAME", DEFAULT_SUPERVITY_SLACK_CHANNEL_NAME).strip(),
        "asana_project_name": os.getenv("SUPERVITY_ASANA_PROJECT_NAME", DEFAULT_SUPERVITY_ASANA_PROJECT_NAME).strip(),
        "asana_workspace_name": os.getenv("SUPERVITY_ASANA_WORKSPACE_NAME", DEFAULT_SUPERVITY_ASANA_WORKSPACE_NAME).strip(),
    }


def execute_supervity_orchestrator(profile: dict, cases: list[dict], run_tag: str) -> dict:
    """Call the Auto Orchestrator when explicitly enabled.

    The default is proof-safe: report configuration without executing the
    external workflow. Enabling execution is a deployment choice because Auto
    workflows can be connected to real downstream systems.
    """

    workflow_url = os.getenv("SUPERVITY_WORKFLOW_EXECUTE_URL", "").strip()
    api_key = os.getenv("SUPERVITY_API_KEY", "").strip()
    workflow_id = os.getenv("SUPERVITY_WORKFLOW_ID", DEFAULT_SUPERVITY_WORKFLOW_ID).strip()
    active_org = os.getenv("SUPERVITY_ACTIVE_ORG", DEFAULT_SUPERVITY_ACTIVE_ORG).strip()
    if not workflow_url or not api_key or not workflow_id:
        return {
            "system": "supervity_auto",
            "ok": False,
            "executed": False,
            "status": "not_configured",
            "detail": "Supervity endpoint, workflow ID, or API key is missing.",
        }

    if not _is_supervity_stream_url(workflow_url):
        return {
            "system": "supervity_auto",
            "ok": False,
            "executed": False,
            "status": "invalid_configuration",
            "detail": "Supervity endpoint must use /api/v1/workflow-runs/execute/stream.",
        }

    if not supervity_trigger_enabled():
        return {
            "system": "supervity_auto",
            "ok": True,
            "executed": False,
            "status": "configured_not_executed",
            "detail": "Supervity is configured; execution is disabled by DAY90_SUPERVITY_TRIGGER_ENABLED.",
        }

    workflow_inputs = _supervity_contract_inputs(profile)

    request_sent = False
    try:
        timeout_seconds = int(os.getenv("DAY90_SUPERVITY_TIMEOUT_SECONDS", "20"))
        if timeout_seconds < 1:
            raise ValueError("DAY90_SUPERVITY_TIMEOUT_SECONDS must be a positive integer.")

        headers = {
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {api_key}",
            "x-source": "external",
        }
        if active_org:
            headers["x-active-org"] = active_org

        files = {"workflowId": (None, workflow_id)}
        for key, value in workflow_inputs.items():
            files[f"inputs[{key}]"] = (None, str(value))

        started_at = time.monotonic()
        run_id = None
        status_text = None
        observed_events: set[str] = set()
        error_event = False
        observation_timed_out = False

        request_sent = True
        with httpx.stream(
            "POST",
            workflow_url,
            headers=headers,
            files=files,
            timeout=timeout_seconds,
        ) as response:
            if response.status_code >= 400:
                return {
                    "system": "supervity_auto",
                    "ok": False,
                    "executed": False,
                    "request_sent": True,
                    "status": "request_rejected",
                    "status_code": response.status_code,
                    "detail": f"Supervity rejected the workflow request with HTTP {response.status_code}.",
                }

            for event_name, event_payload in _iter_supervity_sse_events(response.iter_lines()):
                observed_events.add(event_name)
                event_run_id, event_status = _supervity_event_receipt(event_name, event_payload)
                run_id = event_run_id or run_id
                status_text = event_status or status_text
                if event_name == "error" or (event_name == "result" and event_payload.get("success") is False):
                    error_event = True
                    break
                if status_text and status_text.lower() in SUPERVITY_FAILED_STATUSES:
                    error_event = True
                    break
                if time.monotonic() - started_at >= timeout_seconds:
                    observation_timed_out = True
                    break

            status_code = response.status_code

        if error_event:
            return {
                "system": "supervity_auto",
                "ok": False,
                "executed": bool(run_id),
                "request_sent": True,
                "status": status_text or "failed",
                "status_code": status_code,
                "run_id": run_id,
                "events_observed": sorted(observed_events),
                "detail": "Supervity reported a workflow execution failure.",
            }

        if not run_id:
            return {
                "system": "supervity_auto",
                "ok": False,
                "executed": False,
                "request_sent": True,
                "status": "invalid_response",
                "status_code": status_code,
                "events_observed": sorted(observed_events),
                "detail": "Supervity returned no workflow run ID; execution was not verified.",
            }

        return {
            "system": "supervity_auto",
            "ok": True,
            "executed": True,
            "request_sent": True,
            "status": status_text or "accepted",
            "status_code": status_code,
            "run_id": run_id,
            "events_observed": sorted(observed_events),
            "observation_timed_out": observation_timed_out,
            "detail": f"Auto Orchestrator accepted verified run {run_id}; Workbench approval remains required.",
        }
    except (httpx.HTTPError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:  # pragma: no cover - network dependent
        return {
            "system": "supervity_auto",
            "ok": False,
            "executed": False,
            "request_sent": request_sent,
            "status": "connection_error",
            "detail": f"Supervity connection failed safely ({type(exc).__name__}).",
        }
    except Exception as exc:  # pragma: no cover - defensive production boundary
        return {
            "system": "supervity_auto",
            "ok": False,
            "executed": False,
            "request_sent": request_sent,
            "status": "connection_error",
            "detail": f"Supervity connection failed safely ({type(exc).__name__}).",
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
