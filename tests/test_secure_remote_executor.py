# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from infrastructure.cluster_network.trust_store import TrustStore
from infrastructure.cluster_network.certs import generate_self_signed_cert
from infrastructure.cognitive_core.capability.descriptor import RiskLevel
from infrastructure.cognitive_core.cluster.peer_directory import PeerDirectory
from infrastructure.cognitive_core.cluster.secure_remote_executor import SecureRemoteExecutor
from infrastructure.cognitive_core.cognitive.plan import PlanStep


class FakeSecureClient:
    def __init__(self, response=None):
        self.calls = []
        self._response = response or {"success": True, "output": "OK", "error": None}

    def post_json(self, host, port, path, obj, timeout=5.0):
        self.calls.append((host, port, path, obj))
        return self._response


@pytest.fixture
def step():
    return PlanStep(
        capability_id="cap-1", component_id="comp-1", name="text.uppercase",
        estimated_cost=0.0, risk_level=RiskLevel.LOW,
    )


@pytest.fixture
def peer_directory(tmp_path):
    return PeerDirectory(data_dir=str(tmp_path))


@pytest.fixture
def trust_store(tmp_path):
    return TrustStore(peers_file=str(tmp_path / "peers.json"))


def test_rejects_when_no_known_capability_owner(step, peer_directory, trust_store):
    executor = SecureRemoteExecutor(peer_directory, trust_store, secure_client=FakeSecureClient())
    result = executor(step, {"input": "hi"})
    assert not result.success
    assert "No known node" in result.error


def test_rejects_owner_registered_but_not_in_trust_store(step, peer_directory, trust_store):
    """أمان حرج: عقدة معروفة في PeerDirectory (تدّعي ملكية القدرة) لكن غير
    موجودة في TrustStore يجب أن تُرفَض، ولا تُرسَل لها أي بيانات إطلاقًا."""
    peer_directory.register_capability_origin("cap-1", "node-b")
    peer_directory.register_node("node-b", "https://not-trusted:9999")

    fake_client = FakeSecureClient()
    executor = SecureRemoteExecutor(peer_directory, trust_store, secure_client=fake_client)
    result = executor(step, {"input": "hi"})

    assert not result.success
    assert "TrustStore" in result.error
    assert fake_client.calls == []  # لا محاولة إرسال إطلاقًا


def test_dispatches_over_secure_client_when_peer_trusted(step, peer_directory, trust_store):
    peer_directory.register_capability_origin("cap-1", "node-b")
    cert_pem, _ = generate_self_signed_cert("node-b")
    trust_store.add_peer(
        "node-b", host="10.0.0.5", port=8443, cert_pem=cert_pem.decode("utf-8"), signing_pubkey_hex="ab"
    )

    fake_client = FakeSecureClient(response={"success": True, "output": "HI", "error": None})
    executor = SecureRemoteExecutor(peer_directory, trust_store, secure_client=fake_client)
    result = executor(step, {"input": "hi"})

    assert result.success
    assert result.output == "HI"
    host, port, path, _ = fake_client.calls[0]
    assert (host, port, path) == ("10.0.0.5", 8443, "/goals")
