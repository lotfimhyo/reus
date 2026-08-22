"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

node_runtime — التركيب الإنتاجي الحقيقي الواحد لعقدة قابلة للتشغيل
المستقل الكامل: تُبنى كل مكوّناتها من نفس اللبنات المُختبَرة فعليًا في
`tests/test_cluster_mtls_bootstrap.py` (هوية معاملات حقيقية، TrustStore،
mTLS، بوابة تمهيد)، ومكوّنات العقد الخمس (`node_roles.py`) — لا بنية موازية
جديدة. `scripts/run_node.py` غلاف رفيع فقط لسطر الأوامر يستدعي هذه الدوال.

التسلسل الكامل لعقدة (`compose_node` → `start_node` → اختياريًا
`join_cluster` → ... → `stop_node`):
  1. هوية نقل حقيقية (شهادة X.509 + مفتاح توقيع Ed25519) وهوية مكوّن.
  2. طبقات الذاكرة/القدرات الحقيقية (SQLite + AuditLog).
  3. كل مهارات دور العقدة المطلوب (`NODE_ROLES[role_id].specs`) تُبنى
     وتُربَط فعليًا عبر `AgentCapabilityBinder.build_and_bind` — بنفس بوابات
     الأمان المستخدمة في كل مكان آخر، بلا استثناء لكون هذا "نشرًا".
  4. خادم mTLS حقيقي (`SecureNodeServer` + `ClusterSnapshotNode`) يخدم
     `/cluster/snapshot` لأي عقدة أخرى تنضم لاحقًا.
  5. خادم تمهيد حقيقي (`BootstrapServer`) يستقبل طلبات انضمام عقد جديدة.
  6. إن زُوِّد عنوان عقدة أخرى (`seed_bootstrap_url`)، هذه العقدة تنضم
     كطالب عبر `MTLSJoinClient` — نفس آلية موافقة تلغرام البشرية المبنية
     سابقًا تُطبَّق على الطرف المُستقبِل، لا استثناء لكون الطالب "عقدة نشر
     سحابي" بدل عقدة تطوير محلية.
"""
from __future__ import annotations

import logging
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from infrastructure.agent_factory.builder import AgentBuilder
from infrastructure.capability_binder import AgentCapabilityBinder
from infrastructure.cluster_network.bootstrap_client import BootstrapClient
from infrastructure.cluster_network.bootstrap_server import BootstrapServer
from infrastructure.cluster_network.cluster_snapshot_node import ClusterSnapshotNode
from infrastructure.cluster_network.identity import NodeIdentity
from infrastructure.cluster_network.join_requests import PendingJoinStore
from infrastructure.cluster_network.raft import RaftNode
from infrastructure.cluster_network.raft_cluster_node import RaftClusterNode
from infrastructure.cluster_network.raft_secure_rpc import SecureRaftRpcClient
from infrastructure.cluster_network.raft_storage import RaftStorage
from infrastructure.cluster_network.task_coordinator import ClusterTaskCoordinator
from infrastructure.cluster_network.secure_client import SecureNodeClient
from infrastructure.cluster_network.secure_server import SecureNodeServer
from infrastructure.cluster_network.trust_store import TrustStore
from infrastructure.cognitive_core.capability.capability_layer import CapabilityLayer
from infrastructure.cognitive_core.cluster.mtls_join_client import JoinResult, MTLSJoinClient
from infrastructure.cognitive_core.cluster.peer_directory import PeerDirectory
from infrastructure.cognitive_core.identity import AppendOnlyAuditLog, ComponentIdentity, IdentityRegistry
from infrastructure.cognitive_core.memory.memory_layer import MemoryLayer
from infrastructure.cognitive_core.resource.local_executor import LocalExecutor
from infrastructure.node_roles import get_node_role

logger = logging.getLogger("reus.node_runtime")


@dataclass
class ComposedNode:
    role_id: str
    data_dir: Path
    component_identity: ComponentIdentity
    transport_identity: NodeIdentity
    transport_node_id: str
    identities: IdentityRegistry
    capabilities: CapabilityLayer
    memory: MemoryLayer
    peer_directory: PeerDirectory
    trust_store: TrustStore
    trust_bundle_path: str
    executor: LocalExecutor
    task_coordinator: ClusterTaskCoordinator
    mtls_host: str
    mtls_port: int
    bootstrap_host: str
    bootstrap_port: int
    pending_join_store: PendingJoinStore
    secure_server: SecureNodeServer
    bootstrap_server: Optional[BootstrapServer]
    raft: RaftNode
    raft_cluster: RaftClusterNode
    skills_bound: int

    def own_identity_payload(self) -> dict:
        return {
            "node_id": self.component_identity.component_id,
            "transport_node_id": self.transport_node_id,
            "host": self.mtls_host,
            "mtls_port": self.mtls_port,
            "cert_pem": self.transport_identity.cert_pem,
            "signing_pubkey_hex": self.transport_identity.signing_public_key_hex,
            "component_public_key_hex": self.component_identity.manifest().public_key_hex,
            "component_created_at": self.component_identity.created_at,
        }

    def secure_client_factory(self, trust_bundle_path: str) -> SecureNodeClient:
        return SecureNodeClient(
            own_cert_path=self.transport_identity.cert_path,
            own_key_path=self.transport_identity.tls_key_path,
            trust_bundle_path=trust_bundle_path,
        )

    def build_task_worker(self, orchestrator, task_executor, event_bus, pool_size: int = 4):
        """Create this node's workflow worker with its committed Raft lease gate."""
        from application.task_worker import TaskWorker

        return TaskWorker(
            orchestrator=orchestrator,
            executor=task_executor,
            event_bus=event_bus,
            pool_size=pool_size,
            lease_coordinator=self.task_coordinator,
        )


