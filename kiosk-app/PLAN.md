# Tea Hut Self-Order Kiosk — Product & Technical Plan

**Status:** Draft v2 — for review, nothing built yet
**Target:** Android touchscreen ("incell" smart portable TV), in-store, Tea Hut branches only
**Canvas:** **1080 × 1920 portrait**, locked orientation
**Stack:** Kotlin + Jetpack Compose (app) · TypeScript/Node + Postgres (backend) · TypeScript/React (admin)
**Backend of record:** Square (catalog, orders, payments, locations, loyalty)
**Reference UX:** Chowbus POS kiosk (primary visual target), MenuSifu kiosk (bubble-tea flow)

---

## 0. Read this first — three decisions that shape everything

| # | Decision | Recommendation | Why it matters |
|---|---|---|---|
| 1 | **How does the customer pay?** | Card, on **Square hardware** — confirmed. Primary path is the **Terminal API**: a Square Terminal mounted next to the TV takes the card and the TV never touches card data. | Square **prohibits** the Mobile Payments SDK (a Square Reader puck paired to our own Android app) in *unattended* kiosks and allows *attended* ones only under strict conditions; it also needs Google Play Services and a validated device that a generic portable TV will likely fail. Terminal API is plain HTTPS, so it works on any Android screen. See §4.3a for the Reader alternative. |
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
- Android touchscreen "portable TV", 21"–32", **1080 × 1920 portrait**, Android 9 (API 28)+ — *must be verified, see checklist*
- Square Terminal (payment), mounted at reachable height
- Optional: receipt printer (network ESC/POS, e.g. Epson TM-m30 LAN) — or skip printing, use SMS/email receipts + a number-call screen
- Wi-Fi or Ethernet, PoE preferred; always-on power, surge protected

**Hardware validation checklist (do this before writing app code — 1 day)**
- [ ] Confirm it is real Android (not a Linux/RTOS "smart TV" shell) — `adb shell getprop ro.build.version.release`
- [ ] `adb` over USB or network is enabled (needed for kiosk provisioning)
- [ ] Touch is multi-touch capacitive, and reports as a touchscreen (not a mouse pointer)
- [ ] Screen orientation can be locked to portrait; app renders 1080 × 1920 even if the panel reports 1920 × 1080 landscape natively
- [ ] Reported `densityDpi` and `WindowMetrics` — needed to pin the design-pixel scale (see §6)
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

### Languages & stack (decided)

| Layer | Language / framework | Why |
|---|---|---|
| **Kiosk app** | **Kotlin + Jetpack Compose** (single-activity, MVVM, Room for the menu cache, WorkManager for the offline queue) | Native gets us the Chowbus feel — big photo cards, sliding modifier sheets, animated cart badge, 60fps scroll — without fighting a WebView's touch and scroll behavior. It also puts the kiosk-critical APIs (Device Owner / lock-task, boot receiver, ESC/POS printing, watchdog) directly in reach instead of behind a bridge. Fewer moving parts on a device that runs 14 hours a day unattended. |
| **Backend** | **TypeScript on Node (Fastify)** + **Postgres** + Redis | Square's TypeScript SDK is the best-maintained of the official set, and the types are shared with the admin console. (Python/FastAPI is an equally fine choice if you have a Python-shop preference — Square ships an SDK for it too.) |
| **Admin console** | **TypeScript + React** | Shares API types with the backend; nothing exotic needed. |
| **Display languages** | English + 中文 at launch, Español behind a config toggle | Matches the Chowbus/MenuSifu multilingual kiosk pattern. |

**Rejected alternatives:** React Native / Flutter (would need native bridges for exactly the parts that matter most — kiosk lockdown, printing, boot behavior — while adding a runtime; reconsider only if an iPad version becomes a requirement) and a WebView/PWA shell (touch latency, scroll jank on cheap Android SoCs, and no clean path to lock-task mode).

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

### 4.3a If "Square card reader" means the Reader puck, not the Terminal

Both are "Square card readers" and the difference is not cosmetic:

