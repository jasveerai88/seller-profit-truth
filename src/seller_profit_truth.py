#!/usr/bin/env python3
"""seller-profit-truth — true per-listing profit for Etsy & Gumroad sellers.

Pure Python standard library. Local only: no network, no uploads, no
accounts. Your sales file never leaves your machine.

Marketplace dashboards show you revenue. eRank / Marmalead show you
SEO. Neither subtracts the stacked fees, the shipping you ate, and
the returns — so a "bestseller" can be losing money on every sale.
This tool does the subtraction, fee line by fee line, and flags the
listings whose true net is negative.

Commands:
  report FILE.json|FILE.csv [--json] [fee overrides] [--cad-to-inr R]
  breakeven --platform etsy|gumroad --shipping-cost X --cogs Y
            --target-margin PCT [--shipping-charged S] [--units N]
            [--offsite-ads] [--json] [fee overrides]

Input rows (JSON list, {"listings": [...]} object, or CSV with the
same headers):
  name             listing name (required, non-empty)
  platform         "etsy" | "gumroad" (required)
  price            sale price per unit, excl. shipping (required, >= 0)
  units            units sold (required, integer >= 0)
  shipping_charged per unit (default 0)
  shipping_cost    what YOU pay to ship, per unit (default 0)
  cogs             materials / COGS per unit (default 0)
  returns          units returned (default 0, must be <= units)
  offsite_ads      true/false, Etsy only (default false)

The model (every choice is deliberate and documented):
  kept = units - returns. Refunded units hand price + shipping
  charged back to the buyer, so they are not revenue.
  Percentage/fixed platform fees are charged on KEPT units only
  (platforms credit their fees on a refunded sale).
  Shipping cost is counted on EVERY unit shipped, returns included —
  you paid to ship the returned mug, and that money is gone.
  COGS is counted on kept units only (a returned unit is restocked).
  Etsy's listing fee is a flat per-listing charge; it is owed even
  at zero sales. Per-unit views amortize it over units sold.

Fee defaults — AS OF 2026-11, stamped here and in the README. They
are defaults, not live facts: override any of them with the
--etsy-* / --gumroad-* flags when the platforms change their rates.
  Etsy:    listing $0.20 per listing · transaction 6.5% of
           (price + shipping charged) · processing 3% + $0.25 of
           (price + shipping charged) · offsite ads 12% (opt-in flag)
  Gumroad: 10% + $0.50 per transaction on (price + shipping charged)

Amounts are in the currency of your input file. --cad-to-inr R also
prints INR equivalents (rate R per 1 unit of input currency),
following the CAD + INR display pattern of payout-tracker.

Exit codes: 0 = report computed, no loss-makers (or break-even
solved) · 1 = report computed, at least one LOSS-MAKER found ·
2 = ERROR (bad input, impossible break-even) — clean message,
never a traceback; with --json the error is {"error": ...}.
"""
import argparse
import csv
import io
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

__version__ = "1.0.0"
TOOL = "seller-profit-truth"
FEES_AS_OF = "2026-11"

PLATFORMS = ("etsy", "gumroad")


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# --------------------------------------------------------------------------
# fee rates
# --------------------------------------------------------------------------

@dataclass
class FeeRates:
    etsy_listing_fee: float = 0.20
    etsy_transaction_pct: float = 6.5     # percent
    etsy_processing_pct: float = 3.0      # percent
    etsy_processing_fixed: float = 0.25
    etsy_offsite_ads_pct: float = 12.0    # percent
    gumroad_pct: float = 10.0             # percent
    gumroad_fixed: float = 0.50

    def as_dict(self):
        return {
            "as_of": FEES_AS_OF,
            "etsy": {
                "listing_fee": self.etsy_listing_fee,
                "transaction_pct": self.etsy_transaction_pct,
                "processing_pct": self.etsy_processing_pct,
                "processing_fixed": self.etsy_processing_fixed,
                "offsite_ads_pct": self.etsy_offsite_ads_pct,
            },
            "gumroad": {
                "pct": self.gumroad_pct,
                "fixed": self.gumroad_fixed,
            },
        }


