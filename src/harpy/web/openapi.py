"""OpenAPI 3.1 skeleton generated from web DTOs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from harpy.web.dto import (
    CONTRACT_MODELS,
    AnalysisCatalog,
    AnalysisPlanView,
    ChangeDetail,
    CoveragePage,
    CreatePlanRequest,
    CreatePresetRequest,
    DecisionResource,
    DiffPage,
    ErrorResponse,
    InboxRefreshRequest,
    JobView,
    LocalAuthRequest,
    Me,
    MigrationWarning,
    NoteResource,
    OpenTargetQueued,
    OpenTargetReady,
    OpenTargetRequest,
    PatchPreferencesRequest,
    PersonalSession,
    Preferences,
    Preset,
    RegisterGithubRepositoryRequest,
    RegisterLocalRepositoryRequest,
    ReplacePresetRequest,
    ReportDetail,
    RepositorySummary,
    ResolveMigrationWarningRequest,
    ReviewDetail,
    ReviewEvent,
    SaveNoteRequest,
    SaveSessionRequest,
    SetDecisionRequest,
    SourceEvidence,
    SourcePage,
    StartRunRequest,
)

API_PREFIX = "/api/v1"
TENANT_PREFIX = f"{API_PREFIX}/tenants/{{tenant_id}}"

SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    *CONTRACT_MODELS,
    LocalAuthRequest,
    RegisterLocalRepositoryRequest,
    RegisterGithubRepositoryRequest,
    InboxRefreshRequest,
    OpenTargetRequest,
    SetDecisionRequest,
    SaveNoteRequest,
    CreatePlanRequest,
    StartRunRequest,
    PatchPreferencesRequest,
    CreatePresetRequest,
    ReplacePresetRequest,
    SaveSessionRequest,
    ResolveMigrationWarningRequest,
    ReviewEvent,
    MigrationWarning,
)


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _json_content(
    model: type[BaseModel] | None = None,
    *,
    union: tuple[type[BaseModel], ...] | None = None,
    schema_name: str | None = None,
) -> dict[str, Any]:
    if schema_name is not None:
        schema: dict[str, Any] = _ref(schema_name)
    elif union is not None:
        schema = {"oneOf": [_ref(item.__name__) for item in union]}
    else:
        assert model is not None
        schema = _ref(model.__name__)
    return {"application/json": {"schema": schema}}


def _error_responses() -> dict[str, Any]:
    return {
        "400": {"description": "Invalid request", "content": _json_content(ErrorResponse)},
        "401": {"description": "Authentication required", "content": _json_content(ErrorResponse)},
        "403": {"description": "Forbidden", "content": _json_content(ErrorResponse)},
        "404": {"description": "Not found", "content": _json_content(ErrorResponse)},
        "409": {"description": "Conflict", "content": _json_content(ErrorResponse)},
    }


def _op(
    *,
    operation_id: str,
    summary: str,
    request: type[BaseModel] | None = None,
    response: type[BaseModel] | None = None,
    response_union: tuple[type[BaseModel], ...] | None = None,
    response_schema: str | None = None,
    status: int = 200,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    responses = _error_responses()
    body: dict[str, Any] = {"description": summary}
    if response is not None or response_union is not None or response_schema is not None:
        body["content"] = _json_content(response, union=response_union, schema_name=response_schema)
    responses[str(status)] = body
    operation: dict[str, Any] = {
        "operationId": operation_id,
        "summary": summary,
        "responses": responses,
        "security": [{"session": []}],
    }
    if request is not None:
        operation["requestBody"] = {"required": True, "content": _json_content(request)}
    if extra:
        operation.update(extra)
    return operation


def _page_schema(item_name: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items", "next_cursor", "as_of"],
        "properties": {
            "items": {"type": "array", "items": _ref(item_name)},
            "next_cursor": {"type": ["string", "null"]},
            "as_of": {"type": "string", "format": "date-time"},
            "truncated": {"type": ["boolean", "null"]},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
    }


def _component_schemas() -> dict[str, Any]:
    schemas: dict[str, Any] = {}
    for model in SCHEMA_MODELS:
        generated = model.model_json_schema(
            mode="serialization",
            ref_template="#/components/schemas/{model}",
        )
        nested = generated.pop("$defs", {})
        schemas.update(nested)
        schemas[model.__name__] = generated
    schemas["ReviewSummaryPage"] = _page_schema("ReviewSummary")
    schemas["ReportSummaryPage"] = _page_schema("ReportSummary")
    schemas["ChangeSummaryPage"] = _page_schema("ChangeSummary")
    schemas["RepositorySummaryPage"] = _page_schema("RepositorySummary")
    schemas["ImpactPage"] = _page_schema("Impact")
    schemas["ReviewEventPage"] = _page_schema("ReviewEvent")
    schemas["PresetPage"] = _page_schema("Preset")
    schemas["MigrationWarningPage"] = _page_schema("MigrationWarning")
    return schemas


def _paths() -> dict[str, Any]:
    tenant = TENANT_PREFIX
    return {
        "/health/live": {
            "get": {
                "operationId": "healthLive",
                "summary": "Process liveness",
                "security": [],
                "responses": {"200": {"description": "Process is alive"}},
            }
        },
        f"{API_PREFIX}/me": {
            "get": _op(operation_id="getMe", summary="Current session and memberships", response=Me)
        },
        f"{API_PREFIX}/auth/local": {
            "post": _op(
                operation_id="localAuth",
                summary="Exchange a one-time local bootstrap token",
                request=LocalAuthRequest,
                status=204,
                extra={"security": []},
            )
        },
        f"{API_PREFIX}/auth/logout": {
            "post": _op(operation_id="logout", summary="Invalidate the current session", status=204)
        },
        f"{tenant}/repositories": {
            "get": _op(
                operation_id="listRepositories",
                summary="Authorized registered repositories",
                response_schema="RepositorySummaryPage",
            )
        },
        f"{tenant}/repositories/local": {
            "post": _op(
                operation_id="registerLocalRepository",
                summary="Register a trusted local path",
                request=RegisterLocalRepositoryRequest,
                response=RepositorySummary,
                status=201,
            )
        },
        f"{tenant}/repositories/github": {
            "post": _op(
                operation_id="registerGithubRepository",
                summary="Register a GitHub repository from a locator",
                request=RegisterGithubRepositoryRequest,
                response=JobView,
                status=202,
            )
        },
        f"{tenant}/reviews": {
            "get": _op(
                operation_id="listReviews",
                summary="Stored and cached review rows",
                response_schema="ReviewSummaryPage",
            )
        },
        f"{tenant}/inbox/refresh": {
            "post": _op(
                operation_id="refreshInbox",
                summary="Queue personal inbox metadata refresh",
                request=InboxRefreshRequest,
                response=JobView,
                status=202,
            )
        },
        f"{tenant}/reviews/open": {
            "post": _op(
                operation_id="openTarget",
                summary="Open a saved report or queue acquisition",
                request=OpenTargetRequest,
                response_union=(OpenTargetReady, OpenTargetQueued),
            )
        },
        f"{tenant}/reviews/{{review_id}}": {
            "get": _op(operation_id="getReview", summary="Review metadata", response=ReviewDetail)
        },
        f"{tenant}/reviews/{{review_id}}/refresh": {
            "post": _op(
                operation_id="refreshReview",
                summary="Queue metadata or local observation refresh",
                response=JobView,
                status=202,
            )
        },
        f"{tenant}/reviews/{{review_id}}/reports": {
            "get": _op(
                operation_id="listReports",
                summary="Immutable reports, newest first",
                response_schema="ReportSummaryPage",
            )
        },
        f"{tenant}/reviews/{{review_id}}/reports/{{report_id}}": {
            "get": _op(
                operation_id="getReport", summary="Immutable report detail", response=ReportDetail
            )
        },
        f"{tenant}/reports/{{report_id}}/changes": {
            "get": _op(
                operation_id="listChanges",
                summary="Ranked logical changes",
                response_schema="ChangeSummaryPage",
            )
        },
        f"{tenant}/reports/{{report_id}}/changes/{{change_id}}": {
            "get": _op(
                operation_id="getChange", summary="Logical change detail", response=ChangeDetail
            )
        },
        f"{tenant}/reports/{{report_id}}/files": {
            "get": _op(operation_id="listFiles", summary="Snapshot file metadata")
        },
        f"{tenant}/reports/{{report_id}}/files/{{file_id}}/diff": {
            "get": _op(operation_id="getDiff", summary="Paged diff rows", response=DiffPage)
        },
        f"{tenant}/reports/{{report_id}}/files/{{file_id}}/source": {
            "get": _op(
                operation_id="getSource", summary="Paged captured source", response=SourcePage
            )
        },
        f"{tenant}/reports/{{report_id}}/files/{{file_id}}/copy": {
            "get": {
                "operationId": "copyFile",
                "summary": "Bounded complete patch or side text",
                "security": [{"session": []}],
                "responses": {
                    **_error_responses(),
                    "200": {
                        "description": "Plain text copy payload",
                        "content": {"text/plain": {"schema": {"type": "string"}}},
                    },
                    "413": {
                        "description": "Copy exceeds 10 MiB",
                        "content": _json_content(ErrorResponse),
                    },
                },
            }
        },
        f"{tenant}/reports/{{report_id}}/evidence/{{evidence_id}}": {
            "get": _op(
                operation_id="getEvidence", summary="Source evidence", response=SourceEvidence
            )
        },
        f"{tenant}/reports/{{report_id}}/impacts": {
            "get": _op(
                operation_id="listImpacts",
                summary="Validated API and database impacts",
                response_schema="ImpactPage",
            )
        },
        f"{tenant}/reports/{{report_id}}/coverage": {
            "get": _op(operation_id="getCoverage", summary="Hunk accounting", response=CoveragePage)
        },
        f"{tenant}/reports/{{report_id}}/changes/{{change_id}}/decision": {
            "put": _op(
                operation_id="setDecision",
                summary="Set the shared decision",
                request=SetDecisionRequest,
                response=DecisionResource,
            )
        },
        f"{tenant}/reports/{{report_id}}/changes/{{change_id}}/note": {
            "put": _op(
                operation_id="saveNote",
                summary="Save the shared note",
                request=SaveNoteRequest,
                response=NoteResource,
            )
        },
        f"{tenant}/reports/{{report_id}}/changes/{{change_id}}/history": {
            "get": _op(
                operation_id="listChangeHistory",
                summary="Attributed decision and note history",
                response_schema="ReviewEventPage",
            )
        },
        f"{tenant}/analysis/catalog": {
            "get": _op(
                operation_id="getAnalysisCatalog",
                summary="Scopes, models, and built-in presets",
                response=AnalysisCatalog,
            )
        },
        f"{tenant}/analysis/plans": {
            "post": _op(
                operation_id="createAnalysisPlan",
                summary="Create an expiring analysis plan",
                request=CreatePlanRequest,
                response=AnalysisPlanView,
                status=201,
            )
        },
        f"{tenant}/analysis/runs": {
            "post": _op(
                operation_id="startAnalysis",
                summary="Accept a plan and queue analysis",
                request=StartRunRequest,
                response=JobView,
                status=202,
            )
        },
        f"{tenant}/jobs/{{job_id}}": {
            "get": _op(operation_id="getJob", summary="Durable job status", response=JobView)
        },
        f"{tenant}/jobs/{{job_id}}/cancel": {
            "post": _op(
                operation_id="cancelJob", summary="Request job cancellation", response=JobView
            )
        },
        f"{tenant}/preferences": {
            "get": _op(
                operation_id="getPreferences", summary="Personal preferences", response=Preferences
            ),
            "patch": _op(
                operation_id="updatePreferences",
                summary="Update explicitly edited preference fields",
                request=PatchPreferencesRequest,
                response=Preferences,
            ),
        },
        f"{tenant}/presets": {
            "get": _op(
                operation_id="listPresets",
                summary="Built-in and personal presets",
                response_schema="PresetPage",
            ),
            "post": _op(
                operation_id="createPreset",
                summary="Create a personal preset",
                request=CreatePresetRequest,
                response=Preset,
                status=201,
            ),
        },
        f"{tenant}/presets/{{preset_id}}": {
            "put": _op(
                operation_id="replacePreset",
                summary="Replace a personal preset",
                request=ReplacePresetRequest,
                response=Preset,
            ),
            "delete": _op(
                operation_id="deletePreset", summary="Delete a personal preset", status=204
            ),
        },
        f"{tenant}/reviews/{{review_id}}/session": {
            "get": _op(
                operation_id="loadSession",
                summary="Personal navigation session",
                response=PersonalSession,
            ),
            "put": _op(
                operation_id="saveSession",
                summary="Save personal navigation only",
                request=SaveSessionRequest,
                response=PersonalSession,
            ),
        },
        f"{tenant}/migration/warnings": {
            "get": _op(
                operation_id="listMigrationWarnings",
                summary="Legacy import warnings",
                response_schema="MigrationWarningPage",
            )
        },
        f"{tenant}/migration/warnings/{{warning_id}}/resolve": {
            "post": _op(
                operation_id="resolveMigrationWarning",
                summary="Resolve an import warning",
                request=ResolveMigrationWarningRequest,
                response=MigrationWarning,
            )
        },
        f"{tenant}/events": {
            "get": {
                "operationId": "subscribeEvents",
                "summary": "Authorized server-sent events",
                "security": [{"session": []}],
                "responses": {
                    "200": {
                        "description": "SSE stream",
                        "content": {"text/event-stream": {"schema": _ref("Event")}},
                    }
                },
            }
        },
    }


def openapi_document() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Harpy Web API",
            "version": "1.0.0",
            "description": (
                "Contract skeleton for the Harpy browser workspace. "
                "Unimplemented routes are documented here and are not served."
            ),
        },
        "paths": _paths(),
        "components": {
            "schemas": _component_schemas(),
            "securitySchemes": {
                "session": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "harpy_session",
                }
            },
        },
    }


REQUIRED_PATHS: tuple[str, ...] = (
    "/health/live",
    f"{API_PREFIX}/me",
    f"{API_PREFIX}/auth/local",
    f"{API_PREFIX}/auth/logout",
    f"{TENANT_PREFIX}/repositories",
    f"{TENANT_PREFIX}/reviews",
    f"{TENANT_PREFIX}/reviews/open",
    f"{TENANT_PREFIX}/reports/{{report_id}}/changes",
    f"{TENANT_PREFIX}/analysis/plans",
    f"{TENANT_PREFIX}/analysis/runs",
    f"{TENANT_PREFIX}/events",
)
