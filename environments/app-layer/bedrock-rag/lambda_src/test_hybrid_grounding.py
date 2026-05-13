"""
Unit tests for Hybrid Grounding feature (Requirements 25.1~25.8)
Tests _build_grounding_prompt() and _calculate_grounding_ratios() helper functions,
and verifies grounding_mode parameter handling in generate_hdd_section and handle_query.
"""
import json
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Add lambda_src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from index import (
    _build_grounding_prompt,
    _calculate_grounding_ratios,
    VALID_GROUNDING_MODES,
    KB_COVERAGE_WARNING,
)


class TestBuildGroundingPrompt(unittest.TestCase):
    """Tests for _build_grounding_prompt helper function"""

    def setUp(self):
        self.sample_claims = [
            {'claim_id': 'claim-001', 'statement': 'UCIE PHY has 4 LTSSM states'},
            {'claim_id': 'claim-002', 'statement': 'AHB bus width is 32 bits'},
        ]

    def test_free_mode_returns_empty_string(self):
        """Requirements 25.6: free mode produces no grounding instructions"""
        result = _build_grounding_prompt("free", self.sample_claims)
        self.assertEqual(result, "")

    def test_hybrid_mode_contains_grounded_tag_instruction(self):
        """Requirements 25.1, 25.2: hybrid mode instructs GROUNDED tagging"""
        result = _build_grounding_prompt("hybrid", self.sample_claims)
        self.assertIn("[GROUNDED from claim:", result)
        self.assertIn("HYBRID", result)

    def test_hybrid_mode_contains_inferred_tag_instruction(self):
        """Requirements 25.3: hybrid mode instructs INFERRED tagging"""
        result = _build_grounding_prompt("hybrid", self.sample_claims)
        self.assertIn("[INFERRED]", result)
        self.assertIn("※ Spec 확인 필요", result)

    def test_hybrid_mode_includes_claim_ids(self):
        """Requirements 25.2: hybrid mode lists claim_ids for reference"""
        result = _build_grounding_prompt("hybrid", self.sample_claims)
        self.assertIn("claim-001", result)
        self.assertIn("claim-002", result)

    def test_strict_mode_contains_grounded_only_instruction(self):
        """Requirements 25.6, 25.8: strict mode instructs GROUNDED only"""
        result = _build_grounding_prompt("strict", self.sample_claims)
        self.assertIn("STRICT", result)
        self.assertIn("[GROUNDED from claim:", result)
        self.assertIn("[NOT IN KB]", result)

    def test_strict_mode_does_not_contain_inferred_instruction(self):
        """Requirements 25.6: strict mode should not instruct INFERRED tagging"""
        result = _build_grounding_prompt("strict", self.sample_claims)
        # strict mode should not have INFERRED example/instruction
        self.assertNotIn("[INFERRED]", result)

    def test_strict_mode_includes_claim_ids(self):
        """Requirements 25.2: strict mode lists claim_ids for reference"""
        result = _build_grounding_prompt("strict", self.sample_claims)
        self.assertIn("claim-001", result)
        self.assertIn("claim-002", result)

    def test_empty_claims_list(self):
        """Edge case: empty claims list should not error"""
        result = _build_grounding_prompt("hybrid", [])
        self.assertIn("HYBRID", result)

    def test_claims_without_claim_id(self):
        """Edge case: claims missing claim_id should use fallback"""
        claims = [{'statement': 'Some statement without id'}]
        result = _build_grounding_prompt("hybrid", claims)
        self.assertIn("unknown_0", result)


