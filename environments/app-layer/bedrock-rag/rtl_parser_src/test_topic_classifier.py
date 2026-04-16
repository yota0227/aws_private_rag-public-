"""Tests for topic_classifier module — topic classification and inheritance."""

from topic_classifier import classify_topic, suggest_inherited_topic


# ---------------------------------------------------------------------------
# classify_topic — Trinity RTL patterns
# ---------------------------------------------------------------------------

class TestClassifyTopic:
    """Tests for classify_topic."""

    def test_noc_by_module_name(self):
        assert "NoC" in classify_topic("", "tt_noc_router")

    def test_fpu_by_module_name(self):
        assert "FPU" in classify_topic("", "tt_fpu_gtile")

    def test_edc_by_module_name(self):
        assert "EDC" in classify_topic("", "tt_edc1_node")

    def test_overlay_by_module_name(self):
        assert "Overlay" in classify_topic("", "tt_overlay_wrapper")

    def test_dispatch_by_module_name(self):
        assert "Dispatch" in classify_topic("", "tt_dispatch_engine")

    def test_sfpu_by_module_name(self):
        assert "SFPU" in classify_topic("", "tt_sfpu")

    def test_noc_by_path(self):
        assert "NoC" in classify_topic("/rtl/noc/router.sv", "some_module")

    def test_fpu_by_path(self):
        assert "FPU" in classify_topic("/rtl/fpu/tile.sv", "some_module")

    def test_unclassified(self):
        assert classify_topic("", "random_module") == ["unclassified"]

    def test_multiple_topics(self):
        # Module name matches NoC, path matches FPU
        result = classify_topic("/rtl/fpu/noc_bridge.sv", "tt_noc_bridge")
        assert "NoC" in result
        assert "FPU" in result

    def test_empty_inputs(self):
        assert classify_topic("", "") == ["unclassified"]

    def test_none_inputs(self):
        assert classify_topic(None, None) == ["unclassified"]

    def test_l1_cache_by_path(self):
        assert "L1_Cache" in classify_topic("/rtl/l1/data_cache.sv", "")

    def test_clock_reset_by_prefix(self):
        assert "Clock_Reset" in classify_topic("", "clk_divider")

    def test_dfx_by_prefix(self):
        assert "DFX" in classify_topic("", "tt_dfx_scan")

    def test_niu_by_prefix(self):
        assert "NIU" in classify_topic("", "tt_niu_bridge")


# ---------------------------------------------------------------------------
# suggest_inherited_topic
# ---------------------------------------------------------------------------

class TestSuggestInheritedTopic:
    """Tests for suggest_inherited_topic."""

    def test_inherits_from_parent(self):
        tree = {
            "module_name": "tt_noc_top",
            "topics": ["NoC"],
            "children": [
                {"module_name": "child_a", "topics": ["unclassified"], "children": []},
            ],
        }
        assert suggest_inherited_topic("child_a", tree) == ["NoC"]

    def test_no_classified_ancestor(self):
        tree = {
            "module_name": "top",
            "topics": ["unclassified"],
            "children": [
                {"module_name": "child_a", "topics": ["unclassified"], "children": []},
            ],
        }
        assert suggest_inherited_topic("child_a", tree) == ["unclassified"]

    def test_module_not_found(self):
        tree = {
            "module_name": "top",
            "topics": ["NoC"],
            "children": [],
        }
        assert suggest_inherited_topic("nonexistent", tree) == ["unclassified"]

    def test_empty_tree(self):
        assert suggest_inherited_topic("mod", {}) == ["unclassified"]

    def test_none_module_name(self):
        assert suggest_inherited_topic(None, {"module_name": "top"}) == ["unclassified"]
