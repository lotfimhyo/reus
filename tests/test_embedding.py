# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import numpy as np

from infrastructure.embedding import HashingEmbedder


def test_embedding_is_deterministic():
    embedder = HashingEmbedder(dimension=128)
    v1 = embedder.embed("الوكيل يراقب السوق")
    v2 = embedder.embed("الوكيل يراقب السوق")
    assert v1 == v2


def test_embedding_has_correct_dimension():
    embedder = HashingEmbedder(dimension=256)
    vector = embedder.embed("test content")
    assert len(vector) == 256


def test_embedding_is_normalized():
    embedder = HashingEmbedder(dimension=128)
    vector = np.array(embedder.embed("some meaningful sentence here"))
    assert abs(np.linalg.norm(vector) - 1.0) < 1e-5


def test_similar_texts_have_higher_similarity_than_unrelated():
    embedder = HashingEmbedder(dimension=384)
    a = np.array(embedder.embed("the agent monitors the crypto market"))
    b = np.array(embedder.embed("the agent watches the crypto market closely"))
    c = np.array(embedder.embed("bananas are a good source of potassium"))

    sim_related = float(np.dot(a, b))
    sim_unrelated = float(np.dot(a, c))
    assert sim_related > sim_unrelated


def test_empty_text_returns_zero_vector():
    embedder = HashingEmbedder(dimension=64)
    vector = embedder.embed("   ")
    assert all(v == 0.0 for v in vector)
