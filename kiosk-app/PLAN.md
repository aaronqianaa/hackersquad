# Tea Hut Self-Order Kiosk — Product & Technical Plan

**Status:** Draft v6 — decisions locked through §12; awaiting Phase 0 hardware
**Target:** **ApoloSign 24" FHD Smart Portable TV Gen2** (Android 16, EDLA-certified, touch, rolling stand), in-store, Tea Hut branches only
**Canvas:** **1080 × 1920 portrait**, locked orientation, no logo
**Payment:** Square Reader on the kiosk (Mobile Payments SDK); staff Square Terminal at the counter receives orders
**Stack:** Kotlin + Jetpack Compose (kiosk) · **Firebase** — Cloud Functions/TS + Firestore + Auth + FCM (backend) · Swift + SwiftUI (manager iOS) · TypeScript/React (owner web)
**Backend of record:** Square (catalog, orders, payments, locations, loyalty) — Firebase caches and orchestrates, never owns prices
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

### 2.1 Confirmed device: ApoloSign 24" Smart Portable TV (Gen2)

| Spec (from listing) | Consequence for us |
|---|---|
| 24" FHD touch, portrait-capable on a rolling stand | Matches the 1080 × 1920 canvas exactly. At 24" FHD (~92 ppi), our 96px touch targets are ≈26mm — generously finger-sized — and the type scale reads well at arm's length. |
| **Android 16** | Way past the SDK's API 28 minimum. It's *new*, so Phase 0 verifies the current Mobile Payments SDK release supports it — a release-notes check, not a rework risk. |
| **EDLA Certified** | The big one. EDLA = Google's Enterprise Devices Licensing Agreement → **licensed, genuine Google Mobile Services**: real Play Services (the SDK's hard dependency), real Play Store (clean OTA path via managed Google Play), and standard Android Enterprise provisioning for Device Owner lockdown. This retires the worst risk of the Reader path — "off-brand TV with fake or missing GMS." |
| 128GB storage | Menu images, attract video, logs — no constraint. |
| **Built-in 5200mAh battery** | Double-edged. Good: rides out power blips, no mid-order blackouts. Bad: an unplugged kiosk *keeps running* and then dies hours later — so the heartbeat must report charging state and alert on "on battery" within minutes, not when it's already dead. Also: permanently-docked Li-ion runs warm; nightly reboot + monitoring covers it. |
| **On wheels** | Operational hazard, not a convenience. It can drift out of staff line-of-sight (an §4.3a attended-kiosk condition) or simply walk off. Lock the casters, position it against the counter, cable-anchor it, and mount the Reader to the stand column — not the bezel. |
| Voice remote + camera | Attack surface in a kiosk. Kiosk mode must ignore remote/BT input (a remote press must never exit lock task), the assistant is disabled under Device Owner policy, and the camera is unused in v1 — physically remove or cover the detachable camera. (Later option: loyalty QR scanning.) |
| Consumer "family dashboard" launcher | Fine — Device Owner provisioning starts from a factory reset and replaces the launcher with our app entirely. Provision via QR/adb before it ever touches the store. |

Also note: ApoloSign is still not a "large manufacturer" in Square's recommended sense (Google/Samsung), so the Phase 0 gate below **stays** — but EDLA + genuine GMS moves it from "real chance of failure" to "expected to pass, verify anyway."

**Per-station hardware**
- ApoloSign 24" Gen2 (above), casters locked, cable-anchored, on AC at all times
- **Square Reader (contactless + chip)**, mounted to the stand column at reachable height — **wired via the TV's USB port if it supplies stable power**, else BLE with the charging dock permanently powered
- **No receipt printer** (decided). Receipts are digital — the confirmation screen shows a QR of Square's receipt URL — and anyone who wants paper asks the cashier, who prints it from the staff Square Terminal at the counter.
- Wi-Fi (device has no Ethernet); give it a reserved DHCP lease and the strongest AP in the room

**Adding a kiosk later is a non-event by design:** buy another unit + Reader (~$350), provision (factory reset → Device Owner → install), staff logs in, picks the branch, pairs the Reader — ~15 minutes, zero backend changes. Kiosk count only affects the hardware budget and Wi-Fi capacity, never the software.

**At the counter (existing, not per-kiosk):** the staff **Square Terminal**, which receives kiosk orders the same way it receives counter orders.

### 2.2 Phase 0 hardware gate — run on the actual ApoloSign before any app code (1 day)

*Blocking — a failure here means changing the panel, not changing the plan:*
- [ ] **Square's Mobile Payments SDK sample app installs, authorizes, pairs the Reader, and takes a $1 sandbox payment** on this device. (EDLA makes this likely; likely ≠ done.)
- [ ] Current SDK release supports **Android 16** (release-notes + runtime check)
- [ ] Play Services present, current, and updatable via Play Store
- [ ] Not rooted, passes Play Integrity
- [ ] **Reader connection**: does the USB port power a wired Reader? If BLE: pairs, and holds the connection through a simulated full day (screen on, app foregrounded, 8h+)
- [ ] Bluetooth + runtime permissions can be granted once and survive reboot

