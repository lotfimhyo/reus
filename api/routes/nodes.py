"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

This read-only route exposes: (1) locally available node roles, which are
stable reference information even before any node is deployed; and (2) actual
cloud instances when a cloud provider has been configured through Telegram.

No node deployment or deletion exists on this route. Deployment remains
exclusive to the Telegram double-approval gate (`/deploy_node` then
`/approve`) documented in `infrastructure/cloud/provider_base.py`. Every node
creation and destruction must cross the same approved-chat gate; adding a
convenient deployment button here would be a security regression, not an
improvement. This endpoint mirrors `/list_nodes` information without opening a
new execution path.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from container import get_cloud_manager_holder
from infrastructure.node_roles import NODE_ROLES
from infrastructure.security import verify_api_key

router = APIRouter(prefix="/nodes", tags=["nodes"], dependencies=[Depends(verify_api_key)])


@router.get("")
def list_nodes() -> dict:
    available_roles = [
        {
            "role_id": role.role_id,
            "label": role.label_ar,
            "description": role.description_ar,
            "skill_count": len(role.specs),
        }
        for role in NODE_ROLES.values()
    ]

    holder = get_cloud_manager_holder()
    manager = holder.manager
    cloud_configured = manager is not None and manager.is_configured

    deployed_instances: list[dict] = []
    cloud_error: str | None = None
    if cloud_configured:
        try:
            deployed_instances = [
                {
                    "id": instance.id,
                    "name": instance.name,
                    "provider": instance.provider,
                    "region": instance.region,
                    "size": instance.size,
                    "status": instance.status,
                    "ip_address": instance.ip_address,
                    "monthly_cost_usd": instance.monthly_cost_usd,
                }
                for instance in manager.list_instances()
            ]
        except Exception as exc:  # noqa: BLE001 - a cloud-provider failure must not
            # discard the entire response, including stable node-role reference
            # data. This was verified with a configured-cloud simulation and a
            # real `/nodes` request rather than assumed theoretically.
            cloud_error = f"{type(exc).__name__}: {exc}"

    return {
        "available_roles": available_roles,
        "cloud_configured": cloud_configured,
        "deployed_instances": deployed_instances,
        "cloud_error": cloud_error,
    }
