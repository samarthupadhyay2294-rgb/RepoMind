"""Minimal consistent API error format (Part 1)."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class DatabaseError(AppError):
    def __init__(self, message: str = "Database operation failed.") -> None:
        super().__init__(message, code="DATABASE_ERROR", status_code=500)


class RepositoryNotFoundError(AppError):
    def __init__(self, message: str = "Repository not found.") -> None:
        super().__init__(message, code="REPOSITORY_NOT_FOUND", status_code=404)


class RepositoryValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="REPOSITORY_VALIDATION_ERROR", status_code=400)


class IngestionError(AppError):
    def __init__(self, message: str = "Repository ingestion failed.") -> None:
        super().__init__(message, code="INGESTION_ERROR", status_code=500)


class EmbeddingError(AppError):
    def __init__(self, message: str = "Embedding generation failed.") -> None:
        super().__init__(message, code="EMBEDDING_ERROR", status_code=502)


class QdrantError(AppError):
    def __init__(self, message: str = "Vector store operation failed.") -> None:
        super().__init__(message, code="QDRANT_ERROR", status_code=502)


class ToolError(AppError):
    """Structured investigation-tool failure (input, boundary, or limit)."""

    def __init__(
        self,
        message: str = "Tool execution failed.",
        code: str = "TOOL_ERROR",
        status_code: int = 400,
    ) -> None:
        super().__init__(message, code=code, status_code=status_code)


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content=error_body(exc.code, exc.message)
    )


async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    # Never expose stack traces, paths, env vars, or secrets.
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", "An unexpected error occurred."),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
