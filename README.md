# Hackersquad AI Marketing Agent v1

This repository implements the AI Marketing Agent MVP with:
- FastAPI Web API
- Supervisor Agent + 6 Worker Agents
- Task lifecycle state machine with heartbeats/checkpoints/stale recovery
- Human approval gate for campaign publish readiness
- Configurable trend source connectors (`config/trend_sources.json`)
- Data model for projects, tasks, recommendations, memory, campaigns, artifacts, approvals
- OpenAI provider integration for page analysis, image understanding, and copy generation

## Worker Agents
- `TrendScoutAgent`
- `PageAnalyzerAgent`
- `BrandPatternAgent`
- `VisionProductAgent`
- `CampaignGeneratorAgent`
- `QAComplianceAgent`

## Key API Endpoints
- `POST /projects`
- `POST /projects/{id}/trend-scan`
- `GET /projects/{id}/recommendations`
- `POST /projects/{id}/reference-page/select`
- `POST /projects/{id}/uploads/product-image`
- `POST /projects/{id}/campaigns/generate`
- `GET /projects/{id}/tasks/{task_id}`
- `POST /projects/{id}/campaigns/{campaign_id}/approve`
- `GET /projects/{id}/campaigns/{campaign_id}/artifacts`
- `POST /memory/purge`
- `DELETE /projects/{id}/uploads/{upload_id}`

## Local Run
```bash
pip install -e .[dev]
uvicorn app.main:app --reload
```

## Configure AI Provider
Set these environment variables (or add them to `.env`):
```bash
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
OPENAI_VISION_MODEL=gpt-4.1-mini
```

If `OPENAI_API_KEY` is not set, workers use deterministic fallback logic so local development and tests still run.

## Optional API Security
You can enforce API key and tenant headers for production-like access control:
```bash
API_KEY=your_internal_api_key
REQUIRE_TENANT_HEADER=true
```

When enabled:
- Pass `X-API-Key` on protected routes.
- Pass `X-Tenant-Id` on project-scoped routes and ensure it matches the project tenant.

## Ops Visibility
Use `GET /ops/tasks/summary` for quick workflow health:
- counts by status (`running`, `failed`, `blocked`, `completed`)
- average completion duration in seconds
- tenant-scoped view when `X-Tenant-Id` is provided

## Test
```bash
pytest -q
```

## Reliability Design
- Task states: `queued | running | blocked | stale | completed | failed | cancelled`
- Heartbeat tracking per task (`last_heartbeat_at`)
- Stale detection via watchdog loop
- Retry + recovery from last checkpoint
- Idempotent artifact writes by unique keys

## Temporal, Postgres, Redis
A Docker Compose stack is included for infrastructure parity with the target architecture:
```bash
docker compose up --build
```

Current implementation uses a `TemporalWorkflowEngine` adapter with local-thread fallback for runnable development mode.
