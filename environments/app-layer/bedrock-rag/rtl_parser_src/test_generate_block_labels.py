"""Unit tests for Generate Block Label extraction (Task 4.2).

Tests the _extract_generate_block_labels() internal function and the
extract_generate_block_label_claims() public API.

Validates: Requirements 6.1, 6.2, 6.4
"""

import pytest

from generate_block_parser import (
    _extract_generate_block_labels,
    _strip_comments,
    extract_generate_block_label_claims,
)


# ---------------------------------------------------------------------------
# Test: gen_noc2axi_ne_opt extraction and instance association (Req 6.1, 6.2)
# ---------------------------------------------------------------------------

class TestGenNoc2axiNeOptExtraction:
    """Verify gen_noc2axi_ne_opt label is extracted with associated instances."""

    RTL_CONTENT = """
    module trinity_top #(
        parameter SizeX = 4
    ) (
        input clk
    );

    generate
        for (genvar x = 0; x < SizeX; x++) begin : gen_noc2axi_ne_opt
            trinity_noc2axi_n_opt u_noc2axi (
                .clk(clk),
                .i_x(x)
            );
            trinity_router u_router (
                .clk(clk),
                .i_x(x)
            );
        end
    endgenerate

    endmodule
    """

    def test_label_extracted(self):
        """gen_noc2axi_ne_opt label should be found."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        labels = [r["label"] for r in results]
        assert "gen_noc2axi_ne_opt" in labels

    def test_block_type_is_for(self):
        """gen_noc2axi_ne_opt should have block_type='for'."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        block = next(r for r in results if r["label"] == "gen_noc2axi_ne_opt")
        assert block["block_type"] == "for"

    def test_instances_associated(self):
        """Instances within gen_noc2axi_ne_opt should be listed."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        block = next(r for r in results if r["label"] == "gen_noc2axi_ne_opt")
        assert "u_noc2axi" in block["instances"]
        assert "u_router" in block["instances"]

    def test_hierarchy_path_top_level(self):
        """Top-level block hierarchy_path should be its own label."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        block = next(r for r in results if r["label"] == "gen_noc2axi_ne_opt")
        assert block["hierarchy_path"] == "gen_noc2axi_ne_opt"

    def test_parent_label_is_none(self):
        """Top-level block should have no parent."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        block = next(r for r in results if r["label"] == "gen_noc2axi_ne_opt")
        assert block["parent_label"] is None

    def test_claims_api_produces_hierarchy_claims(self):
        """extract_generate_block_label_claims should produce claims."""
        claims = extract_generate_block_label_claims(
            self.RTL_CONTENT,
            module_name="trinity_top",
            file_path="test.sv",
            pipeline_id="test_pipeline",
        )
        assert len(claims) > 0
        # Should mention gen_noc2axi_ne_opt and instances
        noc_claims = [c for c in claims if "gen_noc2axi_ne_opt" in c["claim_text"]]
        assert len(noc_claims) == 1
        assert "u_noc2axi" in noc_claims[0]["claim_text"]
        assert "u_router" in noc_claims[0]["claim_text"]
        assert noc_claims[0]["topic"] == "Hierarchy"
        assert noc_claims[0]["claim_type"] == "structural"


# ---------------------------------------------------------------------------
# Test: Nested generate block hierarchy path (Req 6.2)
# ---------------------------------------------------------------------------

class TestNestedGenerateBlockHierarchy:
    """Verify nested generate blocks produce correct hierarchy paths."""

    RTL_CONTENT = """
    module test_module (input clk);

    generate
        for (genvar x = 0; x < 4; x++) begin : gen_outer
            for (genvar y = 0; y < 4; y++) begin : gen_inner
                some_module u_inst (
                    .clk(clk),
                    .x(x),
                    .y(y)
                );
            end
        end
    endgenerate

    endmodule
    """

    def test_both_labels_extracted(self):
        """Both gen_outer and gen_inner should be extracted."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        labels = [r["label"] for r in results]
        assert "gen_outer" in labels
        assert "gen_inner" in labels

    def test_inner_parent_is_outer(self):
        """gen_inner's parent should be gen_outer."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        inner = next(r for r in results if r["label"] == "gen_inner")
        assert inner["parent_label"] == "gen_outer"

    def test_inner_hierarchy_path(self):
        """gen_inner hierarchy_path should be 'gen_outer/gen_inner'."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        inner = next(r for r in results if r["label"] == "gen_inner")
        assert inner["hierarchy_path"] == "gen_outer/gen_inner"

    def test_outer_hierarchy_path(self):
        """gen_outer hierarchy_path should be just 'gen_outer'."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        outer = next(r for r in results if r["label"] == "gen_outer")
        assert outer["hierarchy_path"] == "gen_outer"

    def test_instance_assigned_to_innermost_block(self):
        """Instance should be associated with the innermost enclosing block."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        inner = next(r for r in results if r["label"] == "gen_inner")
        assert "u_inst" in inner["instances"]

    def test_outer_block_has_no_direct_instances(self):
        """Outer block should not claim instances that belong to inner."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        outer = next(r for r in results if r["label"] == "gen_outer")
        assert "u_inst" not in outer["instances"]

    def test_three_level_nesting(self):
        """Three levels of nesting should produce correct paths."""
        rtl = """
        module deep_module (input clk);
        generate
            for (genvar a = 0; a < 2; a++) begin : gen_level1
                for (genvar b = 0; b < 2; b++) begin : gen_level2
                    for (genvar c = 0; c < 2; c++) begin : gen_level3
                        leaf_mod u_leaf (.clk(clk));
                    end
                end
            end
        endgenerate
        endmodule
        """
        clean = _strip_comments(rtl)
        results = _extract_generate_block_labels(clean)
        level3 = next(r for r in results if r["label"] == "gen_level3")
        assert level3["hierarchy_path"] == "gen_level1/gen_level2/gen_level3"
        assert level3["parent_label"] == "gen_level2"
        assert "u_leaf" in level3["instances"]


# ---------------------------------------------------------------------------
# Test: Generate if block label extraction (Req 6.4)
# ---------------------------------------------------------------------------

class TestGenerateIfBlockLabel:
    """Verify generate if blocks with labels are correctly extracted."""

    RTL_CONTENT = """
    module conditional_module #(
        parameter ENABLE_FEATURE = 1
    ) (
        input clk,
        output data_out
    );

    generate
        if (ENABLE_FEATURE) begin : gen_feature_enabled
            feature_module u_feature (
                .clk(clk),
                .out(data_out)
            );
        end
    endgenerate

    endmodule
    """

    def test_if_block_label_extracted(self):
        """Generate if block label should be extracted."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        labels = [r["label"] for r in results]
        assert "gen_feature_enabled" in labels

    def test_if_block_type(self):
        """Generate if block should have block_type='if'."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        block = next(r for r in results if r["label"] == "gen_feature_enabled")
        assert block["block_type"] == "if"

    def test_if_block_instances(self):
        """Instances within if block should be associated."""
        clean = _strip_comments(self.RTL_CONTENT)
        results = _extract_generate_block_labels(clean)
        block = next(r for r in results if r["label"] == "gen_feature_enabled")
        assert "u_feature" in block["instances"]

    def test_mixed_for_and_if_blocks(self):
        """Both for and if labeled blocks should be extracted together."""
        rtl = """
        module mixed_module (input clk);
        generate
            for (genvar i = 0; i < 4; i++) begin : gen_loop
                loop_mod u_loop (.clk(clk));
            end

            if (PARAM_A > 0) begin : gen_conditional
                cond_mod u_cond (.clk(clk));
            end
        endgenerate
        endmodule
        """
        clean = _strip_comments(rtl)
        results = _extract_generate_block_labels(clean)
        labels = [r["label"] for r in results]
        assert "gen_loop" in labels
        assert "gen_conditional" in labels

        loop_block = next(r for r in results if r["label"] == "gen_loop")
        cond_block = next(r for r in results if r["label"] == "gen_conditional")
        assert loop_block["block_type"] == "for"
        assert cond_block["block_type"] == "if"
        assert "u_loop" in loop_block["instances"]
        assert "u_cond" in cond_block["instances"]

    def test_nested_if_inside_for(self):
        """Generate if nested inside for should have correct hierarchy."""
        rtl = """
        module nested_if_module (input clk);
        generate
            for (genvar x = 0; x < 4; x++) begin : gen_columns
                if (x < 2) begin : gen_left_half
                    left_mod u_left (.clk(clk));
                end
            end
        endgenerate
        endmodule
        """
        clean = _strip_comments(rtl)
        results = _extract_generate_block_labels(clean)
        left = next(r for r in results if r["label"] == "gen_left_half")
        assert left["block_type"] == "if"
        assert left["parent_label"] == "gen_columns"
        assert left["hierarchy_path"] == "gen_columns/gen_left_half"
        assert "u_left" in left["instances"]


# ---------------------------------------------------------------------------
# Test: Claims API integration
# ---------------------------------------------------------------------------

class TestClaimsGeneration:
    """Verify extract_generate_block_label_claims generates correct claims."""

    def test_nested_claim_includes_hierarchy_info(self):
        """Claims for nested blocks should include hierarchy path info."""
        rtl = """
        module m (input clk);
        generate
            for (genvar x = 0; x < 4; x++) begin : gen_parent
                for (genvar y = 0; y < 4; y++) begin : gen_child
                    child_mod u_child (.clk(clk));
                end
            end
        endgenerate
        endmodule
        """
        claims = extract_generate_block_label_claims(
            rtl, module_name="m", file_path="test.sv", pipeline_id="p1"
        )
        child_claims = [c for c in claims if "gen_child" in c["claim_text"]]
        assert len(child_claims) == 1
        assert "gen_parent/gen_child" in child_claims[0]["claim_text"]
        assert "nested under" in child_claims[0]["claim_text"]

    def test_empty_content_returns_no_claims(self):
        """Empty or no-generate content should return empty list."""
        claims = extract_generate_block_label_claims(
            "module m (input clk); endmodule",
            module_name="m", file_path="test.sv", pipeline_id="p1"
        )
        assert claims == []

    def test_claim_metadata_fields(self):
        """All claims should have correct metadata fields."""
        rtl = """
        module m (input clk);
        generate
            for (genvar i = 0; i < 2; i++) begin : gen_test
                test_mod u_t (.clk(clk));
            end
        endgenerate
        endmodule
        """
        claims = extract_generate_block_label_claims(
            rtl, module_name="m", file_path="foo.sv", pipeline_id="pipe1"
        )
        assert len(claims) == 1
        c = claims[0]
        assert c["analysis_type"] == "claim"
        assert c["claim_type"] == "structural"
        assert c["topic"] == "Hierarchy"
        assert c["module_name"] == "m"
        assert c["file_path"] == "foo.sv"
        assert c["pipeline_id"] == "pipe1"
        assert c["parser_source"] == "generate_block_parser"
