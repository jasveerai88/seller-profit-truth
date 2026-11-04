# seller-profit-truth

**Your bestseller might be losing money.**

Your marketplace dashboard shows revenue. It does not show what is
left after the listing fee, the transaction fee, the payment
processing fee, the offsite-ads fee, the shipping you ate, and the
returns. Stacked together, those routinely eat 20–40% of a sale —
and on the wrong listing, more than the sale was worth. The sample
bundled with this tool proves it: its best-selling physical product,
a mug with 60 sales, **loses 233.17** once the subtraction is done
honestly. eRank and Marmalead will happily help you rank that mug
higher. This tool tells you whether you should.

`seller-profit-truth` reads a simple file of your listings and
sales, then prints — per listing — gross, **every fee line
separately**, total costs, true net profit, true margin %, and a
**LOSS-MAKER** flag. It also has a break-even mode: the minimum
price that *actually* hits your target margin after fees.

- Pure Python 3 standard library — no dependencies, no install step
- Local only — your sales data never leaves your machine
- Script-friendly exit codes: `0` = no loss-makers, `1` = at least
  one loss-maker found, `2` = error

## Fee defaults (as of 2026-11 — override any rate)

These are the platforms' published rates as of November 2026. They
are defaults, **not live facts** — platforms change them. Every rate
can be overridden per run with the flags shown further down.

| Platform | Fee | Default |
|---|---|---|
| Etsy | Listing fee | $0.20 per listing |
| Etsy | Transaction fee | 6.5% of (price + shipping charged) |
| Etsy | Payment processing | 3% + $0.25 of (price + shipping charged) |
| Etsy | Offsite ads (opt-in per listing) | 12% of (price + shipping charged) |
| Gumroad | Platform fee | 10% + $0.50 per transaction, on (price + shipping charged) |

## The model (the choices are deliberate — and stated)

- **Kept units** = units sold − returns. A refunded unit hands the
  price + shipping charged back to the buyer, so it is not revenue.
- **Platform fees are charged on kept units only** (platforms credit
  their percentage/fixed fees on a refunded sale).
- **Shipping cost is counted on every unit shipped, returns
  included.** You paid to ship the returned mug; that money is gone.
- **COGS is counted on kept units only** — a returned unit is
  restocked.
- **Etsy's listing fee is per listing**, charged once per row and
  owed even at zero sales. Per-unit views amortize it over units
  sold (`listing_fee / units`).

## Input format

One row per listing, as JSON (a list, or an object with a
`"listings"` key) or as CSV with the same headers:

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | listing name |
| `platform` | yes | `etsy` or `gumroad` |
| `price` | yes | sale price per unit, excluding shipping |
| `units` | yes | units sold (whole number, ≥ 0) |
| `shipping_charged` | no (0) | shipping charged to the buyer, per unit |
| `shipping_cost` | no (0) | what *you* pay to ship, per unit |
| `cogs` | no (0) | materials / cost of goods, per unit |
| `returns` | no (0) | units returned (must be ≤ `units`) |
| `offsite_ads` | no (false) | Etsy only: this listing ran offsite ads |

Bad rows are rejected with the row number named — no silent zeros,
no tracebacks.

## Usage

```bash
# 1. The profit report (JSON or CSV input)
python3 src/seller_profit_truth.py report examples/sample.json
python3 src/seller_profit_truth.py report examples/sample.csv

# 2. The same numbers as one JSON object (for scripts and agents)
python3 src/seller_profit_truth.py report examples/sample.json --json

# 3. Also print INR equivalents (rate per 1 unit of your currency)
python3 src/seller_profit_truth.py report examples/sample.json --cad-to-inr 67.97

# 4. Override a fee rate when the platform changes it
python3 src/seller_profit_truth.py report examples/sample.json --etsy-transaction-pct 7.0

# 5. Break-even: what must the candle cost to truly keep 20%?
python3 src/seller_profit_truth.py breakeven --platform etsy \
    --shipping-cost 6.25 --cogs 5.50 --target-margin 20 --units 30
```

Fee override flags (both commands): `--etsy-listing-fee`,
`--etsy-transaction-pct`, `--etsy-processing-pct`,
`--etsy-processing-fixed`, `--etsy-offsite-ads-pct`,
`--gumroad-pct`, `--gumroad-fixed`.

Break-even assumes no returns and amortizes the Etsy listing fee
over `--units` expected sales. The solved price is rounded **up**
to the next cent, so the price you actually type into the listing
still hits the target. If fees + target ≥ 100%, the tool says the
target is unreachable and shows you the fee take instead of
inventing a price.

## Use with AI agents

Every command takes `--json`: one JSON object with the same numbers
and exit codes as the text report (errors come back as
`{"error": ...}`):

```bash
python3 src/seller_profit_truth.py report examples/sample.json --json
python3 src/seller_profit_truth.py breakeven --platform gumroad \
    --shipping-cost 0 --cogs 1 --target-margin 50 --json
```

Agents: read [SKILL.md](SKILL.md) first — commands, the full JSON
schemas, exit codes, and the honesty rules (revenue is not profit;
the fee rates are Nov-2026 defaults, never quote them as live fact).

## Real run (verbatim)

