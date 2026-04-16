"""
Pipeline utility functions for RTL auto-analysis pipeline.

Provides Pipeline_ID extraction from S3 object keys following the
directory naming convention: rtl-sources/{chip_type}_{date}/...
"""


_DEFAULT = {
    "pipeline_id": "unknown_unknown",
    "chip_type": "unknown",
    "snapshot_date": "unknown",
}


def extract_pipeline_id(s3_key: str) -> dict:
    """Extract pipeline_id, chip_type, and snapshot_date from an S3 object key.

    The S3 key is expected to follow the pattern:
        rtl-sources/{chip_type}_{date}/path/to/module.sv

    The directory name after ``rtl-sources/`` is split on the first ``_`` to
    derive *chip_type* and *snapshot_date*.  The full directory name becomes
    the *pipeline_id*.

    Args:
        s3_key: S3 object key string.

    Returns:
        A dict with keys ``pipeline_id``, ``chip_type``, ``snapshot_date``.
        Returns default ``unknown`` values when the key cannot be parsed.
    """
    if not s3_key or not isinstance(s3_key, str):
        return dict(_DEFAULT)

    prefix = "rtl-sources/"
    if not s3_key.startswith(prefix):
        return dict(_DEFAULT)

    remainder = s3_key[len(prefix):]
    if not remainder:
        return dict(_DEFAULT)

    # The pipeline directory is the first path segment after the prefix.
    dir_name = remainder.split("/", 1)[0]
    if not dir_name:
        return dict(_DEFAULT)

    # Must contain at least one underscore to split chip_type and date.
    if "_" not in dir_name:
        return dict(_DEFAULT)

    chip_type, snapshot_date = dir_name.split("_", 1)
    if not chip_type or not snapshot_date:
        return dict(_DEFAULT)

    return {
        "pipeline_id": dir_name,
        "chip_type": chip_type,
        "snapshot_date": snapshot_date,
    }
