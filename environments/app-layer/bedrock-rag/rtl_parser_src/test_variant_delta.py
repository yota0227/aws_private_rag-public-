"""Tests for variant_delta module — delta extraction between module sets."""

from variant_delta import extract_variant_delta


class TestExtractVariantDelta:
    """Tests for extract_variant_delta."""

    def test_identical_modules(self):
        modules = [{"module_name": "a", "parameter_list": "P=1", "instance_list": "u1: b"}]
        result = extract_variant_delta(modules, modules)
        assert result["added_modules"] == []
        assert result["removed_modules"] == []
        assert result["parameter_changes"] == []
        assert result["instance_changes"] == []

    def test_added_module(self):
        baseline = [{"module_name": "a"}]
        variant = [{"module_name": "a"}, {"module_name": "b"}]
        result = extract_variant_delta(baseline, variant)
        assert result["added_modules"] == ["b"]
        assert result["removed_modules"] == []

    def test_removed_module(self):
        baseline = [{"module_name": "a"}, {"module_name": "b"}]
        variant = [{"module_name": "a"}]
        result = extract_variant_delta(baseline, variant)
        assert result["removed_modules"] == ["b"]
        assert result["added_modules"] == []

    def test_parameter_change(self):
        baseline = [{"module_name": "a", "parameter_list": "WIDTH=32"}]
        variant = [{"module_name": "a", "parameter_list": "WIDTH=64"}]
        result = extract_variant_delta(baseline, variant)
        assert len(result["parameter_changes"]) == 1
        assert result["parameter_changes"][0]["module_name"] == "a"
        assert result["parameter_changes"][0]["baseline_parameters"] == "WIDTH=32"
        assert result["parameter_changes"][0]["variant_parameters"] == "WIDTH=64"

    def test_instance_added(self):
        baseline = [{"module_name": "a", "instance_list": "u1: b"}]
        variant = [{"module_name": "a", "instance_list": "u1: b, u2: c"}]
        result = extract_variant_delta(baseline, variant)
        assert len(result["instance_changes"]) == 1
        assert "u2" in result["instance_changes"][0]["added_instances"]

    def test_instance_removed(self):
        baseline = [{"module_name": "a", "instance_list": "u1: b, u2: c"}]
        variant = [{"module_name": "a", "instance_list": "u1: b"}]
        result = extract_variant_delta(baseline, variant)
        assert len(result["instance_changes"]) == 1
        assert "u2" in result["instance_changes"][0]["removed_instances"]

    def test_empty_baseline(self):
        variant = [{"module_name": "a"}]
        result = extract_variant_delta([], variant)
        assert result["added_modules"] == ["a"]

    def test_empty_variant(self):
        baseline = [{"module_name": "a"}]
        result = extract_variant_delta(baseline, [])
        assert result["removed_modules"] == ["a"]

    def test_both_empty(self):
        result = extract_variant_delta([], [])
        assert result == {
            "added_modules": [],
            "removed_modules": [],
            "parameter_changes": [],
            "instance_changes": [],
        }

    def test_none_inputs(self):
        result = extract_variant_delta(None, None)
        assert result["added_modules"] == []
        assert result["removed_modules"] == []
