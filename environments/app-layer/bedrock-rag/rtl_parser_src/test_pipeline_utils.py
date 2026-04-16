"""Unit tests for pipeline_utils.extract_pipeline_id."""

import unittest

from pipeline_utils import extract_pipeline_id


class TestExtractPipelineId(unittest.TestCase):
    """Tests for extract_pipeline_id covering valid keys and edge cases."""

    # --- Valid keys ---

    def test_standard_key(self):
        result = extract_pipeline_id("rtl-sources/tt_20260221/dispatch/tt_dispatch_top.sv")
        self.assertEqual(result["pipeline_id"], "tt_20260221")
        self.assertEqual(result["chip_type"], "tt")
        self.assertEqual(result["snapshot_date"], "20260221")

    def test_key_with_deep_path(self):
        result = extract_pipeline_id("rtl-sources/n2_20260501/a/b/c/d.sv")
        self.assertEqual(result["pipeline_id"], "n2_20260501")
        self.assertEqual(result["chip_type"], "n2")
        self.assertEqual(result["snapshot_date"], "20260501")

    def test_multiple_underscores_in_dir(self):
        """chip_type is before first _, snapshot_date is everything after."""
        result = extract_pipeline_id("rtl-sources/tt_n1b0_20260221/path/module.sv")
        self.assertEqual(result["pipeline_id"], "tt_n1b0_20260221")
        self.assertEqual(result["chip_type"], "tt")
        self.assertEqual(result["snapshot_date"], "n1b0_20260221")

    def test_dir_only_no_file(self):
        """Key is just the directory with trailing slash."""
        result = extract_pipeline_id("rtl-sources/tt_20260221/")
        self.assertEqual(result["pipeline_id"], "tt_20260221")
        self.assertEqual(result["chip_type"], "tt")
        self.assertEqual(result["snapshot_date"], "20260221")

    # --- Invalid / edge-case keys → default ---

    def test_empty_string(self):
        result = extract_pipeline_id("")
        self.assertEqual(result, _default())

    def test_none_input(self):
        result = extract_pipeline_id(None)
        self.assertEqual(result, _default())

    def test_no_rtl_sources_prefix(self):
        result = extract_pipeline_id("other-prefix/tt_20260221/module.sv")
        self.assertEqual(result, _default())

    def test_dir_without_underscore(self):
        result = extract_pipeline_id("rtl-sources/tt20260221/module.sv")
        self.assertEqual(result, _default())

    def test_prefix_only(self):
        result = extract_pipeline_id("rtl-sources/")
        self.assertEqual(result, _default())

    def test_leading_underscore_empty_chip(self):
        """Directory name starts with _ → empty chip_type → default."""
        result = extract_pipeline_id("rtl-sources/_20260221/module.sv")
        self.assertEqual(result, _default())

    def test_trailing_underscore_empty_date(self):
        """Directory name ends with _ → empty snapshot_date → default."""
        result = extract_pipeline_id("rtl-sources/tt_/module.sv")
        self.assertEqual(result, _default())

    def test_integer_input(self):
        result = extract_pipeline_id(123)
        self.assertEqual(result, _default())


def _default():
    return {"pipeline_id": "unknown_unknown", "chip_type": "unknown", "snapshot_date": "unknown"}


if __name__ == "__main__":
    unittest.main()
