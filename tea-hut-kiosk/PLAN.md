# Tea Hut Self-Order Kiosk — Product & Technical Plan

**Status:** Draft v1 — for review before any code is written
**Target:** Android self-order kiosk for Tea Hut, connected to Square
**Reference products:** Chowbus POS kiosk, MenuSifu POS kiosk (private/internal app, single tenant)

---

## 0. Read This First — Three Findings That Change the Design

Before the feature list, three things came out of research that affect what we can actually build.

### 0.1 Square forbids taking card payments on an unattended kiosk with the Mobile Payments SDK

Square's Mobile Payments SDK documentation states that using it "to implement payment solutions in unattended terminals or unattended kiosks is **strictly prohibited**." Tap to Pay on Android falls under the same SDK. So the obvious design — customer taps their card on the smart TV — is not available to us.

**The supported path is the Terminal API.** Our Android app builds the cart and the Square `Order`, then calls `CreateTerminalCheckout` to push the amount to a **Square Terminal** paired to the same account. The customer pays on the Terminal; we get the result via webhook or polling. This is exactly how Square's published kiosk case studies (KAIKAKU, in-store QSR kiosks) do it.

**Practical consequence for Tea Hut:** each kiosk station = 1 Android smart TV (the menu/ordering screen) + 1 Square Terminal (the payment device), physically mounted side by side. This is also how Chowbus/MenuSifu kiosks are built — their "kiosk" is a screen plus a separate certified payment terminal.