def _check_rate(value, label, maximum=None):
    if value is None or isinstance(value, bool) \
            or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise ToolError(f"{label} must be a finite number (got {value!r})")
    if value < 0:
        raise ToolError(f"{label} must be >= 0 (got {value})")
    if maximum is not None and value >= maximum:
        raise ToolError(f"{label} must be < {maximum} (got {value})")
    return float(value)


def rates_from_args(a):
    """Build FeeRates from CLI override flags, validating each."""
    r = FeeRates()
    pairs = [
        ("etsy_listing_fee", "--etsy-listing-fee", None),
        ("etsy_transaction_pct", "--etsy-transaction-pct", 100.0),
        ("etsy_processing_pct", "--etsy-processing-pct", 100.0),
        ("etsy_processing_fixed", "--etsy-processing-fixed", None),
        ("etsy_offsite_ads_pct", "--etsy-offsite-ads-pct", 100.0),
        ("gumroad_pct", "--gumroad-pct", 100.0),
        ("gumroad_fixed", "--gumroad-fixed", None),
    ]
    for attr, flag, maximum in pairs:
        value = getattr(a, attr, None)
        if value is not None:
            setattr(r, attr, _check_rate(value, flag, maximum))
    return r


# --------------------------------------------------------------------------
# input loading + validation (every error names its row)
# --------------------------------------------------------------------------

def _fail_row(row_no, msg):
    raise ToolError(f"row {row_no}: {msg}")


def _num_field(row, field, row_no, default=None, integer=False):
    if field not in row or row[field] is None or row[field] == "":
        if default is not None:
            return default
        _fail_row(row_no, f"missing required field '{field}'")
    raw = row[field]
    if isinstance(raw, bool):
        _fail_row(row_no, f"'{field}' must be a number, not true/false")
    if isinstance(raw, str):
        try:
            value = float(raw.strip())
        except ValueError:
            _fail_row(row_no, f"'{field}' is not a number: {raw!r}")
    elif isinstance(raw, (int, float)):
        value = float(raw)
    else:
        _fail_row(row_no, f"'{field}' must be a number (got {raw!r})")
    if not math.isfinite(value):
        _fail_row(row_no, f"'{field}' must be finite (got {raw!r})")
    if value < 0:
        _fail_row(row_no, f"'{field}' must be >= 0 (got {value:g})")
    if integer:
        if value != int(value):
            _fail_row(row_no, f"'{field}' must be a whole number "
                              f"(got {value:g})")
        return int(value)
    return value


def _bool_field(row, field, row_no):
    raw = row.get(field, False)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        low = raw.strip().lower()
        if low in ("true", "yes", "1"):
            return True
        if low in ("false", "no", "0", ""):
            return False
    _fail_row(row_no, f"'{field}' must be true or false (got {raw!r})")


def normalize_row(row, row_no):
    """Validate one raw row dict -> a clean listing dict."""
    if not isinstance(row, dict):
        _fail_row(row_no, f"expected an object of fields, got {row!r}")
    name = row.get("name")
    if not isinstance(name, str) or not name.strip():
        _fail_row(row_no, "'name' is required and must be a non-empty string")
    platform = row.get("platform")
    if not isinstance(platform, str) \
            or platform.strip().lower() not in PLATFORMS:
        _fail_row(row_no, f"'platform' must be one of "
                          f"{'/'.join(PLATFORMS)} (got {platform!r})")
    listing = {
        "name": name.strip(),
        "platform": platform.strip().lower(),
        "price": _num_field(row, "price", row_no),
        "units": _num_field(row, "units", row_no, integer=True),
        "shipping_charged": _num_field(row, "shipping_charged", row_no,
                                       default=0.0),
        "shipping_cost": _num_field(row, "shipping_cost", row_no,
                                    default=0.0),
        "cogs": _num_field(row, "cogs", row_no, default=0.0),
        "returns": _num_field(row, "returns", row_no, default=0,
                              integer=True),
        "offsite_ads": _bool_field(row, "offsite_ads", row_no),
    }
    if listing["returns"] > listing["units"]:
        _fail_row(row_no, f"'returns' ({listing['returns']}) cannot "
                          f"exceed 'units' ({listing['units']})")
    return listing


def _reject_json_constant(name):
    raise ValueError(f"invalid constant {name}")


