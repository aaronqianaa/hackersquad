# Tea Hut Self-Ordering Kiosk — Build Plan

**Status:** Draft v1 — for review, not yet approved
**Owner:** Tea Hut
**Target hardware:** In-cell touchscreen portable smart TV, Android
**POS / payments backend:** Square
**Distribution:** Private (Tea Hut internal only), not published to Google Play

---

## 1. What we are building, in one paragraph

An Android self-ordering kiosk for Tea Hut. Staff log in with their own account,
pick which store branch the device is serving, and hand the screen to customers.
Customers browse the tea menu, customize drinks (size, ice, sugar, toppings),
add to cart, optionally identify as a member, and pay. The menu, orders, payments,
and reporting all live in Tea Hut's existing Square account, so the kiosk is a new
ordering *surface* on top of Square, not a second POS to reconcile. The link between
the kiosk system and the Square account is established once by an owner/manager and
then stays alive indefinitely without anyone re-authorizing it.

---

## 2. Three findings that shape the whole design

These came out of studying how Square's platform actually permits kiosks to be built.
Please read these before the feature list — each one is a constraint, not a preference.

### 2.1 The TV panel cannot take the card payment itself

Square's **Mobile Payments SDK** and the older **Reader SDK** both state that using them
for payment solutions in *unattended terminals or unattended kiosks is strictly prohibited*.
That rules out putting a Square reader on the TV and charging the card in our own app.

The supported path for a custom ordering kiosk is the **Terminal API**: our app builds the
order, then sends a checkout request to a **paired Square Terminal** sitting next to the
screen. The customer taps/dips/swipes on the Terminal, which handles the card data, tipping,
and printed receipt. Our app never touches card data — which also keeps Tea Hut out of PCI
scope. This is the same approach used by the published Square kiosk integrations
(Flash Order, Mobi2Go, KAIKAKU).

**Consequence:** each kiosk station = 1 Android touchscreen (ordering) + 1 Square Terminal
(payment). Budget for the Terminal per station.

**Action item before build starts:** confirm in writing with Square's developer/partner
support that our specific deployment is approved, and whether they classify a
staffed tea shop kiosk as "attended." This is the single biggest go/no-go risk in the plan.

### 2.2 The Square connection must live on a server, not on the tablet

To make the Square link "long term" and safe:

- Square OAuth **access tokens expire in 30 days**.
- A **refresh token obtained through the authorization-code flow does not expire**, and can
  be exchanged for new access tokens indefinitely. (The PKCE flow's refresh tokens are
  single-use and expire in 90 days — so we deliberately use the code flow, not PKCE.)

That means: a small backend service holds the OAuth client secret and refresh token,
renews the access token automatically on a schedule, and the kiosk device never stores a
Square credential at all. The kiosk talks only to our backend. If a device is stolen, no
Square access leaks with it — we just revoke that one device.

This backend is also required anyway, because Square's Terminal and Order **webhooks need a
public HTTPS endpoint** to call, and a tablet cannot be one.

### 2.3 Staff accounts and branch selection are our system, not Square's

Square's own employee/team permissions do not map cleanly to "which kiosk is pointed at which
store." So we own: user accounts, roles, which branches a user may operate, and the
device→branch binding. Branch selection is backed by Square **Locations** — each Tea Hut
branch is a Square location ID — so orders land in the right store's Square dashboard.

---

## 3. Reference apps and what we take from them

Chowbus POS and MenuSifu POS kiosks are the closest reference for a bubble-tea shop, and
their published feature sets line up with what Tea Hut needs:

| Pattern from references | Why it matters for Tea Hut |
|---|---|
| Native handling of complex combos and modifier logic | Bubble tea is modifier-heavy: size, ice %, sugar %, multiple toppings |
| Real bilingual operation (not a bolted-on translation layer) | Both are built for Asian-cuisine restaurants; EN + 中文 is table stakes |
| Loyalty/membership sign-up prompted inside the checkout flow | Reported as the highest-leverage moment for member conversion |
| Timed upsell prompts — add-ons, combo upgrades, premium items | Directly targets average order value |
| Kiosk syncs live to POS, KDS, and inventory | Orders must appear in the kitchen without re-keying |
| Dine-in vs take-out selection up front | Drives fulfillment type and tax/packaging behavior |

