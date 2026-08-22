"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Layer 3 — Memory Layer.

Public surface: other layers must depend only on the symbols exported here.
"""

from infrastructure.cognitive_core.memory.episodic_memory import Episode, EpisodicMemory
from infrastructure.cognitive_core.memory.exceptions import (
    UnknownEntityError,
    UnknownEpisodeError,
    UnknownSessionError,
    VeritasMemoryError,
)
from infrastructure.cognitive_core.memory.memory_layer import MemoryLayer
from infrastructure.cognitive_core.memory.semantic_memory import Entity, Fact, SemanticMemory
from infrastructure.cognitive_core.memory.working_memory import WorkingMemory

__all__ = [
    "MemoryLayer",
    "WorkingMemory",
    "EpisodicMemory",
    "Episode",
    "SemanticMemory",
    "Entity",
    "Fact",
    "VeritasMemoryError",
    "UnknownSessionError",
    "UnknownEpisodeError",
    "UnknownEntityError",
]
