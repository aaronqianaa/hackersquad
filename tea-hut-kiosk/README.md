# Tea Hut Kiosk

Planning workspace for Tea Hut's Android self-ordering kiosk, integrated with Square.

**Nothing is built yet — this folder currently holds the plan for review.**

## Contents

| File | What it is |
|---|---|
| [PLAN.md](PLAN.md) | The main plan: constraints, architecture, screen flow, Square API surface, security, phases, risks |
| [docs/FEATURES.md](docs/FEATURES.md) | Full feature checklist with priorities and target phase |
| [docs/OPEN-QUESTIONS.md](docs/OPEN-QUESTIONS.md) | Decisions needed from Tea Hut, blocking ones first |

## Read this first

Three findings drive the design (details in [PLAN.md §2](PLAN.md#2-three-findings-that-shape-the-whole-design)):

1. **The touchscreen TV cannot take the card payment.** Square prohibits its Mobile Payments
   SDK and Reader SDK on unattended kiosks. Payment goes to a paired **Square Terminal** next
   to the screen, via the Terminal API. Each kiosk lane = 1 touchscreen + 1 Square Terminal.
2. **The Square connection lives on a server, not on the tablet.** A small backend holds the
   OAuth refresh token (non-expiring under the authorization-code flow) and auto-renews the
   30-day access token. The kiosk never stores a Square credential.
3. **Staff accounts and branch selection are ours to build.** Branches map to Square Locations;
   users, roles, and device→branch binding live in our backend.

## Status

- [x] Research reference kiosks and the Square platform constraints
- [x] Draft plan, feature list, and open questions
- [ ] **Plan reviewed and approved by Tea Hut**
- [ ] Phase 0: confirm Square approval, test the actual TV hardware, procure Terminals
- [ ] Phase 1+: build
