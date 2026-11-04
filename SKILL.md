---
name: seller-profit-truth
description: Compute true per-listing profit for Etsy and Gumroad sellers from a JSON/CSV sales file — every platform fee line separately, shipping and returns subtracted, LOSS-MAKER flags on negative listings — plus a break-even mode for the minimum price that truly hits a target margin after fees. Use when pricing a listing, auditing a catalogue, or checking whether a "bestseller" actually makes money. Fee rates are Nov-2026 defaults, overridable — never present them as live fact.
---

# seller-profit-truth — agent skill

## Purpose

Marketplace dashboards report revenue, and SEO tools (eRank,
Marmalead) report rankings; neither subtracts the stacked platform
fees, the shipping the seller ate, and the returns. This tool does
that subtraction per listing and flags the listings whose true net
is negative, and solves the inverse problem too: given costs and a
target margin, the minimum price that actually delivers that margin
after fees. Pure Python standard library; local only; reads one
sales file, writes nothing.

**The honesty core of this tool:** revenue is not profit. A listing
with high sales and a negative `net` is a loss-maker, and the report
says so — never summarise a catalogue by its gross, and never call
a listing profitable from its sales count.

## When to use / not use

Use when:
- Auditing an Etsy/Gumroad catalogue for listings that lose money.
- Pricing (or repricing) a listing: run `breakeven` before the
  price is published.
- An agent needs per-listing profit numbers it can trust in JSON.

Do NOT use when:
- The question is SEO, keywords or rankings — this tool knows
  nothing about search. It judges money only.
- You need accounting-grade books: taxes, platform subscriptions
  and other period fixed costs are out of scope (see Limits).
- The platform is not Etsy or Gumroad — those are the only fee
  models built in.

## Commands

```bash
# Profit report (JSON or CSV input; exit 1 if any loss-maker)
python3 src/seller_profit_truth.py report SALES.json
python3 src/seller_profit_truth.py report SALES.csv --json

# Also display INR equivalents (rate per 1 unit of input currency)
python3 src/seller_profit_truth.py report SALES.json --cad-to-inr 67.97

# Override any fee rate (both commands accept all of these)
python3 src/seller_profit_truth.py report SALES.json \
    --etsy-transaction-pct 7.0 --gumroad-pct 10 --gumroad-fixed 0.50

# Break-even price for a target true margin
python3 src/seller_profit_truth.py breakeven --platform etsy \
    --shipping-charged 0 --shipping-cost 6.25 --cogs 5.50 \
    --target-margin 20 --units 30 [--offsite-ads] [--json]
```

Input rows (JSON list, `{"listings": [...]}` object, or CSV with
the same headers): `name` (required), `platform` (`etsy`|`gumroad`,
required), `price` (required, per unit excl. shipping), `units`
(required, integer ≥ 0); optional `shipping_charged`,
`shipping_cost`, `cogs` (per unit, default 0), `returns` (default
0, ≤ units), `offsite_ads` (bool, Etsy only, default false).

## The model (state it when you report results)

- kept = units − returns; refunded units are not revenue.
- Platform fees are charged on **kept** units only.
- Shipping cost is counted on **every unit shipped**, returns
  included. COGS on kept units only.
- Etsy's listing fee ($0.20 default) is per listing, owed even at
  zero sales; per-unit views amortize it over units sold.
- Break-even assumes **no returns** and rounds the price **up** to
  the cent so the quoted price still hits the target.

## Output JSON schema (`--json`)

`report`: `tool` (`"seller-profit-truth"`), `version`, `command`
(`"report"`), `file`, `currency` (note string), `rates` (the full
rate set used, stamped `as_of: "2026-11"`), `cad_to_inr` (rate or
null), `listings`, `totals`.

Each listing: `name`, `platform`, `units_sold`, `returns`,
`units_kept`, `price`, `shipping_charged`, `gross`, `refunded`,
`fees` (Etsy: `listing_fee`, `transaction_fee`, `processing_fee`,
`offsite_ads_fee`; Gumroad: `platform_fee`), `fees_total`,
`cogs_total`, `shipping_cost_total`, `net`, `margin_pct` (null when
gross is 0), `loss_maker` (bool), `listing_fee_per_unit`,
`net_per_unit_sold`, `notes`. With `--cad-to-inr`, money fields gain
`*_inr` siblings. `totals` sums the same money fields and adds
`margin_pct`, `listings`, `loss_makers`.

`breakeven`: the common fields plus `platform`, `min_price`,
`shipping_charged`, `shipping_cost`, `cogs`, `target_margin_pct`,
`units`, `offsite_ads`, `at_min_price` (`charged_per_unit`,
`fees_per_unit`, `net_per_unit`, `margin_pct`), `note` (null unless
a zero price already hits the target).

On error, stdout is a single object: `{"error": "<message>"}`
(validation errors name the row: `"row 2: ..."`) with exit code 2 —
including argparse usage errors in `--json` mode. Never plain text,
never a traceback.

## Exit codes

- `0` — report computed and **no** listing loses money; or a
  break-even price was solved.
- `1` — report computed and **at least one LOSS-MAKER exists**.
  This is a finding, not a failure: surface the loss-makers by
  name; do not describe the catalogue as healthy.
- `2` — ERROR: missing/unreadable file, malformed row (message
  names the row), invalid flag value, or an unreachable break-even
  target. No report was produced; do not quote any numbers from a
  failed run.

## Limits & honesty rules the agent must respect

- **The fee rates are defaults as of 2026-11, not live facts.**
  When you cite a rate, cite it as "the tool's Nov-2026 default"
  and note it is overridable. If the user gives you a newer rate,
  pass it with the override flags instead of editing code.
- **Revenue is not profit.** If you mention a listing's sales,
  mention its `net` and `margin_pct` too. A `loss_maker: true`
  listing must be reported as losing money, however well it sells.
- **Exit 1 is the tool working, not failing.** It means the audit
  found a bleeder. Report which listings and by how much.
- **The model has edges:** platform subscriptions and other period
  fixed costs are not allocated; taxes are excluded; one currency
  per file (the INR figures are display equivalents only). If a
  conclusion depends on those, say so.
- **Break-even assumes no returns.** For a returns-heavy listing
  the true break-even price is higher — flag that rather than
  presenting the solved price as sufficient.
- Local only: the tool reads the file you point it at and sends
  nothing anywhere.
