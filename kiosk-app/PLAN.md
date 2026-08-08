# Tea Hut Self-Order Kiosk — Product & Technical Plan

**Status:** Draft v1 — for review, nothing built yet
**Target:** Android touchscreen ("incell" smart portable TV), in-store, Tea Hut branches only
**Backend of record:** Square (catalog, orders, payments, locations, loyalty)
**Reference UX:** Chowbus POS kiosk, MenuSifu kiosk (bubble-tea flow)

---

## 0. Read this first — three decisions that shape everything

| # | Decision | Recommendation | Why it matters |
|---|---|---|---|
| 1 | **How does the customer pay?** | **Square Terminal API** — a Square Terminal mounted next to the TV takes the card; the TV never touches card data. | Square **prohibits** the Mobile Payments SDK (card reader attached to your own Android device) in *unattended* kiosks, and only allows *attended* ones under strict conditions. It also requires Google Play Services + a validated device list that a generic portable TV will likely fail. Terminal API is plain HTTPS — works on any Android screen. |
| 2 | **What is a "user account"?** | Accounts are **Tea Hut staff/manager accounts in our own backend**, not Square logins. Square is connected **once per merchant** via OAuth; staff log in to pick which branch this kiosk serves. | Keeps the Square token server-side and long-lived; a kiosk never holds Square credentials. |
| 3 | **How does the Square link stay "long term"?** | Square **OAuth authorization-code flow** (not PKCE). Refresh token is valid **until revoked**; access token expires every 30 days and is auto-refreshed by a backend job. | PKCE refresh tokens are single-use and die after 90 days — wrong choice for a permanent install. |

> **Note on "full copy of MenuSifu / Chowbus is acceptable":** copying their *UX patterns, screen flow, and feature set* is completely normal and is what this plan does. What we won't do is lift their code, image assets, fonts, or branding — that's the part that creates legal exposure, and it's also the part with no value to Tea Hut. Everything below is a clean-room build of the same experience.

---

## 1. Goals

1. A customer walks up, orders a drink with full customization (size / ice / sugar / toppings), pays, and gets an order number — no staff interaction.
2. The order lands in Square exactly as if it had been rung up on the Square POS, so it appears on the KDS / kitchen printer and in all Square reporting.
3. One APK serves every Tea Hut branch; a branch is chosen at setup and remembered.
4. Runs unattended all day: locked to the app, survives Wi-Fi drops, auto-recovers from reboot.

### Non-goals (v1)
- Public release / App Store distribution (internal sideload or private Play channel only)
- Delivery, third-party marketplaces, table service
- Replacing the Square POS at the counter

---

## 2. Hardware & environment

**Kiosk unit (per station)**
- Android touchscreen "portable TV", 21"–32", Android 9 (API 28)+ — *must be verified, see checklist*
- Square Terminal (payment), mounted at reachable height
- Optional: receipt printer (network ESC/POS, e.g. Epson TM-m30 LAN) — or skip printing, use SMS/email receipts + a number-call screen
- Wi-Fi or Ethernet, PoE preferred; always-on power, surge protected

**Hardware validation checklist (do this before writing app code — 1 day)**
- [ ] Confirm it is real Android (not a Linux/RTOS "smart TV" shell) — `adb shell getprop ro.build.version.release`
- [ ] `adb` over USB or network is enabled (needed for kiosk provisioning)
- [ ] Touch is multi-touch capacitive, and reports as a touchscreen (not a mouse pointer)
- [ ] Screen orientation can be locked to portrait (kiosk flows are portrait-first)
- [ ] Google Play Services present? (not required on the Terminal API path — but needed for FCM push; if absent we fall back to polling)
- [ ] Device Owner provisioning possible (`dpm set-device-owner`) — required for true kiosk lockdown
- [ ] Screen never sleeps on AC power; auto-boots when power is restored
- [ ] Webview version / Chrome version if we go hybrid

**If it fails the checklist:** fall back to a commodity Android tablet (Lenovo Tab / Samsung Tab A) in a floor stand — same app, zero code change.

---

## 3. Architecture

