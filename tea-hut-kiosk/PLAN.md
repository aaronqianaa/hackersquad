# Tea Hut Self-Order Kiosk — Product & Technical Plan

**Status:** Draft v1, for review. No code written yet.
**Target:** Android touchscreen portable smart TV (in-cell touch panel), internal use at Tea Hut stores only.
**Backend of record:** Square (menu, orders, payments, locations).

---

## 0. Read this first — three decisions that shape everything

### 0.1 Square forbids taking card payments *on the kiosk device itself*

Square's Mobile Payments SDK (the SDK that would let an Android device drive a Square Reader
directly) explicitly prohibits use in **unattended terminals or unattended kiosks**. A self-order
kiosk is exactly that. So the kiosk screen cannot be the card-reading device.

Square's own first-party "Square Kiosk" product sidesteps this by running on Square Register
hardware, which is locked — we cannot deploy a custom app onto it.

**Recommended payment architecture: Terminal API.** Each kiosk screen is paired 1:1 with a
**Square Terminal** sitting next to it. The kiosk builds the order and asks Square to push a
checkout to that Terminal; the customer taps/dips/swipes on the Terminal; Square notifies us by
webhook. Card data never touches our app or our servers, which also removes essentially all PCI
scope from this project — a large, permanent saving.

Fallbacks layered on top (all planned below): **QR-code pay** (customer scans, pays on their own
phone) and **pay at counter** (kiosk prints/holds an unpaid ticket).

> Cost implication to confirm: one Square Terminal per kiosk screen. If Tea Hut wants kiosks
> without a Terminal at each one, we go QR-only at those stations. This is the single biggest
> open question in the plan — see §11.

### 0.2 A backend server is required. The kiosk cannot talk to Square alone

Square OAuth tokens are merchant-wide credentials. They cannot live on a device sitting in a
public lobby, and they must be refreshed on a schedule the device can't guarantee. We need a small
always-on backend to hold tokens, refresh them, receive Square webhooks, and broker every call.

This also *is* the "long-term connection" the brief asks for. See §4.

### 0.3 On copying Chowbus / MenuSifu

Their **flows and feature sets** are industry-standard for boba QSR and this plan mirrors them
closely and deliberately — attract loop, category rail, sugar/ice/topping modifier ladder, cart
drawer, tip screen, order-number handoff. That's the right call and it's what §5 specifies.

What I will not do is decompile their APKs or lift their code, images, icons, fonts, or copy. That
creates real legal exposure (copyright, and their EULAs) for a shipping production system, and it
buys nothing — the hard part here is the Square integration, not the screens. "Internal only, not
publicly announced" doesn't change the exposure, since the kiosk sits in a public lobby where
customers use it. We build lookalike UI from scratch with Tea Hut's own branding.

---

## 1. System architecture

```
┌─────────────────────────┐     ┌──────────────────────────┐
│  Kiosk (Android TV/tab) │     │  Square Terminal         │
│  Kotlin + Compose       │     │  (customer taps card)    │
│  locked in kiosk mode   │     └───────────┬──────────────┘
└───────────┬─────────────┘                 │
            │ HTTPS (device token)          │ Square cloud
            ▼                               ▼
     ┌──────────────────────────────────────────────┐
     │  Tea Hut Kiosk Backend (FastAPI + Postgres)  │
     │  • staff accounts, roles, device registry    │
     │  • Square OAuth token vault + auto-refresh   │
     │  • menu sync cache, order broker             │
     │  • webhook receiver, admin console           │
     └──────────────────┬───────────────────────────┘
                        │ Square APIs (OAuth)
                        ▼
     ┌──────────────────────────────────────────────┐
     │  Square: Locations · Catalog · Inventory ·   │
     │  Orders · Terminal · Payments · Loyalty      │
     │  → orders land in Square POS / KDS / printer │
     └──────────────────────────────────────────────┘
```

**Stack choice.** Backend in **FastAPI + Postgres**, matching this repo's existing stack so the
team maintains one language server-side. Kiosk in **Kotlin + Jetpack Compose**, Room for the
offline menu cache, DataStore for device config, Retrofit/OkHttp, Hilt.

**Why not a web app in a browser?** Kiosk mode lockdown, reliable auto-start on boot, local label
printing, and offline menu caching are all materially harder in a browser on Android. Native is
the right call for a device that must survive a power cut unattended.

---

## 2. Feature list — device provisioning & kiosk lockdown

