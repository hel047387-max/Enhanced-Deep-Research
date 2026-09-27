from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from deep_research.auth.models import AuthContext
from deep_research.auth.service import AuthService
from deep_research.config import Settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_auth_service(request: Request) -> AuthService:
    service = getattr(request.app.state, "auth_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is unavailable.",
        )
    return service


def get_auth_settings(request: Request) -> Settings:
    return request.app.state.settings


async def authenticate_request(
    request: Request,
    service: AuthService,
) -> AuthContext | None:
    settings = get_auth_settings(request)
    return await service.authenticate(request.cookies.get(settings.auth_cookie_name))


async def require_owner(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthContext:
    context = await authenticate_request(request, service)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    if request.method not in SAFE_METHODS:
        supplied = request.headers.get("X-CSRF-Token", "")
        if not supplied or not secrets.compare_digest(
            supplied,
            context.session.csrf_token,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token.",
            )
    return context
