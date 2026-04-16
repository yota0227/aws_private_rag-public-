"""Unit tests for hierarchy module."""

import csv
import io
import json
import logging
import unittest

from hierarchy import (
    build_hierarchy,
    serialize_hierarchy_csv,
    serialize_hierarchy_json,
)


def _mod(name, instances="", ports="", params="", path=""):
    """Helper to build a module dict."""
    return {
        "module_name": name,
        "instance_list": instances,
        "port_list": ports,
        "parameter_list": params,
        "file_path": path,
    }


class TestBuildHierarchy(unittest.TestCase):
    """Tests for build_hierarchy covering tree construction and edge cases."""

    def test_empty_modules(self):
        self.assertEqual(build_hierarchy([]), [])

    def test_single_module_no_instances(self):
        tree = build_hierarchy([_mod("top")])
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]["module_name"], "top")
        self.assertEqual(tree[0]["instance_name"], "top")
        self.assertEqual(tree[0]["hierarchy_path"], "top")
        self.assertEqual(tree[0]["children"], [])

    def test_two_level_hierarchy(self):
        modules = [
            _mod("top", instances="u_sub: sub_mod"),
            _mod("sub_mod"),
        ]
        tree = build_hierarchy(modules)
        self.assertEqual(len(tree), 1)
        root = tree[0]
        self.assertEqual(root["module_name"], "top")
        self.assertEqual(len(root["children"]), 1)
        child = root["children"][0]
        self.assertEqual(child["module_name"], "sub_mod")
        self.assertEqual(child["instance_name"], "u_sub")
        self.assertEqual(child["hierarchy_path"], "top.u_sub")

    def test_three_level_hierarchy(self):
        modules = [
            _mod("top", instances="u_mid: mid"),
            _mod("mid", instances="u_leaf: leaf"),
            _mod("leaf"),
        ]
        tree = build_hierarchy(modules)
        root = tree[0]
        mid = root["children"][0]
        leaf = mid["children"][0]
        self.assertEqual(leaf["hierarchy_path"], "top.u_mid.u_leaf")
        self.assertEqual(leaf["module_name"], "leaf")

    def test_multiple_children(self):
        modules = [
            _mod("top", instances="u_a: mod_a, u_b: mod_b"),
            _mod("mod_a"),
            _mod("mod_b"),
        ]
        tree = build_hierarchy(modules)
        self.assertEqual(len(tree[0]["children"]), 2)
        names = {c["module_name"] for c in tree[0]["children"]}
        self.assertEqual(names, {"mod_a", "mod_b"})

    def test_root_identification(self):
        """Only modules not instantiated by others are roots."""
        modules = [
            _mod("root_a", instances="u_shared: shared"),
            _mod("root_b", instances="u_shared2: shared"),
            _mod("shared"),
        ]
        tree = build_hierarchy(modules)
        root_names = {n["module_name"] for n in tree}
        self.assertEqual(root_names, {"root_a", "root_b"})

    def test_circular_reference_cut(self):
        """Circular A->B->A should be detected and branch cut."""
        modules = [
            _mod("mod_a", instances="u_b: mod_b"),
            _mod("mod_b", instances="u_a: mod_a"),
        ]
        with self.assertLogs("hierarchy", level="WARNING") as cm:
            tree = build_hierarchy(modules)
        self.assertTrue(any("Circular reference" in msg for msg in cm.output))
        # Both instantiate each other so neither is a pure root;
        # fallback makes both roots. Circular branch is cut.
        self.assertGreaterEqual(len(tree), 1)

    def test_child_not_in_module_list(self):
        """Instance referencing an undefined module should still appear."""
        modules = [_mod("top", instances="u_ext: external_mod")]
        tree = build_hierarchy(modules)
        root = tree[0]
        self.assertEqual(len(root["children"]), 1)
        child = root["children"][0]
        self.assertEqual(child["module_name"], "external_mod")
        self.assertEqual(child["children"], [])