def load_rows(path):
    """Read a .json or .csv file -> list of normalized listing dicts."""
    if not path.is_file():
        raise ToolError(f"file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            raise ToolError(f"could not read {path.name} "
                            f"({exc.__class__.__name__})")
        try:
            data = json.loads(text, parse_constant=_reject_json_constant)
        except ValueError as exc:
            raise ToolError(f"{path.name} is not valid JSON: {exc}")
        if isinstance(data, dict):
            if "listings" not in data:
                raise ToolError(f"{path.name}: a JSON object must hold "
                                f"the rows under a \"listings\" key")
            data = data["listings"]
        if not isinstance(data, list):
            raise ToolError(f"{path.name}: expected a JSON list of "
                            f"listings (or an object with \"listings\")")
        raw_rows = [(i + 1, row) for i, row in enumerate(data)]
    elif suffix == ".csv":
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            raise ToolError(f"could not read {path.name} "
                            f"({exc.__class__.__name__})")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise ToolError(f"{path.name}: empty CSV — no header row")
        raw_rows = [(reader.line_num, row) for row in reader]
    else:
        raise ToolError(f"expected a .json or .csv file (got "
                        f"{path.name})")
    if not raw_rows:
        raise ToolError(f"{path.name}: no listings found — nothing "
                        f"to report")
    return [normalize_row(row, row_no) for row_no, row in raw_rows]


# --------------------------------------------------------------------------
# the math
# --------------------------------------------------------------------------

def compute_listing(listing, rates):
    """One listing -> its full profit breakdown (all amounts unrounded;
    rounding happens only at display)."""
    units = listing["units"]
    kept = units - listing["returns"]
    charged = listing["price"] + listing["shipping_charged"]
    gross = kept * charged
    refunded = listing["returns"] * charged

    fees = {}
    if listing["platform"] == "etsy":
        fees["listing_fee"] = rates.etsy_listing_fee
        fees["transaction_fee"] = \
            rates.etsy_transaction_pct / 100.0 * gross
        fees["processing_fee"] = kept * (
            rates.etsy_processing_pct / 100.0 * charged
            + rates.etsy_processing_fixed)
        fees["offsite_ads_fee"] = (
            rates.etsy_offsite_ads_pct / 100.0 * gross
            if listing["offsite_ads"] else 0.0)
    else:  # gumroad
        fees["platform_fee"] = kept * (
            rates.gumroad_pct / 100.0 * charged + rates.gumroad_fixed)
    fees_total = sum(fees.values())

    cogs_total = kept * listing["cogs"]
    shipping_cost_total = units * listing["shipping_cost"]
    net = gross - fees_total - cogs_total - shipping_cost_total
    margin_pct = (net / gross * 100.0) if gross > 0 else None

    notes = []
    if listing["offsite_ads"] and listing["platform"] != "etsy":
        notes.append("offsite_ads has no effect on gumroad — Gumroad "
                     "has no offsite-ads fee in this model")
    if units == 0 and listing["platform"] == "etsy":
        notes.append("no sales, but the listing fee is still owed")

    return {
        "name": listing["name"],
        "platform": listing["platform"],
        "units_sold": units,
        "returns": listing["returns"],
        "units_kept": kept,
        "price": listing["price"],
        "shipping_charged": listing["shipping_charged"],
        "gross": gross,
        "refunded": refunded,
        "fees": fees,
        "fees_total": fees_total,
        "cogs_total": cogs_total,
        "shipping_cost_total": shipping_cost_total,
        "net": net,
        "margin_pct": margin_pct,
        "loss_maker": net < 0,
        "listing_fee_per_unit": (rates.etsy_listing_fee / units
                                 if listing["platform"] == "etsy"
                                 and units > 0 else None),
        "net_per_unit_sold": (net / units if units > 0 else None),
        "notes": notes,
    }


def compute_report(listings, rates):
    rows = [compute_listing(l, rates) for l in listings]
    totals = {
        "gross": sum(r["gross"] for r in rows),
        "fees_total": sum(r["fees_total"] for r in rows),
        "cogs_total": sum(r["cogs_total"] for r in rows),
        "shipping_cost_total": sum(r["shipping_cost_total"]
                                   for r in rows),
        "net": sum(r["net"] for r in rows),
        "listings": len(rows),
        "loss_makers": sum(1 for r in rows if r["loss_maker"]),
    }
    totals["margin_pct"] = (totals["net"] / totals["gross"] * 100.0
                            if totals["gross"] > 0 else None)
    return rows, totals