```text
$ python3 src/seller_profit_truth.py report examples/sample.json
seller-profit-truth v0.1.0 — report for sample.json (4 listing(s))
Fee rates: defaults as of 2026-11 — override any rate with the --etsy-*/--gumroad-* flags.
Amounts are in the currency of your input file.

1. Vintage Denim Jacket [etsy] — 12 sold, 1 returned, 11 kept
   Gross kept: 594.00 (refunded 54.00)
   Fees: listing 0.20 · transaction 38.61 · processing 20.57 · offsite ads 0.00 = 59.38
   COGS: 198.00 · Shipping cost: 114.00
   TRUE NET: 222.62 (margin 37.5%) · per unit sold 18.55

2. Handmade Soy Candle [etsy] — 30 sold, 2 returned, 28 kept
   Gross kept: 392.00 (refunded 28.00)
   Fees: listing 0.20 · transaction 25.48 · processing 18.76 · offsite ads 0.00 = 44.44
   COGS: 154.00 · Shipping cost: 187.50
   TRUE NET: 6.06 (margin 1.5%) · per unit sold 0.20

3. Printable Wall Art Set [gumroad] — 140 sold, 6 returned, 134 kept
   Gross kept: 1,206.00 (refunded 54.00)
   Fees: platform fee 187.60 = 187.60
   COGS: 0.00 · Shipping cost: 0.00
   TRUE NET: 1,018.40 (margin 84.4%) · per unit sold 7.27

4. Ceramic Mug [etsy] — 60 sold, 9 returned, 51 kept  ⚠ LOSS-MAKER
   Gross kept: 841.50 (refunded 148.50)
   Fees: listing 0.20 · transaction 54.70 · processing 37.99 · offsite ads 100.98 = 193.87
   COGS: 346.80 · Shipping cost: 534.00
   TRUE NET: -233.17 (margin -27.7%) · per unit sold -3.89

TOTALS: gross 3,033.50 · fees 485.29 · COGS 698.80 · shipping 835.50 · TRUE NET 1,013.91 (margin 33.4%)
Loss-makers: 1 of 4 listings
Model: fees are charged on kept units; shipping cost is counted on every unit shipped, returns included; COGS on kept units only.
(exit code: 1 — one loss-maker found)
```

Read the four stories the dashboard never told: the jacket is
genuinely healthy (37.5%); the candle sold 30 units to earn **6.06**
(1.5% — one broken jar from negative); the digital download quietly
carries the shop (84.4%); and the mug — the volume bestseller —
bleeds on every sale, because offsite ads (100.98), 9 returns and
534.00 of eaten shipping were never in its price.

Break-even for that candle, verbatim:

```text
$ python3 src/seller_profit_truth.py breakeven --platform etsy --shipping-cost 6.25 --cogs 5.50 --target-margin 20 --units 30
seller-profit-truth v0.1.0 — break-even [etsy]
Fee rates: defaults as of 2026-11 — override any rate with the --etsy-*/--gumroad-* flags.
Costs per unit: shipping cost 6.25 · COGS 5.50 · shipping charged 0.00 · listing fee amortized over 30 unit(s)
Target margin: 20%
Minimum price: 17.04
At that price, per unit: charged 17.04 · fees 1.88 · net 3.41 · margin 20.0%
Break-even assumes no returns; the price is rounded UP to the next cent so the rounded price still hits the target.
(exit code: 0)
```

The candle sells at 14.00 and keeps 1.5%. To truly keep 20% it has
to cost **17.04** — a number no revenue dashboard will ever show
you.

## Tests

```bash
python3 -m unittest discover -s tests -v
# Ran 45 tests — OK
```

The suite covers both directions: the sample's four listings match
numbers worked by hand from the published fee rates (not copied
from the tool's own output), the loss-maker is flagged and exits 1,
a clean file exits 0, break-even prices round-trip (feed the solved
price back through the margin math and the target comes back),
override flags change the results by exactly the hand-computed
delta, malformed rows fail with their row numbers in text and JSON
modes, and the CSV and JSON samples produce identical reports.

## Internal use

This tool does a real job for its author: it is the pricing-truth
check for the author's own **Gumroad digital products** — every
price is run through the Gumroad fee model (and its break-even)
before it is published, so a "cheap and cheerful" price point can
never silently turn into a per-sale loss after the 10% + $0.50 fee.

## Known limits

- The model is per-listing and per-period: it does not split a
  platform's monthly/annual fixed costs (shop subscriptions,
  promoted-listing budgets) across listings. Add those to a
  listing's `cogs`-side reality yourself, or override a fee rate to
  approximate them.
- Fees are modelled as credited on refunded sales, which matches
  the platforms' current published behaviour; if a platform stops
  crediting a fee, raise that fee's *effective* weight with the
  override flags rather than trusting the default.
- One currency per file: amounts are in whatever currency your
  input uses. `--cad-to-inr` only *displays* equivalents; it does
  not convert the underlying books.
- Taxes (sales tax / VAT / income tax) are out of scope — this is
  contribution profit after platform fees and direct costs, before
  tax.

## Privacy

What it touches: only the sales file you point it at. What it
stores: nothing. What it sends: nothing — there is no network code
in this tool.

## Support

If this saves you from scaling a loss-maker, consider sponsoring:
**https://github.com/sponsors/jasveerai88**

## Licence

MIT — see [LICENSE](LICENSE).