*Non-blocking but shapes the build:*
- [ ] **Factory reset → Device Owner provisioning works** (`dpm set-device-owner` or Android Enterprise QR flow) — required for lock task, disabling the assistant, and silent OTA
- [ ] Lock-task mode ignores the **voice remote** and BT input devices
- [ ] Orientation locks to portrait; app renders 1080 × 1920; note reported `densityDpi` / `WindowMetrics` for the §6 density override
- [ ] Touch is capacitive multi-touch and reports as a touchscreen (not a mouse pointer)
- [ ] Screen stays awake on AC; behavior on power-restore (auto-boot or manual power button?) — if manual, the store runbook needs "press power" in the morning checklist
- [ ] Battery + charging state readable via `BatteryManager` for the heartbeat
- [ ] `adb` access for provisioning; **disabled again before the unit hits the floor**

**If it fails the gate:** a commodity Samsung/Lenovo Android tablet in a floor stand runs the same app with zero code change, and is on the hardware Square actually recommends. Second fallback is the Terminal API path (§4.3a).

---

## 3. Architecture

```
┌──────────────────────────┐         ┌────────────────────────┐        ┌──────────────┐
│  Kiosk App (Android)     │  HTTPS  │  Firebase (backend)    │ HTTPS  │  Square APIs │
│  Kotlin + Compose        │────────▶│                        │───────▶│  Catalog     │
│  + Mobile Payments SDK   │◀────────│  Cloud Functions (TS): │◀───────│  Orders      │
│                          │Firestore│   Square OAuth+refresh │ OAuth  │  Payments    │
│  • menu cache (local DB) │listeners│   scoped token minting │ tokens │  Locations   │
│  • cart / customization  │(live    │   order orchestration  │        │  Loyalty     │
│  • order submit          │ menu +  │   webhook handlers     │        │  Webhooks    │
│  • SDK payment + reader  │ avail-  │  Firestore: menu cache,│        │              │
│  • offline queue         │ ability)│   availability, fleet  │        │              │
│                          │         │  Auth · FCM · Storage  │        │              │
│                          │         │  Remote Config · Rules │        │              │
└──────────────────────────┘         └────────────────────────┘        └──────────────┘
     │              │                          ▲
     │ USB / BLE    │ local net                │ webhooks → HTTPS functions
     ▼              ▼                          │ (payment.updated, catalog.version.updated)
┌──────────┐                                   │
│ Square   │   ┌────────────────────┐          │        ┌──────────────────────┐
│ Reader   │   │ Manager App (iOS)  │  HTTPS   │        │ Staff Square Terminal│
│ (chip/   │   │ Swift + SwiftUI    │──────────┤        │ at the counter —     │
│  tap)    │   │ fleet · 86 · sales │◀─ FCM/   └────────│ receives & works     │
└──────────┘   │ alerts · settings  │  APNs push  orders│ kiosk orders,        │
               └────────────────────┘             land  │ prints receipts      │
                                                  here  │ on request           │
                                                        └──────────────────────┘
```

**Why a backend and not direct kiosk → Square?**
- Square OAuth tokens must never live on a device in a public space (the kiosk gets only the scoped payments token, §4.3).
- Menu/catalog is fetched once per branch and served to all kiosks — fast, cheap, consistent.
- One place to hold order state when a kiosk crashes mid-payment.
- Remote config, remote kill-switch, remote 86, OTA update pointers.
- **Real-time fan-out**: one Square webhook → one Firestore write → every kiosk and manager phone updates in under a second (§4.2a).
- On Firebase (Blaze pay-as-you-go) this is serverless: no VM to patch, and at tea-shop volume the bill is roughly $0–20/mo.

### Languages & stack (decided)

| Layer | Language / framework | Why |
|---|---|---|
| **Kiosk app** | **Kotlin + Jetpack Compose** (single-activity, MVVM, Room for the menu cache, WorkManager for the offline queue) | Native gets us the Chowbus feel — big photo cards, sliding modifier sheets, animated cart badge, 60fps scroll — without fighting a WebView's touch and scroll behavior. It also puts the kiosk-critical APIs (Device Owner / lock-task, boot receiver, ESC/POS printing, watchdog) directly in reach instead of behind a bridge. Fewer moving parts on a device that runs 14 hours a day unattended. |
| **Backend** | **Firebase** (decided): **Cloud Functions in TypeScript** (Square OAuth + scheduled refresh, webhook handlers, order orchestration, scoped-token minting) · **Firestore** (menu cache, live availability, device registry, orders, audit) · **Firebase Auth** (staff/manager/owner accounts + kiosk device identity) · **FCM** (push — wraps APNs, one pipeline for Android kiosks *and* the iOS manager app) · **Cloud Storage** (WebP images, attract media) · **Remote Config** (per-kiosk settings without an app update) · **Crashlytics** (kiosk + iOS crash reporting) · Secret Manager (Square tokens) | One directive covers it: kiosk backend = Firebase. It fits unusually well — Firestore's real-time listeners are exactly the mechanism §4.2a's live availability needs, Functions still speak TypeScript with Square's best SDK, and there's no server to babysit for a bubble-tea shop. |
| **Manager app** | **Swift + SwiftUI (iOS)** — decided | The manager's daily surface is their phone: fleet dashboard, alerts, 86 toggles, sales. Single platform → native SwiftUI, no cross-platform tax; **APNs push** is the payoff — a kiosk running on battery or a dropped reader pings the manager's pocket in seconds. Same backend API as everything else. |
| **Owner web console** | **TypeScript + React** — minimal | The handful of rare, desk-shaped jobs that don't belong on a phone: the one-time Square OAuth connect (browser redirect), staff accounts/roles, branch mapping, bulk menu overrides, attract-media upload. Shares API types with the backend. |
| **Display languages** | English-only v1; i18n scaffold retained (§12) | Kiosk pattern per Chowbus/MenuSifu; 中文 later is a translation file. |

