"""Attach involved files and business-logic flags to API/DB impacts."""

from __future__ import annotations

from harpy.models import (
    AnalysisResult,
    ApiEndpointImpact,
    ChangedFile,
    DbChangeImpact,
    FileCategory,
    LogicalChange,
)


def enrich_contract_impacts(result: AnalysisResult) -> None:
    for api_impact in result.api_impacts:
        _enrich(result, api_impact)
    for db_impact in result.db_impacts:
        _enrich(result, db_impact)


def _enrich(result: AnalysisResult, impact: ApiEndpointImpact | DbChangeImpact) -> None:
    change = _linked_change(result, impact.change_id)
    impact.files = _unique([*impact.files, *_files_for(result, change)])
    detected, reason = _detect_business_logic(result, impact.files, change)
    if detected:
        impact.business_logic = True
        if not impact.business_logic_why:
            impact.business_logic_why = reason
    secure, secure_why = _detect_security(result, impact.files, change)
    if secure:
        impact.security = True
        if not impact.security_why:
            impact.security_why = secure_why


def _linked_change(result: AnalysisResult, change_id: str) -> LogicalChange | None:
    if not change_id:
        return None
    for change in result.changes:
        if change.id == change_id:
            return change
    return None


def _files_for(result: AnalysisResult, change: LogicalChange | None) -> list[str]:
    paths: list[str] = []
    if change is not None:
        paths.extend(change.files)
        hunk_ids = set(change.hunks or change.hunk_ids)
        for hunk in result.hunks:
            if hunk.id in hunk_ids:
                paths.append(hunk.file_path)
    return paths


def _detect_business_logic(
    result: AnalysisResult,
    files: list[str],
    change: LogicalChange | None,
) -> tuple[bool, str]:
    bl_files = [path for path in files if _file_is_business_logic(result, path)]
    if bl_files:
        return True, f"business-logic files: {', '.join(bl_files)}"
    if change is not None:
        domains = {domain.upper() for domain in change.domains}
        if FileCategory.BUSINESS_LOGIC in domains or "BUSINESS_LOGIC" in domains:
            return True, "linked change is classified as business logic"
        if change.business_impact >= 6:
            return True, "linked change has material business impact"
    return False, ""


_AUTH_DOMAINS = {"AUTHORIZATION", "AUTHENTICATION", "AUTH", "SECURITY"}


def _detect_security(
    result: AnalysisResult,
    files: list[str],
    change: LogicalChange | None,
) -> tuple[bool, str]:
    auth_files = [path for path in files if _file_is_auth(result, path)]
    if auth_files:
        return True, f"auth/security files: {', '.join(auth_files)}"
    file_set = set(files)
    if any(signal.auth_change and signal.file_path in file_set for signal in result.signals):
        return True, "static signals mark an auth or permission change"
    if change is not None:
        domains = {domain.upper() for domain in change.domains}
        if domains & _AUTH_DOMAINS:
            return True, "linked change is classified as auth/security"
        if change.security_sensitivity >= 6:
            return True, "linked change has material security sensitivity"
    return False, ""


def _file_is_auth(result: AnalysisResult, path: str) -> bool:
    for file in result.files:
        if file.path != path:
            continue
        return file.category_scores.get(FileCategory.AUTH, 0.0) >= 0.5
    return False


def _file_is_business_logic(result: AnalysisResult, path: str) -> bool:
    for file in result.files:
        if file.path != path:
            continue
        return _changed_file_is_business_logic(file)
    return False


def _changed_file_is_business_logic(file: ChangedFile) -> bool:
    return (
        file.category_scores.get(FileCategory.BUSINESS_LOGIC, 0.0) >= 0.5
        or file.business_logic_probability >= 0.5
    )


def _unique(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for path in paths:
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out