**Scope note on copying:** we replicate these *interaction patterns and flows*, which are
industry-standard and not owned by any one vendor. We will not copy their code, image assets,
fonts, icon sets, or trademarks, and the app will carry Tea Hut's own branding. That keeps the
result functionally equivalent to the references without importing someone else's IP into
Tea Hut's product. Everything in the feature list below is achievable this way.

---

## 4. Architecture

```
┌───────────────────────────────┐
│  Android kiosk app (Kotlin)   │   in-cell touchscreen smart TV
│  - locked in kiosk mode       │
│  - offline menu cache (Room)  │
│  - no Square credentials      │
└───────────┬───────────────────┘
            │ HTTPS + device JWT (device never sees Square tokens)
            ▼
┌───────────────────────────────┐
│  Tea Hut Kiosk Backend        │   FastAPI + Postgres + Redis
│  - staff accounts / roles     │
│  - branch + device registry   │
│  - Square OAuth token vault   │   ← refresh token, auto-renewed
│  - menu sync + kiosk overrides│
│  - order + payment orchestr.  │
│  - webhook receiver           │ ◄── Square webhooks (terminal, order, oauth revoked)
└───────────┬───────────────────┘
            │ Square Connect v2 APIs
            ▼
┌───────────────────────────────┐        ┌────────────────────┐
│  Square                       │───────►│  Square Terminal   │  card, tip, receipt
│  Locations / Catalog /        │        │  (paired per lane) │
│  Inventory / Orders /         │        └────────────────────┘
│  Terminal / Customers /       │
│  Loyalty / Gift Cards         │───────► Square Dashboard, KDS, reporting
└───────────────────────────────┘
```

**Stack choices and why:**

- **Android app: Kotlin + Jetpack Compose (native).** Kiosk lockdown (device-owner APIs,
  lock task mode, custom launcher, boot receiver) is native-only territory, and a cheap
  in-cell panel may not ship Google Play Services — a native build has the fewest external
  dependencies. Flutter/React Native would add risk here for no gain.
- **Backend: FastAPI + Postgres + Redis.** Matches the stack already in use in this
  organization, so there is no new runtime to learn or operate.
- **Admin console: server-rendered web app** on the same backend. Staff use it from a laptop
  or phone; it does not need to be a separate SPA.

**Data flow for one order:**
attract screen → order type → menu (from local cache) → item customization → cart →
member lookup (optional) → backend `CreateOrder` in Square → backend `CreateTerminalCheckout`
against that `order_id` → customer pays on the Terminal → Square webhook → backend pushes
status to the device → success screen with order number → ticket appears on KDS.

---

## 5. Screen-by-screen flow

### Staff-facing (before the kiosk goes live)

| # | Screen | Contents |
|---|---|---|
| S1 | Device provisioning (one time) | Backend URL, 8-char enrollment code issued from the admin console, device names itself (e.g. "Front Lane 1") |
| S2 | Staff login | Email + password on first login; 6-digit PIN for subsequent logins on that device |
| S3 | Branch selection | List of Tea Hut branches pulled from Square Locations, filtered to branches this user may operate; shows the branch's Square connection health |
| S4 | Terminal pairing | Shows the device code to type into the Square Terminal; confirms pairing before the lane can accept payments |
| S5 | Pre-flight check | Green/red list: Square connected, menu synced (with timestamp), Terminal paired, printer/KDS reachable, network OK |
| S6 | "Start Kiosk" | Locks into customer mode; exiting requires a manager PIN |
| S7 | Manager panel (PIN-gated) | Force menu re-sync, 86 an item for today, re-pair Terminal, view last 20 orders, exit kiosk, app version/update |

### Customer-facing

