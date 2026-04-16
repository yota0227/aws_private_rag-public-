"""Unit tests for clock_domain module."""

import unittest
from clock_domain import (
    extract_clock_domains,
    classify_clock_domain,
    detect_cdc_boundary,
)


class TestExtractClockDomains(unittest.TestCase):
    """Tests for extract_clock_domains()."""

    def test_always_ff_posedge(self):
        rtl = "always_ff @(posedge i_ai_clk) begin\n  q <= d;\nend"
        self.assertEqual(extract_clock_domains(rtl), ["i_ai_clk"])

    def test_always_posedge(self):
        rtl = "always @(posedge i_noc_clk) begin\n  q <= d;\nend"
        self.assertEqual(extract_clock_domains(rtl), ["i_noc_clk"])

    def test_multiple_clocks(self):
        rtl = (
            "always_ff @(posedge i_ai_clk) begin\n  a <= b;\nend\n"
            "always @(posedge i_noc_clk) begin\n  c <= d;\nend\n"
            "always_ff @(posedge i_dm_clk) begin\n  e <= f;\nend\n"
        )
        result = extract_clock_domains(rtl)
        self.assertEqual(result, ["i_ai_clk", "i_dm_clk", "i_noc_clk"])

    def test_duplicate_clocks_deduplicated(self):
        rtl = (
            "always_ff @(posedge i_ai_clk) begin end\n"
            "always_ff @(posedge i_ai_clk) begin end\n"
        )
        self.assertEqual(extract_clock_domains(rtl), ["i_ai_clk"])

    def test_no_clock_patterns(self):
        rtl = "assign out = in1 & in2;"
        self.assertEqual(extract_clock_domains(rtl), [])

    def test_empty_input(self):
        self.assertEqual(extract_clock_domains(""), [])
        self.assertEqual(extract_clock_domains(None), [])

    def test_negedge_not_matched(self):
        rtl = "always_ff @(negedge clk) begin end"
        self.assertEqual(extract_clock_domains(rtl), [])


class TestClassifyClockDomain(unittest.TestCase):
    """Tests for classify_clock_domain()."""

    def test_ai_clock_variants(self):
        self.assertEqual(classify_clock_domain("i_ai_clk"), "ai_clock_domain")
        self.assertEqual(classify_clock_domain("ai_clk"), "ai_clock_domain")
        self.assertEqual(classify_clock_domain("aiclk"), "ai_clock_domain")

    def test_noc_clock_variants(self):
        self.assertEqual(classify_clock_domain("i_noc_clk"), "noc_clock_domain")
        self.assertEqual(classify_clock_domain("noc_clk"), "noc_clock_domain")
        self.assertEqual(classify_clock_domain("nocclk"), "noc_clock_domain")
        self.assertEqual(classify_clock_domain("i_nocclk"), "noc_clock_domain")

    def test_dm_clock_variants(self):
        self.assertEqual(classify_clock_domain("i_dm_clk"), "dm_clock_domain")
        self.assertEqual(classify_clock_domain("dm_clk"), "dm_clock_domain")

    def test_ref_clock_variants(self):
        self.assertEqual(classify_clock_domain("i_ref_clk"), "ref_clock_domain")
        self.assertEqual(classify_clock_domain("ref_clk"), "ref_clock_domain")

    def test_unclassified(self):
        self.assertEqual(classify_clock_domain("tck"), "unclassified_clock")
        self.assertEqual(classify_clock_domain("some_random_signal"), "unclassified_clock")

    def test_empty_input(self):
        self.assertEqual(classify_clock_domain(""), "unclassified_clock")
        self.assertEqual(classify_clock_domain(None), "unclassified_clock")

    def test_real_hierarchy_patterns(self):
        """Patterns from trinity_hierarchy.csv."""
        self.assertEqual(classify_clock_domain("i_ai_clk"), "ai_clock_domain")
        self.assertEqual(classify_clock_domain("i_noc_clk"), "noc_clock_domain")
        self.assertEqual(classify_clock_domain("i_dm_clk"), "dm_clock_domain")
        self.assertEqual(classify_clock_domain("i_ref_clk"), "ref_clock_domain")
        self.assertEqual(classify_clock_domain("vc_buf_gated_clk"), "unclassified_clock")
        self.assertEqual(classify_clock_domain("core_clock"), "unclassified_clock")


class TestDetectCdcBoundary(unittest.TestCase):
    """Tests for detect_cdc_boundary()."""

    def test_two_domains_is_cdc(self):
        domains = [
            {"domain": "noc_clock_domain", "signals": ["i_noc_clk"]},
            {"domain": "ai_clock_domain", "signals": ["i_ai_clk"]},
        ]
        result = detect_cdc_boundary(domains)
        self.assertTrue(result["is_cdc_boundary"])
        self.assertEqual(
            result["cdc_pairs"],
            [["ai_clock_domain", "noc_clock_domain"]],
        )

    def test_single_domain_no_cdc(self):
        domains = [
            {"domain": "ai_clock_domain", "signals": ["i_ai_clk"]},
        ]
        result = detect_cdc_boundary(domains)
        self.assertFalse(result["is_cdc_boundary"])
        self.assertEqual(result["cdc_pairs"], [])

    def test_empty_list_no_cdc(self):
        result = detect_cdc_boundary([])
        self.assertFalse(result["is_cdc_boundary"])
        self.assertEqual(result["cdc_pairs"], [])

    def test_none_input(self):
        result = detect_cdc_boundary(None)
        self.assertFalse(result["is_cdc_boundary"])
        self.assertEqual(result["cdc_pairs"], [])

    def test_three_domains_multiple_pairs(self):
        domains = [
            {"domain": "ai_clock_domain", "signals": ["i_ai_clk"]},
            {"domain": "noc_clock_domain", "signals": ["i_noc_clk"]},
            {"domain": "dm_clock_domain", "signals": ["i_dm_clk"]},
        ]
        result = detect_cdc_boundary(domains)
        self.assertTrue(result["is_cdc_boundary"])
        self.assertEqual(len(result["cdc_pairs"]), 3)

    def test_duplicate_domains_counted_once(self):
        domains = [
            {"domain": "ai_clock_domain", "signals": ["i_ai_clk"]},
            {"domain": "ai_clock_domain", "signals": ["ai_clk"]},
        ]
        result = detect_cdc_boundary(domains)
        self.assertFalse(result["is_cdc_boundary"])
        self.assertEqual(result["cdc_pairs"], [])


if __name__ == "__main__":
    unittest.main()
