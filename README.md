# Hackersquad AI Marketing Agent v1

This repository implements the AI Marketing Agent MVP with:
- FastAPI Web API
- Supervisor Agent + 6 Worker Agents
- Task lifecycle state machine with heartbeats/checkpoints/stale recovery
- Human approval gate for campaign publish readiness
- Configurable trend source connectors (`config/trend_sources.json`)
- Data model for projects, tasks, recommendations, memory, campaigns, artifacts, approvals

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