| # | Screen | Contents |
|---|---|---|
| C1 | Attract loop | Full-screen video/promo carousel, "Touch to Order", branch name |
| C2 | Language | EN / 中文 — also switchable from a persistent header button on every screen |
| C3 | Order type | Dine In / Take Out (drives Square fulfillment type) |
| C4 | Menu browse | Category rail, item grid with photos and prices, Featured and Combos rails, search |
| C5 | Item detail | Size/variation, required modifier groups (ice level, sugar level), optional groups (toppings, multi-select with per-option price and max count), quantity, special notes |
| C6 | Suggested add-on | Timed upsell — topping upgrade, combo upgrade, premium tea base |
| C7 | Cart review | Line items with all modifiers, edit/remove, quantity, subtotal/tax/total, promo code entry |
| C8 | Member | Phone-number lookup against Square Customers/Loyalty; show points, redeemable rewards; one-tap enroll for new members |
| C9 | Name for pickup | First name or nickname → printed on the ticket and shown on the pickup display |
| C10 | Payment handoff | "Please pay at the card reader" with live status, animated pointer to the Terminal, cancel button, timeout countdown |
| C11 | Success | Big order number, "receipt printed at the reader", optional SMS/email receipt, auto-return to attract after ~12s |
| C12 | Failure / declined | Plain-language reason, Retry / Change payment / Get help — never dumps a raw API error |
| C13 | Idle timeout | After ~60s of no touch: "Still there?" → 15s countdown → clear cart, return to attract |

**Accessibility & ergonomics:** portrait-first layout with a landscape fallback (many portable
TVs are hardware landscape-locked); all interactive targets ≥ 48dp; primary actions in the
lower half of a tall screen so they stay in reach; high-contrast mode; text scale toggle.

---

## 6. Feature list

Full checklist with priorities lives in **[docs/FEATURES.md](docs/FEATURES.md)**. Summary of
the major groups:

1. **Accounts & access** — staff accounts, roles (Owner / Manager / Staff), per-branch
   permissions, PIN quick-login, forced re-auth, audit log.
2. **Branch & device management** — branch list from Square Locations, device enrollment,
   device→branch binding, remote menu refresh, remote lock/unlock, device health heartbeat.
3. **Square connection** — one-time OAuth authorization, automatic token renewal, connection
   health dashboard, revocation handling, re-auth alerting.
4. **Menu** — Catalog sync (items, variations, modifier lists, categories, images), delta sync,
   inventory-driven auto-86, kiosk-only overrides (hide, rename, re-photo, re-order, feature).
5. **Ordering** — dine-in/take-out, browse, search, item customization, cart edit, promo codes,
   order notes, pickup name.
6. **Payment** — Terminal API checkout, live status, tip on the Terminal, cancel/retry,
   decline handling, gift cards, split-to-cash fallback via staff assist.
7. **Membership & loyalty** — phone lookup, points display, reward redemption, in-flow enrollment.
8. **Merchandising** — featured items, combos, timed upsell prompts, attract-screen media,
   scheduled promos (e.g. happy hour).
9. **Kiosk hardening** — lock task mode, boot auto-start, immersive full-screen, screen-burn
   protection, watchdog restart, offline behavior, OTA updates.
10. **Admin console & reporting** — user management, menu overrides, media upload, kiosk
    analytics (conversion, AOV, abandonment rate, upsell take rate), error log.

---

## 7. Square API surface

| Area | API | Notes |
|---|---|---|
| Authorization | OAuth API (`ObtainToken`, authorization-code flow) | Non-expiring refresh token; renew access token well before its 30-day expiry |
| Branches | Locations API | One Square location per Tea Hut branch |
| Menu | Catalog API | Items, item variations, modifier lists, categories, images; use catalog version for delta sync |
| Stock | Inventory API | Drives automatic 86 of sold-out toppings/items |
| Orders | Orders API | Line items + modifiers + discounts + taxes, fulfillment (pickup + recipient name), `ticket_name`, `source`, metadata for kiosk/device attribution |
| Terminal pairing | Devices API (`CreateDeviceCode`) | Requires `DEVICE_CREDENTIAL_MANAGEMENT` scope; pairing confirmed via webhook returning the device ID |
| Payment | Terminal API (`CreateTerminalCheckout`) | References the `order_id`; tip settings configured on the checkout |
| Members | Customers API + Loyalty API | Phone lookup, points, reward redemption, enrollment |
| Gift cards | Gift Cards API | Balance check and redemption |
| Events | Webhooks | `terminal.checkout.updated`, `order.updated`, `payment.updated`, `oauth.authorization.revoked`, device pairing |

**Cross-cutting:** idempotency keys on every mutating call; exponential backoff with jitter on
429/5xx; every Square call logged with request ID for support escalation.

---

## 8. Security