| | **Square Terminal** (recommended) | **Square Reader** (contactless/chip puck) |
|---|---|---|
| Integration | Terminal API — plain HTTPS from our backend | Mobile Payments SDK — runs **inside** the Android app |
| Device requirements on the TV | None. Any Android screen works. | Play Services, API 28+, and a device Square supports |
| Kiosk usage | Permitted | **Attended kiosks only** — must be in a worker's line of sight, inaccessible outside business hours, staff trained to assist |
| PCI scope | Lightest — card data never reaches our code | Still light, but the SDK lives in our app |
| Hardware cost | ~$299/kiosk | ~$59/kiosk |
| Risk | Second small screen at the station | Real chance the portable TV simply can't run the SDK |

A Tea Hut kiosk inside the store during business hours would likely qualify as *attended*, so the Reader is not off the table — but it hinges entirely on whether that specific TV passes Square's device requirements, which we can't know until §2's hardware validation runs. **Plan of record: build the payment layer behind one internal interface (`PaymentProcessor`) with the Terminal API as the first implementation.** If hardware validation clears the Reader, adding it is a contained piece of work, not a rewrite.

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

## 6. UI/UX spec — 1080 × 1920 portrait, Chowbus-style

### 6.1 Pixel strategy
The panel is a fixed, known size, so we design in **literal pixels** rather than guessing at dp. At startup the app overrides Compose's density so that **1 design px = 1 physical px** on a 1080-wide screen:

```kotlin
CompositionLocalProvider(
    LocalDensity provides Density(
        density = windowWidthPx / 1080f,       // 1.0 on the target panel
        fontScale = 1f                          // ignore system font scaling
    )
) { KioskApp() }
```

Everything below is then specified as exact numbers, and the same build still scales cleanly onto a tablet or a different panel later. Orientation is pinned `portrait` in the manifest; if the panel reports 1920 × 1080 landscape natively, we rotate at the app level and it renders 1080 × 1920 regardless.

### 6.2 Global layout grid (menu screen — the Chowbus signature)

```
 0 ┌────────────────────────────────────────────┐  y=0
   │  HEADER  160px                             │  logo · language pill · Here/To-Go · Start Over
160├──────────┬─────────────────────────────────┤
   │          │                                 │
   │ CATEGORY │   ITEM GRID                     │  2 columns × 400px cards, 20px gutter
   │  RAIL    │   x: 260 → 1060                 │  card: 400w × 440h
   │  240px   │   scrolls vertically            │    image 400×260 (WebP, rounded 24)
   │  icons + │                                 │    name 36px semibold, 2 lines max
   │  labels  │   sticky category headers       │    price 34px + circular "+" 88×88
   │  sticky  │                                 │
   │  active  │                                 │
   │  pill    │                                 │
1640├──────────┴─────────────────────────────────┤
   │  CART BAR  280px                           │  qty badge · subtotal 44px · CHECKOUT pill 520×120
1920└────────────────────────────────────────────┘
```

- **Header (160px):** Tea Hut logo left; language pill (EN / 中文) and Here/To-Go segmented control right; "Start Over" as a text button, deliberately low-contrast so it isn't tapped by accident.
- **Category rail (240px):** vertical, icon + label, sticky highlight pill on the active category, scroll-synced with the grid. This left-rail-plus-grid split *is* the Chowbus kiosk layout and is what makes a 40-item boba menu navigable without paging.
- **Item grid:** two columns is the right density at 1080px — a third column drops cards under the 320px width where photos stop selling. Sticky category headers as you scroll.
- **Cart bar (280px):** always visible, never collapses. Item count badge, running subtotal, and one unmissable CHECKOUT button. Empty state shows a muted "Your cart is empty" instead of hiding.

### 6.3 Item detail (the customization sheet)
Full-screen modal sliding up over the menu in 250ms:

```
hero image      1080 × 720   (full-bleed, close "×" at 88×88 top-right)
name + price    36px padding, title 56px, price 44px
description     32px, muted, 3 lines max
─────────────────────────────────────────
SIZE            required · chips 320×112, selected = filled
ICE LEVEL       required · chips
SUGAR LEVEL     required · chips
TOPPINGS        optional, max N · rows 120px w/ checkbox + price delta
MILK OPTION     optional · rows
SPECIAL REQUEST tap to open keyboard
─────────────────────────────────────────
sticky footer   200px · qty stepper (−  2  +) · ADD TO CART · $6.75
```

