"""Shared API dependencies.

Auth seam: :func:`get_current_owner_id` is the single integration point for
real authentication (Supabase Auth/JWT later). Until then every request is
attributed to ``DEV_OWNER_ID`` — development-only by design. To make that
impossible to deploy by accident, production refuses to serve requests
until an authenticator replaces this stub.
"""

import logging

from app.config import settings
from app.exceptions import AppError

logger = logging.getLogger(__name__)


def get_current_owner_id() -> str:
    if settings.APP_ENV.lower() == "production":
        raise AppError(
            "Authentication is not configured for production.",
            code="AUTH_NOT_CONFIGURED",
            status_code=500,
        )
    return settings.DEV_OWNER_ID