| # | Feature | Notes |
|---|---|---|
| 1.1 | Single-app kiosk lockdown | Lock task mode via Device Owner (COSU), not screen pinning — screen pinning can be exited by anyone. Requires provisioning the TV as a managed device |
| 1.2 | Auto-launch on boot | `BOOT_COMPLETED` receiver; survives power loss |
| 1.3 | Hardware key / nav bar / status bar suppression | No escape to Android settings |
| 1.4 | Screen-always-on + brightness lock | `FLAG_KEEP_SCREEN_ON`, wake lock |
| 1.5 | Hidden staff escape hatch | Long-press corner + staff PIN → exits to admin panel |
| 1.6 | Orientation lock | Portrait or landscape per store; configurable |
| 1.7 | Scheduled nightly reboot | Reduces drift/memory leaks on always-on hardware |
| 1.8 | Remote reboot / remote menu-resync from admin console | |
| 1.9 | Device heartbeat + offline alerting | Backend pages a manager if a kiosk goes dark >5 min during store hours |

## 3. Feature list — accounts, login, branch selection

| # | Feature | Notes |
|---|---|---|
| 2.1 | Staff/manager accounts (email + password) in Tea Hut backend | Separate from Square logins |
| 2.2 | Roles: Owner / Manager / Staff | Owner alone can connect Square and add branches |
| 2.3 | Login on kiosk at setup time | Not per-customer — customers never log in |
| 2.4 | **Branch (Square Location) picker after login** | Pulls the live location list from Square; staff taps the branch |
| 2.5 | Device binds to that branch permanently | Issues a long-lived **device token**; kiosk never re-logs-in |
| 2.6 | Device token rotation + remote revoke | Kill a lost/stolen kiosk from the admin console |
| 2.7 | PIN-protected admin panel on device | Staff PIN, auto-locks after 60s idle |
| 2.8 | Multi-branch support from day one | Tea Hut can add branches without a new build |
| 2.9 | Optional per-device pairing code flow | Manager enters a 6-digit code from the console instead of typing a password on a touchscreen |

## 4. Feature list — Square connection (the "long-term" link)

This is the part the brief calls out specifically, so it gets its own detail.

| # | Feature | Notes |
|---|---|---|
| 3.1 | One-time Square OAuth authorization by the owner | Web flow, in the admin console — **authorization-code flow, not PKCE** |
| 3.2 | Encrypted token vault | Access + refresh token per merchant, encrypted at rest, never sent to the device |
| 3.3 | **Proactive token refresh every ≤7 days** | Square access tokens expire at 30 days. Refreshing at 7 leaves 3 weeks of headroom to notice and fix a failure. Refresh tokens from the code flow do not expire — so the connection is genuinely permanent as long as the refresh job runs |
| 3.4 | Token-age monitor + alerting | Alert if any stored token is older than 8 days — catches a silently broken refresh job before it becomes a dead kiosk on a Saturday |
| 3.5 | Reconnect flow | If the merchant revokes access, admin console shows "Reconnect Square" and kiosks fall back to a maintenance screen |
| 3.6 | Location → branch mapping | Square Location ID stored per branch |
| 3.7 | Terminal device pairing | Generate device code → sign in on the Square Terminal → receive device ID by webhook → store against the kiosk |
| 3.8 | Scope minimization | Request only: `MERCHANT_PROFILE_READ`, `ITEMS_READ`, `INVENTORY_READ`, `ORDERS_READ/WRITE`, `PAYMENTS_READ/WRITE`, `DEVICE_CREDENTIAL_MANAGEMENT`, plus loyalty/gift-card scopes if those features are enabled |
| 3.9 | Sandbox vs production environment toggle | Per-deployment, so we can rehearse with fake cards |

## 5. Feature list — menu sync (Square Catalog → kiosk)

| # | Feature | Notes |
|---|---|---|
| 4.1 | Catalog sync: categories, items, variations, prices | Square is the single source of truth. Staff edit the menu in Square, not in our app |
| 4.2 | Sizes as item **variations** | M / L |
| 4.3 | Customizations as **modifier lists** | Sugar (0/30/50/70/100%), Ice (none/less/regular/extra), Toppings (multi-select, priced), Milk swap, Hot/Iced |
| 4.4 | Per-item modifier rules | Min/max selections, required vs optional, default values (e.g. "regular ice" preselected) |
| 4.5 | Item images | Synced from Square; fallback placeholder; local disk cache |
| 4.6 | Kitchen names for modifiers | Square supports separate customer-facing vs kitchen names — use them so tickets read cleanly |
| 4.7 | Dietary/attribute tags | Caffeine, Contains Nuts, Dairy-Free, Hot, Iced, Seasonal, New, Spicy |
| 4.8 | Sold-out / 86 handling | Inventory counts + item availability → item greys out and cannot be added |
| 4.9 | Per-branch menu | Prices and availability differ by location — respect the location's own catalog/pricing |
| 4.10 | Incremental sync | Poll every 5 min + push on catalog webhook + manual "Sync now" |
| 4.11 | Bilingual menu names | EN / 中文 per item; falls back to Square name if no translation set |

## 6. Feature list — customer ordering UX

