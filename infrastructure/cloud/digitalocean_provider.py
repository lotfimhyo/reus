# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
DigitalOceanProvider: reference CloudProvider implementation using
DigitalOcean's REST API v2 (https://docs.digitalocean.com/reference/api/).
stdlib-only, same style as core/ollama_client.py and
interfaces/telegram_client.py.

A DigitalOcean Personal Access Token grants control of the ENTIRE DO
account, not just this bot's droplets — DO doesn't offer finer-grained
scoping. Consider creating a separate DO team/account dedicated to this
bot so a leaked token can't touch anything else you run there.
"""

import json
import urllib.error
import urllib.request
from typing import List, Optional

from infrastructure.cloud.provider_base import CloudConfig, CloudProvider, InstanceInfo

_API_BASE = "https://api.digitalocean.com/v2"

# A default, publicly available, minimal Ubuntu image — override via
# CloudConfig if you need something else.
_DEFAULT_IMAGE = "ubuntu-22-04-x64"


class DigitalOceanError(RuntimeError):
    pass


class DigitalOceanProvider(CloudProvider):
    def __init__(self, api_base: str = _API_BASE):
        self._api_base = api_base.rstrip("/")

    def _request(self, method: str, path: str, token: str, body: Optional[dict] = None) -> dict:
        url = f"{self._api_base}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise DigitalOceanError(f"DigitalOcean API error ({e.code}) on {method} {path}: {detail}") from e
        except urllib.error.URLError as e:
            raise DigitalOceanError(f"Could not reach DigitalOcean API: {e}") from e

    def create_instance(self, name: str, config: CloudConfig) -> InstanceInfo:
        body = {
            "name": name,
            "region": config.region,
            "size": config.size,
            "image": _DEFAULT_IMAGE,
        }
        if config.user_data:
            # حقل user_data مدعوم فعليًا من DigitalOcean API (cloud-init) —
            # هذا ما يجعل الخادم يشغّل عقدة Reus تلقائيًا عند أول إقلاع، لا
            # مجرد خادم فارغ يحتاج إعدادًا يدويًا لاحقًا.
            body["user_data"] = config.user_data
        result = self._request("POST", "/droplets", config.api_token, body)
        droplet = result["droplet"]
        return InstanceInfo(
            id=str(droplet["id"]),
            name=droplet["name"],
            provider="digitalocean",
            region=config.region,
            size=config.size,
            status=droplet.get("status", "new"),
            ip_address=None,  # not assigned yet right after creation
            monthly_cost_usd=self.estimate_monthly_cost(config),
        )

    def list_instances(self, config: CloudConfig) -> List[InstanceInfo]:
        result = self._request("GET", "/droplets", config.api_token)
        instances = []
        for droplet in result.get("droplets", []):
            ip = None
            for net in droplet.get("networks", {}).get("v4", []):
                if net.get("type") == "public":
                    ip = net.get("ip_address")
                    break
            instances.append(
                InstanceInfo(
                    id=str(droplet["id"]),
                    name=droplet["name"],
                    provider="digitalocean",
                    region=droplet.get("region", {}).get("slug", config.region),
                    size=droplet.get("size_slug", config.size),
                    status=droplet.get("status", "unknown"),
                    ip_address=ip,
                    monthly_cost_usd=float(droplet.get("size", {}).get("price_monthly", 0.0)),
                )
            )
        return instances

    def destroy_instance(self, instance_id: str, config: CloudConfig) -> None:
        self._request("DELETE", f"/droplets/{instance_id}", config.api_token)

    def estimate_monthly_cost(self, config: CloudConfig) -> float:
        try:
            result = self._request("GET", "/sizes", config.api_token)
            for size in result.get("sizes", []):
                if size.get("slug") == config.size:
                    return float(size.get("price_monthly", 0.0))
        except DigitalOceanError:
            pass
        return 0.0  # unknown — caller should treat 0 as "could not verify", not "free"