class TestCalculateGroundingRatios(unittest.TestCase):
    """Tests for _calculate_grounding_ratios helper function"""

    def test_all_grounded(self):
        """Requirements 25.4: all GROUNDED tags → ratio 1.0/0.0"""
        text = (
            "[GROUNDED from claim:abc-1] First statement.\n"
            "[GROUNDED from claim:abc-2] Second statement.\n"
            "[GROUNDED from claim:abc-3] Third statement."
        )
        result = _calculate_grounding_ratios(text)
        self.assertEqual(result['grounded_ratio'], 1.0)
        self.assertEqual(result['inferred_ratio'], 0.0)
        self.assertEqual(result['grounded_count'], 3)
        self.assertEqual(result['inferred_count'], 0)
        self.assertIsNone(result['kb_coverage_warning'])

    def test_all_inferred(self):
        """Requirements 25.4, 25.5: all INFERRED → ratio 0.0/1.0 + warning"""
        text = (
            "[INFERRED] First inference. ※ Spec 확인 필요\n"
            "[INFERRED] Second inference. ※ Spec 확인 필요\n"
        )
        result = _calculate_grounding_ratios(text)
        self.assertEqual(result['grounded_ratio'], 0.0)
        self.assertEqual(result['inferred_ratio'], 1.0)
        self.assertEqual(result['inferred_count'], 2)
        self.assertEqual(result['kb_coverage_warning'], KB_COVERAGE_WARNING)

    def test_mixed_tags(self):
        """Requirements 25.4: mixed tags → correct ratio calculation"""
        text = (
            "[GROUNDED from claim:abc-1] Grounded fact.\n"
            "[GROUNDED from claim:abc-2] Another grounded fact.\n"
            "[INFERRED] An inference. ※ Spec 확인 필요\n"
        )
        result = _calculate_grounding_ratios(text)
        self.assertAlmostEqual(result['grounded_ratio'], 2/3, places=3)
        self.assertAlmostEqual(result['inferred_ratio'], 1/3, places=3)
        self.assertEqual(result['grounded_count'], 2)
        self.assertEqual(result['inferred_count'], 1)
        self.assertIsNone(result['kb_coverage_warning'])

    def test_no_tags_returns_zero(self):
        """Edge case: no tags (free mode output) → 0.0/0.0"""
        text = "This is a free-form answer without any grounding tags."
        result = _calculate_grounding_ratios(text)
        self.assertEqual(result['grounded_ratio'], 0.0)
        self.assertEqual(result['inferred_ratio'], 0.0)
        self.assertEqual(result['grounded_count'], 0)
        self.assertEqual(result['inferred_count'], 0)
        self.assertIsNone(result['kb_coverage_warning'])

    def test_inferred_ratio_above_half_triggers_warning(self):
        """Requirements 25.5: inferred_ratio > 0.5 triggers KB coverage warning"""
        text = (
            "[GROUNDED from claim:abc-1] One grounded.\n"
            "[INFERRED] First inference.\n"
            "[INFERRED] Second inference.\n"
            "[INFERRED] Third inference.\n"
        )
        result = _calculate_grounding_ratios(text)
        self.assertGreater(result['inferred_ratio'], 0.5)
        self.assertEqual(result['kb_coverage_warning'], KB_COVERAGE_WARNING)

    def test_inferred_ratio_exactly_half_no_warning(self):
        """Requirements 25.5: inferred_ratio == 0.5 does NOT trigger warning"""
        text = (
            "[GROUNDED from claim:abc-1] Grounded.\n"
            "[INFERRED] Inferred.\n"
        )
        result = _calculate_grounding_ratios(text)
        self.assertEqual(result['inferred_ratio'], 0.5)
        self.assertIsNone(result['kb_coverage_warning'])

    def test_grounded_without_claim_id(self):
        """Edge case: [GROUNDED] without claim_id still counts"""
        text = "[GROUNDED] A statement without specific claim reference."
        result = _calculate_grounding_ratios(text)
        self.assertEqual(result['grounded_count'], 1)
        self.assertEqual(result['grounded_ratio'], 1.0)

    def test_sum_equals_one(self):
        """Requirements 25.4: grounded_ratio + inferred_ratio = 1.0 when tags exist"""
        text = (
            "[GROUNDED from claim:a] Fact 1.\n"
            "[GROUNDED from claim:b] Fact 2.\n"
            "[INFERRED] Inference 1.\n"
            "[INFERRED] Inference 2.\n"
            "[INFERRED] Inference 3.\n"
        )
        result = _calculate_grounding_ratios(text)
        self.assertAlmostEqual(
            result['grounded_ratio'] + result['inferred_ratio'], 1.0, places=3
        )


class TestValidGroundingModes(unittest.TestCase):
    """Tests for VALID_GROUNDING_MODES constant"""

    def test_contains_all_three_modes(self):
        """Requirements 25.6: three valid modes"""
        self.assertEqual(VALID_GROUNDING_MODES, {"strict", "hybrid", "free"})


class TestGenerateHddSectionGroundingMode(unittest.TestCase):
    """Integration tests for generate_hdd_section with grounding_mode"""

    @patch('index.dynamodb')
    def test_invalid_grounding_mode_returns_400(self, mock_dynamodb):
        """Requirements 25.6: invalid grounding_mode returns 400"""
        from index import generate_hdd_section
        event = {
            'body': json.dumps({
                'topic': 'ucie/phy',
                'section_title': 'Test Section',
                'grounding_mode': 'invalid_mode'
            })
        }
        result = generate_hdd_section(event)
        self.assertEqual(result['statusCode'], 400)
        body = json.loads(result['body'])
        self.assertIn('invalid grounding_mode', body['error'])

    @patch('index.dynamodb')
    def test_strict_mode_no_claims_returns_not_in_kb(self, mock_dynamodb):
        """Requirements 25.8: strict mode with no claims returns [NOT IN KB]"""
        from index import generate_hdd_section

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        mock_dynamodb.Table.return_value = mock_table

        event = {
            'body': json.dumps({
                'topic': 'ucie/phy',
                'section_title': 'Test Section',
                'grounding_mode': 'strict'
            })
        }
        result = generate_hdd_section(event)
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertIn('[NOT IN KB]', body['markdown'])
        self.assertEqual(body['claims_used'], 0)
        self.assertEqual(body['grounding_mode'], 'strict')

    @patch('index.dynamodb')
    def test_default_grounding_mode_is_hybrid(self, mock_dynamodb):
        """Requirements 25.6: default grounding_mode is hybrid"""
        from index import generate_hdd_section

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        mock_dynamodb.Table.return_value = mock_table

        event = {
            'body': json.dumps({
                'topic': 'ucie/phy',
                'section_title': 'Test Section'
                # no grounding_mode specified
            })
        }
        result = generate_hdd_section(event)
        # With no claims and hybrid mode, should return 403 (no approved claims)
        self.assertEqual(result['statusCode'], 403)


class TestHandleQueryGroundingMode(unittest.TestCase):
    """Integration tests for handle_query with grounding_mode"""

    @patch('index.BEDROCK_KB_ID', 'test-kb-id')
    def test_invalid_grounding_mode_returns_400(self):
        """Requirements 25.7: invalid grounding_mode in rag_query returns 400"""
        from index import handle_query
        event = {
            'body': json.dumps({
                'query': 'What is UCIE PHY?',
                'grounding_mode': 'invalid'
            })
        }
        result = handle_query(event)
        self.assertEqual(result['statusCode'], 400)
        body = json.loads(result['body'])
        self.assertIn('invalid grounding_mode', body['error'])


if __name__ == '__main__':
    unittest.main()
