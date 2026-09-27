from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from deep_research.auth.dependencies import (
    authenticate_request,
    get_auth_service,
    require_owner,
)
from deep_research.auth.models import AuthContext, IssuedSession
from deep_research.auth.passwords import InvalidPassword
from deep_research.auth.service import AuthService, InvalidCredentials, LoginRateLimited
from deep_research.config import Settings
from deep_research.persistence.auth_store import RegistrationClosed


class AuthCredentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class AuthStatusResponse(BaseModel):
    registration_open: bool
    authenticated: bool


class AuthSessionResponse(BaseModel):
    user_id: str
    username: str
    role: str
    csrf_token: str


router = APIRouter(prefix="/api/v1/auth")


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _set_session_cookie(
    response: Response,
    issued: IssuedSession,
    settings: Settings,
) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=issued.raw_token,
        max_age=settings.auth_cookie_max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _session_response(issued: IssuedSession) -> AuthSessionResponse:
    return AuthSessionResponse(
        user_id=issued.user.user_id,
        username=issued.user.username,
        role=issued.user.role,
        csrf_token=issued.csrf_token,
    )


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthStatusResponse:
    context = await authenticate_request(request, service)
    return AuthStatusResponse(
        registration_open=await service.registration_open(),
        authenticated=context is not None,
    )


@router.post(
    "/register",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_owner(
    body: AuthCredentials,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSessionResponse:
    try:
        issued = await service.register(body.username, body.password)
    except RegistrationClosed as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner registration is closed.",
        ) from exc
    except InvalidPassword as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    _set_session_cookie(response, issued, _settings(request))
    return _session_response(issued)


@router.post("/login", response_model=AuthSessionResponse)
async def login_owner(
    body: AuthCredentials,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthSessionResponse:
    client_ip = request.client.host if request.client is not None else "unknown"
    try:
        issued = await service.login(body.username, body.password, client_ip)
    except (InvalidCredentials, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        ) from exc
    except LoginRateLimited as exc:
        settings = _settings(request)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts.",
            headers={"Retry-After": str(settings.auth_login_window_seconds)},
        ) from exc
    _set_session_cookie(response, issued, _settings(request))
    return _session_response(issued)


@router.get("/me", response_model=AuthSessionResponse)
async def current_owner(
    context: Annotated[AuthContext, Depends(require_owner)],
) -> AuthSessionResponse:
    return AuthSessionResponse(
        user_id=context.user.user_id,
        username=context.user.username,
        role=context.user.role,
        csrf_token=context.session.csrf_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_owner(
    request: Request,
    response: Response,
    context: Annotated[AuthContext, Depends(require_owner)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    settings = _settings(request)
    raw_token = request.cookies.get(settings.auth_cookie_name)
    await service.logout(raw_token)
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
