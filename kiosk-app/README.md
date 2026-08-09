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
| Plan | Draft v5 — decisions locked (see PLAN.md §12 log) |
| Device | ApoloSign 24" FHD Smart Portable TV Gen2 — Android 16, EDLA-certified, touch, rolling stand |
| Canvas | 1080 × 1920 portrait, locked, no logo, English-only v1, accent #007AFF |
| App language | Kotlin + Jetpack Compose |
| Backend language | TypeScript (Node/Fastify) + Postgres |
| Payment | Square Reader on the kiosk via Mobile Payments SDK (PLAN.md §4.3) |
| Staff | Square Terminal at the counter receives kiosk orders + prints receipts on request |
| Loyalty | Square Loyalty in MVP (PLAN.md §4.4) |
| Square connection | Not yet authorized |
| Hardware | Device confirmed; **Phase 0 SDK gate on the real unit still blocks build start** (PLAN.md §2.2) |