The core flow, mirroring the standard boba-kiosk pattern:

```
Attract loop → [tap] → Dine in / Take out → Menu browse → Item detail (size→sugar→ice→toppings)
   → Cart → Upsell → Checkout (name/phone/promo) → Tip → Pay on Terminal → Order number → Attract
```

| # | Feature | Notes |
|---|---|---|
| 5.1 | Attract / screensaver loop | Looping video or image carousel, uploadable per branch from admin console. Tap anywhere to start |
| 5.2 | Language toggle EN / 中文 | Persistent header toggle; resets to default after each order |
| 5.3 | Dine-in vs Take-out selector | Maps to Square dining option + fulfillment type so it filters correctly on KDS |
| 5.4 | Category rail + item grid | Large photo cards, name, price. Thumb-reachable, 44dp+ targets |
| 5.5 | Search | Optional — on-screen keyboard, useful once the menu passes ~40 items |
| 5.6 | Item detail sheet | Stepped modifier selection, live running price, quantity stepper |
| 5.7 | Special instructions | Free-text note per line item, capped length, profanity filter |
| 5.8 | Upsell prompts | "Add boba for $0.75?" on item add; "Add a snack?" at cart. This is where kiosks earn their keep on average order value |
| 5.9 | Cart drawer | Edit modifiers, change qty, remove, clear cart |
| 5.10 | Idle timeout | 60s warning modal → 90s auto-cancel and return to attract, cart discarded |
| 5.11 | Order name / number entry | Customer's first name for the cup label |
| 5.12 | Promo / discount code entry | Square discounts and comps |
| 5.13 | Loyalty enrolment + redemption | Phone-number lookup at checkout; earn points, redeem rewards. Works across branches |
| 5.14 | Accessibility mode | "Lower the screen" toggle for wheelchair reach, large-text mode, high-contrast palette |
| 5.15 | Big-button, high-contrast visual design | Tea Hut branding; designed for a glossy in-cell panel under store lighting |

## 7. Feature list — payment & fulfillment

| # | Feature | Notes |
|---|---|---|
| 6.1 | **Terminal API checkout (primary)** | Kiosk creates the Square Order → backend creates a Terminal checkout on the paired Terminal → live status on the kiosk screen ("Please tap your card on the terminal") |
| 6.2 | Live checkout status | Pending → In progress → Completed / Canceled, driven by webhook + polling fallback |
| 6.3 | Payment timeout & cancel | Customer can cancel; auto-cancel after 2 min and release the cart |
| 6.4 | Decline / retry handling | Clear message, retry, or switch to another method |
| 6.5 | **QR-code pay (fallback)** | Square payment link rendered as a QR; customer pays on their phone. Also the answer for kiosks with no Terminal |
| 6.6 | **Pay at counter (fallback)** | Sends an unpaid open ticket to the POS; customer pays at the register |
| 6.7 | Tip screen | Configurable presets (%, flat, none), skippable, per-branch on/off |
| 6.8 | Gift card support | Square gift cards as a tender |
| 6.9 | Cash — explicitly out of scope on the kiosk | Routes to "pay at counter" |
| 6.10 | Order pushes to Square POS / KDS | Correct fulfillment type and dining option so kitchen routing and filters work |
| 6.11 | Cup label printing | Local Bluetooth/USB/network label printer, one label per drink with modifiers — the boba-shop-specific requirement |
| 6.12 | Order number display + confirmation screen | Large number, hold ~8s, auto-return to attract |
| 6.13 | Digital receipt | Email / SMS / on-screen QR. Optional paper receipt if a printer is attached |
| 6.14 | Refunds | **Not on the kiosk.** Staff handle refunds in Square POS — deliberate, prevents obvious abuse |

## 8. Feature list — admin console (web)

| # | Feature |
|---|---|
| 7.1 | Square connect / reconnect / connection health |
| 7.2 | Branch list, add/edit branch, map to Square Location |
| 7.3 | Kiosk device registry: name, branch, paired Terminal, last heartbeat, app version |
| 7.4 | Per-branch config: tip presets, languages, idle timeouts, dine-in enabled, upsell rules |
| 7.5 | Screensaver / promo media upload per branch |
| 7.6 | Staff accounts and roles |
| 7.7 | Live order feed + kiosk-attributed sales reporting |
| 7.8 | Remote actions: resync menu, reboot, revoke device, put into maintenance mode |
| 7.9 | Audit log of admin actions |

## 9. Feature list — reliability, offline & ops