- Required groups are enforced from Square's modifier `min/max` — the Add button stays disabled with an inline "Choose a size" hint until they're satisfied, and the sheet auto-scrolls to the first unsatisfied group when they try.
- Price in the footer updates live as modifiers are tapped. This one detail is why kiosk topping attach-rates beat counter ordering.
- Chip-per-choice (not dropdowns) for ice/sugar — one tap, no hidden state, works with a fingertip.

### 6.4 Design tokens
| Token | Value |
|---|---|
| Type scale (px) | display 64 · title 56 · section 44 · body 36 · caption 28 |
| Min touch target | 96 × 96 px, 32px minimum spacing between targets |
| Corner radius | cards 24 · chips 56 (pill) · buttons 60 (pill) |
| Screen padding | 40px left/right inside the grid area |
| Motion | 200ms for state, 250ms for sheets, ease-out; no motion longer than 300ms |
| ADA reach band | all primary actions between y=900 and y=1500 so a seated user can reach them |
| Contrast | 4.5:1 minimum on all text; high-contrast mode swaps the palette |
| Palette | Tea Hut brand colors — **needs your logo/brand file**; placeholder warm-neutral + single accent until then |

### 6.5 Assets
- Item photos: 800 × 520 source, delivered as WebP, preloaded into the Coil disk cache during menu sync so the grid never shows a spinner.
- Attract loop: 1080 × 1920 H.264 video or a still image carousel, uploaded per branch from the admin console.
- Every image has a branded placeholder — a menu item with no photo must never render an empty box.

---

## 7. Feature list

Legend: **M** = MVP (launch) · **P1** = fast follow · **P2** = later

### 7.1 Customer ordering
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

### 7.2 Checkout & payment
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

### 7.3 Kitchen & store operations
| # | Feature | Pri |
|---|---|---|
| 29 | Orders land in Square as normal orders → **Square KDS / kitchen printer** with no extra work | M |
| 30 | Direct ESC/POS ticket printing from the kiosk as a backup path | P1 |
| 31 | Order source tagged "Kiosk #N" so reporting can split kiosk vs counter | M |
| 32 | Daily kiosk sales summary in the admin console (count, AOV, top items, attach rate of toppings) | P1 |
| 33 | Customer-facing "now serving / ready" board (second screen or same TV when idle) | P2 |

### 7.4 Admin & fleet management
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

### 7.5 Platform / reliability
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

## 8. Screen flow

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

## 9. Data model (backend, abbreviated)

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

## 10. Security & PCI

- Card data never touches the kiosk or our backend — the Square Terminal is a validated P2PE device. Keeps us in the lightest possible PCI scope.
- Square tokens: encrypted at rest, server-side only, rotated, revocable.
- Kiosk holds only a revocable device token scoped to one branch.
- TLS + certificate pinning on the kiosk; no debug builds in the field.
- Kiosk mode prevents customers from reaching settings, browser, or files.
- No customer PII on the device beyond the current in-progress order; phone/email go straight to Square/our backend and are cleared on completion.

---

## 11. Build plan

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

## 12. Open questions for you

1. **Which Square reader, exactly?** — a **Square Terminal** (handheld with its own screen, ~$299) or a **Square Reader** puck (~$59)? See §4.3a; it decides whether payment runs over HTTPS from the backend or inside the app, and the Reader path is contingent on the TV passing Square's device requirements. Also: does Tea Hut already own hardware, or is it being bought per kiosk?
2. **How many branches and how many kiosks per branch** at launch?
3. **Receipts** — do you want a printer at the kiosk, or is an order number on-screen + SMS/email enough? (Skipping the printer removes a whole class of jams and paper-outs.)
4. **Loyalty** — is Square Loyalty already running at Tea Hut, or is that new?
5. **Tips at a kiosk** — on or off? (Boba kiosks are split; off is a smoother flow, on is real money.)
6. **Languages** — is English + Chinese enough for v1, or is Spanish needed day one?
7. **The exact TV model** — send me the make/model and I'll verify it against the checklist in §2 before we commit to it. Confirm too that **1920 is the tall dimension** (portrait), which is what §6 is designed against.
8. **Menu photography** — do we have per-item photos already in Square, or does that need to happen? (Kiosk conversion lives and dies on the photos.)
9. **Tea Hut brand assets** — logo, brand colors, and any font. §6.4 has a placeholder palette until these land.

---

## 13. Blockers on my side

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
