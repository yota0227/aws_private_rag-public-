"""Unit tests for claim attribution accuracy (Task 21)."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from claim_generator import _filter_claim_targets, _validate_claim_diversity


class TestFilterClaimTargets:
    def test_excludes_reg_inner(self):
        modules = [
            {"module_name": "tt_noc_router"},
            {"module_name": "tt_noc_repeater"},
            {"module_name": "tt_noc_rr_arb"},
            {"module_name": "tt_noc_mesh_ctrl"},
            {"module_name": "tt_noc_vc_alloc"},
            {"module_name": "tt_noc_sw_alloc"},
            {"module_name": "tt_noc_input_port"},
            {"module_name": "tt_noc_output_port"},
            {"module_name": "tt_noc_crossbar"},
            {"module_name": "tt_noc_credit_mgr"},
            {"module_name": "tt_fds_dispatch_reg_inner"},
            {"module_name": "tt_edc1_biu_soc_apb4_wrap"},
            {"module_name": "tt_generic_reg_inner"},
        ]
        result = _filter_claim_targets(modules, "NoC")
        names = [m["module_name"] for m in result]
        assert "tt_noc_router" in names
        # tt_fds_ and tt_edc1_biu_ are whitelisted functional blocks — always included
        assert "tt_fds_dispatch_reg_inner" in names
        assert "tt_edc1_biu_soc_apb4_wrap" in names
        # generic _reg_inner without whitelist prefix is excluded (enough datapath >= 10)
        assert "tt_generic_reg_inner" not in names

    def test_fallback_when_few_datapath(self):
        modules = [
            {"module_name": "tt_fds_dispatch_reg_inner"},
            {"module_name": "tt_fds_tensixneo_reg_inner"},
        ]
        result = _filter_claim_targets(modules, "Overlay")
        assert len(result) == 2  # includes register modules as fallback

    def test_empty_modules(self):
        result = _filter_claim_targets([], "NoC")
        assert result == []


class TestValidateClaimDiversity:
    def test_diverse_claims(self):
        claims = [
            {"module_name": "mod_a"},
            {"module_name": "mod_b"},
            {"module_name": "mod_c"},
        ]
        assert _validate_claim_diversity(claims, "NoC") is True

    def test_single_module_dominant(self):
        claims = [
            {"module_name": "mod_a"},
            {"module_name": "mod_a"},
            {"module_name": "mod_a"},
            {"module_name": "mod_a"},
            {"module_name": "mod_b"},
        ]
        assert _validate_claim_diversity(claims, "NoC") is False

    def test_single_claim(self):
        claims = [{"module_name": "mod_a"}]
        assert _validate_claim_diversity(claims, "NoC") is True

    def test_empty_claims(self):
        assert _validate_claim_diversity([], "NoC") is True