**Rejected alternatives:** React Native / Flutter (would need native bridges for exactly the parts that matter most — kiosk lockdown, printing, boot behavior — while adding a runtime; reconsider only if an iPad version becomes a requirement) and a WebView/PWA shell (touch latency, scroll jank on cheap Android SoCs, and no clean path to lock-task mode).

---

## 4. Square integration design

### 4.1 Connecting the Square account (one-time, long-term)
1. Tea Hut owner opens the admin console → **Connect Square** → Square OAuth consent (authorization-code flow).
2. Backend exchanges `code` → `access_token` (30-day) + `refresh_token` (**valid until revoked**).
3. Tokens stored in **Google Secret Manager** (never in Firestore, never returned to a client); Functions read them at call time.
4. A **scheduled Cloud Function** refreshes the access token every **7 days** (and on any `401`), so an expiry can never take a store offline.
5. `ListLocations` pulls every Tea Hut branch → these become the selectable **branches**.
6. Revocation/disconnect flow + alerting if refresh ever fails.

7. **Always persist the `refresh_token` returned by each `ObtainToken` call** and alert on any refresh failure. Square documents code-flow refresh tokens as valid until revoked, but the safe implementation never assumes the old one survives.

**OAuth scopes needed:** `MERCHANT_PROFILE_READ`, `ITEMS_READ`, `INVENTORY_READ`, `ORDERS_READ`, `ORDERS_WRITE`, `PAYMENTS_READ`, `PAYMENTS_WRITE`, **`PAYMENTS_WRITE_IN_PERSON`** (required by the Mobile Payments SDK), `CUSTOMERS_READ/WRITE` (loyalty), `LOYALTY_READ/WRITE`, `GIFTCARDS_READ`.

### 4.2 Menu (Catalog API)
- Backend pulls the full catalog per location and caches it: categories → items → **variations** (sizes) → **modifier lists** (ice, sugar, toppings, milk swap) → images → taxes.
- Bubble-tea mapping: **size = item variation** (M/L), **ice / sugar / topping = modifier lists** with min/max selection rules. Toppings priced per modifier.
- Incremental re-sync on `catalog.version.updated` webhook + a 10-min scheduled poll as a webhook-loss safety net; the structural menu (items/prices/modifiers) lands in Firestore and kiosks pick it up via listener.
- **Item photos come from Square** (decided): each item's `CatalogImage` URLs are pulled during sync, resized/re-encoded to WebP by the backend, and cached on the kiosk. Card images center-crop to 400×260 (~1.54:1), so photos uploaded to Square should be ≥800px wide with the drink centered; items without a photo get the branded placeholder, never an empty box.
- Fields Square can't express (sort order, "recommended" flags, upsell rules, per-item photo *override* if a Square photo crops badly) live in our DB, keyed by Square catalog ID — never a second source of truth for price.
- Sold-out / 86 handling is real-time — see §4.2a.

### 4.2a Real-time availability — **decided: Square is the switch, kiosks follow in ~1s**

Requirement: when an item is marked unavailable in Square, every kiosk reflects it in real time. Square gives us the trigger; Firestore gives us the fan-out.

**The trigger (Square side).** An item variation carries a per-location `sold_out` flag (`ItemVariationLocationOverrides`). It flips when staff mark an item sold out on the **Square Terminal / POS at the counter**, or automatically when tracked inventory hits zero. Every flip fires the `catalog.version.updated` webhook. (Tracked-count changes additionally fire `inventory.count.updated`.)

**The pipeline.**
```
Staff tap "sold out" on the Square Terminal (or stock hits 0)
  → Square webhook → HTTPS Cloud Function (signature-verified)
    → fetch catalog delta since last version
      → write branches/{id}/availability/{itemId} in one Firestore batch
        → every kiosk's snapshot listener fires        →  item greys out
        → the manager iOS app's listener fires          →  dashboard updates
```
End-to-end target: **under ~2s** from the tap on the Terminal to the grey card on the kiosk. No polling in the hot path — the 10-min poll exists only to self-heal if a webhook is ever dropped, and a `version` field on the availability doc makes replayed/out-of-order webhooks harmless.