| # | Feature | Notes |
|---|---|---|
| 8.1 | Offline menu cache (Room) | Kiosk keeps browsing during a network blip |
| 8.2 | Degraded mode | Network down → allow browsing, block payment, show "Please order at the counter" |
| 8.3 | Idempotent order creation | Idempotency keys on every Square write so a retry never double-charges |
| 8.4 | Local order queue + replay | Unsent orders replay on reconnect, deduplicated |
| 8.5 | Crash reporting + remote logs | |
| 8.6 | Remote app update | MDM-driven or in-app updater |
| 8.7 | Webhook signature verification, replay protection | |
| 8.8 | Rate limiting + backoff against Square | |
| 8.9 | Health dashboard | All kiosks across all branches, one screen |

## 10. Security & compliance

- **PCI scope: minimal by design.** Card data is entered on Square Terminal hardware and never
  passes through our app, our device, or our servers.
- Square OAuth tokens encrypted at rest, held server-side only, never on the device.
- Device tokens are per-device, revocable, rotating.
- TLS everywhere; certificate pinning on the kiosk→backend channel.
- Staff PIN with lockout after failed attempts; admin panel auto-locks at 60s idle.
- No customer PII stored beyond what Square already holds — phone/email for receipts and loyalty
  pass straight through to Square rather than being stored by us.
- Full audit log of admin and device actions.

---

## 11. Open questions — I need answers to these before building

1. **Is there a Square Terminal at each kiosk station, or do we need QR-only?** This is the top
   question — it changes the payment module and the hardware budget.
2. **Exact TV model, Android version, and does it have Google Play Services?** Some portable
   smart-TV panels ship AOSP-only, which affects the update path and Play-dependent libraries.
3. **Can the device be provisioned as Device Owner?** Needed for true kiosk lockdown. If the
   vendor ships it pre-provisioned or without factory-reset access, we fall back to screen pinning
   plus a physical lock.
4. **How many branches now, and how many planned?**
5. **Is Tea Hut already on Square POS with the full menu built in Square Catalog?** If the menu
   isn't in Square yet, that's a prerequisite work item, not a build item.
6. **Is Square KDS in use, or paper tickets from a kitchen printer?**
7. **Label printer** — make/model, and is one already in the store?
8. **Square Loyalty** — active subscription? Drives whether §6.5.13 is in Phase 2 or dropped.
9. **Tipping on the kiosk** — yes or no? (Reasonable arguments both ways for a boba QSR.)
10. **Languages** — EN + 中文 confirmed? Simplified, traditional, or both?

---

## 12. Proposed phasing

| Phase | Scope | Rough size |
|---|---|---|
| **0 — Spike** | Prove Square OAuth + Terminal API checkout end-to-end in sandbox; prove kiosk lockdown on the actual TV hardware | ~1 week. **Do this before committing to the rest** — it de-risks both unknowns |
| **1 — Core ordering** | Backend + auth + branch select + catalog sync + browse/customize/cart + Terminal payment + order to POS + confirmation | ~4–6 weeks |
| **2 — Store-ready** | Kiosk lockdown hardening, offline mode, cup labels, receipts, tip screen, attract loop, admin console v1, bilingual | ~3–4 weeks |
| **3 — Growth** | Loyalty, promos, upsell rules engine, gift cards, QR fallback, reporting, multi-branch rollout tooling | ~3–4 weeks |
| **4 — Pilot** | One branch, one kiosk, live, staff-attended. Iterate on real customer behaviour before rolling out | ~2 weeks |

Phase 0 matters more than it looks. Both of its unknowns — whether Square Terminal pairing behaves
the way the docs describe, and whether this particular TV can be made a Device Owner — are cheap to
test now and expensive to discover in week five.

---

## 13. References

- [Square in-person payment options](https://developer.squareup.com/docs/in-person-payment-options)
- [Square Mobile Payments SDK](https://developer.squareup.com/docs/mobile-payments-sdk) — note the unattended-kiosk prohibition
- [Square Terminal API overview](https://developer.squareup.com/docs/terminal-api/overview) · [connecting a Terminal to a POS app](https://developer.squareup.com/docs/terminal-api/integrate-square-terminal)
- [Square OAuth best practices](https://developer.squareup.com/docs/oauth-api/best-practices) · [refresh/revoke tokens](https://developer.squareup.com/docs/oauth-api/refresh-revoke-limit-scope)
- [Square Orders API](https://developer.squareup.com/docs/orders-api/what-it-does) · [fulfillments](https://developer.squareup.com/docs/orders-api/fulfillments)
- [Square Catalog: manage menus](https://developer.squareup.com/docs/catalog-api/manage-menus)
- [Square KDS order routing](https://squareup.com/help/us/en/article/7959-route-orders-with-your-kds)
- [Android lock task mode](https://developer.android.com/work/dpc/dedicated-devices/lock-task-mode)
- Feature-set reference: [Chowbus kiosk ordering](https://pos.chowbus.com/en/products/kiosk-ordering) · [MenuSifu boba kiosk features](https://www.menusifu.com/blog/boba-shop-kiosk-system)
