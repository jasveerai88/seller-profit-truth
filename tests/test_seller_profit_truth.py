#!/usr/bin/env python3
"""Tests for seller-profit-truth. Stdlib unittest only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

The fee-math tests use numbers worked by hand from the published
fee defaults (Nov 2026) — not numbers copied out of the tool's own
output. Both directions are covered: profitable listings report a
positive net and exit 0; a loss-maker is flagged and exits 1;
malformed input exits 2 with the row number named, in text AND in
--json mode.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SRC = PACK_ROOT / "src" / "seller_profit_truth.py"
EXAMPLES = PACK_ROOT / "examples"
sys.path.insert(0, str(PACK_ROOT / "src"))

import seller_profit_truth as spt  # noqa: E402

RATES = spt.FeeRates()


def listing(**over):
    base = {"name": "Test", "platform": "etsy", "price": 10.0,
            "units": 1, "shipping_charged": 0.0, "shipping_cost": 0.0,
            "cogs": 0.0, "returns": 0, "offsite_ads": False}
    base.update(over)
    return base


def run_cli(*args):
    return subprocess.run([sys.executable, str(SRC), *args],
                          capture_output=True, text=True)


def write_tmp(content, suffix):
    f = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False,
                                    encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


class TestEtsyFeeMath(unittest.TestCase):
    """Hand-checked against the Nov-2026 defaults:
    listing 0.20 · transaction 6.5% · processing 3% + 0.25 · ads 12%."""

    def test_jacket_numbers(self):
        # price 48, ship charged 6 -> charged 54; 12 sold, 1 returned
        # gross 11*54 = 594.00
        # transaction 6.5% * 594 = 38.61
        # processing 11 * (3% * 54 + 0.25) = 11 * 1.87 = 20.57
        # fees 0.20 + 38.61 + 20.57 = 59.38
        # cogs 11 * 18 = 198 · shipping 12 * 9.50 = 114
        # net 594 - 59.38 - 198 - 114 = 222.62
        r = spt.compute_listing(listing(
            name="Vintage Denim Jacket", price=48.0, units=12,
            shipping_charged=6.0, shipping_cost=9.5, cogs=18.0,
            returns=1), RATES)
        self.assertAlmostEqual(r["gross"], 594.00)
        self.assertAlmostEqual(r["refunded"], 54.00)
        self.assertAlmostEqual(r["fees"]["listing_fee"], 0.20)
        self.assertAlmostEqual(r["fees"]["transaction_fee"], 38.61)
        self.assertAlmostEqual(r["fees"]["processing_fee"], 20.57)
        self.assertAlmostEqual(r["fees"]["offsite_ads_fee"], 0.0)
        self.assertAlmostEqual(r["fees_total"], 59.38)
        self.assertAlmostEqual(r["cogs_total"], 198.00)
        self.assertAlmostEqual(r["shipping_cost_total"], 114.00)
        self.assertAlmostEqual(r["net"], 222.62)
        self.assertAlmostEqual(r["margin_pct"], 37.478, places=2)
        self.assertFalse(r["loss_maker"])

    def test_offsite_ads_fee_line(self):
        # mug: charged 16.50, 51 kept -> gross 841.50
        # ads 12% * 841.50 = 100.98
        r = spt.compute_listing(listing(
            name="Ceramic Mug", price=12.0, units=60,
            shipping_charged=4.5, shipping_cost=8.9, cogs=6.8,
            returns=9, offsite_ads=True), RATES)
        self.assertAlmostEqual(r["fees"]["offsite_ads_fee"], 100.98)
        self.assertAlmostEqual(r["fees_total"], 193.8725)
        self.assertAlmostEqual(r["net"], -233.1725)
        self.assertTrue(r["loss_maker"])

    def test_return_shipping_is_eaten(self):
        # 1 sold, 1 returned: no revenue, but the outbound shipping
        # cost is gone for good -> net is negative by that amount.
        r = spt.compute_listing(listing(
            platform="gumroad", price=10.0, units=1,
            shipping_cost=4.0, returns=1), RATES)
        self.assertEqual(r["units_kept"], 0)
        self.assertAlmostEqual(r["gross"], 0.0)
        self.assertAlmostEqual(r["net"], -4.0)
        self.assertTrue(r["loss_maker"])
        self.assertIsNone(r["margin_pct"])

    def test_zero_sales_etsy_still_owes_listing_fee(self):
        r = spt.compute_listing(listing(units=0), RATES)
        self.assertAlmostEqual(r["net"], -0.20)
        self.assertTrue(r["loss_maker"])
        self.assertTrue(any("listing fee" in n for n in r["notes"]))

    def test_zero_sales_gumroad_is_zero(self):
        r = spt.compute_listing(listing(platform="gumroad", units=0),
                                RATES)
        self.assertAlmostEqual(r["net"], 0.0)
        self.assertFalse(r["loss_maker"])

    def test_listing_fee_amortization(self):
        r = spt.compute_listing(listing(units=12, price=48.0), RATES)
        self.assertAlmostEqual(r["listing_fee_per_unit"], 0.20 / 12)


class TestGumroadFeeMath(unittest.TestCase):
    """Gumroad default: 10% + 0.50 per transaction on charged total."""

    def test_wall_art_numbers(self):
        # price 9, 140 sold, 6 returned -> 134 kept
        # fee per unit 10% * 9 + 0.50 = 1.40 -> 134 * 1.40 = 187.60
        # net 1206 - 187.60 = 1018.40
        r = spt.compute_listing(listing(
            name="Printable Wall Art Set", platform="gumroad",
            price=9.0, units=140, returns=6), RATES)
        self.assertAlmostEqual(r["gross"], 1206.00)
        self.assertAlmostEqual(r["fees"]["platform_fee"], 187.60)
        self.assertAlmostEqual(r["net"], 1018.40)
        self.assertAlmostEqual(r["margin_pct"], 84.4444, places=3)
        self.assertFalse(r["loss_maker"])

    def test_offsite_ads_flag_warns_on_gumroad(self):
        r = spt.compute_listing(listing(platform="gumroad",
                                        offsite_ads=True), RATES)
        self.assertTrue(any("no effect on gumroad" in n
                            for n in r["notes"]))
        self.assertNotIn("offsite_ads_fee", r["fees"])


class TestOverrides(unittest.TestCase):
    def test_gumroad_pct_override(self):
        row = listing(platform="gumroad", price=9.0, units=140,
                      returns=6)
        custom = spt.FeeRates(gumroad_pct=0.0)
        r = spt.compute_listing(row, custom)
        # only the fixed 0.50 remains: 134 * 0.50 = 67.00
        self.assertAlmostEqual(r["fees"]["platform_fee"], 67.00)
        self.assertAlmostEqual(r["net"], 1206.00 - 67.00)

    def test_etsy_rates_override_changes_result(self):
        row = listing(price=48.0, units=12, shipping_charged=6.0,
                      shipping_cost=9.5, cogs=18.0, returns=1)
        before = spt.compute_listing(row, RATES)["net"]
        after = spt.compute_listing(
            row, spt.FeeRates(etsy_transaction_pct=0.0))["net"]
        self.assertGreater(after, before)
        self.assertAlmostEqual(after - before, 38.61)

    def test_bad_rate_rejected(self):
        class A:  # minimal stand-in for parsed args
            etsy_listing_fee = None
            etsy_transaction_pct = 150.0
            etsy_processing_pct = None
            etsy_processing_fixed = None
            etsy_offsite_ads_pct = None
            gumroad_pct = None
            gumroad_fixed = None
        with self.assertRaises(spt.ToolError):
            spt.rates_from_args(A())


class TestValidation(unittest.TestCase):
    def _bad(self, rows, needle):
        path = write_tmp(json.dumps(rows), ".json")
        with self.assertRaises(spt.ToolError) as ctx:
            spt.load_rows(Path(path))
        self.assertIn(needle, str(ctx.exception))

    def test_missing_price_names_row(self):
        self._bad([listing(), {"name": "X", "platform": "etsy",
                               "units": 1}], "row 2")

    def test_negative_price(self):
        self._bad([listing(price=-1)], "row 1")

    def test_returns_exceed_units(self):
        self._bad([listing(units=2, returns=3)], "returns")

    def test_unknown_platform(self):
        self._bad([listing(platform="shopify")], "platform")

    def test_nan_rejected(self):
        path = write_tmp('[{"name": "X", "platform": "etsy", '
                         '"price": NaN, "units": 1}]', ".json")
        with self.assertRaises(spt.ToolError):
            spt.load_rows(Path(path))

    def test_bool_is_not_a_number(self):
        self._bad([dict(listing(), price=True)], "row 1")

    def test_fractional_units(self):
        self._bad([listing(units=2.5)], "whole number")

    def test_empty_name(self):
        self._bad([listing(name="  ")], "name")

    def test_row_not_an_object(self):
        self._bad([42], "row 1")

    def test_empty_file(self):
        path = write_tmp("[]", ".json")
        with self.assertRaises(spt.ToolError):
            spt.load_rows(Path(path))

    def test_malformed_json(self):
        path = write_tmp("{not json", ".json")
        with self.assertRaises(spt.ToolError) as ctx:
            spt.load_rows(Path(path))
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_csv_bad_number_names_line(self):
        path = write_tmp(
            "name,platform,price,units\n"
            "Good,etsy,10,1\n"
            "Bad,etsy,$12,1\n", ".csv")
        with self.assertRaises(spt.ToolError) as ctx:
            spt.load_rows(Path(path))
        self.assertIn("row 3", str(ctx.exception))
        self.assertIn("not a number", str(ctx.exception))

    def test_object_without_listings_key(self):
        path = write_tmp('{"rows": []}', ".json")
        with self.assertRaises(spt.ToolError) as ctx:
            spt.load_rows(Path(path))
        self.assertIn("listings", str(ctx.exception))


class TestCsvJsonAgreement(unittest.TestCase):
    def test_sample_files_agree(self):
        a = spt.load_rows(EXAMPLES / "sample.json")
        b = spt.load_rows(EXAMPLES / "sample.csv")
        rows_a, totals_a = spt.compute_report(a, RATES)
        rows_b, totals_b = spt.compute_report(b, RATES)
        self.assertEqual([r["name"] for r in rows_a],
                         [r["name"] for r in rows_b])
        for key in ("gross", "fees_total", "net"):
            self.assertAlmostEqual(totals_a[key], totals_b[key])
        # the shipped sample's hand-verified totals
        self.assertAlmostEqual(totals_a["gross"], 3033.50)
        self.assertAlmostEqual(totals_a["fees_total"], 485.29, places=2)
        self.assertAlmostEqual(totals_a["net"], 1013.9075)
        self.assertEqual(totals_a["loss_makers"], 1)
        mug = [r for r in rows_a if r["name"] == "Ceramic Mug"][0]
        self.assertTrue(mug["loss_maker"])
        self.assertAlmostEqual(mug["net"], -233.1725)


class TestBreakeven(unittest.TestCase):
    def test_candle_breakeven_hand_checked(self):
        # r = 6.5% + 3% = 9.5%; fixed/unit = 0.25 + 0.20/30
        # charged = (0.25666… + 6.25 + 5.50) / (1 - .095 - .20)
        #         = 12.00666… / 0.705 = 17.0307… -> rounds UP to 17.04
        be = spt.solve_breakeven("etsy", 0.0, 6.25, 5.50, 20.0, RATES,
                                 units=30)
        self.assertAlmostEqual(be["min_price"], 17.04)
        self.assertGreaterEqual(be["at_min_price"]["margin_pct"], 20.0)

    def test_roundtrip_margin_hits_target(self):
        for platform, kw in (("etsy", dict(units=25)),
                             ("gumroad", dict())):
            be = spt.solve_breakeven(platform, 3.0, 7.0, 4.0, 25.0,
                                     RATES, **kw)
            price = be["min_price"]
            at = spt.unit_margin_pct(price, 3.0, 7.0, 4.0, platform,
                                     RATES, units=kw.get("units", 1))
            below = spt.unit_margin_pct(price - 0.01, 3.0, 7.0, 4.0,
                                        platform, RATES,
                                        units=kw.get("units", 1))
            self.assertGreaterEqual(at, 25.0, platform)
            self.assertLess(below, 25.0, platform)

    def test_breakeven_through_report_math(self):
        # Price a listing at the break-even price and run the full
        # report path: the margin must land on the target.
        be = spt.solve_breakeven("etsy", 0.0, 6.25, 5.50, 20.0, RATES,
                                 units=30)
        r = spt.compute_listing(listing(
            price=be["min_price"], units=30, shipping_cost=6.25,
            cogs=5.50), RATES)
        self.assertAlmostEqual(r["margin_pct"], 20.0, delta=0.15)
        self.assertGreaterEqual(r["margin_pct"], 20.0)

    def test_impossible_target_is_clean_error(self):
        # Gumroad takes 10%; a 95% target can never fit.
        with self.assertRaises(spt.ToolError) as ctx:
            spt.solve_breakeven("gumroad", 0.0, 1.0, 1.0, 95.0, RATES)
        self.assertIn("unreachable", str(ctx.exception))

    def test_offsite_ads_raise_breakeven(self):
        plain = spt.solve_breakeven("etsy", 0.0, 6.25, 5.50, 20.0,
                                    RATES, units=30)
        ads = spt.solve_breakeven("etsy", 0.0, 6.25, 5.50, 20.0, RATES,
                                  offsite_ads=True, units=30)
        self.assertGreater(ads["min_price"], plain["min_price"])


class TestCli(unittest.TestCase):
    def test_report_sample_exit_1_with_loss_maker(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"))
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("LOSS-MAKER", p.stdout)
        self.assertIn("TRUE NET 1,013.91", p.stdout)
        self.assertNotIn("Traceback", p.stderr)

    def test_report_clean_file_exit_0(self):
        path = write_tmp(json.dumps([listing(
            platform="gumroad", price=20.0, units=5)]), ".json")
        p = run_cli("report", path)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_report_json_mode(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"), "--json")
        self.assertEqual(p.returncode, 1)
        obj = json.loads(p.stdout)
        self.assertEqual(obj["tool"], "seller-profit-truth")
        self.assertEqual(obj["version"], "1.0.0")
        self.assertEqual(obj["totals"]["loss_makers"], 1)
        self.assertAlmostEqual(obj["totals"]["net"], 1013.91)
        mug = [l for l in obj["listings"]
               if l["name"] == "Ceramic Mug"][0]
        self.assertTrue(mug["loss_maker"])
        self.assertIn("offsite_ads_fee", mug["fees"])

    def test_json_and_text_agree(self):
        text = run_cli("report", str(EXAMPLES / "sample.json"))
        js = run_cli("report", str(EXAMPLES / "sample.json"), "--json")
        self.assertEqual(text.returncode, js.returncode)
        obj = json.loads(js.stdout)
        self.assertIn(f"{obj['totals']['net']:,.2f}", text.stdout)

    def test_missing_file_clean_error(self):
        p = run_cli("report", "/nonexistent/sales.json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("ERROR: file not found", p.stdout)
        self.assertNotIn("Traceback", p.stderr)

    def test_missing_file_json_error_object(self):
        p = run_cli("report", "/nonexistent/sales.json", "--json")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stdout),
                         {"error": "file not found: "
                                   "/nonexistent/sales.json"})

    def test_bad_row_json_error_object(self):
        path = write_tmp(json.dumps([listing(price=-3)]), ".json")
        p = run_cli("report", path, "--json")
        self.assertEqual(p.returncode, 2)
        obj = json.loads(p.stdout)
        self.assertIn("row 1", obj["error"])

    def test_argparse_error_is_json_in_json_mode(self):
        p = run_cli("report", "--json")  # missing the file argument
        self.assertEqual(p.returncode, 2)
        obj = json.loads(p.stdout)
        self.assertIn("error", obj)

    def test_wrong_extension(self):
        path = write_tmp("[]", ".txt")
        p = run_cli("report", path)
        self.assertEqual(p.returncode, 2)
        self.assertIn(".json or .csv", p.stdout)

    def test_override_flag_changes_cli_result(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"),
                    "--gumroad-pct", "0", "--json")
        obj = json.loads(p.stdout)
        art = [l for l in obj["listings"]
               if l["platform"] == "gumroad"][0]
        self.assertAlmostEqual(art["fees"]["platform_fee"], 67.00)

    def test_cad_to_inr_fields(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"),
                    "--cad-to-inr", "67.97", "--json")
        obj = json.loads(p.stdout)
        self.assertAlmostEqual(obj["totals"]["net_inr"],
                               round(1013.91 * 67.97, 2), places=1)
        p2 = run_cli("report", str(EXAMPLES / "sample.json"),
                     "--cad-to-inr", "67.97")
        self.assertIn("₹", p2.stdout)

    def test_bad_cad_to_inr(self):
        p = run_cli("report", str(EXAMPLES / "sample.json"),
                    "--cad-to-inr", "-5")
        self.assertEqual(p.returncode, 2)
        self.assertIn("ERROR", p.stdout)

    def test_breakeven_cli(self):
        p = run_cli("breakeven", "--platform", "etsy",
                    "--shipping-cost", "6.25", "--cogs", "5.50",
                    "--target-margin", "20", "--units", "30")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("Minimum price: 17.04", p.stdout)

    def test_breakeven_json(self):
        p = run_cli("breakeven", "--platform", "gumroad",
                    "--shipping-cost", "0", "--cogs", "1",
                    "--target-margin", "50", "--json")
        self.assertEqual(p.returncode, 0)
        obj = json.loads(p.stdout)
        self.assertEqual(obj["command"], "breakeven")
        self.assertGreaterEqual(obj["at_min_price"]["margin_pct"], 50.0)

    def test_breakeven_impossible_json_error(self):
        p = run_cli("breakeven", "--platform", "gumroad",
                    "--shipping-cost", "1", "--cogs", "1",
                    "--target-margin", "95", "--json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("unreachable", json.loads(p.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
