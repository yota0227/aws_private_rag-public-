"""Common object schema and constants for Tool_Guide_Object records.

Defines the shared 5-field record (``id``, ``object_type``, ``canonical_text``,
``metadata``, ``evidence``) that mirrors RTL corpus objects (R3.5), the 7
metadata fields (R3.1), the closed ``object_type`` allowed set (R3.2), and the
fixed ``"미확인"`` placeholder for values not confirmed in the source (R3.4).

This module is intentionally limited to data structures and constants. Parsing
(``parse_structure``) and object building (``build_objects``) live in later
tasks (2.x / 3.x).

Requirements validated: 3.1, 3.5, 6.5
"""

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# R3.2 — closed object_type allowed set (Glossary-aligned). Types outside this
# set must NOT produce an object. MVP (R6.1) only activates command/option;
# flow_step/example/section are schema-defined but excluded from MVP indexing
# and activated later without schema/pipeline changes (R6.5).
OBJECT_TYPES: frozenset[str] = frozenset(
    {"command", "option", "flow_step", "example", "section"}
)

# R3.4 — fixed placeholder string for any metadata/evidence value that cannot
# be confirmed from the source. No guessing, no defaults.
UNKNOWN: str = "미확인"

# The 7 metadata field names, in canonical order (R3.1).
METADATA_FIELDS: tuple[str, ...] = (
    "tool_name",
    "tool_version",
    "command",
    "option",
    "section",
    "doc_version",
    "object_type",
)


def is_allowed_object_type(object_type: str) -> bool:
    """Return True if ``object_type`` is in the closed allowed set (R3.2)."""
    return object_type in OBJECT_TYPES


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ToolGuideMetadata:
    """The 7 metadata fields (R3.1).

    All fields are strings and always present. Values not confirmed in the
    source are set to the fixed string :data:`UNKNOWN` (R3.4). Fields default
    to :data:`UNKNOWN` so a record is never missing a metadata key.
    """

    tool_name: str = UNKNOWN
    tool_version: str = UNKNOWN
    command: str = UNKNOWN
    option: str = UNKNOWN
    section: str = UNKNOWN
    doc_version: str = UNKNOWN
    object_type: str = UNKNOWN

    def to_dict(self) -> dict[str, str]:
        """Return the metadata as a plain dict with all 7 fields present."""
        return {name: getattr(self, name) for name in METADATA_FIELDS}


@dataclass
class Evidence:
    """Source provenance for an object (R3.3).

    ``source_file`` and ``doc_version`` are required; at least one of ``page``
    or ``section`` must be present. Validation of that rule belongs to the
    object builder (task 3.x); this structure only models the fields.
    """

    source_file: str = UNKNOWN
    doc_version: str = UNKNOWN
    page: int | None = None
    section: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return evidence as a dict, omitting optional fields that are None."""
        result: dict[str, Any] = {
            "source_file": self.source_file,
            "doc_version": self.doc_version,
        }
        if self.page is not None:
            result["page"] = self.page
        if self.section is not None:
            result["section"] = self.section
        return result


@dataclass
class ToolGuideObject:
    """Common 5-field record, identical in shape to RTL corpus objects (R3.5).

    Top-level fields: ``id``, ``object_type``, ``canonical_text``,
    ``metadata``, ``evidence``.
    """

    id: str
    object_type: str
    canonical_text: str
    metadata: ToolGuideMetadata = field(default_factory=ToolGuideMetadata)
    evidence: Evidence = field(default_factory=Evidence)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the record to a plain dict (claim-db compatible shape)."""
        return {
            "id": self.id,
            "object_type": self.object_type,
            "canonical_text": self.canonical_text,
            "metadata": self.metadata.to_dict(),
            "evidence": self.evidence.to_dict(),
        }
