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
├── firebase/    # Cloud Functions (TS): Square OAuth + refresh, webhooks, orders; Firestore rules; FCM
├── ios-manager/ # Swift + SwiftUI manager app: fleet dashboard, push alerts, 86 toggle, settings
└── admin/       # Minimal owner web console: Square connect, staff accounts, branch mapping
```

## Status

| | |
|---|---|
| Plan | Draft v6 — decisions locked (see PLAN.md §12 log) |
| Device | ApoloSign 24" FHD Smart Portable TV Gen2 — Android 16, EDLA-certified, touch, rolling stand |
| Canvas | 1080 × 1920 portrait, locked, no logo, English-only v1, accent #007AFF |
| App language | Kotlin + Jetpack Compose |
| Backend | Firebase — Cloud Functions (TypeScript) + Firestore + Auth + FCM |
| Manager app | iOS — Swift + SwiftUI, APNs push alerts |
| Payment | Square Reader on the kiosk via Mobile Payments SDK (PLAN.md §4.3) |
| Staff | Square Terminal at the counter receives kiosk orders + prints receipts on request |
| Loyalty | Square Loyalty in MVP (PLAN.md §4.4) |
| Availability | Real-time — Square sold-out → kiosks in ~1–2s (PLAN.md §4.2a) |
| Square connection | Not yet authorized |
| Hardware | Device confirmed; **Phase 0 SDK gate on the real unit still blocks build start** (PLAN.md §2.2) |
