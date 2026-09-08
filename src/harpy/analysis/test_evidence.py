"""Test-evidence levels. These do not automatically progress."""

from __future__ import annotations

from enum import StrEnum


class EvidenceLevel(StrEnum):
    RELATED_FILE = "related_file"
    RELATED_TEST = "related_test"
    ASSERTION_LOCATED = "assertion_located"
    BEHAVIOR_MAPPING_INFERRED = "behavior_mapping_inferred"
    EXECUTED_PASS = "executed_pass"
    EXECUTED_FAIL = "executed_fail"
