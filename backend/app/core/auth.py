"""Who is calling, and are they allowed to?

The frontend logs in with Supabase Auth and sends the access token (a signed
JWT) as `Authorization: Bearer <token>`. We verify the signature against the
project's public keys (JWKS), then look up the caller's role in `profiles`.
"""

from dataclasses import dataclass
from datetime import timedelta
from enum import IntEnum
from functools import lru_cache

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.db import get_pool


class Role(IntEnum):
    viewer = 0
    responder = 1
    approver = 2
    admin = 3


@dataclass(frozen=True)
class User:
    id: str
    email: str | None
    role: Role


_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{get_settings().supabase_url}/auth/v1/.well-known/jwks.json")


# Laptops drift. Without tolerance, a clock a few seconds behind Supabase makes every
# token look issued-in-the-future and all logins fail with no visible cause.
CLOCK_SKEW_LEEWAY = timedelta(seconds=90)


def decode_token(token: str) -> dict:
    """Verify a Supabase access token and return its claims. Raises jwt.InvalidTokenError."""
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience="authenticated",
        leeway=CLOCK_SKEW_LEEWAY,
    )


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        claims = decode_token(creds.credentials)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc

    async with get_pool().connection() as conn:
        row = await (
            await conn.execute("select role from public.profiles where id = %s", (claims["sub"],))
        ).fetchone()
    role = Role[row["role"]] if row else Role.viewer
    return User(id=claims["sub"], email=claims.get("email"), role=role)


def require_role(minimum: Role):
    """Dependency factory: `Depends(require_role(Role.approver))`."""

    async def check(user: User = Depends(current_user)) -> User:
        if user.role < minimum:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Requires role '{minimum.name}' or higher"
            )
        return user

    return check


router = APIRouter()


@router.get("/api/me")
async def me(user: User = Depends(current_user)) -> dict:
    return {"id": user.id, "email": user.email, "role": user.role.name}