def _unit_economics(platform, rates, offsite_ads):
    """(proportional rate on charged, fixed fee per unit excl. listing
    amortization) for one platform."""
    if platform == "etsy":
        prop = (rates.etsy_transaction_pct + rates.etsy_processing_pct
                + (rates.etsy_offsite_ads_pct if offsite_ads else 0.0)) \
            / 100.0
        fixed = rates.etsy_processing_fixed
        listing_fee = rates.etsy_listing_fee
    else:
        prop = rates.gumroad_pct / 100.0
        fixed = rates.gumroad_fixed
        listing_fee = 0.0
    return prop, fixed, listing_fee


def unit_margin_pct(price, shipping_charged, shipping_cost, cogs,
                    platform, rates, offsite_ads=False, units=1):
    """True margin % of ONE kept unit at a given price (no returns)."""
    charged = price + shipping_charged
    if charged <= 0:
        return None
    prop, fixed, listing_fee = _unit_economics(platform, rates,
                                               offsite_ads)
    fees = prop * charged + fixed + listing_fee / units
    net = charged - fees - shipping_cost - cogs
    return net / charged * 100.0


def solve_breakeven(platform, shipping_charged, shipping_cost, cogs,
                    target_margin_pct, rates, offsite_ads=False,
                    units=1):
    """Minimum price whose true margin equals the target, solved
    exactly from net = margin * charged, then rounded UP to the next
    cent so the quoted price still hits the target after rounding."""
    if units < 1:
        raise ToolError("--units must be at least 1 for break-even")
    if not (0 <= target_margin_pct < 100):
        raise ToolError(f"--target-margin must be >= 0 and < 100 "
                        f"(got {target_margin_pct:g})")
    prop, fixed, listing_fee = _unit_economics(platform, rates,
                                               offsite_ads)
    target = target_margin_pct / 100.0
    denom = 1.0 - prop - target
    if denom <= 0:
        raise ToolError(
            f"target margin {target_margin_pct:g}% is unreachable on "
            f"{platform}: the fees alone take {prop * 100:g}% of every "
            f"sale, leaving {100 - prop * 100:g}% — a {target_margin_pct:g}% "
            f"margin plus {prop * 100:g}% fees meets or exceeds 100%")
    per_unit_fixed = fixed + listing_fee / units
    charged_needed = (per_unit_fixed + shipping_cost + cogs) / denom
    price = charged_needed - shipping_charged
    note = None
    if price <= 0:
        price = 0.0
        note = ("even a price of 0 hits the target — the shipping "
                "charged alone covers the costs at this margin")
    else:
        price = math.ceil((price - 1e-9) * 100) / 100.0
    margin_at = unit_margin_pct(price, shipping_charged, shipping_cost,
                                cogs, platform, rates, offsite_ads, units)
    charged = price + shipping_charged
    fees_at = prop * charged + per_unit_fixed
    return {
        "platform": platform,
        "min_price": round(price, 2),
        "shipping_charged": shipping_charged,
        "shipping_cost": shipping_cost,
        "cogs": cogs,
        "target_margin_pct": target_margin_pct,
        "units": units,
        "offsite_ads": offsite_ads,
        "at_min_price": {
            "charged_per_unit": round(charged, 2),
            "fees_per_unit": round(fees_at, 2),
            "net_per_unit": round(charged - fees_at - shipping_cost
                                  - cogs, 2),
            "margin_pct": (round(margin_at, 2)
                           if margin_at is not None else None),
        },
        "note": note,
    }


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _fmt(value, cad_to_inr=None):
    text = f"{value:,.2f}"
    if cad_to_inr is not None:
        text += f" (₹{value * cad_to_inr:,.0f})"
    return text


def _fmt_margin(margin_pct):
    return f"{margin_pct:.1f}%" if margin_pct is not None else "n/a"


