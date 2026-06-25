"""Tests for the Tool_Guide_Object common schema and constants.

Covers the closed object_type set (R3.2), the "미확인" placeholder (R3.4), the
5-field record shape (R3.5), and the 7 metadata fields (R3.1).
"""

from schema import (
    METADATA_FIELDS,
    OBJECT_TYPES,
    UNKNOWN,
    Evidence,
    ToolGuideMetadata,
    ToolGuideObject,
    is_allowed_object_type,
)


def test_object_types_closed_set():
    assert OBJECT_TYPES == frozenset(
        {"command", "option", "flow_step", "example", "section"}
    )


def test_unknown_placeholder_value():
    assert UNKNOWN == "미확인"


def test_is_allowed_object_type():
    assert is_allowed_object_type("command")
    assert is_allowed_object_type("section")
    assert not is_allowed_object_type("widget")
    assert not is_allowed_object_type("")


def test_metadata_has_seven_fields_all_default_unknown():
    meta = ToolGuideMetadata()
    as_dict = meta.to_dict()
    assert tuple(as_dict.keys()) == METADATA_FIELDS
    assert len(as_dict) == 7
    assert all(value == UNKNOWN for value in as_dict.values())


def test_evidence_omits_none_optional_fields():
    ev = Evidence(source_file="vcs_user_guide.pdf", doc_version="2023.12", page=42)
    d = ev.to_dict()
    assert d == {
        "source_file": "vcs_user_guide.pdf",
        "doc_version": "2023.12",
        "page": 42,
    }
    assert "section" not in d


def test_tool_guide_object_has_five_top_level_fields():
    obj = ToolGuideObject(
        id="toolguide#vcs#2023.12#command#elaborate",
        object_type="command",
        canonical_text="Command 'elaborate' compiles and elaborates the design.",
        metadata=ToolGuideMetadata(
            tool_name="vcs",
            tool_version="2023.12",
            command="elaborate",
            doc_version="2023.12-rev1",
            object_type="command",
        ),
        evidence=Evidence(
            source_file="vcs_user_guide.pdf",
            doc_version="2023.12-rev1",
            section="4.2 Elaboration",
        ),
    )
    record = obj.to_dict()
    assert set(record.keys()) == {
        "id",
        "object_type",
        "canonical_text",
        "metadata",
        "evidence",
    }
    # unset metadata fields fall back to the fixed placeholder, never missing
    assert record["metadata"]["option"] == UNKNOWN
    assert len(record["metadata"]) == 7
