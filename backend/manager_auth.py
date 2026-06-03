"""Simple shared-secret auth for the manager web app."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


def manager_key_configured() -> bool:
    return bool((os.environ.get("MANAGER_WEB_KEY") or "").strip())


def require_manager_key(x_manager_key: str = Header(default="", alias="X-Manager-Key")) -> None:
    expected = (os.environ.get("MANAGER_WEB_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            503,
            "MANAGER_WEB_KEY is not configured on the server",
        )
    if (x_manager_key or "").strip() != expected:
        raise HTTPException(401, "Invalid manager key")
