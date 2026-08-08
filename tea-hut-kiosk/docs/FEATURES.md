# Tea Hut Kiosk — Feature List

Priority key: **M** = must have for launch · **S** = should have · **C** = could have (v1.1+)
Phase numbers refer to the delivery phases in [../PLAN.md](../PLAN.md#9-delivery-phases).

---

## 1. Accounts & access

| # | Feature | Pri | Phase |
|---|---|---|---|
| 1.1 | Staff account with email + password | M | 1 |
| 1.2 | Roles: Owner, Manager, Staff — with distinct permissions | M | 1 |
| 1.3 | Per-user branch permissions (which branches a user may operate) | M | 1 |
| 1.4 | 6-digit PIN quick-login on an already-enrolled device | M | 2 |
| 1.5 | PIN rate limiting + lockout after failed attempts | M | 2 |
| 1.6 | Manager PIN required to exit kiosk mode or change branch | M | 2 |
| 1.7 | Password reset by email | S | 1 |
| 1.8 | Audit log of logins, branch changes, kiosk exits, overrides | S | 1 |
| 1.9 | Forced logout / session expiry after N hours | S | 2 |
| 1.10 | Two-factor auth for Owner accounts | C | 6 |

## 2. Branch & device management

| # | Feature | Pri | Phase |
|---|---|---|---|
| 2.1 | Branch list sourced from Square Locations | M | 1 |
| 2.2 | Branch selection screen after login | M | 2 |
| 2.3 | Device enrollment via one-time code from admin console | M | 2 |
| 2.4 | Device → branch binding, persisted across reboots | M | 2 |
| 2.5 | Named lanes (e.g. "Front Lane 1", "Patio") | S | 2 |
| 2.6 | Device heartbeat + last-seen + app version in admin console | S | 2 |
| 2.7 | Pre-flight health check screen before going live | M | 2 |
| 2.8 | Remote "refresh menu now" push to a device | S | 6 |
| 2.9 | Remote lock / unlock / reboot a device | C | 6 |
| 2.10 | Per-device revocation (kill a stolen device's access) | M | 2 |

## 3. Square connection (the long-term link)

| # | Feature | Pri | Phase |
|---|---|---|---|
| 3.1 | One-time OAuth authorization by an Owner (authorization-code flow) | M | 1 |
| 3.2 | Encrypted server-side token vault — no Square token on any device | M | 1 |
| 3.3 | Scheduled access-token renewal with safety margin before 30-day expiry | M | 1 |
| 3.4 | Connection health indicator (connected / expiring / broken) | M | 1 |
| 3.5 | Handle `oauth.authorization.revoked` webhook and alert staff | M | 4 |
| 3.6 | Re-authorize flow that does not require re-enrolling devices | M | 1 |
| 3.7 | Alert (email/SMS) when renewal fails | S | 6 |
| 3.8 | Scope audit — request only the scopes actually used | M | 1 |

## 4. Menu

| # | Feature | Pri | Phase |
|---|---|---|---|
| 4.1 | Catalog sync: categories, items, variations, modifier lists, images | M | 3 |
| 4.2 | Delta sync using catalog version (avoid full re-pull) | S | 3 |
| 4.3 | Local offline cache so browsing survives a network drop | M | 3 |
| 4.4 | Scheduled background sync + manual force-sync | M | 3 |
| 4.5 | Auto-86 items from Square Inventory stock levels | S | 3 |
| 4.6 | Manual "86 for today" toggle in the manager panel | M | 3 |
| 4.7 | Kiosk-only overrides: hide item, rename, alternate photo, custom sort | S | 3 |
| 4.8 | Featured / Combos rails | S | 5 |
| 4.9 | Bilingual item names and descriptions (EN + 中文) | M | 3 |
| 4.10 | Item search | S | 3 |
| 4.11 | Per-branch menu differences (branch A has an item branch B doesn't) | M | 3 |
| 4.12 | Prices always sourced from Square — overrides never change price | M | 3 |

## 5. Ordering

| # | Feature | Pri | Phase |
|---|---|---|---|
| 5.1 | Dine In / Take Out selection driving Square fulfillment type | M | 3 |
| 5.2 | Category browse with photo grid | M | 3 |
| 5.3 | Item detail with size/variation selection | M | 3 |
| 5.4 | Required modifier groups (ice level, sugar level) with validation | M | 3 |
| 5.5 | Optional multi-select modifier groups (toppings) with max-count limits | M | 3 |
| 5.6 | Per-modifier price deltas shown inline | M | 3 |
| 5.7 | Quantity selector | M | 3 |
| 5.8 | Free-text item note (e.g. "less ice than usual") | S | 3 |
| 5.9 | Cart review with full modifier detail, edit and remove | M | 3 |
| 5.10 | Live subtotal / tax / total | M | 3 |
| 5.11 | Promo / discount code entry | S | 5 |
| 5.12 | Pickup name or nickname on the ticket | M | 4 |
| 5.13 | Idle timeout with "still there?" prompt and cart clear | M | 3 |
| 5.14 | Table number entry for dine-in | C | 5 |

## 6. Payment

| # | Feature | Pri | Phase |
|---|---|---|---|
| 6.1 | Square Terminal pairing via device code | M | 4 |
| 6.2 | Order created in Square, then Terminal checkout against that order | M | 4 |
| 6.3 | Live payment status on the kiosk driven by Terminal webhooks | M | 4 |
| 6.4 | Tip capture on the Terminal (configurable presets) | S | 4 |
| 6.5 | Customer-initiated cancel during payment | M | 4 |
| 6.6 | Checkout timeout with automatic cleanup | M | 4 |
| 6.7 | Decline / failure handling in plain language + retry | M | 4 |
| 6.8 | "Get help" path that flags a staff member | S | 4 |
| 6.9 | Gift card redemption | S | 5 |
| 6.10 | Fallback to pay-at-counter, with the order preserved | S | 4 |
| 6.11 | Receipt: printed by the Terminal; optional SMS/email | M | 4 |
| 6.12 | Idempotency on every order and payment call | M | 4 |

## 7. Membership & loyalty

| # | Feature | Pri | Phase |
|---|---|---|---|
| 7.1 | Member lookup by phone number | S | 5 |
| 7.2 | Show points balance and available rewards | S | 5 |
| 7.3 | Redeem a reward against the current order | S | 5 |
| 7.4 | One-tap enrollment during checkout | S | 5 |
| 7.5 | Points accrual on kiosk orders | S | 5 |
| 7.6 | Birthday / anniversary offer surfacing | C | 6 |

## 8. Merchandising & upsell

| # | Feature | Pri | Phase |
|---|---|---|---|
| 8.1 | Attract-loop video / image carousel, uploadable per branch | M | 5 |
| 8.2 | Featured item rail on the menu screen | S | 5 |
| 8.3 | Timed add-on prompt after item customization | S | 5 |
| 8.4 | Combo upgrade suggestion | S | 5 |
| 8.5 | Cart-level "add a topping?" prompt before payment | S | 5 |
| 8.6 | Scheduled promos (happy hour, day-part menus) | C | 6 |
| 8.7 | Upsell take-rate tracking | S | 6 |

## 9. Kiosk hardening

| # | Feature | Pri | Phase |
|---|---|---|---|
| 9.1 | Lock task mode / device-owner lockdown | M | 2 |
| 9.2 | Auto-start on boot | M | 2 |
| 9.3 | Immersive full-screen, status/nav bar suppressed | M | 2 |
| 9.4 | Fallback lockdown (launcher replacement) if device owner unavailable | M | 2 |
| 9.5 | Watchdog that restarts the app if it crashes or freezes | M | 2 |
| 9.6 | Screen-burn protection on the attract loop | S | 5 |
| 9.7 | Offline mode: browse allowed, new checkouts blocked with clear messaging | M | 3 |
| 9.8 | Crash + error reporting back to the backend | S | 2 |
| 9.9 | Self-hosted OTA APK update channel (no Play Store) | S | 6 |
| 9.10 | Staged rollout of updates (one lane first) | C | 6 |

## 10. Admin console & reporting

| # | Feature | Pri | Phase |
|---|---|---|---|
| 10.1 | User and role management | M | 6 |
| 10.2 | Square connect / reconnect button + health | M | 1 |
| 10.3 | Device registry with status | S | 6 |
| 10.4 | Menu override editor | S | 6 |
| 10.5 | Attract media upload per branch | S | 6 |
| 10.6 | Kiosk analytics: orders, AOV, conversion, abandonment, upsell take rate | S | 6 |
| 10.7 | Error / event log viewer | S | 6 |
| 10.8 | Export to CSV | C | 6 |

## 11. Accessibility & localization

| # | Feature | Pri | Phase |
|---|---|---|---|
| 11.1 | English + Chinese throughout, switchable on any screen | M | 3 |
| 11.2 | Touch targets ≥ 48dp, primary actions within reach on a tall screen | M | 3 |
| 11.3 | High-contrast mode | S | 5 |
| 11.4 | Text-size toggle | S | 5 |
| 11.5 | Portrait and landscape layouts | M | 2 |
| 11.6 | Additional languages via resource files only | C | — |