Alternatives if you'd rather not buy Terminals:
- **Square Kiosk** (Square's own first-party product, Square Register hardware). Turnkey, but we don't control the UI and there's no Tea Hut branding/flow customization. Rules this whole project out.
- **Pay-at-counter mode.** Kiosk produces the order + a ticket number, customer pays at the main POS. Zero extra hardware, but loses the labor savings that justify a kiosk.
- **QR handoff.** Kiosk shows a QR; customer pays on their own phone via a Square-hosted checkout link. Cheap, but adds friction and fails for cash-preferring or phone-less customers.

**Recommendation: Terminal API + Square Terminal per station, with pay-at-counter as a configurable fallback mode.** Decision needed from you — see §12.

### 0.2 The "incell smart portable TV" is the riskiest single component

These portable Android smart TVs (the rolling-stand, battery-backed 21–32" units) are usually:
- Running an **Android TV / AOSP fork**, not standard Android tablet builds
- **Not Play Protect certified** — Google Play Services may be absent or partial
- Often **rooted or shipping custom ROMs** — which Square's SDKs refuse to run on (this affects the Terminal-pairing path far less, since payment never touches this device, another reason to prefer §0.1's recommendation)
- Missing **device owner provisioning**, which we need for true kiosk lockdown
- Sometimes **remote-only input** — touch is present but the launcher assumes a D-pad

**Action before we write a line of code:** buy one unit and run a 1-day hardware spike (§11, Milestone 0). We need to confirm: Android API level ≥ 26, touch digitizer works with standard `View` touch events, we can install an APK via ADB/sideload, we can set our app as HOME activity or enter lock task mode, and Wi-Fi is stable. If the unit fails this, the fallback is a **standard Samsung Galaxy Tab A9+ / Lenovo Tab** on a floor stand — cheaper, certified, and fully supported.

### 0.3 "Full copy of MenuSifu/Chowbus" needs one boundary

You noted this is internal-only for Tea Hut and never publicly announced, so copying their flows is fine. Two clarifications on what "copy" safely means:

- **Copy freely:** screen flow, information architecture, the modifier-picker interaction, upsell placement, layout proportions, the whole UX pattern. Interface conventions aren't protectable and these patterns are industry-standard.
- **Do not copy:** their literal logo, their brand name, their photography/food images, or decompiled code from their APKs. We build Tea Hut's own visual identity on top of their proven layout, and use Tea Hut's own product photos.

This costs us nothing — the value in those apps is the flow, not the pixels — and it keeps the project clean even though it's private.

---

## 1. What We're Building

A single-purpose Android application that runs full-screen and locked-down on a touchscreen in Tea Hut stores. A customer walks up, browses the drink menu, customizes a drink (size, ice, sweetness, toppings), adds it to a cart, optionally identifies themselves for loyalty, pays, and gets a ticket number. The order lands in Square as a real `Order`, so it flows into Tea Hut's existing Square reporting, inventory, and kitchen/printer setup with no separate reconciliation.

Staff use the same app in a hidden admin mode to log in, pick which store branch this kiosk represents, and manage day-to-day settings.

### Explicitly in scope
- Android kiosk app (customer ordering UI + staff admin UI)
- A small backend service (required — see §4.2) that holds Square OAuth tokens and brokers API calls
- Square integration: catalog, orders, payments, loyalty, customers

### Explicitly out of scope for v1
- Building our own POS (Square is the POS)
- Kitchen display system (Square's existing KDS/printers handle this)
- Delivery / third-party marketplace integration
- Multi-tenant SaaS features — this is Tea Hut only

---

## 2. Feature List

Prioritized as **MVP** (must ship to go live), **P1** (fast follow, weeks after launch), **P2** (nice to have).

### 2.1 Account, Login & Store Selection

| # | Feature | Pri |
|---|---|---|
| 1.1 | Staff account login (email + password) against our backend, not Square | MVP |
| 1.2 | Store branch picker shown immediately after login; lists only branches this account is entitled to | MVP |
| 1.3 | Branch selection persists across app restarts and device reboots — set once at install, never re-asked | MVP |
| 1.4 | Roles: `owner` (all branches, can change Square connection), `manager` (own branch, settings + refunds), `staff` (open/close kiosk only) | MVP |
| 1.5 | Device registration — each kiosk gets a device ID + friendly name ("Tea Hut Flushing — Kiosk 1"), visible in admin | MVP |
| 1.6 | Session model: staff login is a **one-time provisioning act**, not a per-shift login. Once bound, the kiosk stays bound with no staff present | MVP |
| 1.7 | Hidden admin entry: long-press a corner for 5s + 6-digit manager PIN | MVP |
| 1.8 | Remote unbind / wipe a kiosk from the admin web console (stolen or decommissioned device) | P1 |
| 1.9 | Password reset by email | P1 |
| 1.10 | Audit log of logins, branch changes, and setting changes | P1 |

### 2.2 Square Connection (Long-Term)

| # | Feature | Pri |
|---|---|---|
| 2.1 | Square OAuth **authorization code flow**, performed once by the owner in the admin web console — never on the kiosk device | MVP |
| 2.2 | Refresh token stored server-side; code-flow refresh tokens **do not expire**, which is what makes the connection long-term | MVP |
| 2.3 | Automatic access-token refresh on a schedule (every ~20 days; access tokens live 30 days) plus reactive refresh on `401 UNAUTHORIZED` | MVP |
| 2.4 | One Square location mapped per Tea Hut branch; the kiosk's branch determines its `location_id` | MVP |
| 2.5 | Connection health screen: connected/disconnected, token last-refreshed, scopes granted, "Reconnect" button | MVP |
| 2.6 | Requested scopes, minimum needed: `MERCHANT_PROFILE_READ`, `ITEMS_READ`, `ORDERS_READ`, `ORDERS_WRITE`, `PAYMENTS_READ`, `PAYMENTS_WRITE`, `DEVICE_CREDENTIAL_MANAGEMENT`, `CUSTOMERS_READ`, `CUSTOMERS_WRITE`, `LOYALTY_READ`, `LOYALTY_WRITE`, `INVENTORY_READ` | MVP |
| 2.7 | Kiosk never holds a Square token — it holds our own short-lived device JWT and calls our backend | MVP |
| 2.8 | Square webhook receiver for `payment.updated`, `terminal.checkout.updated`, `order.updated`, `catalog.version.updated` | MVP |
| 2.9 | Alert (email/SMS to owner) if refresh fails or the connection is revoked | P1 |
| 2.10 | Sandbox vs production environment toggle for testing | MVP |

### 2.3 Menu & Catalog

| # | Feature | Pri |
|---|---|---|
| 3.1 | Pull the live menu from Square Catalog API — categories, items, item variations (sizes), modifier lists, prices, taxes | MVP |
| 3.2 | Local cache of the full catalog so the kiosk boots and runs instantly and survives brief network loss | MVP |
| 3.3 | Auto-resync on `catalog.version.updated` webhook, plus a periodic sync and a manual "Sync now" in admin | MVP |
| 3.4 | Per-branch availability — an item hidden at one branch stays visible at another | MVP |
| 3.5 | Sold-out handling: read Square inventory; grey out and block sold-out items and toppings | MVP |
| 3.6 | Product images, high-resolution, uploaded via admin console and cached on device (Square catalog images used if present) | MVP |
| 3.7 | Category rail + item grid layout, tuned for the screen's aspect ratio | MVP |
| 3.8 | Search by drink name | P1 |
| 3.9 | Kiosk-only menu overrides — hide an item from kiosk while keeping it on the counter POS | P1 |
| 3.10 | Featured / seasonal carousel on the menu screen | P1 |
| 3.11 | Nutritional info / allergen tags per item | P2 |

### 2.4 Drink Customization (the core of a tea shop kiosk)

| # | Feature | Pri |
|---|---|---|
| 4.1 | Size selection driven by Square item variations (M / L), with price deltas | MVP |
| 4.2 | **Ice level** — No Ice / Less Ice / Regular / Extra Ice | MVP |
| 4.3 | **Sweetness level** — 0% / 25% / 50% / 75% / 100% | MVP |
| 4.4 | **Toppings** — multi-select, each with its own price (boba, pudding, grass jelly, aloe, cheese foam, etc.), with a configurable max count | MVP |
| 4.5 | **Milk / base swaps** — oat, almond, whole, non-dairy, with price deltas | MVP |
| 4.6 | Temperature — hot / iced, where the item supports both | MVP |
| 4.7 | Required vs optional modifier enforcement — can't add to cart until required choices are made | MVP |
| 4.8 | Live price preview that updates as modifiers are tapped | MVP |
| 4.9 | Per-item quantity stepper | MVP |
| 4.10 | Default modifier presets per item (e.g. Classic Milk Tea defaults to 50% sugar, regular ice) to cut taps | MVP |
| 4.11 | All modifiers map to real Square `modifier_list` / `modifier` objects so the ticket prints correctly and costs are tracked | MVP |
| 4.12 | Free-text special instructions ("light foam"), passed as an order line note | P1 |
| 4.13 | "Repeat last drink" for returning loyalty customers | P2 |

### 2.5 Cart & Upsell

| # | Feature | Pri |
|---|---|---|
| 5.1 | Persistent cart panel: line items with modifiers, line prices, running subtotal | MVP |
| 5.2 | Edit or remove a line item; re-opens the customization sheet pre-filled | MVP |
| 5.3 | Tax, and total, computed by Square's Orders API (never by us — avoids tax drift) | MVP |
| 5.4 | Upsell screen after "Checkout": suggested toppings / snacks / size upgrade, dismissible in one tap | MVP |
| 5.5 | Cart abandonment timeout — 90s of inactivity shows a "Still there?" prompt, then clears and returns to attract screen | MVP |
| 5.6 | Order type: Here / To Go | MVP |
| 5.7 | Promo / discount code entry, validated against Square | P1 |
| 5.8 | Combo & bundle pricing | P2 |

### 2.6 Customer Identity & Loyalty

| # | Feature | Pri |
|---|---|---|
| 6.1 | Optional phone-number entry to attach the order to a Square loyalty account | MVP |
| 6.2 | Enroll a new loyalty member right at the kiosk (phone number only) | MVP |
| 6.3 | Show current points balance and points earned on this order | MVP |
| 6.4 | Redeem loyalty rewards at checkout | P1 |
| 6.5 | Skip-identification path that never blocks the order | MVP |
| 6.6 | Square gift card balance check + redemption | P1 |
| 6.7 | SMS "your drink is ready" notification | P2 |

### 2.7 Payment

| # | Feature | Pri |
|---|---|---|
| 7.1 | Create a Square `Order` with all line items, modifiers, taxes, and the branch `location_id` | MVP |
| 7.2 | Push payment to the paired Square Terminal via `CreateTerminalCheckout` | MVP |
| 7.3 | Live "Pay on the card reader →" screen with an arrow pointing at the physical Terminal | MVP |
| 7.4 | Poll `GetTerminalCheckout` + listen for the `terminal.checkout.updated` webhook; whichever lands first wins | MVP |
| 7.5 | Handle every terminal outcome: approved, declined, cancelled by customer, timed out, device offline | MVP |
| 7.6 | Terminal device pairing flow in admin: generate a device code, staff enters it on the Terminal, pairing persists | MVP |
| 7.7 | Configurable **pay-at-counter mode** — kiosk finalizes an unpaid order and prints a ticket; customer pays at the main POS (fallback if a Terminal is offline or not purchased) | MVP |
| 7.8 | Idempotency keys on every order/payment call, so a retry after a network blip never double-charges | MVP |
| 7.9 | Tip prompt on the Terminal (Square handles the UI) | P1 |
| 7.10 | QR-to-phone payment as a third mode | P2 |
| 7.11 | Cash handling — **not supported**, by design; cash goes to the counter | — |

### 2.8 Order Completion

| # | Feature | Pri |
|---|---|---|
| 8.1 | Confirmation screen with a large ticket/order number | MVP |
| 8.2 | Order pushes into Square, so existing kitchen printers / KDS pick it up with no extra work | MVP |
| 8.3 | Receipt options: printed (via Terminal), SMS/email (via Square), or none | MVP |
| 8.4 | Auto-return to attract screen after 10s | MVP |
| 8.5 | Ticket-number scheme that doesn't collide with counter POS numbering (kiosk prefix, e.g. `K-042`) | MVP |

### 2.9 Kiosk Mode & Device Management

| # | Feature | Pri |
|---|---|---|
| 9.1 | Android lock task mode / screen pinning — customer cannot escape to the launcher | MVP |
| 9.2 | Suppress status bar, nav bar, notifications; block the recents and home gestures | MVP |
| 9.3 | Keep-screen-on, auto-launch on boot | MVP |
| 9.4 | Attract screen / idle loop: full-screen promo image or video, taps anywhere to start | MVP |
| 9.5 | Offline banner + degraded mode (browse cached menu; block checkout with a clear message) | MVP |
| 9.6 | Crash auto-restart back into the attract screen | MVP |
| 9.7 | Remote config: opening hours, upsell rules, attract media, timeouts — pushed from the backend | P1 |
| 9.8 | Remote health telemetry: online/offline, app version, last order time, Terminal reachability | P1 |
| 9.9 | OTA app updates without a store visit | P1 |
| 9.10 | Screen-brightness scheduling / off-hours sleep | P2 |

### 2.10 Admin & Reporting

| # | Feature | Pri |
|---|---|---|
| 10.1 | Web admin console (browser, used by owner/manager) for staff accounts, branches, Square connection, kiosk device list | MVP |
| 10.2 | Attract-screen media upload per branch | MVP |
| 10.3 | On-device admin panel for network setup, Terminal pairing, sync-now, exit-kiosk | MVP |
| 10.4 | Kiosk sales summary — orders/day, average ticket, top drinks, kiosk vs counter split | P1 |
| 10.5 | Upsell acceptance rate reporting | P2 |
| 10.6 | Multi-language UI — English + Chinese, toggle on the attract screen | P1 |

---

## 3. Screen Flow

```
[Attract Loop] ──tap──> [Order Type: Here / To Go]
                              │
                              ▼
                    ┌──> [Menu: category rail + item grid] <──┐
                    │              │ tap item                 │
                    │              ▼                          │
                    │   [Customize sheet]                     │
                    │     size → ice → sugar →                │
                    │     toppings → milk → qty               │
                    │              │ Add to Cart              │
                    │              └──────────────────────────┘
                    │
                    │ tap Checkout
                    ▼
              [Upsell: "Add boba? Go Large?"]
                    │ skip or add
                    ▼
              [Loyalty: phone number / skip]
                    │
                    ▼
              [Review order + total]
                    │ Pay
                    ▼
        ┌───────────────────────────────┐
        │  Terminal mode                │  Counter mode
        │  "Pay on the reader →"        │  "Pay at the counter"
        │  poll + webhook               │  order created unpaid
        └───────────────┬───────────────┘
                        ▼
              [Confirmation: ticket # K-042]
                        │ 10s
                        ▼
                  [Attract Loop]
```

Staff path, entered by long-pressing a corner:

```
[Any screen] ──long-press corner 5s──> [Manager PIN] ──> [Admin Panel]
                                                            ├─ Branch (first-run only)
                                                            ├─ Square connection status
                                                            ├─ Pair Terminal
                                                            ├─ Sync catalog
                                                            ├─ Network / Wi-Fi
                                                            └─ Exit kiosk mode
```

---

## 4. Architecture

### 4.1 Components

```
┌──────────────────────────┐
│  Android Kiosk App       │  Kotlin + Jetpack Compose
│  (smart TV, touchscreen) │  Local Room cache of catalog
└───────────┬──────────────┘
            │ HTTPS, device JWT
            ▼
┌──────────────────────────┐        ┌───────────────────┐
│  Tea Hut Backend         │◄──────►│  Square APIs      │
│  - staff accounts        │ OAuth  │  Catalog, Orders, │
│  - branch ↔ location map │ token  │  Terminal,        │
│  - Square token vault    │        │  Payments,        │
│  - API broker            │        │  Loyalty,         │
│  - webhook receiver      │◄───────│  Customers,       │
│  - admin web console     │webhook │  Inventory        │
└───────────┬──────────────┘        └───────────────────┘
            │
            ▼
    Postgres + Redis

        (physically beside the kiosk screen)
┌──────────────────────────┐
│  Square Terminal         │  takes the card payment
└──────────────────────────┘
```

### 4.2 Why a backend is not optional

It's tempting to have the Android app talk to Square directly and skip a server. That doesn't work here, for four reasons:

1. **Token security.** An OAuth refresh token that never expires, sitting on a device in a public lobby, is an unacceptable risk. Square's own OAuth best practices say not to expose tokens in client-side code. Server-side vault, kiosk gets a short-lived JWT instead.
2. **Webhooks need a public HTTPS endpoint.** Terminal checkout results, catalog updates, and payment status all arrive by webhook. A kiosk behind store Wi-Fi can't receive them.
3. **Token refresh must happen even when kiosks are off.** If every kiosk is powered down for a month, a device-side refresher would let the token lapse. A server cron doesn't.
4. **Multi-branch and multi-device.** One Square connection serving N kiosks across M branches needs a central place to hold the mapping.

The backend is small — roughly: auth, a token vault, a thin Square proxy, a webhook receiver, and an admin UI.

### 4.3 Tech stack

| Layer | Choice | Why |
|---|---|---|
| Kiosk app | Kotlin, Jetpack Compose, min SDK 26 | Native gives us reliable lock task mode and touch handling; Compose makes the modifier sheet fast to iterate |
| Local cache | Room (SQLite) | Catalog + pending orders survive restarts |
| Networking | Retrofit + OkHttp | Standard, good retry/interceptor story |
| Backend | Python FastAPI or Node/NestJS | Either is fine; FastAPI matches the tooling already in this repo |
| Square client | Official Square SDK (Python or Node) | Handles versioning and retries |
| Database | Postgres | Tokens, accounts, branch mapping, device registry |
| Cache/queue | Redis | Webhook dedupe, terminal-checkout polling state |
| Admin console | React SPA served by the backend | Owner-facing, desktop browser |
| Hosting | Single small cloud VM or container service | Load is trivial — a handful of kiosks |

### 4.4 Data model (backend)

```
staff_account   (id, email, password_hash, role, created_at)
branch          (id, name, address, square_location_id, timezone, active)
staff_branch    (staff_account_id, branch_id)              -- entitlements
square_conn     (id, merchant_id, access_token_enc, refresh_token_enc,
                 expires_at, scopes, environment, status, last_refreshed_at)
kiosk_device    (id, branch_id, name, device_jwt_hash, app_version,
                 last_seen_at, terminal_device_id, mode, status)
kiosk_order     (id, kiosk_device_id, square_order_id, square_payment_id,
                 ticket_number, state, total_cents, created_at)
catalog_cache   (branch_id, payload_json, square_catalog_version, synced_at)
audit_log       (id, actor, action, target, metadata_json, created_at)
```

Tokens are encrypted at rest with a KMS-held key, never logged, never returned by any API.

---

## 5. Square Long-Term Connection — How It Actually Stays Connected

This is the requirement you called out specifically, so here's the mechanism in detail.

1. **One-time authorization.** The owner opens the admin console on a laptop, clicks "Connect Square," and completes Square's OAuth authorization-code flow with the scopes in §2.2.6. This happens once, on a trusted machine — never on a kiosk in a store lobby.
2. **We store both tokens.** The access token expires in 30 days. The refresh token, obtained through the **code flow** (not PKCE), **does not expire**. PKCE refresh tokens are single-use and expire in 90 days, which is why we deliberately use the code flow with a client secret held server-side.
3. **Proactive refresh.** A scheduled job runs daily and refreshes any access token within 10 days of expiry — so roughly every 20 days, with a 10-day safety margin against outages.
4. **Reactive refresh.** Any Square call returning `401 UNAUTHORIZED` triggers an immediate refresh and one retry of the original request.
5. **Failure surfacing.** If a refresh fails (seller revoked access, app credentials rotated), the connection is marked `disconnected`, the owner is alerted, and the admin console shows a "Reconnect" button. Kiosks switch to cached-menu + pay-at-counter mode rather than showing a hard error to customers.
6. **What the kiosk holds.** Never a Square token. Each kiosk holds a device JWT issued by our backend, valid 24h, auto-renewed on each heartbeat. A stolen kiosk yields no Square credentials and can be revoked from the admin console.

Net effect: the owner authorizes once and never thinks about it again. That is the "long term" property.

---

## 6. Offline & Failure Behavior

Store Wi-Fi will drop. The kiosk must degrade gracefully rather than showing a stack trace to a customer.

| Failure | Behavior |
|---|---|
| Backend unreachable | Browse cached menu; checkout blocked with "Please order at the counter"; retry in background |
| Square API down | Same as above; existing carts preserved |
| Terminal offline / unpaired | Auto-fall back to pay-at-counter mode; alert to admin console |
| Payment declined | Clear message, return to payment screen, cart intact, customer can retry or cancel |
| Payment result ambiguous (network died mid-charge) | Never re-charge. Poll `GetTerminalCheckout` by idempotency key until resolved; show "Checking with the reader…" |
| Catalog sync fails | Keep serving the last good cache; show a small staff-visible warning in admin |
| App crash | Auto-restart into attract screen; cart discarded; crash reported to backend |

---

## 7. Security

- Square tokens encrypted at rest, server-side only, never on the device or in logs
- Kiosk authenticates with a short-lived, revocable device JWT
- Manager PIN is per-account, rate-limited, and lockout-protected after 5 failures
- All traffic TLS; certificate pinning on the kiosk against our backend
- No card data ever touches our app or the Android device — the Square Terminal handles it end to end, which keeps us out of PCI scope
- Customer phone numbers stored only in Square (loyalty), not mirrored in our database
- Full audit log of admin actions

---

## 8. Hardware Bill of Materials (per kiosk station)

| Item | Notes |
|---|---|
| Android touchscreen | The incell portable smart TV, **pending the Milestone 0 spike**. Fallback: Samsung Galaxy Tab A9+ on a floor stand |
| Square Terminal | Required for card payment; one per station |
| Floor or counter stand | With cable management and a lockable device enclosure |
| Power | Screen + Terminal; portable TVs have batteries but must run wired for all-day use |
| Network | Store Wi-Fi; strongly prefer a dedicated SSID for kiosks |
| Receipt printing | Terminal prints; or route to the existing kitchen printer via Square |

---

## 9. What Is Deliberately *Not* Being Built

Calling these out so expectations are set:

- **No cash acceptance.** Bill validators are expensive and out of scope; cash customers use the counter.
- **No custom kitchen display.** Square's existing KDS/printer setup receives kiosk orders automatically, because we create real Square orders.
- **No standalone menu editor.** The menu lives in Square Catalog — one source of truth, edited where staff already edit it. We only add kiosk-specific overrides (§3.9).
- **No public app store release.** Internal sideload / private distribution only.
- **No multi-tenant support.** Tea Hut only. If that changes later, the branch model already generalizes.

---

## 10. Estimated Effort

Rough, assuming one experienced full-stack + Android developer.

| Milestone | Scope | Estimate |
|---|---|---|
| **M0 — Hardware spike** | Validate the incell TV against §0.2 checklist; go/no-go on hardware | 1–2 days |
| **M1 — Backend foundation** | Accounts, branches, Square OAuth + token vault + refresh job, admin console skeleton | 1.5 weeks |
| **M2 — Catalog pipeline** | Catalog sync, cache, per-branch availability, image handling, admin sync UI | 1 week |
| **M3 — Kiosk ordering UI** | Attract, menu, customization sheet, cart, upsell — the bulk of the UX work | 2.5 weeks |
| **M4 — Payment** | Orders API, Terminal pairing + checkout, webhooks, all failure paths, idempotency | 1.5 weeks |
| **M5 — Loyalty** | Phone lookup, enrollment, points display | 0.5 week |
| **M6 — Kiosk lockdown** | Lock task mode, boot launch, admin panel, offline mode, crash recovery | 1 week |
| **M7 — Pilot** | One kiosk in one branch, live with real customers, fix what breaks | 1 week |
| **M8 — Rollout** | Remaining branches, reporting, remote config, OTA updates | 1 week |

**Total: roughly 10–11 weeks to a stable multi-branch rollout**, with a usable pilot around week 8.

---

## 11. Suggested Build Order

1. **M0 hardware spike first.** Everything else assumes the device works. Don't build 8 weeks of software against a screen we haven't validated.
2. **Backend + Square OAuth second.** The long-term connection is the foundational requirement you named; get it proven and refreshing before building UI on top.
3. **Catalog third.** Real Tea Hut menu data on screen early makes every later UI decision concrete.
4. **Ordering UI fourth**, and expect to iterate on the customization sheet — it's the screen customers spend the most time on and the one worth polishing.
5. **Payment fifth**, built against Square's sandbox, then a real Terminal.
6. **Lock it down, then pilot.**

---

## 12. Open Questions — Need Your Answers Before M1

1. **Payment hardware.** Do we buy Square Terminals (one per kiosk), or launch in pay-at-counter mode first? This is the biggest single decision and it's a cost question, not a technical one. *Recommendation: buy one Terminal for the pilot store, decide on the rest after seeing it work.*
2. **How many branches and how many kiosks per branch?** Affects Terminal count and rollout timeline.
3. **Is Tea Hut's Square catalog already fully built out** with modifier lists for ice/sugar/toppings? If not, that's setup work in Square before M2 and it's substantial for a tea menu.
4. **Loyalty:** is Square Loyalty already active on the account?
5. **Languages:** English only at launch, or English + Chinese from day one? Affects UI layout, not just strings.
6. **Attract screen content:** who supplies promo images/video, and how often do they change?
7. **Where does the backend get hosted?** Any existing cloud account or preference?
8. **Do you already own an incell unit** we can test, or should M0 include purchasing one?

---

## 13. Sources

Research behind §0 and §5:

- [Square — Take Payments and Build Integrations on Square Hardware](https://developer.squareup.com/docs/in-person-payment-options)
- [Square — Mobile Payments SDK](https://developer.squareup.com/docs/mobile-payments-sdk)
- [Square — Build on Android (Mobile Payments SDK)](https://developer.squareup.com/docs/mobile-payments-sdk/android)
- [Square — Terminal API Overview](https://developer.squareup.com/docs/terminal-api/overview)
- [Square — Connect a Square Terminal to a POS Application](https://developer.squareup.com/docs/terminal-api/integrate-square-terminal)
- [Square — OAuth API Overview](https://developer.squareup.com/docs/oauth-api/overview)
- [Square — Refresh, Revoke, and Limit Scope of OAuth Tokens](https://developer.squareup.com/docs/oauth-api/refresh-revoke-limit-scope)
- [Square — OAuth Best Practices](https://developer.squareup.com/docs/oauth-api/best-practices)
- [Square — In-Person Payments APIs & SDKs](https://developer.squareup.com/us/en/in-person-payments)
- [Square — Announcing Mobile Payments SDK GA and New Terminal API Features](https://developer.squareup.com/blog/announcing-mobile-payments-sdk-ga-and-new-terminal-api-features/)
- [Square Kiosk product announcement](https://squareup.com/us/en/press/announcing-square-kiosk)
- [Chowbus — Restaurant Self Ordering Kiosk](https://www.chowbus.com/hardware/restaurant-kiosk)
- [MenuSifu — Best Self Ordering Kiosk for Restaurants](https://www.menusifu.com/hardware/restaurant-kiosk)
- [MenuSifu — Boba Kiosk: 10 Key Features for Faster Bubble Tea Ordering](https://www.menusifu.com/blog/boba-shop-kiosk-system)
- [MenuSifu — The Ultimate POS System for Bubble Tea Shops](https://www.menusifu.com/restaurants/bubble-tea-pos-system)
