# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from domain.memory import MemoryRecord
from domain.memory_repository import MemoryNotFound
from infrastructure.embedding import HashingEmbedder
from infrastructure.faiss_memory_repository import FaissMemoryRepository

DIM = 128


@pytest.fixture
def embedder() -> HashingEmbedder:
    return HashingEmbedder(dimension=DIM)


@pytest.fixture
def repo() -> FaissMemoryRepository:
    return FaissMemoryRepository(dimension=DIM)


def test_add_and_get(repo: FaissMemoryRepository, embedder: HashingEmbedder):
    record = MemoryRecord(agent_id="a1", content="hello world")
    repo.add(record, embedder.embed(record.content))
    fetched = repo.get(record.memory_id)
    assert fetched.content == "hello world"


def test_get_missing_raises(repo: FaissMemoryRepository):
    with pytest.raises(MemoryNotFound):
        repo.get("unknown")


def test_search_returns_most_similar_first(repo: FaissMemoryRepository, embedder: HashingEmbedder):
    r1 = MemoryRecord(agent_id="a1", content="the market is bullish today")
    r2 = MemoryRecord(agent_id="a1", content="market sentiment is very bullish")
    r3 = MemoryRecord(agent_id="a1", content="I like eating pizza on weekends")
    for r in (r1, r2, r3):
        repo.add(r, embedder.embed(r.content))

    results = repo.search(embedder.embed("bullish market sentiment"), top_k=2)
    ids = [res.record.memory_id for res in results]
    assert r1.memory_id in ids
    assert r2.memory_id in ids
    assert r3.memory_id not in ids


def test_search_filters_by_agent(repo: FaissMemoryRepository, embedder: HashingEmbedder):
    r1 = MemoryRecord(agent_id="agent-1", content="shared topic content")
    r2 = MemoryRecord(agent_id="agent-2", content="shared topic content")
    repo.add(r1, embedder.embed(r1.content))
    repo.add(r2, embedder.embed(r2.content))

    results = repo.search(embedder.embed("shared topic content"), top_k=5, agent_id="agent-1")
    assert len(results) == 1
    assert results[0].record.agent_id == "agent-1"


def test_delete_excludes_from_search_and_get(repo: FaissMemoryRepository, embedder: HashingEmbedder):
    record = MemoryRecord(agent_id="a1", content="temporary information")
    repo.add(record, embedder.embed(record.content))
    repo.delete(record.memory_id)

    with pytest.raises(MemoryNotFound):
        repo.get(record.memory_id)
    results = repo.search(embedder.embed("temporary information"), top_k=5)
    assert all(r.record.memory_id != record.memory_id for r in results)


def test_list_by_agent_excludes_other_agents_and_deleted(repo: FaissMemoryRepository, embedder: HashingEmbedder):
    r1 = MemoryRecord(agent_id="a1", content="one")
    r2 = MemoryRecord(agent_id="a1", content="two")
    r3 = MemoryRecord(agent_id="a2", content="three")
    for r in (r1, r2, r3):
        repo.add(r, embedder.embed(r.content))
    repo.delete(r2.memory_id)

    result = repo.list_by_agent("a1")
    assert len(result) == 1
    assert result[0].memory_id == r1.memory_id
