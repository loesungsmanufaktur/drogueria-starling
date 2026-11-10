from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Business error with a stable code the UI can translate."""

    status_code = 400

    def __init__(self, code: str, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class Forbidden(AppError):
    status_code = 403


class Unauthorized(AppError):
    status_code = 401


def _body(detail: Any, code: str) -> dict[str, Any]:
    return {"detail": detail, "code": code}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(_body(exc.detail, exc.code), exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(_body(errors, "VALIDATION_ERROR"), 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            _body(exc.detail, f"HTTP_{exc.status_code}"), exc.status_code, headers=exc.headers
        )
