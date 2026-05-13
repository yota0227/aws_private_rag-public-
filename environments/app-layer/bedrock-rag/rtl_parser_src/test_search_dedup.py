"""Unit tests for search result deduplication (_dedup_search_results)."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from handler import _dedup_search_results, _get_result_fingerprint


class TestGetResultFingerprint:
    """Test fingerprint generation for different analysis types."""

    def test_claim_fingerprint_by_text(self):
        r = {"analysis_type": "claim", "claim_text": "Module X has 10 ports", "file_path": "a/b.sv"}
        fp = _get_result_fingerprint(r, "claim")
        assert fp == "claim:Module X has 10 ports"

    def test_claim_same_text_different_path(self):
        r1 = {"analysis_type": "claim", "claim_text": "Same claim", "file_path": "path1/f.sv"}
        r2 = {"analysis_type": "claim", "claim_text": "Same claim", "file_path": "path2/f.sv"}
        assert _get_result_fingerprint(r1, "claim") == _get_result_fingerprint(r2, "claim")

    def test_claim_different_text(self):
        r1 = {"analysis_type": "claim", "claim_text": "Claim A"}
        r2 = {"analysis_type": "claim", "claim_text": "Claim B"}
        assert _get_result_fingerprint(r1, "claim") != _get_result_fingerprint(r2, "claim")

    def test_hdd_section_fingerprint(self):
        r = {"analysis_type": "hdd_section", "hdd_section_title": "FPU HDD", "topic": "FPU"}
        fp = _get_result_fingerprint(r, "hdd_section")
        assert fp == "hdd:FPU:FPU HDD"

    def test_module_parse_fingerprint(self):
        r = {"analysis_type": "module_parse", "module_name": "trinity", "sub_record_type": ""}
        fp = _get_result_fingerprint(r, "module_parse")
        assert fp == "mp:trinity:module_parse:"

    def test_module_parse_chunk_fingerprint(self):
        r = {"analysis_type": "module_parse_chunk", "module_name": "trinity",
             "sub_record_type": "port_summary"}
        fp = _get_result_fingerprint(r, "module_parse_chunk")
        assert fp == "mp:trinity:module_parse_chunk:port_summary"

    def test_unknown_type_uses_basename(self):
        r = {"analysis_type": "unknown", "module_name": "foo",
             "file_path": "rtl-sources/tt/rtl/foo.sv"}
        fp = _get_result_fingerprint(r, "unknown")
        assert fp == "other:foo:foo.sv"


class TestDedupSearchResults:
    """Test _dedup_search_results end-to-end."""

    def test_removes_duplicate_claims(self):
        results = [
            {"analysis_type": "claim", "claim_text": "Module X has 10 ports",
             "file_path": "path1/f.sv", "score": 5.0},
            {"analysis_type": "claim", "claim_text": "Module X has 10 ports",
             "file_path": "path2/f.sv", "score": 4.5},
            {"analysis_type": "claim", "claim_text": "Module X has 10 ports",
             "file_path": "path3/f.sv", "score": 4.0},
            {"analysis_type": "claim", "claim_text": "Module Y has 5 ports",
             "file_path": "path1/g.sv", "score": 3.0},
        ]
        deduped = _dedup_search_results(results, 50)
        assert len(deduped) == 2
        assert deduped[0]["score"] == 5.0  # highest score kept
        assert deduped[1]["claim_text"] == "Module Y has 5 ports"

    def test_removes_duplicate_module_parse(self):
        results = [
            {"analysis_type": "module_parse", "module_name": "trinity",
             "sub_record_type": "", "file_path": "used_in_n1/rtl/trinity.sv", "score": 3.0},
            {"analysis_type": "module_parse", "module_name": "trinity",
             "sub_record_type": "", "file_path": "used_in_n1/mem_port/rtl/trinity.sv", "score": 2.8},
            {"analysis_type": "module_parse", "module_name": "trinity",
             "sub_record_type": "", "file_path": "rtl/trinity.sv", "score": 2.5},
        ]
        deduped = _dedup_search_results(results, 50)
        assert len(deduped) == 1
        assert deduped[0]["score"] == 3.0

    def test_keeps_different_analysis_types(self):
        results = [
            {"analysis_type": "claim", "claim_text": "Claim A", "score": 5.0},
            {"analysis_type": "hdd_section", "hdd_section_title": "FPU HDD",
             "topic": "FPU", "score": 4.0},
            {"analysis_type": "module_parse", "module_name": "trinity",
             "sub_record_type": "", "score": 3.0},
        ]
        deduped = _dedup_search_results(results, 50)
        assert len(deduped) == 3

    def test_respects_max_results(self):
        results = [
            {"analysis_type": "claim", "claim_text": f"Claim {i}", "score": 10 - i}
            for i in range(20)
        ]
        deduped = _dedup_search_results(results, 5)
        assert len(deduped) == 5
        assert deduped[0]["claim_text"] == "Claim 0"

    def test_empty_results(self):
        assert _dedup_search_results([], 50) == []

    def test_no_duplicates_unchanged(self):
        results = [
            {"analysis_type": "claim", "claim_text": "A", "score": 3.0},
            {"analysis_type": "claim", "claim_text": "B", "score": 2.0},
            {"analysis_type": "claim", "claim_text": "C", "score": 1.0},
        ]
        deduped = _dedup_search_results(results, 50)
        assert len(deduped) == 3

    def test_mixed_duplicates_realistic(self):
        """Simulate real scenario: same claim from 5 file variants + unique hdd_section."""
        results = []
        # 5 duplicates of same claim (different file paths)
        for i in range(5):
            results.append({
                "analysis_type": "claim",
                "claim_text": "Module 'trinity' has 106 total ports",
                "file_path": f"variant{i}/trinity.sv",
                "score": 5.0 - i * 0.1,
            })
        # 1 unique hdd_section
        results.append({
            "analysis_type": "hdd_section",
            "hdd_section_title": "FPU HDD",
            "topic": "FPU",
            "score": 3.0,
        })
        # 3 duplicates of module_parse
        for i in range(3):
            results.append({
                "analysis_type": "module_parse",
                "module_name": "trinity",
                "sub_record_type": "",
                "file_path": f"path{i}/trinity.sv",
                "score": 2.5 - i * 0.1,
            })

        deduped = _dedup_search_results(results, 50)
        # Should have: 1 claim + 1 hdd_section + 1 module_parse = 3
        assert len(deduped) == 3
        assert deduped[0]["analysis_type"] == "claim"
        assert deduped[1]["analysis_type"] == "hdd_section"
        assert deduped[2]["analysis_type"] == "module_parse"
