from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/ai", tags=["AI Manager"])


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    context: dict = {}


@router.post("/chat")
def chat(request: ChatRequest):
    message = request.message.lower()
    page = request.context.get("page", "the current page")

    if "trigger" in message or "run" in message:
        response = (
            "I can prepare a Day90 Guardian run from the Command Center. "
            "The current backend has captured the trigger path; live Supervity execution will be enabled after the Workflow API key is stored server-side."
        )
        tool_name = "prepare_day90_run"
    elif "confidential" in message:
        response = (
            "Confidential cases are isolated from dashboards, Slack, and public Asana descriptions. "
            "Only the restricted People Ops Workbench queue receives the masked case summary."
        )
        tool_name = "explain_confidential_gate"
    elif "policy" in message:
        response = (
            "Day90 policies are business-editable gates. Changing a threshold or route affects the next evaluation and records an audit event."
        )
        tool_name = "explain_policy_gate"
    else:
        response = (
            f"On {page}, I can help inspect Day90 risk routes, open Workbench cases, explain operator evidence, or prepare a controlled run. "
            "The current proof surface is focused on onboarding, access, compliance, payroll, engagement, manager follow-up, and confidential routing."
        )
        tool_name = "summarize_day90_context"

    return {
        "response": response,
        "tool_calls": [
            {
                "id": "day90-manager-001",
                "name": tool_name,
                "args": {"page": page},
                "result": {"status": "ready"},
            }
        ],
    }
