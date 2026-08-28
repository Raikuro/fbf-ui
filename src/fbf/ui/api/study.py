"""API routes for YAML study configuration loading, parsing, DTO conversion, and validation."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from fbf.ui.orchestration.study_service import (
    PathForbiddenError,
    StudyConfigDTO,
    StudyService,
    ValidationResultDTO,
)

router = APIRouter(prefix="/study", tags=["study"])
_service = StudyService()


class ErrorDetail(BaseModel):
    """Structured error payload."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standardized API error response container."""

    error: ErrorDetail


class ParsePathRequest(BaseModel):
    """Payload for requesting server path parsing."""

    path: str = Field(description="Server filesystem path relative to permitted workspace root.")


class ParseTextRequest(BaseModel):
    """Payload for requesting raw YAML text parsing."""

    yaml_content: str = Field(description="Raw YAML document content.")


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    """Construct standardized HTTPException with ErrorResponse detail payload."""
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


@router.post("/upload", response_model=StudyConfigDTO)
async def upload_study_yaml(file: UploadFile = File(...)) -> StudyConfigDTO:  # noqa: B008
    """Parse uploaded YAML study configuration file."""
    if not file.filename:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "EMPTY_CONTENT", "No file selected.")

    contents = await file.read()
    if not contents:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "EMPTY_CONTENT", "Uploaded file is empty.")

    if len(contents) > _service.MAX_UPLOAD_BYTES:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            "FILE_TOO_LARGE",
            f"File size exceeds maximum limit of {_service.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    try:
        raw_text = contents.decode("utf-8")
    except UnicodeDecodeError:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_ENCODING",
            "File encoding is not valid UTF-8.",
        ) from None

    return _parse_text_internal(raw_text)


@router.post("/parse-path", response_model=StudyConfigDTO)
def parse_path_study_yaml(payload: ParsePathRequest) -> StudyConfigDTO:
    """Parse server filesystem YAML file relative to permitted workspace root."""
    if not payload.path or not payload.path.strip():
        raise _http_error(status.HTTP_400_BAD_REQUEST, "EMPTY_CONTENT", "Path must not be empty.")

    try:
        return _service.parse_server_file(payload.path)
    except PathForbiddenError as err:
        raise _http_error(status.HTTP_403_FORBIDDEN, "PATH_FORBIDDEN", str(err)) from None
    except FileNotFoundError as err:
        raise _http_error(status.HTTP_404_NOT_FOUND, "FILE_NOT_FOUND", str(err)) from None
    except IsADirectoryError as err:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "IS_DIRECTORY", str(err)) from None
    except ValueError as err:
        msg = str(err)
        is_schema = any(k in msg for k in ("policy", "cohorts", "dataset"))
        code = "INVALID_SCHEMA" if is_schema else "INVALID_YAML"
        raise _http_error(status.HTTP_400_BAD_REQUEST, code, msg) from None


@router.post("/parse-text", response_model=StudyConfigDTO)
def parse_text_study_yaml(payload: ParseTextRequest) -> StudyConfigDTO:
    """Parse raw YAML text payload."""
    if not payload.yaml_content or not payload.yaml_content.strip():
        raise _http_error(
            status.HTTP_400_BAD_REQUEST, "EMPTY_CONTENT", "YAML content must not be empty."
        )

    return _parse_text_internal(payload.yaml_content)


def _parse_text_internal(raw_text: str) -> StudyConfigDTO:
    """Helper delegating text parsing to StudyService and transforming exceptions to HTTP errors."""
    try:
        return _service.parse_yaml_text(raw_text)
    except ValueError as err:
        msg = str(err)
        is_schema = any(k in msg for k in ("policy", "cohorts", "dataset"))
        code = "INVALID_SCHEMA" if is_schema else "INVALID_YAML"
        raise _http_error(status.HTTP_400_BAD_REQUEST, code, msg) from None
    except Exception as err:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "INVALID_YAML", str(err)) from None


@router.post("/validate-form", response_model=ValidationResultDTO)
def validate_form_study_config(payload: StudyConfigDTO) -> ValidationResultDTO:
    """Validate StudyConfigDTO form data using Core validation."""
    try:
        return _service.validate_config_dto(payload)
    except Exception as err:
        return ValidationResultDTO(is_valid=False, errors=[str(err)])
