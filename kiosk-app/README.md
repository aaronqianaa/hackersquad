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
| Plan | Draft v2 — awaiting review |
| Canvas | 1080 × 1920 portrait, locked |
| App language | Kotlin + Jetpack Compose |
| Backend language | TypeScript (Node/Fastify) + Postgres |
| Payment | Square card reader — Terminal API primary (see PLAN.md §4.3a) |
| Square connection | Not yet authorized |
| Hardware | Not yet validated (see PLAN.md §2 checklist) |
