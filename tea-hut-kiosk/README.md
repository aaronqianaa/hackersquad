# Tea Hut Kiosk

Android self-order kiosk for Tea Hut, connected to Square.

**Status:** planning only — no code yet.

- [`PLAN.md`](./PLAN.md) — full product and technical plan, feature list, architecture, milestones, and open questions.

## Quick summary

A locked-down Android app on a touchscreen in-store. Customers browse the Tea Hut
menu, customize drinks (size / ice / sweetness / toppings / milk base), pay, and get a
ticket number. Orders are created as real Square orders, so they flow into Tea Hut's
existing Square reporting, inventory, and kitchen printers with no separate
reconciliation.

Staff log in once per device and select the store branch; the kiosk then stays bound to
that branch permanently. The Square connection is authorized once by the owner and
stays alive indefinitely via a server-side, non-expiring OAuth refresh token.

## Three things to read before reviewing the plan

1. Square's Mobile Payments SDK **prohibits unattended kiosk use** — payments go
   through a paired **Square Terminal** via the Terminal API instead. See PLAN.md §0.1.
2. The incell portable smart TV needs a **hardware validation spike** before any
   real build work starts. See PLAN.md §0.2.
3. There are **8 open questions** that need answers before implementation. See
   PLAN.md §12.
