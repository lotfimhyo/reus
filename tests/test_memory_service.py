# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from application.agent_service import AgentService, RegisterAgentCommand
from application.memory_service import MemoryService, StoreMemoryCommand
from domain.entities import PermissionDenied
from domain.repositories import AgentNotFound
from infrastructure.embedding import HashingEmbedder
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.faiss_memory_repository import FaissMemoryRepository
from infrastructure.memory_repository import InMemoryAgentRepository

DIM = 128


@pytest.fixture
def agent_repo() -> InMemoryAgentRepository:
    return InMemoryAgentRepository()


@pytest.fixture
def agent_service(agent_repo: InMemoryAgentRepository) -> AgentService:
    return AgentService(repository=agent_repo, event_bus=InMemoryEventBus())


@pytest.fixture
def memory_service(agent_repo: InMemoryAgentRepository) -> MemoryService:
    return MemoryService(
        memory_repo=FaissMemoryRepository(dimension=DIM),
        agent_repo=agent_repo,
        embedder=HashingEmbedder(dimension=DIM),
    )


def test_store_requires_write_permission(agent_service: AgentService, memory_service: MemoryService):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="reader", permissions={"read:memory"}, goals=[])
    )
    with pytest.raises(PermissionDenied):
        memory_service.store(StoreMemoryCommand(agent_id=agent.agent_id, content="x", tags=[]))


def test_store_updates_agent_memory_refs(agent_service: AgentService, memory_service: MemoryService, agent_repo):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="writer", permissions={"write:memory"}, goals=[])
    )
    record = memory_service.store(
        StoreMemoryCommand(agent_id=agent.agent_id, content="important fact", tags=["fact"])
    )
    refreshed = agent_repo.get(agent.agent_id)
    assert record.memory_id in refreshed.memory_refs


def test_search_requires_read_permission(agent_service: AgentService, memory_service: MemoryService):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="writer-only", permissions={"write:memory"}, goals=[])
    )
    memory_service.store(StoreMemoryCommand(agent_id=agent.agent_id, content="secret", tags=[]))
    with pytest.raises(PermissionDenied):
        memory_service.search(agent.agent_id, "secret")


def test_search_finds_stored_memory(agent_service: AgentService, memory_service: MemoryService):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="full-access", permissions={"read:memory", "write:memory"}, goals=[])
    )
    memory_service.store(StoreMemoryCommand(agent_id=agent.agent_id, content="the price of gold rose sharply", tags=[]))
    results = memory_service.search(agent.agent_id, "gold price increase")
    assert len(results) == 1


def test_forget_removes_from_refs(agent_service: AgentService, memory_service: MemoryService, agent_repo):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="full-access", permissions={"read:memory", "write:memory"}, goals=[])
    )
    record = memory_service.store(StoreMemoryCommand(agent_id=agent.agent_id, content="temp note", tags=[]))
    memory_service.forget(agent.agent_id, record.memory_id)
    refreshed = agent_repo.get(agent.agent_id)
    assert record.memory_id not in refreshed.memory_refs


def test_store_unknown_agent_raises(memory_service: MemoryService):
    with pytest.raises(AgentNotFound):
        memory_service.store(StoreMemoryCommand(agent_id="ghost", content="x", tags=[]))
