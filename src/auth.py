import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request


@dataclass(frozen=True)
class Principal:
    actor: str
    role: str


def authenticate(request: Request, authorization: str | None = Header(default=None)) -> Principal:
    settings = request.app.state.settings
    configured = [settings.reviewer_api_key, settings.reader_api_key]
    if settings.app_env in {"local", "test"} and not any(configured):
        return Principal("local-demo-human", "reviewer")
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    for key, role in zip(configured, ["reviewer", "reader"], strict=True):
        if key and secrets.compare_digest(token, key.get_secret_value()):
            fingerprint = hashlib.sha256(token.encode()).hexdigest()[:12]
            return Principal(f"{role}:{fingerprint}", role)
    raise HTTPException(
        401, "Valid bearer credential required", headers={"WWW-Authenticate": "Bearer"}
    )


def require_reviewer(principal: Principal):
    if principal.role != "reviewer":
        raise HTTPException(403, "Human reviewer authorization required")
