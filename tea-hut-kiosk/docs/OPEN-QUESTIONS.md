# Open Questions

Grouped by whether the answer blocks the build. Blocking items should be resolved in
Phase 0 before code starts.

---

## Blocking

**Q1. Has Square approved this deployment?**
Square prohibits the Mobile Payments SDK and Reader SDK on unattended kiosks. The plan routes
payment to a paired Square Terminal instead, which is the supported path — but we should get
written confirmation from Square developer support that a Tea Hut kiosk lane qualifies.
*If the answer is no, the whole payment architecture changes and Square's own first-party
Kiosk product becomes the fallback.*

**Q2. What is the exact model of the in-cell smart portable TV?**
Needed to test three things on the real unit: (a) can it be set as Android device owner for
true kiosk lockdown, (b) does it ship with Google Play Services, (c) is it landscape-locked
in hardware. All three change implementation work in Phase 2.

**Q3. Does Tea Hut already own Square Terminals?**
One Terminal is required per kiosk lane. If they need purchasing, that is lead time on the
critical path.

**Q4. How many branches, and how many lanes per branch, at launch?**
Drives the pilot plan, the device registry design, and hardware budget.

---

## Shapes the design, not blocking

**Q5. Is there an existing Square loyalty program?**
If yes, we connect to it. If no, one has to be created in Square before the membership
features (section 7 of the feature list) can be built.

**Q6. Where does the customer's order ticket go?**
Options: Square KDS, a LAN receipt printer at the bar, or the Terminal's printed receipt only.
This determines whether we need printer integration work at all.

**Q7. Dine-in handling.**
Is dine-in just "pickup at counter when your number is called," or does Tea Hut want table
numbers and runner delivery? Table numbers add a screen and a fulfillment change.

**Q8. Tipping.**
Should the kiosk prompt for tips at all? If yes, the Terminal handles the prompt — we just
configure presets. Some tea shops skip it on kiosks to speed the line.

**Q9. Bilingual content source.**
Does Square Catalog already carry Chinese item names, or do translations need to live in our
override layer? Affects how much of the menu work is data entry vs. code.

**Q10. Who hosts the backend?**
A small VPS is sufficient. Needs a stable public HTTPS endpoint for Square webhooks and a
domain. Confirm who owns the hosting account and the domain.

**Q11. Branding assets.**
Tea Hut logo, brand colors, fonts, and item photography — the kiosk is photo-driven, and
menu photos are the single biggest visual quality factor. Are there existing product photos?

**Q12. Refunds and voids.**
Should a manager be able to void or refund from the kiosk's manager panel, or is that
strictly done from the Square POS/Dashboard? Recommend the latter for v1.

---

## Deferred (revisit after pilot)

- Should the kiosk backend later power QR table-side ordering as a second surface?
- Do we want customer-facing order-status displays (the "now serving" screen)?
- Multi-tenant support, if Tea Hut ever franchises.
