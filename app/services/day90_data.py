from __future__ import annotations

import csv
import os
import time
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

import httpx


DATASET_DIR = Path(os.getenv("DAY90_DATASET_DIR", "/app/day90_dataset"))
AS_OF_DATE = date(2026, 8, 3)
SUPABASE_RECORDS_TABLE = "round2_day90_source_records"
SUPABASE_LOAD_ID = os.getenv("DAY90_SUPABASE_LOAD_ID", "R2-20260803")
PROFILE_CACHE_TTL_SECONDS = int(os.getenv("DAY90_PROFILE_CACHE_TTL_SECONDS", "3600"))
_PROFILE_CACHE: dict | None = None
_PROFILE_CACHE_EXPIRES_AT = 0.0
SOURCE_FILES = [
    "Workers.csv",
    "Onboarding_Tasks.csv",
    "Provisioning_Integration.csv",
    "Peakon_Engagement.csv",
    "Compliance_Items.csv",
    "Payroll_Records.csv",
    "Learning_Milestones.csv",
    "Cross_Team_Dependencies.csv",
    "Manager_Directory.csv",
    "Locations_Entities.csv",
    "Attrition_History.csv",
]


def _read_csv(name: str) -> list[dict[str, str]]:
    path = DATASET_DIR / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _supabase_configured() -> bool:
    return bool(
        os.getenv("SUPABASE_URL", "").strip()
        and os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )


def _read_supabase(name: str) -> list[dict[str, str]]:
    if not _supabase_configured():
        return []

    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    table_name = name.removesuffix(".csv")
    endpoint = f"{url}/rest/v1/{SUPABASE_RECORDS_TABLE}"
    params = {
        "load_id": f"eq.{SUPABASE_LOAD_ID}",
        "source_table": f"eq.{table_name}",
        "select": "payload",
        "order": "row_index.asc",
        
    }
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    try:
        all_rows = []
        offset = 0
        page_size = 1000
        while True:
            response = httpx.get(
                endpoint,
                params={**params, "limit": str(page_size), "offset": str(offset)},
                headers=headers,
                timeout=12,
            )
            response.raise_for_status()
            page = response.json()
            all_rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
    except Exception:
        return []

    return [row.get("payload") or {} for row in all_rows]


def _read_source(name: str) -> tuple[list[dict[str, str]], str]:
    supabase_rows = _read_supabase(name)
    if supabase_rows:
        return supabase_rows, "supabase"
    return _read_csv(name), "csv_mount"


def _read_supabase_sources(names: list[str]) -> dict[str, list[dict[str, str]]] | None:
    if not _supabase_configured():
        return None

    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    table_names = [name.removesuffix(".csv") for name in names]
    endpoint = f"{url}/rest/v1/{SUPABASE_RECORDS_TABLE}"
    params = {
        "load_id": f"eq.{SUPABASE_LOAD_ID}",
        "source_table": f"in.({','.join(table_names)})",
        "select": "source_table,payload",
    }
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }

    try:
        grouped: dict[str, list[dict[str, str]]] = {name: [] for name in names}
        offset = 0
        page_size = int(os.getenv("DAY90_SUPABASE_PAGE_SIZE", "10000"))
        while True:
            response = httpx.get(
                endpoint,
                params={**params, "limit": str(page_size), "offset": str(offset)},
                headers=headers,
                timeout=12,
            )
            response.raise_for_status()
            page = response.json()
            for row in page:
                source_table = row.get("source_table")
                file_name = f"{source_table}.csv" if source_table else ""
                if file_name in grouped:
                    grouped[file_name].append(row.get("payload") or {})
            if len(page) < page_size:
                break
            offset += page_size
    except Exception:
        return None

    return grouped if any(grouped.values()) else None


def _read_sources(names: list[str]) -> dict[str, tuple[list[dict[str, str]], str]]:
    supabase_sources = _read_supabase_sources(names)
    if supabase_sources:
        return {
            name: (
                supabase_sources.get(name) or _read_csv(name),
                "supabase" if supabase_sources.get(name) else "csv_mount",
            )
            for name in names
        }

    return {name: (_read_csv(name), "csv_mount") for name in names}


def _parse_date(value: str | None) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            continue
    return None


def _score(signals: Counter) -> int:
    return (
        signals["confidential"] * 100
        + signals["pay_errors"] * 22
        + signals["comp_overdue"] * 14
        + signals["blocked_prov"] * 8
        + signals["day1_blocks"] * 10
        + signals["low_engagement"] * 9
        + signals["manager_slow"] * 6
        + signals["learning_incomplete"] * 2
        + signals["missing_manager"] * 20
    )


def dataset_available() -> bool:
    return DATASET_DIR.exists() and (DATASET_DIR / "Workers.csv").exists()