def _money(value, cad_to_inr=None):
    """JSON money: rounded number, plus an _inr sibling when asked."""
    return round(value, 2)


def _with_inr(obj, fields, cad_to_inr):
    if cad_to_inr is None:
        return obj
    for f in fields:
        if obj.get(f) is not None:
            obj[f + "_inr"] = round(obj[f] * cad_to_inr, 2)
    return obj


def report_as_json(rows, totals, source_name, rates, cad_to_inr):
    listings = []
    for r in rows:
        obj = {
            "name": r["name"],
            "platform": r["platform"],
            "units_sold": r["units_sold"],
            "returns": r["returns"],
            "units_kept": r["units_kept"],
            "price": _money(r["price"]),
            "shipping_charged": _money(r["shipping_charged"]),
            "gross": _money(r["gross"]),
            "refunded": _money(r["refunded"]),
            "fees": {k: _money(v) for k, v in r["fees"].items()},
            "fees_total": _money(r["fees_total"]),
            "cogs_total": _money(r["cogs_total"]),
            "shipping_cost_total": _money(r["shipping_cost_total"]),
            "net": _money(r["net"]),
            "margin_pct": (round(r["margin_pct"], 2)
                           if r["margin_pct"] is not None else None),
            "loss_maker": r["loss_maker"],
            "listing_fee_per_unit": (
                round(r["listing_fee_per_unit"], 4)
                if r["listing_fee_per_unit"] is not None else None),
            "net_per_unit_sold": (
                round(r["net_per_unit_sold"], 2)
                if r["net_per_unit_sold"] is not None else None),
            "notes": r["notes"],
        }
        listings.append(_with_inr(obj, ("gross", "fees_total",
                                        "cogs_total",
                                        "shipping_cost_total", "net"),
                                  cad_to_inr))
    totals_obj = {
        "gross": _money(totals["gross"]),
        "fees_total": _money(totals["fees_total"]),
        "cogs_total": _money(totals["cogs_total"]),
        "shipping_cost_total": _money(totals["shipping_cost_total"]),
        "net": _money(totals["net"]),
        "margin_pct": (round(totals["margin_pct"], 2)
                       if totals["margin_pct"] is not None else None),
        "listings": totals["listings"],
        "loss_makers": totals["loss_makers"],
    }
    _with_inr(totals_obj, ("gross", "fees_total", "cogs_total",
                           "shipping_cost_total", "net"), cad_to_inr)
    return {
        "tool": TOOL, "version": __version__, "command": "report",
        "file": source_name,
        "currency": "amounts are in the currency of the input file",
        "rates": rates.as_dict(),
        "cad_to_inr": cad_to_inr,
        "listings": listings,
        "totals": totals_obj,
    }


_FEE_LABELS = {
    "listing_fee": "listing",
    "transaction_fee": "transaction",
    "processing_fee": "processing",
    "offsite_ads_fee": "offsite ads",
    "platform_fee": "platform fee",
}