def _load_or_create_component_identity(root: Path) -> ComponentIdentity:
    """Persist the node component identity with owner-only file permissions."""
    identity_path = root / "component_identity.json"
    if identity_path.exists():
        data = json.loads(identity_path.read_text(encoding="utf-8"))
        return ComponentIdentity.from_persisted(
            component_id=data["component_id"],
            component_type=data["component_type"],
            private_key_hex=data["private_key_hex"],
            created_at=data["created_at"],
        )
    identity = ComponentIdentity.create("node")
    payload = {
        "component_id": identity.component_id,
        "component_type": identity.component_type,
        "private_key_hex": identity.export_private_key_hex(),
        "created_at": identity.created_at,
    }
    temp_path = identity_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.chmod(temp_path, 0o600)
    temp_path.replace(identity_path)
    return identity


def compose_node(
    role_id: str,
    data_dir: str,
    mtls_host: str = "127.0.0.1",
    mtls_port: int = 8443,
    bootstrap_host: str = "127.0.0.1",
    bootstrap_port: int = 8080,
    node_label: Optional[str] = None,
) -> ComposedNode:
    """يبني عقدة كاملة (كل الطبقات + الخوادم مُنشَأة، لكن **غير بادئة
    الاستماع بعد** — انظر `start_node`) لدور مُعرَّف في `node_roles.py`.
    يرفع `ValueError` فورًا لدور غير معروف قبل أي بناء فعلي — لا نشر جزئي
    صامت لعقدة بلا مهارات محدَّدة."""
    role = get_node_role(role_id)  # يرفع ValueError مبكرًا لدور غير معروف

    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    component_identity = _load_or_create_component_identity(root)
    transport_node_id = node_label or f"reus-{component_identity.component_id}"
    transport_identity = NodeIdentity(transport_node_id, base_dir=str(root / "transport"))

    audit_log = AppendOnlyAuditLog(str(root / "audit.jsonl"))
    identities = IdentityRegistry(persist_path=str(root / "identities.json"))
    capabilities = CapabilityLayer(audit_log, data_dir=str(root / "capabilities"))
    memory = MemoryLayer(audit_log, data_dir=str(root / "memory"))
    peer_directory = PeerDirectory(data_dir=str(root))
    trust_store = TrustStore(peers_file=str(root / "peers.json"))
    trust_bundle_path = str(root / "trust_bundle.pem")
    trust_store.build_trust_bundle(trust_bundle_path, own_cert_pem=transport_identity.cert_pem)

    executor = LocalExecutor()
    agent_builder = AgentBuilder(output_dir=str(root / "agents" / "generated"))
    binder = AgentCapabilityBinder(
        builder=agent_builder,
        capability_layer=capabilities,
        local_executor=executor,
        component_id=component_identity.component_id,
    )

    skills_bound = 0
    for spec in role.specs:
        # يرفع CapabilityBindingRejected فورًا إن فشلت أي مهارة أساسية —
        # لا نشر جزئي صامت لعقدة ببعض مهاراتها فقط.
        binder.build_and_bind(spec)
        skills_bound += 1

    def secure_client_factory() -> SecureNodeClient:
        return SecureNodeClient(
            own_cert_path=transport_identity.cert_path,
            own_key_path=transport_identity.tls_key_path,
            trust_bundle_path=trust_bundle_path,
        )

    raft_rpc = SecureRaftRpcClient(trust_store, secure_client_factory)
    raft = RaftNode(
        node_id=transport_node_id,
        get_peer_ids=trust_store.transport_peer_ids,
        rpc_client=raft_rpc,
        storage=RaftStorage(str(root / "raft_state.json")),
    )
    snapshot_node = RaftClusterNode(
        node_id=component_identity.component_id,
        trust_store=trust_store,
        capabilities=capabilities,
        memory=memory,
        raft=raft,
        transport_node_id=transport_node_id,
    )
    task_coordinator = ClusterTaskCoordinator(
        cluster=snapshot_node, executor=executor, assignee_id=transport_node_id
    )
    secure_server = SecureNodeServer(
        node=snapshot_node,
        host=mtls_host,
        port=mtls_port,
        cert_path=transport_identity.cert_path,
        key_path=transport_identity.tls_key_path,
        trust_bundle_path=trust_bundle_path,
    )

    pending_join_store = PendingJoinStore(persist_path=str(root / "pending_joins.json"))
    composed = ComposedNode(
        role_id=role_id,
        data_dir=root,
        component_identity=component_identity,
        transport_identity=transport_identity,
        transport_node_id=transport_node_id,
        identities=identities,
        capabilities=capabilities,
        memory=memory,
        peer_directory=peer_directory,
        trust_store=trust_store,
        trust_bundle_path=trust_bundle_path,
        executor=executor,
        task_coordinator=task_coordinator,
        mtls_host=mtls_host,
        mtls_port=mtls_port,
        bootstrap_host=bootstrap_host,
        bootstrap_port=bootstrap_port,
        pending_join_store=pending_join_store,
        secure_server=secure_server,
        bootstrap_server=None,
        raft=raft,
        raft_cluster=snapshot_node,
        skills_bound=skills_bound,
    )
    composed.bootstrap_server = BootstrapServer(
        pending_store=pending_join_store,
        own_identity_payload_fn=composed.own_identity_payload,
        host=bootstrap_host,
        port=bootstrap_port,
    )
    return composed


