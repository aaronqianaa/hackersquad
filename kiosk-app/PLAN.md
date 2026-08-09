# Tea Hut Self-Order Kiosk — Product & Technical Plan

**Status:** Draft v3 — for review, nothing built yet
**Target:** Android touchscreen ("incell" smart portable TV), in-store, Tea Hut branches only
**Canvas:** **1080 × 1920 portrait**, locked orientation, no logo
**Payment:** Square Reader on the kiosk (Mobile Payments SDK); staff Square Terminal at the counter receives orders
**Stack:** Kotlin + Jetpack Compose (app) · TypeScript/Node + Postgres (backend) · TypeScript/React (admin)
**Backend of record:** Square (catalog, orders, payments, locations, loyalty)
**Reference UX:** Chowbus POS kiosk (primary visual target), MenuSifu kiosk (bubble-tea flow)

---

## 0. Read this first — three decisions that shape everything

| # | Decision | Recommendation | Why it matters |
|---|---|---|---|
| 1 | **How does the customer pay?** | **Square Reader attached to the kiosk**, driven by the **Mobile Payments SDK** inside our app — decided. The staff **Square Terminal** is a separate counter device for receiving and working orders, not part of the kiosk payment path. | This is a supported configuration *provided the kiosk stays attended* (inside the store, in staff line of sight, during business hours) — see §4.3a for the three conditions. It also means the SDK's device requirements become a **hard gate** on the TV in Phase 0, and a scoped Square token now lives on the device (§4.3 covers how that's contained). Payment sits behind a `PaymentProcessor` interface so a fallback stays a swap, not a rewrite. |
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
- Android touchscreen "portable TV", 21"–32", **1080 × 1920 portrait**, Android 9 (API 28)+ — *must pass the gate below*
- **Square Reader (contactless + chip)**, mounted at the kiosk at reachable height, **wired to the TV if the port allows** (preferred over Bluetooth LE: no pairing drift, no battery to die mid-shift). If BLE-only, use the charging dock and keep it permanently powered.
- Optional: receipt printer (network ESC/POS, e.g. Epson TM-m30 LAN) — or skip printing, use SMS/email receipts + a number-call screen
- Wi-Fi or Ethernet, PoE preferred; always-on power, surge protected

**At the counter (existing, not per-kiosk):** the staff **Square Terminal**, which receives kiosk orders the same way it receives counter orders.

**Phase 0 hardware gate — do this on the real TV before any app code is written (1 day)**

*Blocking — a failure here means changing the panel, not changing the plan:*
- [ ] **Mobile Payments SDK runs and authorizes on this device.** Square does not support rooted devices, custom ROMs, or OEM devices that break its security rules, and recommends major manufacturers. Off-brand TV firmware is the real risk. Test with the SDK's sample app before anything else.
- [ ] **Google Play Services present and current** — required by the SDK.
- [ ] Android **API 28+**, not rooted, stock-enough ROM
- [ ] **Square Reader connects** — wired if possible, else BLE pairs and holds a connection for a full day
- [ ] Bluetooth (for BLE readers) and the required runtime permissions can be granted and stay granted

*Non-blocking but shapes the build:*
- [ ] Confirm it is real Android (not a Linux/RTOS "smart TV" shell) — `adb shell getprop ro.build.version.release`
- [ ] `adb` over USB or network is enabled (needed for kiosk provisioning)
- [ ] Touch is multi-touch capacitive, and reports as a touchscreen (not a mouse pointer)
- [ ] Screen orientation can be locked to portrait; app renders 1080 × 1920 even if the panel reports 1920 × 1080 landscape natively
- [ ] Reported `densityDpi` and `WindowMetrics` — needed to pin the design-pixel scale (see §6)
- [ ] Device Owner provisioning possible (`dpm set-device-owner`) — required for true kiosk lockdown
- [ ] Screen never sleeps on AC power; auto-boots when power is restored

**If it fails the gate:** a commodity Samsung/Lenovo Android tablet in a floor stand runs the same app with zero code change, and is on the hardware Square actually recommends. Second fallback is the Terminal API path (§4.3a).

---

## 3. Architecture

