"""
Project: Veritas AI
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
Copyright: © Lotfi Mahiddine
Architecture: Veritas AI

Goal — step 1 of the cognitive cycle ("فهم الهدف") from the master
architecture doc, section 2.5. A Goal is the structured input the Cognitive
Engine reasons about; it is deliberately simple in this phase (no nested
sub-goals, no natural-language goal parsing) — those are future-phase
concerns.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Goal:
    """
    A concrete, structured objective for the Cognitive Engine to pursue.

    A goal is matched against the Capability Registry using either
    `required_capability_name` (an exact capability name) or
    `required_tags` (all tags must be present on a candidate capability) —
    at least one of the two must be provided so goal analysis has something
    to search on.
    """

    description: str
    payload: dict[str, Any] = field(default_factory=dict)
    required_capability_name: Optional[str] = None
    required_tags: tuple[str, ...] = ()
    goal_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.description or not self.description.strip():
            raise ValueError("Goal.description must be non-empty.")
        if not self.required_capability_name and not self.required_tags:
            raise ValueError(
                "Goal must specify required_capability_name and/or "
                "required_tags so it can be matched against the "
                "Capability Registry."
            )