- Square client secret and refresh token stored **server-side only**, encrypted at rest.
- Kiosk devices authenticate with a per-device JWT that rotates; revocable individually from
  the admin console.
- No card data ever enters our app or backend — the Square Terminal owns that path, so Tea Hut
  stays out of PCI DSS scope beyond SAQ-A-level obligations.
- Staff passwords hashed with Argon2; PINs are per-device and rate-limited with lockout.
- Manager PIN required to exit kiosk mode, void, or change branch.
- Full audit log: logins, branch changes, 86 actions, menu overrides, kiosk exits, refunds.
- TLS everywhere; webhook signature verification on every inbound Square event.

---

## 9. Delivery phases

| Phase | Deliverable | Est. |
|---|---|---|
| **0. Decisions & procurement** | Confirm Terminal API approval with Square, confirm the exact TV model can be set as device owner, order 1 Square Terminal + 1 panel for the pilot lane | 1 wk |
| **1. Backend foundation** | FastAPI service, Postgres schema, staff accounts + roles, Square OAuth connect flow, token auto-renewal job, branch list from Locations | 2 wks |
| **2. Android shell** | Kotlin app, device enrollment, kiosk lockdown, staff login, branch selection, pre-flight screen | 2 wks |
| **3. Menu** | Catalog sync + delta sync, local cache, browse/search, item customization with modifier logic, cart | 2–3 wks |
| **4. Payment** | Terminal pairing, order creation, Terminal checkout, webhook status pipeline, receipts, success/failure/retry | 2 wks |
| **5. Members & merchandising** | Loyalty lookup/redeem/enroll, promo codes, gift cards, upsell prompts, attract media | 2 wks |
| **6. Admin console & reporting** | User management, menu overrides, media upload, kiosk analytics, OTA update channel | 1–2 wks |
| **7. Pilot & hardening** | One lane at one branch for 2 weeks, soak testing, offline/network-drop drills, staff training, rollout runbook | 2 wks |

**Rough total: 12–15 weeks for one full-time developer**, assuming Phase 0 clears without a
Square policy blocker. Phases 1–4 are the minimum viable kiosk that can take a real order.

---

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Square does not approve the unattended-kiosk deployment | **Blocks the project** | Resolve in Phase 0, in writing, before any code. Fallback: staff-attended framing, or Square's own first-party Kiosk product |
| The in-cell TV cannot be set as Android device owner (needed for true lockdown) | Kiosk can be exited by customers | Test on the actual unit in Phase 0. Fallback: replace the home launcher + immersive sticky mode + navigation blocking (weaker but workable) |
| Panel ships without Google Play Services | No FCM push, no Play updates | Design assumes this: WebSocket/poll for push, self-hosted APK update channel |
| Hardware landscape-locked | Portrait design unusable | Build both layouts from day one; decide the primary at Phase 0 after seeing the unit |
| Network drop mid-order | Customer stuck at payment | Menu served from local cache so browsing survives; block *new* checkouts when offline with a clear "please order at the counter" message; never queue a payment locally |
| Square catalog can't express a needed kiosk behavior | Menu gaps | Kiosk-override layer in our backend from the start (Phase 3), rather than bolted on later |
| Modifier pricing drift between kiosk and counter | Wrong charges | Single source of truth is Square Catalog; overrides may change presentation but never price |

---

## 11. Open questions for Tea Hut

Answers to these change the build — see **[docs/OPEN-QUESTIONS.md](docs/OPEN-QUESTIONS.md)**
for the full list. The blocking ones:

1. How many branches and how many kiosk lanes per branch at launch?
2. Does Tea Hut already own Square Terminals, or do they need to be purchased?
3. Exact model of the in-cell smart TV — needed to test device-owner lockdown and orientation.
4. Is there an existing Square loyalty program to connect to, or does one need creating?
5. Should the kiosk print a customer-facing ticket, or is the Terminal's receipt enough?
6. Dine-in: does Tea Hut want table numbers, or is everything pickup-at-counter?

---

## 12. What is explicitly out of scope for v1

- Delivery / third-party marketplace integration
- Table-side QR ordering (separate surface, can reuse this backend later)
- Cash acceptance hardware
- Any POS replacement — Square remains the POS of record
- Public Play Store distribution
