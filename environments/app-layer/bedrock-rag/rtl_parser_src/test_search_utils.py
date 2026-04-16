"""Tests for search_utils module — OpenSearch query builder."""

from search_utils import build_search_query


class TestBuildSearchQuery:
    """Tests for build_search_query."""

    def test_empty_params(self):
        result = build_search_query({})
        assert result["query"]["bool"]["must"] == [{"match_all": {}}]

    def test_none_params(self):
        result = build_search_query(None)
        assert result["query"]["bool"]["must"] == [{"match_all": {}}]

    def test_single_topic(self):
        result = build_search_query({"topic": "NoC"})
        must = result["query"]["bool"]["must"]
        assert len(must) == 1
        assert must[0] == {"term": {"topic": "NoC"}}

    def test_multiple_params(self):
        result = build_search_query({
            "topic": "FPU",
            "pipeline_id": "tt_20260221",
        })
        must = result["query"]["bool"]["must"]
        assert len(must) == 2
        fields = {list(clause["term"].keys())[0] for clause in must}
        assert "topic" in fields
        assert "pipeline_id" in fields

    def test_empty_value_excluded(self):
        result = build_search_query({"topic": "", "pipeline_id": "tt_001"})
        must = result["query"]["bool"]["must"]
        assert len(must) == 1
        assert must[0] == {"term": {"pipeline_id": "tt_001"}}

    def test_none_value_excluded(self):
        result = build_search_query({"topic": None, "pipeline_id": "tt_001"})
        must = result["query"]["bool"]["must"]
        assert len(must) == 1

    def test_unknown_param_ignored(self):
        result = build_search_query({"unknown_field": "value"})
        assert result["query"]["bool"]["must"] == [{"match_all": {}}]

    def test_all_params(self):
        result = build_search_query({
            "topic": "EDC",
            "clock_domain": "ai_clock_domain",
            "hierarchy_path": "trinity.edc",
            "pipeline_id": "tt_20260221",
            "analysis_type": "clock_domain",
        })
        must = result["query"]["bool"]["must"]
        assert len(must) == 5
