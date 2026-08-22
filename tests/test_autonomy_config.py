"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app
"""

import pytest
from pydantic import ValidationError

from config import Settings


def test_autonomy_requires_explicit_local_model_enablement():
    with pytest.raises(ValidationError, match="REUS_AUTONOMY_ENABLED requires REUS_OLLAMA_ENABLED"):
        Settings(autonomy_enabled=True, ollama_enabled=False)


def test_autonomy_rejects_non_positive_build_budget():
    with pytest.raises(ValidationError, match="AUTONOMY_MAX_AGENT_BUILDS_PER_GOAL"):
        Settings(autonomy_max_agent_builds_per_goal=0)


def test_autonomy_defaults_are_conservative():
    settings = Settings()

    assert settings.autonomy_enabled is False
    assert settings.autonomy_auto_promote_low_risk is False
    assert settings.autonomy_max_agent_builds_per_goal == 1