**Kiosk behavior on a flip:**
- In the grid and item sheet: card greys instantly with a "Sold out" badge; an open customization sheet for that item disables ADD with the same badge.
- **Already in a cart:** checkout re-validates every line against the availability doc before `CreateOrder`; anything that went dark triggers a clear "X just sold out — remove it and continue?" dialog rather than a cryptic order failure. (`CreateOrder` remains the final authority — a race that slips through fails loudly and refunds nothing, because payment only happens after the order is accepted.)
- **Offline:** last-known availability applies, and the listener catches up the moment connectivity returns (Firestore handles the resubscribe).
- The manager iOS app's 86 toggle writes the *same* availability doc directly (plus the Square override via API where applicable), so both paths — Square-side and app-side — converge on one document that kiosks watch.

### 4.3 Order + payment flow (Square Reader + Mobile Payments SDK) — **decided**

Payment happens on a **Square Reader attached to the kiosk**, driven by the **Mobile Payments SDK inside our Android app**. The staff's Square Terminal is a separate device used at the counter to receive and work orders — it is not in the kiosk's payment path.

**Authorizing the SDK (on every app start)**
1. Kiosk authenticates as its **Firebase Auth device identity** (custom token minted at provisioning, scoped by security rules to its own branch).
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
1. Kiosk builds cart → calls the `createOrder` callable Cloud Function.
2. The function runs `CreateOrder` in Square (location = branch, source = "Tea Hut Kiosk", line items with variation + modifier IDs, taxes/discounts, `fulfillment` = PICKUP with the customer's name/number, `reference_id` = our order number). Idempotency key = our order UUID. Returns `order_id` + total.
3. Kiosk shows its own tip screen (if enabled), then calls the SDK's `startPaymentActivity` with `PaymentParameters`: amount, `orderId`, `referenceId`, `tipMoney`, `autocomplete = true`, idempotency key = our order UUID.
4. Reader prompts: **tap / insert / Apple Pay / Google Pay**. The SDK owns this UI; our app shows a matching full-screen "Tap or insert your card" state with a Cancel button.
5. Success callback → payment is attached to the order → the order is paid and flows to the **staff Square Terminal**, KDS, kitchen printer, and Square reporting automatically.
6. Kiosk shows the order number + a **QR of the payment's `receipt_url`** (Square's hosted digital receipt — scan it, no hardware, no paper); paper on request from the cashier's Terminal. Returns to attract.
7. Failure paths: declined → retry or switch tender; canceled → back to cart with the cart intact; **app killed mid-payment** → on relaunch the kiosk asks the backend to reconcile by idempotency key before ever re-charging.

**Non-negotiable rule:** the idempotency key is the order UUID, generated once when the cart is submitted and reused on every retry. Double-charging a customer at an unattended screen is the worst failure this system can have.

### 4.3a Operating conditions this choice commits Tea Hut to

Square permits the Mobile Payments SDK **only in attended kiosks**. All three conditions must hold, and they are operational, not technical:

- [ ] The kiosk **cannot be physically reached by customers outside business hours** (inside the locked store, or shuttered).
- [ ] It is **in the line of sight** of a staff member during business hours.
- [ ] Staff are **trained to assist** customers with payment problems.

An in-store Tea Hut kiosk meets all three, so this is a supported configuration. Worth stating plainly because it rules out a vestibule kiosk, a 24-hour lobby, or an outdoor window later without revisiting the payment path.

**Device risk — largely retired, still verified.** Square states the SDK is **not compatible with rooted devices, custom ROMs, or OEM devices that violate its security rules**, and recommends major manufacturers. The confirmed ApoloSign is **EDLA-certified** (licensed genuine GMS — see §2.1), which removes the fake/missing-Play-Services failure mode that kills this class of device. It's still not a Google/Samsung name, so the §2.2 gate runs on the real unit before anything else is built — expected to pass, verified anyway.

**Because the unit is on wheels with a battery**, the attended-kiosk conditions above are enforced physically: casters locked, cable-anchored beside the counter, wheeled to the back (or shuttered) at close. A kiosk that can roll is a kiosk that can leave staff line-of-sight.

**Contingency if the TV fails the SDK check** (in order of preference): (a) swap the panel for a Samsung/Lenovo Android tablet in a floor stand — same app, no code change; (b) fall back to the Terminal API path with a Square Terminal at the kiosk; (c) QR pay-on-phone. The payment layer sits behind a single `PaymentProcessor` interface precisely so this stays a swap and not a rewrite.

### 4.4 Square Loyalty integration — **MVP (decided)**

All loyalty calls run on the backend with the full-scope token (`LOYALTY_READ/WRITE`, `CUSTOMERS_READ/WRITE`); the kiosk only ever sends a phone number and receives balances/rewards.

**Checkout flow (optional, skippable in one tap):**
1. After cart review: **"Earn rewards?"** screen — big numeric pad, phone number entry, prominent **Skip**.
2. Backend `SearchLoyaltyAccounts` by phone →
   - **Found:** show first name (if on file), point balance, and any redeemable rewards.
   - **Not found:** one-tap enroll (`CreateLoyaltyAccount`) with the program's terms shown; declining continues as guest.