def render_report_text(rows, totals, source_name, rates, cad_to_inr):
    lines = [
        f"seller-profit-truth v{__version__} — report for {source_name} "
        f"({totals['listings']} listing(s))",
        f"Fee rates: defaults as of {FEES_AS_OF} — override any rate "
        f"with the --etsy-*/--gumroad-* flags.",
        "Amounts are in the currency of your input file."
        + (f" INR equivalents at {cad_to_inr:g} per unit."
           if cad_to_inr is not None else ""),
        "",
    ]
    for i, r in enumerate(rows, 1):
        flag = "  ⚠ LOSS-MAKER" if r["loss_maker"] else ""
        lines.append(
            f"{i}. {r['name']} [{r['platform']}] — {r['units_sold']} "
            f"sold, {r['returns']} returned, {r['units_kept']} kept"
            f"{flag}")
        fee_bits = " · ".join(
            f"{_FEE_LABELS.get(k, k)} {_fmt(v, cad_to_inr)}"
            for k, v in r["fees"].items())
        lines.append(f"   Gross kept: {_fmt(r['gross'], cad_to_inr)}"
                     + (f" (refunded {_fmt(r['refunded'], cad_to_inr)})"
                        if r["refunded"] else ""))
        lines.append(f"   Fees: {fee_bits} "
                     f"= {_fmt(r['fees_total'], cad_to_inr)}")
        lines.append(f"   COGS: {_fmt(r['cogs_total'], cad_to_inr)} · "
                     f"Shipping cost: "
                     f"{_fmt(r['shipping_cost_total'], cad_to_inr)}")
        per_unit = (f" · per unit sold "
                    f"{_fmt(r['net_per_unit_sold'], cad_to_inr)}"
                    if r["net_per_unit_sold"] is not None else "")
        lines.append(f"   TRUE NET: {_fmt(r['net'], cad_to_inr)} "
                     f"(margin {_fmt_margin(r['margin_pct'])})"
                     f"{per_unit}")
        for note in r["notes"]:
            lines.append(f"   Note: {note}")
        lines.append("")
    lines.append(
        f"TOTALS: gross {_fmt(totals['gross'], cad_to_inr)} · fees "
        f"{_fmt(totals['fees_total'], cad_to_inr)} · COGS "
        f"{_fmt(totals['cogs_total'], cad_to_inr)} · shipping "
        f"{_fmt(totals['shipping_cost_total'], cad_to_inr)} · TRUE NET "
        f"{_fmt(totals['net'], cad_to_inr)} "
        f"(margin {_fmt_margin(totals['margin_pct'])})")
    lines.append(f"Loss-makers: {totals['loss_makers']} of "
                 f"{totals['listings']} listings")
    lines.append("Model: fees are charged on kept units; shipping cost "
                 "is counted on every unit shipped, returns included; "
                 "COGS on kept units only.")
    return "\n".join(lines)


