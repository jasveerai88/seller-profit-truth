# Changelog

## v0.1.0 — 2026-11-04

First release.

- **`report FILE.json|FILE.csv`** — per-listing true profit for Etsy
  and Gumroad: gross kept, **every fee line separately** (Etsy:
  listing, transaction, payment processing, offsite ads; Gumroad:
  the platform fee), COGS, shipping cost, true net and true margin,
  plus a **LOSS-MAKER flag** on any listing whose net is negative —
  and a totals row for the whole file. Exit code is 1 when any
  loss-maker is found, so a script can catch a bleeding catalogue.
- **The model is stated, not hidden:** fees are charged on kept
  units (units − returns); refunded units are not revenue; shipping
  cost is counted on *every* unit shipped, returns included (you
  paid to ship the returned item); COGS on kept units only; Etsy's
  listing fee is a flat per-listing charge, owed even at zero sales,
  amortized over units sold in per-unit views.
- **`breakeven`** — the minimum price that truly hits a target
  margin after fees, solved exactly and rounded **up** to the cent
  so the quoted price still hits the target. An unreachable target
  (fees + target ≥ 100%) is a clean error that shows the fee take.
- **Fee defaults stamped "as of 2026-11"** in the README, the code
  and every report header — Etsy listing $0.20, transaction 6.5%,
  processing 3% + $0.25, offsite ads 12%; Gumroad 10% + $0.50 —
  and **every rate is overridable** with `--etsy-*` / `--gumroad-*`
  flags, so the tool survives the platforms changing their prices.
- **`--cad-to-inr RATE`** — also prints INR equivalents next to
  every amount (the CAD + INR display pattern of payout-tracker).
- **Validation with row numbers:** missing fields, negative or
  non-finite numbers, fractional units, `returns > units`, unknown
  platforms and non-numeric CSV cells are clean errors that name
  the exact row — never a traceback, never a silent zero.
- **`--json` on both commands** — one JSON object with the same
  numbers and exit codes as the text report; errors are
  `{"error": ...}` objects, argparse usage errors included.
- **`SKILL.md`** at the repo root for AI coding agents: commands,
  the JSON schemas, exit codes, and the honesty rules (a balance of
  sales is not profit; a SKIP-free model still rests on the fee
  defaults — cite them as defaults, never as live fact).
- Bundled sample (`examples/sample.json` + the identical
  `examples/sample.csv`): four listings whose bestseller by volume —
  a 60-sale ceramic mug — is a **−233.17 loss-maker** once offsite
  ads, returns and eaten shipping are subtracted.
- 45 stdlib-unittest tests: fee math for both platforms checked by
  hand against the published rates, the loss-maker flag, break-even
  round-trips (price → margin returns the target), override flags,
  malformed-row errors with row numbers, and CSV/JSON agreement on
  the same data.
- Pure Python standard library; local only; MIT licence.
