# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, Request, status

from config import Settings, get_settings
from infrastructure.rate_limiter import client_key_from_request

logger = logging.getLogger("reus_veritas.security")


def _enforce_admin_rate_limit(request: Request) -> None:
    """Apply before every key comparison in this module, deliberately. Because
    REUS_API_KEY has the strongest privilege, applying a limit only after a 401
    would omit failed guessing attempts. The same ordering used by /chat is
    centralized here for every administrative endpoint so a future route cannot
    accidentally omit it."""
    from container import get_admin_rate_limiter

    limiter = get_admin_rate_limiter()
    allowed, retry_after = limiter.allow(client_key_from_request(request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Request limit exceeded. Try again later.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def verify_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> str:
    """Verify an API key with a timing-safe hmac.compare_digest comparison.
    Reject a missing or incorrect key before execution."""
    _enforce_admin_rate_limit(request)
    settings: Settings = get_settings()
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        logger.warning("unauthorized_access_attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is missing or invalid",
        )
    return x_api_key


def verify_user_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Verify only user_api_key, separately from verify_api_key. An
    administrative api_key is not accepted as a substitute, and vice versa.
    Each route validates only its intended credential. Rate limiting for this
    surface is applied directly by api/routes/chat.py through
    enforce_chat_rate_limit."""
    settings: Settings = get_settings()
    pairing_authorized = False
    if x_api_key:
        from container import get_control_plane_pairing_store

        pairing_authorized = get_control_plane_pairing_store().verify_user_key(x_api_key)
    if not x_api_key or (not settings.user_api_key or not hmac.compare_digest(x_api_key, settings.user_api_key)) and not pairing_authorized:
        logger.warning("unauthorized_user_access_attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User API key is missing or invalid",
        )
    return x_api_key


def verify_agent_access(agent_id: str, request: Request, x_api_key: str | None = Header(default=None)) -> str:
    """Allow access through the fully privileged administrative key or a
    self-service token for this exact agent_id. An agent A token never grants
    access to agent B. This checks identity only; routes requiring a specific
    permission must use require_agent_scope."""
    _enforce_admin_rate_limit(request)
    settings: Settings = get_settings()
    if x_api_key and hmac.compare_digest(x_api_key, settings.api_key):
        return agent_id

    if x_api_key:
        from container import get_agent_token_service  # Deferred import avoids a cycle with container.py.

        token = get_agent_token_service().authenticate(x_api_key)
        if token is not None and hmac.compare_digest(token.agent_id, agent_id):
            return agent_id

    logger.warning("unauthorized_agent_access_attempt", extra={"agent_id": agent_id})
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid primary API key or a token for this exact agent is required",
    )


def require_agent_scope(required_permission: str):
    """Return a FastAPI dependency that checks identity like
    verify_agent_access and also verifies that the token's effective scopes—the
    intersection of token scopes and current agent permissions—include the
    required permission. The primary API key bypasses scope checks as fully
    privileged administrative access. Agent authorization remains independently
    enforced later by MemoryService."""

    def dependency(agent_id: str, request: Request, x_api_key: str | None = Header(default=None)) -> str:
        _enforce_admin_rate_limit(request)
        settings: Settings = get_settings()
        if x_api_key and hmac.compare_digest(x_api_key, settings.api_key):
            return agent_id

        if x_api_key:
            from container import get_agent_token_service

            token_service = get_agent_token_service()
            token = token_service.authenticate(x_api_key)
            if token is not None and hmac.compare_digest(token.agent_id, agent_id):
                effective_scopes = token_service.get_effective_scopes(token)
                if required_permission in effective_scopes:
                    return agent_id
                logger.warning(
                    "token_scope_denied",
                    extra={
                        "agent_id": agent_id,
                        "payload": {"required_permission": required_permission, "token_id": token.token_id},
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This token does not include the required permission: '{required_permission}'",
                )

        logger.warning("unauthorized_agent_access_attempt", extra={"agent_id": agent_id})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid primary API key or a token for this exact agent is required",
        )

    return dependency