```
┌──────────────────────────┐         ┌────────────────────────┐        ┌──────────────┐
│  Kiosk App (Android)     │  HTTPS  │   Tea Hut Backend      │ HTTPS  │  Square APIs │
│  Kotlin + Compose        │────────▶│   (our server)         │───────▶│  Catalog     │
│                          │◀────────│                        │◀───────│  Orders      │
│  • menu cache (local DB) │  device │  • staff accounts      │ OAuth  │  Terminal    │
│  • cart / customization  │  JWT    │  • Square OAuth tokens │ tokens │  Payments    │
│  • order submit          │         │  • catalog sync + cache│        │  Locations   │
│  • Terminal payment poll │         │  • order orchestration │        │  Loyalty     │
│  • offline queue         │         │  • device registry     │        │  Webhooks    │
└──────────────────────────┘         └────────────────────────┘        └──────────────┘
          │                                     ▲
          │ local network                       │ webhooks (payment updated,
          ▼                                     │ catalog updated, device paired)
   ┌──────────────┐   ┌──────────────┐          │
   │ Square       │   │ Receipt      │          │
   │ Terminal     │   │ printer      │          │
   └──────────────┘   └──────────────┘          │
```

**Why a backend and not direct kiosk → Square?**
- Square OAuth tokens must never live on a device in a public space.
- Menu/catalog is fetched once per branch and served to all kiosks — fast, cheap, consistent.
- One place to hold order state when a kiosk crashes mid-payment.
- Remote config, remote kill-switch, remote menu overrides (86'd items), OTA update pointers.
- Cheap to host: single small VM or a container ($10–20/mo), Postgres, one cron worker.

**Recommended stack**
- App: **Kotlin + Jetpack Compose**, single-activity, MVVM; Room for local cache; WorkManager for the offline queue. (Compose gives the animated, image-heavy MenuSifu look without fighting a WebView; a React Native/Flutter build is viable if you'd rather share code with a future iPad version — say the word and I'll re-cost it.)
- Backend: **Node + TypeScript (Fastify)** or **Python FastAPI** + **Postgres** + Redis. Square's official SDK exists for both.
- Admin console: small web app (same backend) for staff accounts, branch mapping, kiosk registry, menu overrides.

---

## 4. Square integration design

### 4.1 Connecting the Square account (one-time, long-term)
1. Tea Hut owner opens the admin console → **Connect Square** → Square OAuth consent (authorization-code flow).
2. Backend exchanges `code` → `access_token` (30-day) + `refresh_token` (**valid until revoked**).
3. Tokens stored **encrypted at rest** (KMS or libsodium sealed box), never returned to a client.
4. A cron job refreshes the access token every **7 days** (and on any `401`), so an expiry can never take a store offline.
5. `ListLocations` pulls every Tea Hut branch → these become the selectable **branches**.
6. Revocation/disconnect flow + alerting if refresh ever fails.

**OAuth scopes needed:** `MERCHANT_PROFILE_READ`, `ITEMS_READ`, `INVENTORY_READ`, `ORDERS_READ`, `ORDERS_WRITE`, `PAYMENTS_READ`, `PAYMENTS_WRITE`, `CUSTOMERS_READ/WRITE` (loyalty), `LOYALTY_READ/WRITE`, `GIFTCARDS_READ`, `DEVICE_CREDENTIAL_MANAGEMENT` (Terminal pairing).

### 4.2 Menu (Catalog API)
- Backend pulls the full catalog per location and caches it: categories → items → **variations** (sizes) → **modifier lists** (ice, sugar, toppings, milk swap) → images → taxes.
- Bubble-tea mapping: **size = item variation** (M/L), **ice / sugar / topping = modifier lists** with min/max selection rules. Toppings priced per modifier.
- Incremental re-sync every 10 min + on `catalog.version.updated` webhook; kiosk pulls a diff on a version bump.
- Fields Square can't express (kiosk-only hero images, sort order, "recommended" flags, translations, upsell rules) live in our DB, keyed by Square catalog ID — never a second source of truth for price.
- Sold-out: Square inventory `NONE`/tracked-zero → grey out; plus a manual 86 toggle in the admin console that propagates in seconds.

### 4.3 Order + payment flow (Terminal API path)
1. Kiosk builds cart → `POST /orders` on our backend.
2. Backend `CreateOrder` in Square (location = branch, source = "Tea Hut Kiosk", line items with variation + modifier IDs, taxes/discounts, `fulfillment` = PICKUP with the customer's name/number, `reference_id` = our order number). Idempotency key = our order UUID.
3. Backend `CreateTerminalCheckout` → `device_id` of the paired Terminal, amount = order total, `DeviceCheckoutOptions` (tip screen on/off, skip receipt screen, `collect_signature: false`).
4. Kiosk shows "Please pay on the card reader →" with a live countdown and a **Cancel** button (`CancelTerminalCheckout`).
5. `terminal.checkout.updated` webhook (with polling as a belt-and-braces fallback) → on `COMPLETED`, backend pays the order (`PayOrder`) → order becomes a real, paid Square order → flows to KDS / kitchen printer / Square reporting automatically.
6. Kiosk shows order number + prints/sends receipt, returns to the attract screen.
7. Failure paths: declined → retry or choose another tender; timeout → auto-cancel and release; kiosk crash mid-payment → backend reconciles on reconnect using the checkout ID.

**Terminal pairing:** admin console → `CreateDeviceCode` for the branch → 5-minute code entered on the Terminal → `device.code.paired` webhook returns the permanent `device_id`, which we bind to that kiosk record. Re-pair is a two-tap operation for staff.

### 4.4 Alternate tenders (all optional toggles per branch)
- **Cash / pay at counter** — order created as unpaid/OPEN, ticket prints, customer pays a cashier on Square POS. Good day-one fallback while the Terminal is being set up.
- **QR pay on phone** — backend creates a Square payment link, kiosk shows a QR; customer pays on their own phone. Zero extra hardware; also the disaster fallback if a Terminal dies.
- **Square gift card** — scan barcode on the Terminal or key in.
- **Mobile Payments SDK + Square Reader on the TV itself** — *not recommended*: Square restricts this to **attended** kiosks (in line of sight of trained staff, inaccessible outside business hours) and requires Play Services + a supported device. Revisit only if hardware validation passes and you want a single-screen unit.

---

## 5. Accounts, branches & device identity

**Roles**
| Role | Can do |
|---|---|
| Owner | Connect/disconnect Square, create accounts, all branches |
| Manager | Their branch: menu overrides, 86 items, kiosk settings, view orders, pair Terminal |
| Staff | Unlock kiosk (exit to home / refund-free admin actions), start/stop kiosk mode |

**Flow on a fresh kiosk**
1. App launches → **Login** (email + password, or a short staff PIN after the first login on that device).
2. **Select branch** — list of Square locations the account is allowed to serve.
3. **Select/pair Terminal** for that branch.
4. Device registers itself → backend issues a **device token** (long-lived, revocable, scoped to that one branch); the staff session ends. From then on the kiosk boots straight into the attract screen with no login — even after a power cut.
5. Exiting kiosk mode requires a manager PIN + a hidden gesture (5-tap corner), matching how Chowbus/MenuSifu do it.

Device registry in the admin console: name ("Tea Hut Flushing #2"), branch, Terminal ID, app version, last seen, battery/network, remote reboot + remote unpair.

---

## 6. Feature list

Legend: **M** = MVP (launch) · **P1** = fast follow · **P2** = later

### 6.1 Customer ordering
| # | Feature | Pri |
|---|---|---|
| 1 | Attract / idle screen: looping video or promo images, "Tap to Order", auto-return after 45s idle | M |
| 2 | Language picker — **English / 中文 / Español** (persisted per session, resets each order) | M |
| 3 | Order type: **Here / To Go** (drives Square fulfillment + tax where applicable) | M |
| 4 | Category rail + item grid, large photos, portrait layout, thumb-reachable | M |
| 5 | Item detail: photo, description, calories/allergen note, size (variation) picker | M |
| 6 | **Drink customization**: ice level, sugar level, toppings (multi-select w/ max), milk swap, hot/cold, temperature — each priced, each validated against Square modifier min/max | M |
| 7 | Quantity stepper, per-item "special request" note (free text → Square line-item note) | M |
| 8 | Cart drawer: edit / remove / re-customize, live subtotal | M |
| 9 | **Upsell prompts**: "Add a topping?" on item add, "Popular with your order" before checkout | P1 |
| 10 | Combos / set meals (drink + snack bundle pricing) | P1 |
| 11 | Search + "Best sellers" / "New" / "Recommended" merchandising rows | P1 |
| 12 | Sold-out / 86'd items greyed with a reason badge | M |
| 13 | Customer name or nickname for the order (for call-out) | M |
| 14 | Phone number capture → SMS "your drink is ready" | P1 |
| 15 | Item nutrition / allergen sheet | P2 |
| 16 | Accessibility: high-contrast mode, larger-text mode, a reachable "lower the UI" ADA button for wheelchair height | P1 |

### 6.2 Checkout & payment
| # | Feature | Pri |
|---|---|---|
| 17 | Order review: line items with all modifiers spelled out, tax, total | M |
| 18 | Promo code entry → Square discount | P1 |
| 19 | **Tip prompt** (configurable %, on the Terminal or on-screen, skippable) | M |
| 20 | Pay via **Square Terminal** — tap / chip / swipe / Apple Pay / Google Pay | M |
| 21 | Cash / pay-at-counter fallback | M |
| 22 | QR pay-on-phone fallback | P1 |
| 23 | Square **gift card** redemption | P1 |
| 24 | **Loyalty**: phone-number enrollment + point accrual + reward redemption (Square Loyalty) | P1 |
| 25 | Decline / timeout / cancel handling with clear recovery copy in all 3 languages | M |
| 26 | Receipt options: print, email, SMS, or none | M |
| 27 | Order-number confirmation screen + optional QR to track status | M |
| 28 | Split payment / multiple tenders | P2 |

### 6.3 Kitchen & store operations
| # | Feature | Pri |
|---|---|---|
| 29 | Orders land in Square as normal orders → **Square KDS / kitchen printer** with no extra work | M |
| 30 | Direct ESC/POS ticket printing from the kiosk as a backup path | P1 |
| 31 | Order source tagged "Kiosk #N" so reporting can split kiosk vs counter | M |
| 32 | Daily kiosk sales summary in the admin console (count, AOV, top items, attach rate of toppings) | P1 |
| 33 | Customer-facing "now serving / ready" board (second screen or same TV when idle) | P2 |

### 6.4 Admin & fleet management
| # | Feature | Pri |
|---|---|---|
| 34 | Staff accounts, roles, password reset, per-branch permissions | M |
| 35 | Branch (Square location) mapping and selection | M |
| 36 | Square connect / reconnect / health indicator with token-expiry alerting | M |
| 37 | Kiosk registry: online status, app version, last order, remote reboot | M |
| 38 | Menu overrides: hero images, sort order, translations, hide item, 86 toggle | M |
| 39 | Per-kiosk settings: tip prompt, idle timeout, languages enabled, tenders enabled | M |
| 40 | Attract-screen media upload (images/video) per branch | P1 |
| 41 | Remote config push without an app update | P1 |
| 42 | Audit log (who changed what, who exited kiosk mode) | P1 |

### 6.5 Platform / reliability
| # | Feature | Pri |
|---|---|---|
| 43 | **Kiosk lockdown**: Device Owner + LockTask mode — no status bar, no home/recents, no other apps | M |
| 44 | Auto-launch on boot, watchdog restart on crash, screen-always-on | M |
| 45 | **Offline mode**: browse + build a cart from the local menu cache; queue unpaid orders; block card payment while offline with a clear message | M |
| 46 | Idempotency everywhere (no double-charge, no duplicate order on retry) | M |
| 47 | Crash/ANR reporting + remote logs (Sentry or self-hosted) | M |
| 48 | OTA app updates (private Play channel or self-hosted APK + silent install as Device Owner) | P1 |
| 49 | Health heartbeat + alert if a kiosk goes dark for >10 min during store hours | P1 |
| 50 | Auto-recovery: nightly restart at 4am, cache re-sync at open | P1 |

---

## 7. Screen flow

```
Attract ──tap──▶ Language ──▶ Here/To Go ──▶ Menu ──tap item──▶ Item Detail
                                                │                    │
                                                │                add to cart
                                                ▼                    │
                                              Cart ◀─────────────────┘
                                                │
                                             Checkout (review, promo, loyalty, tip)
                                                │
                                       ┌────────┴────────┐
                                   Card on Terminal   Cash / QR
                                       └────────┬────────┘
                                                ▼
                                    Confirmation (order #, receipt) ──30s──▶ Attract
```
Every screen: a persistent "Start Over" and a language toggle; every screen auto-returns to Attract after 60s of inactivity (with a 15s "Are you still there?" countdown that preserves the cart if tapped).

---

## 8. Data model (backend, abbreviated)

```
merchant(id, square_merchant_id, access_token_enc, refresh_token_enc, expires_at, status)
branch(id, merchant_id, square_location_id, name, timezone, settings_json)
user(id, email, password_hash, role, created_at)
user_branch(user_id, branch_id)
kiosk(id, branch_id, name, device_token_hash, terminal_device_id, app_version, last_seen_at, settings_json)
catalog_cache(branch_id, square_version, payload_json, synced_at)
menu_override(branch_id, square_object_id, hidden, sold_out, sort, image_url, i18n_json)
kiosk_order(id, kiosk_id, branch_id, square_order_id, square_checkout_id, state, total, created_at)
audit_log(id, actor, action, target, meta_json, at)
```

---

## 9. Security & PCI

- Card data never touches the kiosk or our backend — the Square Terminal is a validated P2PE device. Keeps us in the lightest possible PCI scope.
- Square tokens: encrypted at rest, server-side only, rotated, revocable.
- Kiosk holds only a revocable device token scoped to one branch.
- TLS + certificate pinning on the kiosk; no debug builds in the field.
- Kiosk mode prevents customers from reaching settings, browser, or files.
- No customer PII on the device beyond the current in-progress order; phone/email go straight to Square/our backend and are cleared on completion.

---

## 10. Build plan

| Phase | Scope | Est. |
|---|---|---|
| **0. Validate** | Hardware checklist, Square sandbox app, confirm Terminal API on a real Terminal, confirm the TV runs a Compose app in lock-task mode | 3–5 days |
| **1. Backend core** | Auth + roles, Square OAuth + token refresh, locations, catalog sync, device registry | 1.5–2 wks |
| **2. Kiosk MVP** | Attract → menu → customization → cart → checkout → Terminal payment → confirmation; offline cache; kiosk lockdown | 3–4 wks |
| **3. Ops** | Admin console (menu overrides, 86, kiosk settings, Terminal pairing), receipts, reporting | 1.5–2 wks |
| **4. Pilot** | One kiosk in one Tea Hut store, 2 weeks of live tuning, staff training, runbook | 2 wks |
| **5. Fast-follow** | Loyalty, gift cards, upsell, combos, SMS-ready, QR pay, OTA | 2–3 wks |

**Rough total to a live pilot: ~8–10 weeks of one full-time developer.** MVP-only (phases 0–2 + minimal admin) can be live in ~6 weeks if we accept manual menu setup.

---

## 11. Open questions for you

1. **Square Terminal** — does Tea Hut already have one per store, or do we budget one per kiosk (~$299 each)?
2. **How many branches and how many kiosks per branch** at launch?
3. **Receipts** — do you want a printer at the kiosk, or is an order number on-screen + SMS/email enough? (Skipping the printer removes a whole class of jams and paper-outs.)
4. **Loyalty** — is Square Loyalty already running at Tea Hut, or is that new?
5. **Tips at a kiosk** — on or off? (Boba kiosks are split; off is a smoother flow, on is real money.)
6. **Languages** — is English + Chinese enough for v1, or is Spanish needed day one?
7. **The exact TV model** — send me the make/model and I'll verify it against the checklist in §2 before we commit to it.
8. **Menu photography** — do we have per-item photos already in Square, or does that need to happen? (Kiosk conversion lives and dies on the photos.)

---

## 12. Blockers on my side

- The **Square MCP connector in this session is not authorized**, so I can't inspect the live Tea Hut catalog or locations yet. Authorize it in your claude.ai connector settings when you want me to pull the real menu structure.
- `developer.squareup.com` is blocked by this environment's network proxy, so API details above come from Square's published docs via search plus general knowledge. Any exact request/response shapes will be verified against the SDK during Phase 0.

---

## Sources
- [Square Mobile Payments SDK](https://developer.squareup.com/docs/mobile-payments-sdk) · [Build on Android](https://developer.squareup.com/docs/mobile-payments-sdk/android) — attended-kiosk restriction, API 28+
- [Square Terminal API overview](https://developer.squareup.com/docs/terminal-api/overview) · [POS pairing](https://developer.squareup.com/docs/terminal-api/pos-integration) — device codes, `device_id`, `DEVICE_CREDENTIAL_MANAGEMENT`
- [Square OAuth: refresh, revoke, limit scope](https://developer.squareup.com/docs/oauth-api/refresh-revoke-limit-scope) · [OAuth best practices](https://developer.squareup.com/docs/oauth-api/best-practices) — 30-day access tokens, code-flow refresh tokens valid until revoked
- [Square Catalog API: modifiers](https://developer.squareup.com/docs/catalog-api/enable-modifiers-on-items) · [item options](https://developer.squareup.com/docs/catalog-api/item-options)
- [Chowbus restaurant kiosk](https://www.chowbus.com/hardware/restaurant-kiosk) · [MenuSifu boba kiosk features](https://www.menusifu.com/blog/boba-shop-kiosk-system) · [MenuSifu kiosk hardware](https://www.menusifu.com/hardware/restaurant-kiosk) — reference feature set
- [KioskBuddy ↔ Square Terminal](https://www.kioskbuddy.app/help/square-terminal) · [Sending kiosk orders to Square POS](https://www.kioskbuddy.app/help/square-orders) — proof the Terminal API path works in production
