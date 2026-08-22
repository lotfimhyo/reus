# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
CloudTelegramCommands: يربط CloudDeploymentManager بـ TelegramService كأوامر
/configure_cloud، /deploy_node، /list_nodes، /destroy_node — كلها أوامر
إدارية (register_admin_command) لا تصل إلا من محادثة ضمن admin_chat_ids.

كل إجراء يُنشئ أو يُدمّر بنية تحتية فوترة يمرّ عبر نفس بوابة الموافقة
(TelegramService.request_approval) — لا شيء يُنشأ أو يُدمَّر دون /approve
صريح من محادثة إدارية مصرَّح لها، فوق حدي max_instances/budget_cap
المفروضين في CloudDeploymentManager نفسه قبل أي اقتراح.

مصدر المزوّد والتوكن والحدود القصوى: فقط عبر /configure_cloud من المطوّر —
لا يكتشفها أو يختارها النظام نفسه أبدًا. هذا القرار منقول كما هو من
Project Phoenix دون تخفيف.
"""
from __future__ import annotations

import shlex
import time
import uuid
from typing import Dict, Optional, Type

from application.telegram_service import TelegramService
from infrastructure.cloud.deployment_manager import CloudDeploymentManager, CloudLimitExceeded
from infrastructure.cloud.digitalocean_provider import DigitalOceanProvider
from infrastructure.cloud.node_cloud_init import build_node_cloud_init_script
from infrastructure.cloud.provider_base import CloudConfig, CloudProvider
from infrastructure.event_bus import Event, EventBus
from infrastructure.node_roles import NODE_ROLES

_PROVIDERS: Dict[str, Type[CloudProvider]] = {
    "digitalocean": DigitalOceanProvider,
}

_CONFIGURE_USAGE = (
    "الاستخدام: /configure_cloud provider=digitalocean token=<token> region=nyc3 "
    "size=s-1vcpu-1gb max_instances=2 budget_cap=20 "
    'source_fetch_cmd="git clone https://.../reus.git /opt/reus"\n'
    "(source_fetch_cmd إلزامي — كيف يصل كود Reus لخادم سحابي فارغ. استخدم علامتي "
    "اقتباس حول القيمة إن احتوت مسافات.)"
)


class CloudTelegramCommands:
    def __init__(
        self,
        service: TelegramService,
        provider_factory=None,
        event_bus: EventBus | None = None,
        seed_bootstrap_url_provider=None,
        manager_holder=None,
    ):
        """`provider_factory(provider_name) -> CloudProvider` — يُستبدَل فقط
        في الاختبارات (لتوجيه DigitalOceanProvider نحو خادم وهمي).
        `seed_bootstrap_url_provider() -> str | None` — دالة اختيارية تُعيد
        عنوان بوابة تمهيد عقدة منسِّقة موجودة (إن وُجدت) لضم العقدة السحابية
        الجديدة تلقائيًا للعنقود عند إقلاعها. `None`/غير مزوَّدة يعني: عقدة
        مستقلة بلا انضمام تلقائي — يبقى ممكنًا لاحقًا يدويًا.
        `manager_holder` — صندوق مشترك اختياري (`CloudManagerHolder`) يُملأ
        فور نجاح /configure_cloud، ليصبح المدير مرئيًا خارج تلغرام أيضًا
        (مسار /nodes في لوحة التحكم تحديدًا) دون تكرار الحالة."""
        self._service = service
        self._manager: Optional[CloudDeploymentManager] = None
        self._provider_factory = provider_factory or (lambda name: _PROVIDERS[name]())
        self._bus = event_bus
        self._source_fetch_cmd: Optional[str] = None
        self._seed_bootstrap_url_provider = seed_bootstrap_url_provider
        self._manager_holder = manager_holder

        service.register_admin_command("/configure_cloud", self._cmd_configure)
        service.register_admin_command("/deploy_node", self._cmd_deploy)
        service.register_admin_command("/list_nodes", self._cmd_list)
        service.register_admin_command("/destroy_node", self._cmd_destroy)

    def _publish(self, name: str, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(Event(name=name, payload=payload))

    def _send(self, chat_id: str, text: str) -> None:
        self._service.deliver(chat_id, text)

    def _cmd_configure(self, chat_id: str, args: str) -> None:
        try:
            parsed = dict(kv.split("=", 1) for kv in shlex.split(args))
            provider_name = parsed["provider"].lower()
            if provider_name not in _PROVIDERS:
                self._send(chat_id, f"مزوّد غير معروف '{provider_name}'. المدعوم: {sorted(_PROVIDERS)}")
                return
            source_fetch_cmd = parsed["source_fetch_cmd"]
            config = CloudConfig(
                provider=provider_name,
                api_token=parsed["token"],
                region=parsed["region"],
                size=parsed["size"],
                max_instances=int(parsed["max_instances"]),
                budget_cap_usd_per_month=float(parsed["budget_cap"]),
            )
        except (KeyError, ValueError):
            self._send(chat_id, _CONFIGURE_USAGE)
            return

        self._manager = CloudDeploymentManager(self._provider_factory(provider_name))
        if self._manager_holder is not None:
            self._manager_holder.manager = self._manager
        self._manager.configure(config)
        self._source_fetch_cmd = source_fetch_cmd
        self._publish(
            "cloud.configured",
            {  # لا يُنشَر التوكن نفسه في الحدث إطلاقًا — فقط بيانات غير حسّاسة
                "provider": provider_name,
                "region": config.region,
                "max_instances": config.max_instances,
                "budget_cap_usd_per_month": config.budget_cap_usd_per_month,
            },
        )
        self._send(
            chat_id,
            f"تم ضبط السحابة: {provider_name}، المنطقة={config.region}، الحجم={config.size}، "
            f"حد أقصى {config.max_instances} عقدة، سقف ${config.budget_cap_usd_per_month:.2f}/شهر.\n"
            f"ملاحظة: توكن الـ API أُرسل في هذه المحادثة — تعامل معه كسرّ حساس، ويمكنك "
            f"إلغاءه/تدويره من لوحة {provider_name} في أي وقت.",
        )

    def _cmd_deploy(self, chat_id: str, args: str) -> None:
        if not self._manager:
            self._send(chat_id, "السحابة غير مضبوطة بعد. استخدم /configure_cloud أولًا.")
            return

        parts = args.split(maxsplit=1)
        if not parts or parts[0] not in NODE_ROLES:
            self._send(
                chat_id,
                f"الاستخدام: /deploy_node <role_id> [name]\nالأدوار المتاحة: {sorted(NODE_ROLES)}",
            )
            return
        role_id = parts[0]
        name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else f"reus-{role_id}-{int(time.time())}"

        try:
            proposal = self._manager.propose_new_instance(name)
        except CloudLimitExceeded as e:
            self._publish("cloud.deploy_rejected", {"name": name, "role_id": role_id, "reason": str(e)})
            self._send(chat_id, f"رُفض النشر: {e}")
            return

        if not self._source_fetch_cmd:
            self._send(chat_id, "لم يُضبَط source_fetch_cmd بعد. أعد /configure_cloud بتضمينه.")
            return

        seed_url = self._seed_bootstrap_url_provider() if self._seed_bootstrap_url_provider else None
        try:
            cloud_init_script = build_node_cloud_init_script(
                role_id=role_id, source_fetch_cmd=self._source_fetch_cmd, seed_bootstrap_url=seed_url
            )
        except ValueError as e:
            self._send(chat_id, f"تعذّر توليد سكربت الإقلاع: {e}")
            return

        approval_id = f"deploy-{uuid.uuid4().hex[:8]}"
        seed_note = f"\nستنضم تلقائيًا للعنقود عبر: {seed_url}" if seed_url else "\nستُنشَر كعقدة مستقلة (بلا عنقود موجود لتنضم إليه الآن)."
        self._service.request_approval(
            chat_id,
            approval_id,
            f"{proposal.describe()}\nالدور: {role_id}{seed_note}",
            on_approve=lambda: self._execute_deploy(chat_id, name, role_id, cloud_init_script),
            on_reject=lambda: self._send(chat_id, f"أُلغي نشر '{name}'."),
        )

    def _execute_deploy(self, chat_id: str, name: str, role_id: str, cloud_init_script: str) -> None:
        try:
            self._manager.set_user_data(cloud_init_script)
            instance = self._manager.execute_new_instance(name)
            self._publish(
                "cloud.instance_deployed",
                {
                    "name": instance.name,
                    "id": instance.id,
                    "role_id": role_id,
                    "provider": instance.provider,
                    "monthly_cost_usd": instance.monthly_cost_usd,
                },
            )
            self._send(
                chat_id,
                f"تم النشر: {instance.name} ({instance.id}) دور={role_id} على {instance.provider}، "
                f"الحالة={instance.status}، ~${instance.monthly_cost_usd:.2f}/شهر",
            )
        except Exception as e:  # noqa: BLE001
            self._publish("cloud.deploy_failed", {"name": name, "role_id": role_id, "error": str(e)})
            self._send(chat_id, f"فشل النشر: {e}")
        finally:
            self._manager.set_user_data("")  # إعادة ضبط بعد كل عملية نشر — لا يتسرّب لعملية تالية

    def _cmd_list(self, chat_id: str, args: str) -> None:
        if not self._manager:
            self._send(chat_id, "السحابة غير مضبوطة بعد.")
            return
        instances = self._manager.list_instances()
        if not instances:
            self._send(chat_id, "لا توجد عقد سحابية.")
            return
        lines = [
            f"{i.name} ({i.id}): {i.status}، {i.ip_address or 'بلا IP بعد'}، ${i.monthly_cost_usd:.2f}/شهر"
            for i in instances
        ]
        self._send(chat_id, "\n".join(lines))

    def _cmd_destroy(self, chat_id: str, args: str) -> None:
        instance_id = args.strip()
        if not instance_id:
            self._send(chat_id, "الاستخدام: /destroy_node <instance_id>")
            return
        if not self._manager:
            self._send(chat_id, "السحابة غير مضبوطة بعد.")
            return

        approval_id = f"destroy-{uuid.uuid4().hex[:8]}"
        self._service.request_approval(
            chat_id,
            approval_id,
            f"حذف العقدة {instance_id}؟ هذا الإجراء لا رجعة فيه.",
            on_approve=lambda: self._execute_destroy(chat_id, instance_id),
            on_reject=lambda: self._send(chat_id, f"أُلغي حذف {instance_id}."),
        )

    def _execute_destroy(self, chat_id: str, instance_id: str) -> None:
        try:
            self._manager.destroy_instance(instance_id)
            self._publish("cloud.instance_destroyed", {"instance_id": instance_id})
            self._send(chat_id, f"تم حذف العقدة {instance_id}.")
        except Exception as e:  # noqa: BLE001
            self._publish("cloud.destroy_failed", {"instance_id": instance_id, "error": str(e)})
            self._send(chat_id, f"فشل الحذف: {e}")
