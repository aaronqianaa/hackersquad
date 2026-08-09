# Tea Hut Kiosk

Self-order kiosk app for Tea Hut stores. Android touchscreen in-store, connected to Square
(catalog, orders, payments, locations, loyalty).

Nothing is implemented yet — this folder currently holds the plan.

- **[PLAN.md](./PLAN.md)** — product & technical plan, full feature list, build phases, open questions.

## Shape of the system (once built)

```
kiosk-app/
├── PLAN.md
├── android/     # Kotlin + Jetpack Compose kiosk client
├── backend/     # API: staff auth, Square OAuth + token refresh, catalog sync, order orchestration
└── admin/       # Web console: branches, kiosks, menu overrides, Terminal pairing
```

## Status

| | |
|---|---|
| Plan | Draft v3 — awaiting review |
| Canvas | 1080 × 1920 portrait, locked, no logo |
| App language | Kotlin + Jetpack Compose |
| Backend language | TypeScript (Node/Fastify) + Postgres |
| Payment | Square Reader on the kiosk via Mobile Payments SDK (PLAN.md §4.3) |
| Staff | Square Terminal at the counter receives kiosk orders |
| Square connection | Not yet authorized |
| Hardware | **Not yet validated — Phase 0 SDK gate blocks all other work** (PLAN.md §2) |