3. **Redeem:** customer picks a reward → backend `CreateLoyaltyReward` against the order → Square applies the discount server-side → the new total is what the Reader charges. If payment is then canceled or fails terminally, backend `DeleteLoyaltyReward` releases the hold — a reward must never be burned without a payment.
4. **Accrue:** after the payment completes, backend `AccumulateLoyaltyPoints` with the order ID (idempotent on our order UUID — points can't double-accrue on a retry).
5. Confirmation screen shows **points earned + new balance** ("You have 240 ⭐ — 60 more for a free topping"), which is the whole reason kiosk loyalty converts.

Program details (point name, earning rule, reward tiers) are read from `RetrieveLoyaltyProgram` at sync time and rendered as configured in Square — nothing hardcoded. If the merchant has no loyalty program active, the screens simply don't appear.

### 4.5 Alternate tenders (all optional toggles per branch)
- **Cash / pay at counter** — order created as unpaid/OPEN; it appears on the staff Square Terminal and the customer pays there. Also the graceful degradation whenever the reader is offline.
- **QR pay on phone** — backend creates a Square payment link, kiosk shows a QR; customer pays on their own phone. Zero extra hardware, and the disaster fallback if a reader dies mid-shift.
- **Square gift card** — keyed/scanned at checkout, or handed to staff at the counter.

---

## 5. Accounts, branches & device identity

**Roles**
| Role | Can do |
|---|---|
| Owner | **Web console:** connect/disconnect Square, create accounts, branch mapping — all branches. Can also use the manager iOS app. |
| Manager | **iOS app (their daily surface):** fleet dashboard + push alerts, 86 items, menu overrides, kiosk settings, sales, remote reboot/deauthorize — their branch. Sets the kiosk-unlock PIN. |
| Staff | **On the kiosk itself:** unlock (manager PIN + hidden gesture), start/stop kiosk mode, assist customers. No app of their own. |

**Flow on a fresh kiosk**
1. App launches → **Login** (email + password, or a short staff PIN after the first login on that device).
2. **Select branch** — list of Square locations the account is allowed to serve.
3. **Pair the Square Reader** — the SDK's built-in reader settings screen; verify a $0.00 test connection.
4. Device registers itself → backend issues a **device token** (long-lived, revocable, scoped to that one branch) and mints the first scoped payments token; the staff session ends. From then on the kiosk boots straight into the attract screen with no login — even after a power cut — re-authorizing the SDK silently on each start.
5. Exiting kiosk mode requires a manager PIN + a hidden gesture (5-tap corner), matching how Chowbus/MenuSifu do it. Reader settings live behind the same PIN.

The device registry lives in the backend and renders in the **manager iOS app**: name ("Tea Hut Flushing #2"), branch, **reader serial / connection state / battery**, app version, last seen, network, **device charging state**, remote reboot, remote deauthorize + token revoke. Anything red pushes an APNs alert to the branch's managers.

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

On the confirmed 24" panel this works out to ~92 ppi — every design px ≈ 0.28mm. The 96px minimum touch target is ≈26mm of physical glass, comfortably above the ~9mm usability floor, and the 36px body size is ≈10mm tall — legible at arm's length. A 24" portrait screen is more forgiving than the tablets Chowbus runs on; the risk flips from "too small to tap" to "sparse," so the grid and photography have to fill the space confidently.

### 6.2 Global layout grid (menu screen — the Chowbus signature)

```
 0 ┌────────────────────────────────────────────┐  y=0
   │  HEADER  160px                             │  Here/To-Go · Start Over  (no logo, English-only v1)
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

- **Header (160px):** **no logo** and **no language pill** (English-only v1) — the header carries just the Here/To-Go segmented control on the left and "Start Over" as a low-contrast text button on the right. That much emptiness buys the option of shrinking it to 140px for more grid — worth a look on the real panel. When 中文 flips on later, the language pill returns to the left slot.
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
| Palette | Photo-forward (no logo): warm neutral background, near-black text, and **accent = Apple blue `#007AFF`** (decided) — used *only* for price, the "+" button, CHECKOUT, and selected-chip fills. Usage rule: white text on `#007AFF` sits at ~4:1 contrast, which passes WCAG only for large text — so the accent always carries **large type** (≥36px) or icons, never fine print; small text on blue gets a darkened variant (`#0062CC`). |

### 6.5 Assets
- Item photos: **pulled from Square's catalog images** (decided) — backend fetches `CatalogImage` URLs at sync, re-encodes to WebP at 800×520, kiosk preloads them into the Coil disk cache during menu sync so the grid never shows a spinner. Photos uploaded to Square should be ≥800px wide, drink centered, since cards center-crop to ~1.54:1. Admin console flags items whose Square photo is missing or too small.
- Attract loop: 1080 × 1920 H.264 video or a still image carousel, uploaded per branch from the admin console.
- Every image has a branded placeholder — a menu item with no photo must never render an empty box.

---

## 7. Feature list

Legend: **M** = MVP (launch) · **P1** = fast follow · **P2** = later

### 7.1 Customer ordering
| # | Feature | Pri |
|---|---|---|
| 1 | Attract / idle screen: looping video or promo images, "Tap to Order", auto-return after 45s idle | M |
| 2 | **English-only v1** (decided). i18n scaffolding ships from day one with a hidden config toggle, so 中文/Español later is a translation file, not a rebuild | M |
| 3 | Order type: **Here / To Go** (drives Square fulfillment + tax where applicable) | M |
| 4 | Category rail + item grid, large photos, portrait layout, thumb-reachable | M |
| 5 | Item detail: photo, description, calories/allergen note, size (variation) picker | M |
| 6 | **Drink customization**: ice level, sugar level, toppings (multi-select w/ max), milk swap, hot/cold, temperature — each priced, each validated against Square modifier min/max | M |
| 7 | Quantity stepper, per-item "special request" note (free text → Square line-item note) | M |
| 8 | Cart drawer: edit / remove / re-customize, live subtotal | M |
| 9 | **Upsell prompts**: "Add a topping?" on item add, "Popular with your order" before checkout | P1 |
| 10 | Combos / set meals (drink + snack bundle pricing) | P1 |
| 11 | Search + "Best sellers" / "New" / "Recommended" merchandising rows | P1 |
| 12 | **Real-time sold-out** (decided, §4.2a): Square-side flips reach every kiosk in ~1–2s via Firestore listener; greyed card + badge, in-cart re-validation at checkout | M |
| 13 | Customer name or nickname for the order (for call-out) | M |
| 14 | Phone number capture → SMS "your drink is ready" | P1 |
| 15 | Item nutrition / allergen sheet | P2 |
| 16 | Accessibility: high-contrast mode, larger-text mode, a reachable "lower the UI" ADA button for wheelchair height | P1 |

### 7.2 Checkout & payment
| # | Feature | Pri |
|---|---|---|
| 17 | Order review: line items with all modifiers spelled out, tax, total | M |
| 18 | Promo code entry → Square discount | P1 |
| 19 | **Tip prompt** (decided): on-screen preset % buttons + a **No tip** button of equal visual weight — skippable in one tap, never guilt-boxed; passed to the SDK as `tipMoney` | M |
| 20 | Pay via **Square Reader** (Mobile Payments SDK) — tap / chip / Apple Pay / Google Pay | M |
| 20a | **Reader state handling**: connection + battery monitoring, "reconnecting" state, auto-disable card payment when the reader is down instead of failing a customer mid-checkout | M |
| 20b | **Reader pairing & diagnostics screen** behind the manager PIN (SDK's built-in settings UI) | M |
| 20c | **Crash-safe payments**: order-UUID idempotency key, reconcile-before-recharge on relaunch | M |
| 21 | Cash / pay-at-counter fallback (order lands on the staff Square Terminal unpaid) | M |
| 22 | QR pay-on-phone fallback | P1 |
| 23 | Square **gift card** redemption | P1 |
| 24 | **Square Loyalty** (decided — see §4.4): phone entry, one-tap enrollment, reward redemption before payment, accrual after, points on the confirmation screen | M |
| 25 | Decline / timeout / cancel handling with clear recovery copy | M |
| 26 | **Receipts** (decided): no kiosk printer — confirmation shows a **QR of Square's `receipt_url`**; paper on request from the cashier's staff Terminal | M |
| 27 | Order-number confirmation screen + optional QR to track status | M |
| 28 | Split payment / multiple tenders | P2 |

### 7.3 Kitchen & store operations
| # | Feature | Pri |
|---|---|---|
| 29 | Orders land in Square as normal orders → **staff Square Terminal**, KDS, and kitchen printer with no extra work | M |
| 30 | ~~Direct ESC/POS ticket printing from the kiosk~~ — dropped (no printer, decided) | — |
| 31 | Order source tagged "Kiosk #N" so reporting can split kiosk vs counter | M |
| 32 | Daily kiosk sales summary in the admin console (count, AOV, top items, attach rate of toppings) | P1 |
| 33 | Customer-facing "now serving / ready" board (second screen or same TV when idle) | P2 |

### 7.4 Admin & fleet management
Two surfaces (decided): **[iOS]** = manager app (Swift/SwiftUI), **[web]** = minimal owner console.

| # | Feature | Surface | Pri |
|---|---|---|---|
| 34 | Staff accounts, roles, password reset, per-branch permissions | web | M |
| 35 | Branch (Square location) mapping and selection | web | M |
| 36 | Square connect / reconnect / health indicator with token-expiry alerting | web (+ status in iOS) | M |
| 37 | Kiosk fleet dashboard: online status, app version, last order, **reader connection + battery, device charging state**, remote reboot, remote deauthorize | iOS | M |
| 37a | **Push alerts (FCM→APNs)**: kiosk offline, running on battery, reader disconnected, Square token refresh failure | iOS | M |
| 38 | 86 / sold-out toggle (propagates to kiosks in seconds) | iOS | M |
| 38a | Menu overrides: sort order, hide item, photo override | iOS + web | M |
| 39 | Per-kiosk settings: tip %, idle timeout, tenders enabled | iOS | M |
| 39a | Daily sales at a glance: kiosk count, AOV, top items | iOS | P1 |
| 40 | Attract-screen media upload (images/video) per branch | web | P1 |
| 41 | Remote config push without an app update — **Firebase Remote Config** | backend | P1 |
| 42 | Audit log (who changed what, who exited kiosk mode) | web | P1 |

### 7.5 Platform / reliability
| # | Feature | Pri |
|---|---|---|
| 43 | **Kiosk lockdown**: Device Owner + LockTask mode — no status bar, no home/recents, no other apps; **voice remote / BT input ignored, assistant disabled, camera unused** | M |
| 44 | Auto-launch on boot, watchdog restart on crash, screen-always-on | M |
| 45 | **Offline mode**: browse + build a cart from the local menu cache; queue unpaid orders; block card payment while offline with a clear message | M |
| 46 | Idempotency everywhere (no double-charge, no duplicate order on retry) | M |
| 47 | Crash/ANR reporting + remote logs — **Firebase Crashlytics** (kiosk + iOS manager app) | M |
| 48 | OTA app updates via **managed Google Play** (EDLA device has real Play Store) or self-hosted APK + silent install as Device Owner | P1 |
| 49 | Health heartbeat via Firestore presence doc (last-seen + charging state): **alert within minutes if the unit is running on battery** (5200mAh means an unplugged kiosk dies silently hours later), alert if dark >10 min during store hours — a scheduled Function watches, FCM delivers | M |
| 50 | Auto-recovery: nightly restart at 4am (also good Li-ion hygiene for a permanently-docked battery), cache re-sync at open | P1 |

---

## 8. Screen flow

```
Attract ──tap──▶ Here/To Go ──▶ Menu ──tap item──▶ Item Detail
                                                │                    │
                                                │                add to cart
                                                ▼                    │
                                              Cart ◀─────────────────┘
                                                │
                                    Review ──▶ Loyalty (phone / skip) ──▶ Tip (% / No tip)
                                                │
                                       ┌────────┴────────┐
                                 Card on Square      Cash at counter
                                 Reader (tap/chip)   (order → staff Terminal)
                                       └────────┬────────┘
                                                ▼
                          Confirmation (order # · points earned · receipt QR) ──30s──▶ Attract
```
Every screen: a persistent "Start Over"; every screen auto-returns to Attract after 60s of inactivity (with a 15s "Are you still there?" countdown that preserves the cart if tapped). A payment in progress never times out from under the customer.

---

## 9. Data model (Firestore, abbreviated)

```
merchants/{merchantId}          square_merchant_id, status, token_secret_ref   ← tokens live in Secret Manager
  branches/{branchId}           square_location_id, name, timezone, settings
    menu/{version}              structural catalog snapshot (items, prices, modifiers) — kiosks listen
    availability/{itemId}       sold_out, hidden, reason, version, updated_at  — the §4.2a live doc
    overrides/{objectId}        sort, recommended, photo_override, upsell
    kiosks/{kioskId}            name, reader_serial, app_version, presence: {last_seen, charging,
                                reader_state}, settings                        — manager app listens
    orders/{orderUuid}          square_order_id, state, total, payment_state, created_at
                                (idempotency anchor: the doc id IS the order UUID)
users/{uid}                     role + branch claims mirror (authority = Auth custom claims)
audit/{eventId}                 actor, action, target, meta, at
```

Access is enforced by **Firestore security rules**: a kiosk identity can read only its own branch's `menu`/`availability`/`overrides` and write only its own `presence`; managers read/write their branches via custom claims; `orders` and everything financial is **Functions-only** (no direct client writes). Order state transitions happen in Firestore transactions keyed on the order UUID — the same idempotency spine §4.3 relies on.

---

## 10. Security & PCI

- **Card data is captured and encrypted by the Square Reader and handled entirely by the Mobile Payments SDK.** Our code never sees a PAN and never handles card entry UI. The app is still part of the payment flow, so it stays locked down, signed, and current on SDK versions.
- Square tokens: the **full-scope token lives only on the server**, encrypted at rest, rotated, revocable.
- The kiosk holds (a) a revocable device token scoped to one branch and (b) a **narrowed payments-only Square token** (`MERCHANT_PROFILE_READ`, `PAYMENTS_WRITE`, `PAYMENTS_WRITE_IN_PERSON`) in the Android Keystore, re-minted before expiry and revocable per device from the admin console. No catalog, customer, or reporting access from the device's token.
- Physical security matters more on this path than on the Terminal path: the device is the payment terminal. Kiosk lockdown, no adb in the field, tamper-evident mounting, and one-tap remote deauthorize if a unit goes missing.
- **Firestore security rules are part of the security boundary**, not a config detail: kiosks are branch-scoped read-only identities, financial writes are Functions-only, and rules changes are code-reviewed like code. Square webhook functions verify the signature before touching anything.
- TLS + certificate pinning on the kiosk; no debug builds in the field.
- Kiosk mode prevents customers from reaching settings, browser, or files.
- No customer PII on the device beyond the current in-progress order; phone/email go straight to Square/our backend and are cleared on completion.

---

## 11. Build plan

| Phase | Scope | Est. |
|---|---|---|
| **0. Validate — GATE** | **On the actual ApoloSign Gen2: run Square's Mobile Payments SDK sample app, authorize, pair the Reader, take a $1 sandbox payment; confirm Android 16 SDK support.** Then the rest of §2.2 — factory-reset → Device Owner, lock-task vs voice remote, portrait lock, battery telemetry. *Nothing else starts until this passes.* Order 1 unit + 1 Reader now; ~$350 answers every open hardware question. | 3–5 days |
| **1. Backend core** | Firebase project + security rules, Auth + roles (custom claims), Square OAuth + scheduled refresh (Secret Manager), **scoped token minting for devices**, locations, catalog sync → Firestore, **§4.2a availability pipeline**, device registry | 1.5–2 wks |
| **2. Kiosk MVP** | Attract → menu → customization → cart → checkout → **Reader payment via MPS** → confirmation; reader state handling; crash-safe idempotency; offline cache; kiosk lockdown | 3–4 wks |
| **3. Ops** | **Manager iOS app** (fleet dashboard, APNs alerts, 86 toggle, kiosk settings, sales glance) + minimal owner web console (Square connect, accounts, branches) | 2–2.5 wks |
| **4. Pilot** | One kiosk in one Tea Hut store, 2 weeks of live tuning, staff training, runbook | 2 wks |
| **5. Fast-follow** | Loyalty, gift cards, upsell, combos, SMS-ready, QR pay, OTA | 2–3 wks |

**Rough total to a live pilot: ~9–11 weeks of one full-time developer.** The iOS manager app adds real scope but runs against the same backend API as everything else, and can be built in parallel with Phase 2 if a second developer exists. A pilot *can* start before the iOS app ships (the web console covers setup; alerts fall back to email) — but day-to-day ops without it means a manager walking to a laptop, so it's in the main build, not fast-follow.

---

## 12. Decisions log & remaining questions

**Decided (v5):**
| Question | Decision |
|---|---|
| Device | ApoloSign 24" Gen2 (§2.1) |
| Kiosk count | Doesn't gate anything — kiosks scale horizontally, adding one is ~15 min + hardware (§2.1) |
| Receipts | No kiosk printer. QR to Square's digital receipt on-screen; paper on request from the cashier's staff Terminal |
| Tips | On — preset % + equal-weight **No tip** button, one-tap skippable |
| Loyalty | Square Loyalty in MVP (§4.4) |
| Languages | English-only v1; i18n scaffold retained |
| Menu photos | Pulled from Square catalog images (§4.2) |
| Accent color | Apple blue `#007AFF` (§6.4) |
| Logo | None |
| Manager surface | **Separate iOS app** (Swift/SwiftUI) with push alerts; minimal web console retained for owner setup (§3, §7.4) |
| Backend | **Firebase** — Cloud Functions (TS) + Firestore + Auth + FCM + Storage + Remote Config + Crashlytics (§3) |
| Availability | **Real-time**: Square sold-out flips fan out to kiosks in ~1–2s via webhook → Firestore listener (§4.2a) |

**Still open:**
1. **Wired or BLE Reader** — does the ApoloSign's USB port power a wired Reader? Phase 0 settles it; BLE + powered dock is the fallback.
2. **Confirm §4.3a's attended conditions** — always inside, staff line of sight, inaccessible after close; "who wheels it where at close" goes in the store runbook.
3. **Verify at pilot:** cashier can pull up a kiosk payment on the staff Terminal and print its receipt (transaction history at the same location — expected to work, confirm on real hardware).
4. **Is Square Loyalty already configured** in the Tea Hut account (earning rule + reward tiers)? The kiosk renders whatever the program defines; if it's not set up yet, that's a 30-minute Square Dashboard task before pilot.

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
- [Monitor sold-out item variations](https://developer.squareup.com/docs/inventory-api/monitor-sold-out-status-on-item-variation) · [ItemVariationLocationOverrides](https://developer.squareup.com/reference/square/objects/ItemVariationLocationOverrides) · [catalog.version.updated](https://developer.squareup.com/reference/square/catalog-api/webhooks/catalog.version.updated) — per-location `sold_out`, auto-set at zero stock, webhook on every flip (§4.2a)
- [Chowbus restaurant kiosk](https://www.chowbus.com/hardware/restaurant-kiosk) · [MenuSifu boba kiosk features](https://www.menusifu.com/blog/boba-shop-kiosk-system) · [MenuSifu kiosk hardware](https://www.menusifu.com/hardware/restaurant-kiosk) — reference feature set
- [KioskBuddy ↔ Square Terminal](https://www.kioskbuddy.app/help/square-terminal) · [Sending kiosk orders to Square POS](https://www.kioskbuddy.app/help/square-orders) — proof the Terminal API path works in production
