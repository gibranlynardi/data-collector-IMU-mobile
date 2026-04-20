from __future__ import annotations

from dataclasses import dataclass
from hmac import compare_digest

from fastapi import Header, HTTPException, Request

from app.core.config import get_settings


@dataclass(frozen=True)
class AccessIdentity:
    actor_type: str
    actor_id: str


def _is_enforced(expected_token: str) -> bool:
    return bool(expected_token.strip())


def _extract_header_or_bearer(header_value: str | None, authorization: str | None) -> str | None:
    if header_value and header_value.strip():
        return header_value.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def _validate_token(candidate: str | None, expected: str) -> bool:
    if not _is_enforced(expected):
        return True
    if not candidate:
        return False
    return compare_digest(candidate, expected)


def verify_device_enrollment_token(token: str | None) -> bool:
    settings = get_settings()
    return _validate_token(token, settings.device_enrollment_token)


def verify_operator_token(token: str | None) -> bool:
    settings = get_settings()
    return _validate_token(token, settings.operator_api_token)


def enforce_operator_token(
    *,
    request: Request,
    operator_token: str | None,
    authorization: str | None,
    operator_id: str | None,
) -> AccessIdentity:
    settings = get_settings()
    candidate = _extract_header_or_bearer(operator_token, authorization)
    if not _validate_token(candidate, settings.operator_api_token):
        raise HTTPException(status_code=401, detail="operator token invalid or missing")

    resolved_operator_id = (operator_id or "").strip() or "operator"
    request.state.operator_id = resolved_operator_id
    request.state.auth_actor_type = "operator"
    return AccessIdentity(actor_type="operator", actor_id=resolved_operator_id)


def enforce_device_token(
    *,
    request: Request,
    enrollment_token: str | None,
    authorization: str | None,
    device_id: str | None,
) -> AccessIdentity:
    settings = get_settings()
    candidate = _extract_header_or_bearer(enrollment_token, authorization)
    if not _validate_token(candidate, settings.device_enrollment_token):
        raise HTTPException(status_code=401, detail="device enrollment token invalid or missing")

    resolved_device_id = (device_id or "").strip() or "device"
    request.state.operator_id = resolved_device_id
    request.state.auth_actor_type = "device"
    return AccessIdentity(actor_type="device", actor_id=resolved_device_id)


def require_operator_access(
    request: Request,
    x_operator_token: str | None = Header(default=None, alias="X-Operator-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
) -> AccessIdentity:
    return enforce_operator_token(
        request=request,
        operator_token=x_operator_token,
        authorization=authorization,
        operator_id=x_operator_id,
    )


def require_device_access(
    request: Request,
    x_device_enrollment_token: str | None = Header(default=None, alias="X-Device-Enrollment-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
) -> AccessIdentity:
    return enforce_device_token(
        request=request,
        enrollment_token=x_device_enrollment_token,
        authorization=authorization,
        device_id=x_device_id,
    )


def require_operator_or_device_access(
    request: Request,
    x_operator_token: str | None = Header(default=None, alias="X-Operator-Token"),
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
    x_device_enrollment_token: str | None = Header(default=None, alias="X-Device-Enrollment-Token"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AccessIdentity:
    settings = get_settings()
    operator_enforced = _is_enforced(settings.operator_api_token)
    device_enforced = _is_enforced(settings.device_enrollment_token)

    operator_candidate = _extract_header_or_bearer(x_operator_token, authorization)
    if operator_enforced and _validate_token(operator_candidate, settings.operator_api_token):
        resolved_operator_id = (x_operator_id or "").strip() or "operator"
        request.state.operator_id = resolved_operator_id
        request.state.auth_actor_type = "operator"
        return AccessIdentity(actor_type="operator", actor_id=resolved_operator_id)

    device_candidate = _extract_header_or_bearer(x_device_enrollment_token, authorization)
    if device_enforced and _validate_token(device_candidate, settings.device_enrollment_token):
        resolved_device_id = (x_device_id or "").strip() or "device"
        request.state.operator_id = resolved_device_id
        request.state.auth_actor_type = "device"
        return AccessIdentity(actor_type="device", actor_id=resolved_device_id)

    if not operator_enforced and not device_enforced:
        resolved_operator_id = (x_operator_id or "").strip() or "operator"
        request.state.operator_id = resolved_operator_id
        request.state.auth_actor_type = "operator"
        return AccessIdentity(actor_type="operator", actor_id=resolved_operator_id)

    if operator_enforced and not device_enforced:
        raise HTTPException(status_code=401, detail="operator token invalid or missing")

    if device_enforced and not operator_enforced:
        raise HTTPException(status_code=401, detail="device enrollment token invalid or missing")

    raise HTTPException(status_code=401, detail="valid operator or device token required")


def get_request_actor(request: Request) -> tuple[str | None, str | None]:
    actor_id = getattr(request.state, "operator_id", None)
    actor_type = getattr(request.state, "auth_actor_type", None)
    if actor_id is None:
        return None, actor_type
    return str(actor_id), str(actor_type) if actor_type is not None else None
