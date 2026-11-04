# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** seller-profit-truth's promise is
  "clone and run". Pull requests that add a third-party dependency
  will not be merged.
- **Local only.** No network calls, no telemetry, no uploads of user
  files.
- **Fee rates are data, never gospel.** The defaults are stamped
  "as of 2026-11" everywhere they appear. A PR updating a default
  rate must cite the platform's own fee page and update the stamp,
  the README table and the tests in the same change.
- **The model stays explicit.** Fees on kept units, shipping cost
  on every unit shipped, COGS on kept units, listing fee per
  listing. Any change to those choices is a behaviour change: it
  needs the README model section, the changelog and the tests
  updated together — and a hand-worked example proving the new math.
- **Both directions tested.** A behaviour change needs a test where
  good input succeeds and bad input fails cleanly — not just one
  side. Money math needs a hand-checked number, not a number copied
  from the tool's own output.

## Getting started

```bash
git clone https://github.com/jasveerai88/seller-profit-truth
cd seller-profit-truth
python3 -m unittest discover -s tests -v
python3 src/seller_profit_truth.py report examples/sample.json
python3 src/seller_profit_truth.py breakeven --platform etsy \
    --shipping-cost 6.25 --cogs 5.50 --target-margin 20 --units 30
```

## Pull requests

1. Fork, branch, and keep the change to one topic.
2. Add or update tests under `tests/`; the full suite must pass.
3. Note the change in `CHANGELOG.md` under an "Unreleased" heading.
4. Describe the behaviour change with a real before/after run if the
   CLI output changes.
