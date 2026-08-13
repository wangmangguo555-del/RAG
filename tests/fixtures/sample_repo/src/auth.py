from dataclasses import dataclass
from datetime import UTC, datetime


class TokenExpiredError(Exception):
    """Raised when a refresh token has passed its expiration time."""


@dataclass
class RefreshToken:
    expires_at: datetime
    revoked: bool = False


def validate_refresh_token(token: RefreshToken) -> bool:
    """Accept only active and unexpired refresh tokens."""
    if token.revoked:
        return False
    if token.expires_at <= datetime.now(UTC):
        raise TokenExpiredError("refresh token has expired")
    return True
