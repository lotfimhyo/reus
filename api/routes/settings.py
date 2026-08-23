"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

This route changes a limited allowlisted set of settings, including Telegram,
task-executor, and model-provider configuration, from the control plane rather
than by manual configuration-file editing. It requires the administrative API
key and is constrained by `ALLOWED_SETTINGS_KEYS`; it can never change
`REUS_API_KEY` or `REUS_USER_API_KEY` themselves.

An important operational boundary is explicit: a saved setting is not active
immediately. Settings are cached at process startup and background workers are
constructed then as well. Restart the server or container after saving a new
value. Every `POST /settings` response includes `restart_required: true` for
this reason.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from infrastructure.env_file_writer import (
    ALLOWED_SETTINGS_KEYS,
    InvalidSettingKey,
    InvalidSettingValue,
    read_env_file,
    update_env_file,
)
from infrastructure.security import verify_api_key

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(verify_api_key)])


class SettingsUpdateRequest(BaseModel):
    values: dict[str, str]


@router.get("")
def get_settings_values() -> dict:
    """Return editable values; sensitive provider keys and Telegram tokens are
    masked as present or empty and never returned as plaintext."""
    return {
        "values": read_env_file(),
        "editable_keys": sorted(ALLOWED_SETTINGS_KEYS),
    }


@router.post("")
def update_settings_values(body: SettingsUpdateRequest) -> dict:
    try:
        update_env_file(body.values)
    except (InvalidSettingKey, InvalidSettingValue) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        "status": "saved",
        "restart_required": True,
        "message": "Settings were saved. Restart the server or container to apply the changes.",
    }
