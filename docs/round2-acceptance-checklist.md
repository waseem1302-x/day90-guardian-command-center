# Round 2 acceptance checklist

Use this checklist before recording or deploying the winner submission. It is deliberately evidence-driven: every item has a visible UI or command that proves it.

## 1. Supervity orchestration

- [ ] Workflow is saved as the current v12/default version.
- [ ] Graph visibly contains data validation, the two parallel operators, fan-in, policy routing, Intervention Execution, Workbench Gates, and Final Console Output.
- [ ] A live `approved_test` run returns a `batch_id`, route counts, separate operator calls, parallel fan-out/fan-in, workbench gates, and retry/duplicate results.

## 2. Data and integrations

- [ ] Dashboard reports Supabase as the live source and shows connected systems without exposing secrets.
- [ ] Supabase, Slack, and Asana connections are verified in Supervity Integrations.
- [ ] The local Data Manager shows source lineage, table counts, and computed signals.

## 3. Human safety and actions

- [ ] Amber approval produces a masked Slack message and assigned Asana review task.
- [ ] Red approval produces only the restricted HR Asana task; it is never broadcast to Slack.
- [ ] Confidential and Data Quality cases remain internal Workbench gates with no public artifact.
- [ ] Approving the same case twice returns the original receipts and creates no duplicate action.

## 4. Auditability

- [ ] Workbench displays employee ID, case key, reason, evidence, route, security boundary, reviewer note, and decision.
- [ ] The Dashboard audit trail shows the trigger, human decision, and action receipts.
- [ ] Slack/Asana evidence contains the case key and synthetic-data/privacy notice, not raw confidential text.

## 5. Quality verification

Run inside the backend image:

```powershell
docker compose up -d --build backend frontend
docker compose exec backend pytest -q
```

The same checks can be run end-to-end with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-round2.ps1
```

The suite must pass health/readiness, secret-safe registry, route-aware actions, privacy gates, idempotency, and approval-gating tests.

## 6. Responsive UI

- [ ] At laptop width, the header breadcrumb truncates cleanly and never overlaps Search, AI Manager, notifications, or the account menu.
- [ ] Dashboard, Data Manager, Workbench, AI Policies, and AI Insights have no horizontal page scrollbar.
- [ ] Workbench action receipts and route policy guidance are visible after a decision.

## 7. Deployment and repository safety

- [ ] `.env` is ignored; only `.env.example` is committed.
- [ ] `AUTH_BYPASS=false` and `APP_ENV=staging` or `production` in shared deployments.
- [ ] Secrets come from the deployment secret manager; rotate any credential ever shown in a recording.
- [ ] Health checks pass at `/api/health` and `/api/ready`, and the frontend container is healthy.
- [ ] GitHub Actions `Round 2 verification` is green for backend tests and the frontend production build.