```
┌──────────────────────────┐         ┌────────────────────────┐        ┌──────────────┐
│  Kiosk App (Android)     │  HTTPS  │   Tea Hut Backend      │ HTTPS  │  Square APIs │
│  Kotlin + Compose        │────────▶│   (our server)         │───────▶│  Catalog     │
│  + Mobile Payments SDK   │◀────────│                        │◀───────│  Orders      │
│                          │  device │  • staff accounts      │ OAuth  │  Payments    │
│  • menu cache (local DB) │  JWT +  │  • Square OAuth tokens │ tokens │  Locations   │
│  • cart / customization  │ scoped  │  • scoped token minting│        │  Loyalty     │
│  • order submit          │ payment │  • catalog sync + cache│        │  Webhooks    │
│  • SDK payment + reader  │  token  │  • order orchestration │        │              │
│  • offline queue         │         │  • device registry     │        │              │
└──────────────────────────┘         └────────────────────────┘        └──────────────┘
     │              │                          ▲
     │ USB / BLE    │ local net                │ webhooks (payment.updated,
     ▼              ▼                          │ catalog.version.updated)
┌──────────┐  ┌──────────┐                     │
│ Square   │  │ Receipt  │                     │        ┌──────────────────────┐
│ Reader   │  │ printer  │                     └────────│ Staff Square Terminal│
│ (chip/   │  │ (opt.)   │                       orders │ at the counter —     │
│  tap)    │  │          │                       land   │ receives & works     │
└──────────┘  └──────────┘                       here   │ kiosk orders         │
                                                        └──────────────────────┘
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

7. **Always persist the `refresh_token` returned by each `ObtainToken` call** and alert on any refresh failure. Square documents code-flow refresh tokens as valid until revoked, but the safe implementation never assumes the old one survives.

**OAuth scopes needed:** `MERCHANT_PROFILE_READ`, `ITEMS_READ`, `INVENTORY_READ`, `ORDERS_READ`, `ORDERS_WRITE`, `PAYMENTS_READ`, `PAYMENTS_WRITE`, **`PAYMENTS_WRITE_IN_PERSON`** (required by the Mobile Payments SDK), `CUSTOMERS_READ/WRITE` (loyalty), `LOYALTY_READ/WRITE`, `GIFTCARDS_READ`.

### 4.2 Menu (Catalog API)
- Backend pulls the full catalog per location and caches it: categories → items → **variations** (sizes) → **modifier lists** (ice, sugar, toppings, milk swap) → images → taxes.
- Bubble-tea mapping: **size = item variation** (M/L), **ice / sugar / topping = modifier lists** with min/max selection rules. Toppings priced per modifier.
- Incremental re-sync every 10 min + on `catalog.version.updated` webhook; kiosk pulls a diff on a version bump.
- Fields Square can't express (kiosk-only hero images, sort order, "recommended" flags, translations, upsell rules) live in our DB, keyed by Square catalog ID — never a second source of truth for price.
- Sold-out: Square inventory `NONE`/tracked-zero → grey out; plus a manual 86 toggle in the admin console that propagates in seconds.

### 4.3 Order + payment flow (Square Reader + Mobile Payments SDK) — **decided**

Payment happens on a **Square Reader attached to the kiosk**, driven by the **Mobile Payments SDK inside our Android app**. The staff's Square Terminal is a separate device used at the counter to receive and work orders — it is not in the kiosk's payment path.

**Authorizing the SDK (on every app start)**
1. Kiosk authenticates to our backend with its device token.
2. Backend calls `ObtainToken` with `grant_type=refresh_token` **and a narrowed `scopes` list** — `MERCHANT_PROFILE_READ`, `PAYMENTS_WRITE`, `PAYMENTS_WRITE_IN_PERSON` only — producing a payments-only access token for that device. The full-scope token never leaves the server.
3. Backend returns `{access_token, location_id}` over TLS; kiosk stores it in the Android **Keystore / EncryptedSharedPreferences**, never in plain prefs or logs.
4. Kiosk calls `AuthorizationManager.authorize(accessToken, locationId)`. On unpair, remote wipe, or branch change → `deauthorize()` and the backend revokes the token.
5. Token is re-minted well before its 30-day expiry, and on any authorization error.

> This is the one real cost of the Reader path: a Square access token now lives on a device in a public room. Narrow scope + Keystore + per-device revocation reduce that to "someone who physically opens the device could take payments for Tea Hut" — which is the same thing they could do by picking up the reader.

**Reader pairing**
- The SDK's `ReaderManager` handles pairing; `settingsManager.showSettings()` gives a prebuilt reader-management screen we expose behind the manager PIN.
- Square Reader (contactless + chip) connects over **Bluetooth LE**, or **wired to Android** — prefer the wired/docked connection for a fixed kiosk: no pairing drift, no battery.
- App monitors reader state continuously; a disconnected or low-battery reader raises a fleet alert *and* auto-hides card payment on the kiosk rather than failing a customer mid-checkout.

**Taking a payment**
1. Kiosk builds cart → `POST /orders` on our backend.
2. Backend `CreateOrder` in Square (location = branch, source = "Tea Hut Kiosk", line items with variation + modifier IDs, taxes/discounts, `fulfillment` = PICKUP with the customer's name/number, `reference_id` = our order number). Idempotency key = our order UUID. Returns `order_id` + total.
3. Kiosk shows its own tip screen (if enabled), then calls the SDK's `startPaymentActivity` with `PaymentParameters`: amount, `orderId`, `referenceId`, `tipMoney`, `autocomplete = true`, idempotency key = our order UUID.
4. Reader prompts: **tap / insert / Apple Pay / Google Pay**. The SDK owns this UI; our app shows a matching full-screen "Tap or insert your card" state with a Cancel button.
5. Success callback → payment is attached to the order → the order is paid and flows to the **staff Square Terminal**, KDS, kitchen printer, and Square reporting automatically.
6. Kiosk shows the order number + receipt options, returns to attract.
7. Failure paths: declined → retry or switch tender; canceled → back to cart with the cart intact; **app killed mid-payment** → on relaunch the kiosk asks the backend to reconcile by idempotency key before ever re-charging.

**Non-negotiable rule:** the idempotency key is the order UUID, generated once when the cart is submitted and reused on every retry. Double-charging a customer at an unattended screen is the worst failure this system can have.

### 4.3a Operating conditions this choice commits Tea Hut to

Square permits the Mobile Payments SDK **only in attended kiosks**. All three conditions must hold, and they are operational, not technical:

- [ ] The kiosk **cannot be physically reached by customers outside business hours** (inside the locked store, or shuttered).
- [ ] It is **in the line of sight** of a staff member during business hours.
- [ ] Staff are **trained to assist** customers with payment problems.

An in-store Tea Hut kiosk meets all three, so this is a supported configuration. Worth stating plainly because it rules out a vestibule kiosk, a 24-hour lobby, or an outdoor window later without revisiting the payment path.

**Also on the risk list — §2's hardware gate is now a hard gate.** Square states the SDK is **not compatible with rooted devices, custom ROMs, or OEM devices that violate its security rules**, and recommends running it on devices from major manufacturers (Google, Samsung). An off-brand "smart portable TV" is a genuine risk of failing exactly this test. We find that out in Phase 0, on real hardware, before anything else is built.

**Contingency if the TV fails the SDK check** (in order of preference): (a) swap the panel for a Samsung/Lenovo Android tablet in a floor stand — same app, no code change; (b) fall back to the Terminal API path with a Square Terminal at the kiosk; (c) QR pay-on-phone. The payment layer sits behind a single `PaymentProcessor` interface precisely so this stays a swap and not a rewrite.

### 4.4 Alternate tenders (all optional toggles per branch)
- **Cash / pay at counter** — order created as unpaid/OPEN; it appears on the staff Square Terminal and the customer pays there. Also the graceful degradation whenever the reader is offline.
- **QR pay on phone** — backend creates a Square payment link, kiosk shows a QR; customer pays on their own phone. Zero extra hardware, and the disaster fallback if a reader dies mid-shift.
- **Square gift card** — keyed/scanned at checkout, or handed to staff at the counter.

---

## 5. Accounts, branches & device identity

**Roles**
| Role | Can do |
|---|---|
| Owner | Connect/disconnect Square, create accounts, all branches |
| Manager | Their branch: menu overrides, 86 items, kiosk settings, view orders, pair/unpair the reader |
| Staff | Unlock kiosk (exit to home / refund-free admin actions), start/stop kiosk mode |

**Flow on a fresh kiosk**
1. App launches → **Login** (email + password, or a short staff PIN after the first login on that device).
2. **Select branch** — list of Square locations the account is allowed to serve.
3. **Pair the Square Reader** — the SDK's built-in reader settings screen; verify a $0.00 test connection.
4. Device registers itself → backend issues a **device token** (long-lived, revocable, scoped to that one branch) and mints the first scoped payments token; the staff session ends. From then on the kiosk boots straight into the attract screen with no login — even after a power cut — re-authorizing the SDK silently on each start.
5. Exiting kiosk mode requires a manager PIN + a hidden gesture (5-tap corner), matching how Chowbus/MenuSifu do it. Reader settings live behind the same PIN.

Device registry in the admin console: name ("Tea Hut Flushing #2"), branch, **reader serial / connection state / battery**, app version, last seen, network, remote reboot, remote deauthorize + token revoke.

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
   │  HEADER  160px                             │  language pill · Here/To-Go · Start Over  (no logo)
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

- **Header (160px):** **no logo** (per your call). The language pill (EN / 中文) sits left where the logo would go, Here/To-Go segmented control right, and "Start Over" as a low-contrast text button so it isn't tapped by accident. Dropping the logo actually buys back ~240px of horizontal room and lets the header shrink to 140px if we want more grid — worth a look on the real panel.
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
| Palette | No logo, so the UI is **photo-forward**: warm neutral background, near-black text, one accent color used only for price, the "+" button, and CHECKOUT. With no branding to carry the screen, the food photography and the accent do all the work — which raises the bar on photo quality, not lowers it. |

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
| 19 | **Tip prompt** — on-screen, kiosk-owned, configurable %, skippable; passed to the SDK as `tipMoney` | M |
| 20 | Pay via **Square Reader** (Mobile Payments SDK) — tap / chip / Apple Pay / Google Pay | M |
| 20a | **Reader state handling**: connection + battery monitoring, "reconnecting" state, auto-disable card payment when the reader is down instead of failing a customer mid-checkout | M |
| 20b | **Reader pairing & diagnostics screen** behind the manager PIN (SDK's built-in settings UI) | M |
| 20c | **Crash-safe payments**: order-UUID idempotency key, reconcile-before-recharge on relaunch | M |
| 21 | Cash / pay-at-counter fallback (order lands on the staff Square Terminal unpaid) | M |
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
| 29 | Orders land in Square as normal orders → **staff Square Terminal**, KDS, and kitchen printer with no extra work | M |
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
| 37 | Kiosk registry: online status, app version, last order, **reader connection + battery**, remote reboot, remote deauthorize | M |
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

- **Card data is captured and encrypted by the Square Reader and handled entirely by the Mobile Payments SDK.** Our code never sees a PAN and never handles card entry UI. The app is still part of the payment flow, so it stays locked down, signed, and current on SDK versions.
- Square tokens: the **full-scope token lives only on the server**, encrypted at rest, rotated, revocable.
- The kiosk holds (a) a revocable device token scoped to one branch and (b) a **narrowed payments-only Square token** (`MERCHANT_PROFILE_READ`, `PAYMENTS_WRITE`, `PAYMENTS_WRITE_IN_PERSON`) in the Android Keystore, re-minted before expiry and revocable per device from the admin console. No catalog, customer, or reporting access from the device's token.
- Physical security matters more on this path than on the Terminal path: the device is the payment terminal. Kiosk lockdown, no adb in the field, tamper-evident mounting, and one-tap remote deauthorize if a unit goes missing.
- TLS + certificate pinning on the kiosk; no debug builds in the field.
- Kiosk mode prevents customers from reaching settings, browser, or files.
- No customer PII on the device beyond the current in-progress order; phone/email go straight to Square/our backend and are cleared on completion.

---

## 11. Build plan

| Phase | Scope | Est. |
|---|---|---|
| **0. Validate — GATE** | **Run Square's Mobile Payments SDK sample app on the actual TV, authorize it, pair the Reader, take a $1 sandbox payment.** Then the rest of §2's checklist and a Compose app in lock-task mode. *Nothing else starts until this passes.* | 3–5 days |
| **1. Backend core** | Auth + roles, Square OAuth + token refresh, **scoped token minting for devices**, locations, catalog sync, device registry | 1.5–2 wks |
| **2. Kiosk MVP** | Attract → menu → customization → cart → checkout → **Reader payment via MPS** → confirmation; reader state handling; crash-safe idempotency; offline cache; kiosk lockdown | 3–4 wks |
| **3. Ops** | Admin console (menu overrides, 86, kiosk settings, reader diagnostics), receipts, reporting | 1.5–2 wks |
| **4. Pilot** | One kiosk in one Tea Hut store, 2 weeks of live tuning, staff training, runbook | 2 wks |
| **5. Fast-follow** | Loyalty, gift cards, upsell, combos, SMS-ready, QR pay, OTA | 2–3 wks |

**Rough total to a live pilot: ~8–10 weeks of one full-time developer.** MVP-only (phases 0–2 + minimal admin) can be live in ~6 weeks if we accept manual menu setup.

---

## 12. Open questions for you

1. **Which Reader model, and wired or Bluetooth?** — the current Square Reader (contactless + chip) can run wired to Android or over BLE. Wired is strongly preferred for a fixed kiosk. Does the TV expose a usable USB port, and is there a dock/mount in mind?
2. **How many branches and how many kiosks per branch** at launch?
3. **Receipts** — do you want a printer at the kiosk, or is an order number on-screen + SMS/email enough? (Skipping the printer removes a whole class of jams and paper-outs.)
4. **Loyalty** — is Square Loyalty already running at Tea Hut, or is that new?
5. **Tips at a kiosk** — on or off? (Boba kiosks are split; off is a smoother flow, on is real money.)
6. **Languages** — is English + Chinese enough for v1, or is Spanish needed day one?
7. **The exact TV model — now the highest-priority question.** With the Reader path chosen, whether the SDK runs on that firmware decides the whole build. Send me the make/model; better yet, that's the first thing Phase 0 tests on the real unit. Confirm too that **1920 is the tall dimension** (portrait), which is what §6 is designed against.
8. **Menu photography** — do we have per-item photos already in Square, or does that need to happen? With no logo, the photos carry the entire screen, so this went from important to critical.
9. **Accent color** — one color for price, the "+" button, and CHECKOUT. Pick one, or I'll choose a tea-toned default.
10. **Is the kiosk always inside, in staff line of sight, and inaccessible after close?** Confirming §4.3a's three conditions, since the Reader path depends on them.

---

## 13. Blockers on my side

- The **Square MCP connector in this session is not authorized**, so I can't inspect the live Tea Hut catalog or locations yet. Authorize it in your claude.ai connector settings when you want me to pull the real menu structure.
- `developer.squareup.com` is blocked by this environment's network proxy, so API details above come from Square's published docs via search plus general knowledge. Any exact request/response shapes will be verified against the SDK during Phase 0.

---

## Sources
- [Square Mobile Payments SDK](https://developer.squareup.com/docs/mobile-payments-sdk) · [Build on Android](https://developer.squareup.com/docs/mobile-payments-sdk/android) — attended-kiosk restriction, API 28+, no rooted/custom-ROM/non-compliant OEM devices, Bluetooth for contactless readers
- [Authorize your Android application](https://developer.squareup.com/docs/mobile-payments-sdk/android/configure-authorize) — `authorize(accessToken, locationId)`, required `PAYMENTS_WRITE_IN_PERSON`
- [Pair and manage card readers](https://developer.squareup.com/docs/mobile-payments-sdk/android/pair-manage-readers) — `ReaderManager`, `settingsManager.showSettings()`
- [Square OAuth: refresh, revoke, limit scope](https://developer.squareup.com/docs/oauth-api/refresh-revoke-limit-scope) · [OAuth best practices](https://developer.squareup.com/docs/oauth-api/best-practices) — 30-day access tokens, code-flow refresh tokens valid until revoked, `scopes` narrowing on `ObtainToken`
- [Square Terminal API overview](https://developer.squareup.com/docs/terminal-api/overview) — retained as the §4.3a fallback path
- [Square Catalog API: modifiers](https://developer.squareup.com/docs/catalog-api/enable-modifiers-on-items) · [item options](https://developer.squareup.com/docs/catalog-api/item-options)
- [Chowbus restaurant kiosk](https://www.chowbus.com/hardware/restaurant-kiosk) · [MenuSifu boba kiosk features](https://www.menusifu.com/blog/boba-shop-kiosk-system) · [MenuSifu kiosk hardware](https://www.menusifu.com/hardware/restaurant-kiosk) — reference feature set
- [KioskBuddy ↔ Square Terminal](https://www.kioskbuddy.app/help/square-terminal) · [Sending kiosk orders to Square POS](https://www.kioskbuddy.app/help/square-orders) — proof the Terminal API path works in production