def _compute_day90_profile_uncached() -> dict:
    sources = _read_sources(SOURCE_FILES)
    workers, workers_source = sources["Workers.csv"]
    tasks, tasks_source = sources["Onboarding_Tasks.csv"]
    provisioning, provisioning_source = sources["Provisioning_Integration.csv"]
    engagement, engagement_source = sources["Peakon_Engagement.csv"]
    compliance, compliance_source = sources["Compliance_Items.csv"]
    payroll, payroll_source = sources["Payroll_Records.csv"]
    learning, learning_source = sources["Learning_Milestones.csv"]
    dependencies, dependencies_source = sources["Cross_Team_Dependencies.csv"]
    managers, managers_source = sources["Manager_Directory.csv"]
    locations, locations_source = sources["Locations_Entities.csv"]
    attrition, attrition_source = sources["Attrition_History.csv"]
    source_map = {
        "Workers": workers_source,
        "Onboarding_Tasks": tasks_source,
        "Provisioning_Integration": provisioning_source,
        "Peakon_Engagement": engagement_source,
        "Compliance_Items": compliance_source,
        "Payroll_Records": payroll_source,
        "Learning_Milestones": learning_source,
        "Cross_Team_Dependencies": dependencies_source,
        "Manager_Directory": managers_source,
        "Locations_Entities": locations_source,
        "Attrition_History": attrition_source,
    }
    source_kind = "supabase" if any(source == "supabase" for source in source_map.values()) else "csv_mount"

    manager_ids = {row["Manager_WID"] for row in managers}
    missing_manager_ids = [
        row["Employee_ID"] for row in workers if row.get("Manager_WID") not in manager_ids
    ]

    overdue_tasks = [
        row
        for row in tasks
        if row.get("Status") != "Completed"
        and (due := _parse_date(row.get("Due_Date")))
        and due < AS_OF_DATE
    ]
    completed_after_due = [
        row
        for row in tasks
        if row.get("Status") == "Completed"
        and (due := _parse_date(row.get("Due_Date")))
        and (completed := _parse_date(row.get("Completed_Date")))
        and completed > due
    ]
    blocked_provisioning = [
        row for row in provisioning if row.get("Status") == "Blocked"
    ]
    requested_provisioning = [
        row for row in provisioning if row.get("Status") == "Requested"
    ]
    missing_compliance = [
        row for row in compliance if row.get("status") == "Missing"
    ]
    overdue_compliance = [
        row
        for row in compliance
        if row.get("status") != "Verified"
        and (due := _parse_date(row.get("due_date")))
        and due < AS_OF_DATE
    ]
    payroll_errors = [
        row
        for row in payroll
        if row.get("status") == "Error" or row.get("error_reason", "").strip()
    ]
    confidential = [
        row for row in engagement if row.get("x_confidential", "").lower() == "true"
    ]
    low_engagement = [
        row
        for row in engagement
        if row.get("x_confidential", "").lower() != "true"
        and row.get("Score", "").isdigit()
        and int(row["Score"]) <= 4
    ]
    nonresponse = [
        row
        for row in engagement
        if row.get("sentiment", "").lower() == "nonresponse"
        or not row.get("Score", "").strip()
    ]
    manager_slow = [
        row
        for row in engagement
        if row.get("manager_response_days", "").isdigit()
        and int(row["manager_response_days"]) >= 5
    ]
    incomplete_learning = [
        row for row in learning if row.get("status") != "Completed"
    ]
    day_one_blocks = [
        row
        for row in dependencies
        if row.get("blocks_day_one", "").lower() == "true"
        and row.get("status") != "Completed"
    ]

    signals: defaultdict[str, Counter] = defaultdict(Counter)
    for row in overdue_tasks:
        signals[row["Employee_ID"]]["overdue_tasks"] += 1
    for row in blocked_provisioning:
        signals[row["Employee_ID"]]["blocked_prov"] += 1
    for row in overdue_compliance:
        signals[row["employee_id"]]["comp_overdue"] += 1
    for row in missing_compliance:
        signals[row["employee_id"]]["comp_missing"] += 1
    for row in payroll_errors:
        signals[row["employee_id"]]["pay_errors"] += 1
    for row in low_engagement:
        signals[row["Employee_ID"]]["low_engagement"] += 1
    for row in confidential:
        signals[row["Employee_ID"]]["confidential"] += 1
    for row in manager_slow:
        signals[row["Employee_ID"]]["manager_slow"] += 1
    for row in incomplete_learning:
        signals[row["employee_id"]]["learning_incomplete"] += 1
    for row in day_one_blocks:
        signals[row["employee_id"]]["day1_blocks"] += 1
    for employee_id in missing_manager_ids:
        signals[employee_id]["missing_manager"] += 1

    candidate_cases = []
    for employee_id, case_signals in signals.items():
        risk_score = _score(case_signals)
        if risk_score < 35 and not (
            case_signals["confidential"]
            or case_signals["pay_errors"]
            or case_signals["comp_overdue"]
        ):
            continue
        if case_signals["confidential"]:
            route = "CONFIDENTIAL"
        elif case_signals["missing_manager"]:
            route = "DATA_QUALITY"
        elif case_signals["pay_errors"] or case_signals["comp_overdue"] or risk_score >= 85:
            route = "RED"
        else:
            route = "AMBER"
        candidate_cases.append(
            {
                "employee_id": employee_id,
                "route": route,
                "score": risk_score,
                "signals": dict(case_signals),
            }
        )

    route_order = {"CONFIDENTIAL": 0, "RED": 1, "DATA_QUALITY": 2, "AMBER": 3}
    candidate_cases.sort(
        key=lambda case: (
            route_order.get(case["route"], 99),
            -case["score"],
            case["employee_id"],
        )
    )
    route_counts = Counter(case["route"] for case in candidate_cases)

    by_family: defaultdict[str, list[int]] = defaultdict(list)
    for row in attrition:
        if row.get("left_flag", "").isdigit():
            by_family[row["job_family"]].append(int(row["left_flag"]))
    attrition_rates = {
        family: round(sum(values) / len(values) * 100, 1)
        for family, values in by_family.items()
    }

    return {
        "source": {
            "kind": source_kind,
            "available": bool(workers),
            "path": (
                f"{os.getenv('SUPABASE_URL', '').rstrip('/')}/rest/v1/{SUPABASE_RECORDS_TABLE}"
                if source_kind == "supabase"
                else str(DATASET_DIR)
            ),
            "as_of_date": AS_OF_DATE.isoformat(),
            "tables_by_source": source_map,
        },
        "counts": {
            "workers": len(workers),
            "cohorts": len({row.get("cohort") for row in workers if row.get("cohort")}),
            "tasks": len(tasks),
            "provisioning": len(provisioning),
            "engagement": len(engagement),
            "managers": len(managers),
            "locations": len(locations),
            "compliance": len(compliance),
            "payroll": len(payroll),
            "learning": len(learning),
            "attrition_history": len(attrition),
            "cross_team_dependencies": len(dependencies),
        },
        "quality": {
            "missing_manager_refs": len(missing_manager_ids),
            "missing_manager_employee_ids": missing_manager_ids,
            "overdue_incomplete_tasks": len(overdue_tasks),
            "completed_after_due": len(completed_after_due),
        },
        "provisioning": {
            "blocked": len(blocked_provisioning),
            "requested": len(requested_provisioning),
            "blocked_by_resource": Counter(
                row["Resource"] for row in blocked_provisioning
            ).most_common(),
        },
        "compliance": {
            "missing": len(missing_compliance),
            "overdue": len(overdue_compliance),
        },
        "payroll": {
            "errors": len(payroll_errors),
            "error_employee_ids": [row["employee_id"] for row in payroll_errors],
        },
        "engagement": {
            "confidential": len(confidential),
            "confidential_employee_ids": [row["Employee_ID"] for row in confidential],
            "low_nonconf": len(low_engagement),
            "nonresponse": len(nonresponse),
            "manager_slow_ge_5d": len(manager_slow),
        },
        "learning": {"incomplete": len(incomplete_learning)},
        "dependencies": {
            "day_one_blockers_open": len(day_one_blocks),
            "open_by_team": Counter(row["team"] for row in day_one_blocks).most_common(),
        },
        "attrition_rates": attrition_rates,
        "route_counts": {
            "GREEN": max(len(workers) - sum(route_counts.values()), 0),
            "AMBER": route_counts["AMBER"],
            "RED": route_counts["RED"],
            "CONFIDENTIAL": route_counts["CONFIDENTIAL"],
            "DATA_QUALITY": route_counts["DATA_QUALITY"],
        },
        "candidate_cases": candidate_cases,
    }

def compute_day90_profile(force_refresh: bool = False) -> dict:
    """Return the computed Day90 profile with a short in-process cache."""

    global _PROFILE_CACHE, _PROFILE_CACHE_EXPIRES_AT

    now = time.monotonic()
    if (
        not force_refresh
        and _PROFILE_CACHE is not None
        and now < _PROFILE_CACHE_EXPIRES_AT
    ):
        return deepcopy(_PROFILE_CACHE)

    profile = _compute_day90_profile_uncached()
    _PROFILE_CACHE = deepcopy(profile)
    _PROFILE_CACHE_EXPIRES_AT = now + PROFILE_CACHE_TTL_SECONDS
    return profile