def start_node(composed: ComposedNode) -> None:
    composed.secure_server.start()
    composed.bootstrap_server.start()
    composed.raft.start()
    logger.info(
        "node_started",
        extra={
            "role_id": composed.role_id,
            "node_id": composed.component_identity.component_id,
            "skills_bound": composed.skills_bound,
            "mtls_port": composed.mtls_port,
            "bootstrap_port": composed.bootstrap_port,
        },
    )


def stop_node(composed: ComposedNode) -> None:
    composed.raft.stop()
    composed.secure_server.stop()
    composed.bootstrap_server.stop()


def join_cluster(composed: ComposedNode, seed_bootstrap_url: str, max_wait_seconds: float = 300.0) -> JoinResult:
    """يجب استدعاؤها بعد `start_node` (خادم mTLS يجب أن يكون يستمع فعليًا
    قبل أن تطلب عقدة أخرى استقبال لقطتها). ينتظر (bounded) موافقة بشرية
    فعلية عبر تلغرام على الطرف المُستقبِل — انظر توثيق `MTLSJoinClient`."""
    join_client = MTLSJoinClient(
        node_identity=composed.component_identity,
        own_identity_payload_fn=composed.own_identity_payload,
        identities=composed.identities,
        capabilities=composed.capabilities,
        memory=composed.memory,
        peer_directory=composed.peer_directory,
        trust_store=composed.trust_store,
        trust_bundle_path=composed.trust_bundle_path,
        secure_client_factory=composed.secure_client_factory,
        bootstrap_client=BootstrapClient(),
        max_wait_seconds=max_wait_seconds,
    )
    result = join_client.join(seed_bootstrap_url)
    composed.secure_server.refresh_trust(composed.trust_bundle_path)
    logger.info(
        "node_joined_cluster",
        extra={
            "role_id": composed.role_id,
            "peer_component_id": result.peer_component_id,
            "capabilities_ingested": result.capabilities_ingested,
            "facts_ingested": result.facts_ingested,
        },
    )
    return result