class TestNodeFields(unittest.TestCase):
    """Tests for node field completeness (Req 2.2, 2.3)."""

    def test_required_fields_present(self):
        modules = [_mod("top", ports="input clk, output data")]
        tree = build_hierarchy(modules)
        node = tree[0]
        for field in [
            "module_name", "instance_name", "hierarchy_path",
            "clock_signals", "reset_signals", "memory_instances", "children",
        ]:
            self.assertIn(field, node, f"Missing field: {field}")

    def test_clock_signal_extraction(self):
        modules = [_mod("top", ports="input i_ai_clk, input i_noc_clk, output data")]
        tree = build_hierarchy(modules)
        self.assertEqual(tree[0]["clock_signals"], ["i_ai_clk", "i_noc_clk"])

    def test_clock_pattern_case_insensitive(self):
        modules = [_mod("top", ports="input SYS_CLOCK, input ref_CLK")]
        tree = build_hierarchy(modules)
        self.assertEqual(tree[0]["clock_signals"], ["SYS_CLOCK", "ref_CLK"])

    def test_reset_signal_extraction(self):
        modules = [_mod("top", ports="input i_rst_n, input global_reset, output q")]
        tree = build_hierarchy(modules)
        self.assertEqual(tree[0]["reset_signals"], ["i_rst_n", "global_reset"])

    def test_memory_instance_identification(self):
        modules = [
            _mod("top", instances="u_sram_256x64: sram_mod, u_logic: logic_mod")
        ]
        tree = build_hierarchy(modules)
        self.assertEqual(tree[0]["memory_instances"], ["u_sram_256x64"])

    def test_memory_patterns(self):
        """All memory patterns should be detected."""
        inst = (
            "u_mem: t1, u_sram: t2, u_ram: t3, u_rom: t4, "
            "u_fifo: t5, u_reg_bank: t6, u_latch: t7, u_logic: t8"
        )
        modules = [_mod("top", instances=inst)]
        tree = build_hierarchy(modules)
        self.assertEqual(len(tree[0]["memory_instances"]), 7)

    def test_no_clock_no_reset(self):
        modules = [_mod("top", ports="input data_in, output data_out")]
        tree = build_hierarchy(modules)
        self.assertEqual(tree[0]["clock_signals"], [])
        self.assertEqual(tree[0]["reset_signals"], [])


class TestSerializeJson(unittest.TestCase):
    """Tests for serialize_hierarchy_json (Req 2.5)."""

    def test_roundtrip(self):
        modules = [
            _mod("top", instances="u_sub: sub", ports="input clk, input rst_n"),
            _mod("sub", ports="input clk"),
        ]
        tree = build_hierarchy(modules)
        json_str = serialize_hierarchy_json(tree)
        restored = json.loads(json_str)
        self.assertEqual(tree, restored)

    def test_empty_tree(self):
        json_str = serialize_hierarchy_json([])
        self.assertEqual(json.loads(json_str), [])


class TestSerializeCsv(unittest.TestCase):
    """Tests for serialize_hierarchy_csv (Req 2.5)."""

    def test_csv_columns(self):
        modules = [_mod("top", ports="input clk, input rst")]
        tree = build_hierarchy(modules)
        csv_str = serialize_hierarchy_csv(tree)
        reader = csv.DictReader(io.StringIO(csv_str))
        self.assertEqual(
            reader.fieldnames,
            ["Hierarchy", "Module", "Clock", "Reset", "Memory_Instances"],
        )

    def test_csv_row_count(self):
        modules = [
            _mod("top", instances="u_a: a, u_b: b"),
            _mod("a"),
            _mod("b"),
        ]
        tree = build_hierarchy(modules)
        csv_str = serialize_hierarchy_csv(tree)
        rows = list(csv.DictReader(io.StringIO(csv_str)))
        self.assertEqual(len(rows), 3)  # top + a + b

    def test_csv_slash_separated_signals(self):
        modules = [_mod("top", ports="input clk1, input clk2, input rst_a")]
        tree = build_hierarchy(modules)
        csv_str = serialize_hierarchy_csv(tree)
        rows = list(csv.DictReader(io.StringIO(csv_str)))
        self.assertEqual(rows[0]["Clock"], "clk1/clk2")
        self.assertEqual(rows[0]["Reset"], "rst_a")

    def test_csv_json_module_set_match(self):
        """CSV and JSON should contain the same set of modules."""
        modules = [
            _mod("top", instances="u_a: a"),
            _mod("a", instances="u_b: b"),
            _mod("b"),
        ]
        tree = build_hierarchy(modules)

        json_str = serialize_hierarchy_json(tree)
        csv_str = serialize_hierarchy_csv(tree)

        def _collect_json_modules(nodes):
            names = set()
            for n in nodes:
                names.add(n["module_name"])
                names |= _collect_json_modules(n.get("children", []))
            return names

        json_modules = _collect_json_modules(json.loads(json_str))
        csv_modules = {
            row["Module"]
            for row in csv.DictReader(io.StringIO(csv_str))
        }
        self.assertEqual(json_modules, csv_modules)

    def test_empty_tree_csv(self):
        csv_str = serialize_hierarchy_csv([])
        rows = list(csv.DictReader(io.StringIO(csv_str)))
        self.assertEqual(len(rows), 0)


if __name__ == "__main__":
    unittest.main()