def render_breakeven_text(be, rates):
    lines = [
        f"seller-profit-truth v{__version__} — break-even "
        f"[{be['platform']}]",
        f"Fee rates: defaults as of {FEES_AS_OF} — override any rate "
        f"with the --etsy-*/--gumroad-* flags.",
        f"Costs per unit: shipping cost {be['shipping_cost']:,.2f} · "
        f"COGS {be['cogs']:,.2f} · shipping charged "
        f"{be['shipping_charged']:,.2f}"
        + (f" · listing fee amortized over {be['units']} unit(s)"
           if be["platform"] == "etsy" else "")
        + (" · offsite ads ON" if be["offsite_ads"] else ""),
        f"Target margin: {be['target_margin_pct']:g}%",
        f"Minimum price: {be['min_price']:,.2f}",
        f"At that price, per unit: charged "
        f"{be['at_min_price']['charged_per_unit']:,.2f} · fees "
        f"{be['at_min_price']['fees_per_unit']:,.2f} · net "
        f"{be['at_min_price']['net_per_unit']:,.2f} · margin "
        f"{_fmt_margin(be['at_min_price']['margin_pct'])}",
        "Break-even assumes no returns; the price is rounded UP to "
        "the next cent so the rounded price still hits the target.",
    ]
    if be["note"]:
        lines.append(f"Note: {be['note']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in --json mode
    ({"error": ...} on stdout, same exit code 2) — an agent driving
    this tool with --json never gets plain text or a traceback. The
    flag lives on the class so subparsers share it."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def _add_rate_flags(p):
    p.add_argument("--etsy-listing-fee", type=float, default=None,
                   help=f"Etsy listing fee per listing (default "
                        f"{FeeRates.etsy_listing_fee})")
    p.add_argument("--etsy-transaction-pct", type=float, default=None,
                   help=f"Etsy transaction fee %% (default "
                        f"{FeeRates.etsy_transaction_pct})")
    p.add_argument("--etsy-processing-pct", type=float, default=None,
                   help=f"Etsy processing fee %% (default "
                        f"{FeeRates.etsy_processing_pct})")
    p.add_argument("--etsy-processing-fixed", type=float, default=None,
                   help=f"Etsy processing fixed fee (default "
                        f"{FeeRates.etsy_processing_fixed})")
    p.add_argument("--etsy-offsite-ads-pct", type=float, default=None,
                   help=f"Etsy offsite-ads fee %% (default "
                        f"{FeeRates.etsy_offsite_ads_pct})")
    p.add_argument("--gumroad-pct", type=float, default=None,
                   help=f"Gumroad fee %% (default "
                        f"{FeeRates.gumroad_pct})")
    p.add_argument("--gumroad-fixed", type=float, default=None,
                   help=f"Gumroad fixed fee (default "
                        f"{FeeRates.gumroad_fixed})")


def _cad_to_inr(a):
    rate = getattr(a, "cad_to_inr", None)
    if rate is None:
        return None
    if not math.isfinite(rate) or rate <= 0:
        raise ToolError(f"--cad-to-inr must be a positive finite "
                        f"number (got {rate!r})")
    return rate


def cmd_report(a):
    rates = rates_from_args(a)
    cad_to_inr = _cad_to_inr(a)
    path = Path(a.file)
    listings = load_rows(path)
    rows, totals = compute_report(listings, rates)
    if a.json:
        print(json.dumps(report_as_json(rows, totals, path.name, rates,
                                        cad_to_inr), indent=2))
    else:
        print(render_report_text(rows, totals, path.name, rates,
                                 cad_to_inr))
    return 1 if totals["loss_makers"] else 0


def cmd_breakeven(a):
    rates = rates_from_args(a)
    for flag, value in (("--shipping-charged", a.shipping_charged),
                        ("--shipping-cost", a.shipping_cost),
                        ("--cogs", a.cogs),
                        ("--target-margin", a.target_margin)):
        if value is None or (isinstance(value, float)
                             and not math.isfinite(value)):
            raise ToolError(f"{flag} must be a finite number")
        if value < 0:
            raise ToolError(f"{flag} must be >= 0 (got {value:g})")
    be = solve_breakeven(a.platform, a.shipping_charged,
                         a.shipping_cost, a.cogs, a.target_margin,
                         rates, offsite_ads=a.offsite_ads,
                         units=a.units)
    if a.json:
        print(json.dumps({"tool": TOOL, "version": __version__,
                          "command": "breakeven",
                          "rates": rates.as_dict(), **be}, indent=2))
    else:
        print(render_breakeven_text(be, rates))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _JsonAwareParser.json_mode = "--json" in argv
    ap = _JsonAwareParser(
        prog=TOOL,
        description="True per-listing profit for Etsy & Gumroad "
                    "sellers — every fee line, shipping and returns "
                    "subtracted (stdlib only, local only).")
    sub = ap.add_subparsers(dest="command", required=True,
                            parser_class=_JsonAwareParser)

    p_rep = sub.add_parser(
        "report", help="per-listing true profit from a .json/.csv "
                       "sales file")
    p_rep.add_argument("file", help="sales file (.json or .csv)")
    p_rep.add_argument("--cad-to-inr", type=float, default=None,
                       help="also print INR equivalents at this rate "
                            "per 1 unit of the input currency")
    p_rep.add_argument("--json", action="store_true",
                       help="print one JSON object instead of the "
                            "text report")
    _add_rate_flags(p_rep)
    p_rep.set_defaults(func=cmd_report)

    p_be = sub.add_parser(
        "breakeven", help="minimum price that truly hits a target "
                          "margin after fees")
    p_be.add_argument("--platform", choices=PLATFORMS, required=True)
    p_be.add_argument("--shipping-charged", type=float, default=0.0,
                      help="shipping charged to the buyer, per unit "
                           "(default 0)")
    p_be.add_argument("--shipping-cost", type=float, required=True,
                      help="what you pay to ship, per unit")
    p_be.add_argument("--cogs", type=float, required=True,
                      help="materials / COGS per unit")
    p_be.add_argument("--target-margin", type=float, required=True,
                      help="target true margin, in percent (e.g. 20)")
    p_be.add_argument("--units", type=int, default=1,
                      help="expected units sold — amortizes the Etsy "
                           "listing fee (default 1)")
    p_be.add_argument("--offsite-ads", action="store_true",
                      help="include Etsy's offsite-ads fee")
    p_be.add_argument("--json", action="store_true",
                      help="print one JSON object instead of the "
                           "text report")
    _add_rate_flags(p_be)
    p_be.set_defaults(func=cmd_breakeven)

    a = ap.parse_args(argv)

    def fail(msg):
        if getattr(a, "json", False):
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    try:
        return a.func(a)
    except ToolError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
