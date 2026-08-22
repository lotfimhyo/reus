# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

import pytest

from application.agent_service import AgentService, RegisterAgentCommand
from application.agent_token_service import AgentTokenService
from domain.agent_token import AgentToken, ScopeExceedsAgentPermissions, TokenAlreadyRevoked
from domain.agent_token_repository import AgentTokenNotFound
from domain.repositories import AgentNotFound
from infrastructure.agent_token_repository import InMemoryAgentTokenRepository
from infrastructure.event_bus import InMemoryEventBus
from infrastructure.memory_repository import InMemoryAgentRepository


@pytest.fixture
def agent_repo() -> InMemoryAgentRepository:
    return InMemoryAgentRepository()


@pytest.fixture
def agent_service(agent_repo) -> AgentService:
    return AgentService(repository=agent_repo, event_bus=InMemoryEventBus())


@pytest.fixture
def token_service(agent_repo) -> AgentTokenService:
    return AgentTokenService(token_repo=InMemoryAgentTokenRepository(), agent_repo=agent_repo)


def test_issue_token_requires_existing_agent(token_service: AgentTokenService):
    with pytest.raises(AgentNotFound):
        token_service.issue_token("ghost-agent")


def test_issue_token_returns_usable_plaintext(token_service: AgentTokenService, agent_service: AgentService):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    issued = token_service.issue_token(agent.agent_id, label="ci-pipeline")

    assert issued.plaintext.startswith("rvos_")
    assert issued.token.label == "ci-pipeline"
    assert issued.token.agent_id == agent.agent_id
    assert issued.token.revoked is False


def test_authenticate_valid_token_returns_matching_agent(token_service: AgentTokenService, agent_service: AgentService):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    issued = token_service.issue_token(agent.agent_id)

    authenticated = token_service.authenticate(issued.plaintext)

    assert authenticated is not None
    assert authenticated.agent_id == agent.agent_id
    assert authenticated.last_used_at is not None  # تُسجَّل لحظة الاستخدام


def test_authenticate_unknown_token_returns_none(token_service: AgentTokenService):
    assert token_service.authenticate("rvos_totally-made-up-token") is None


def test_authenticate_revoked_token_returns_none(token_service: AgentTokenService, agent_service: AgentService):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    issued = token_service.issue_token(agent.agent_id)

    token_service.revoke_token(agent.agent_id, issued.token.token_id)

    assert token_service.authenticate(issued.plaintext) is None


def test_revoke_unknown_token_raises(token_service: AgentTokenService, agent_service: AgentService):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions=set(), goals=[]))
    with pytest.raises(AgentTokenNotFound):
        token_service.revoke_token(agent.agent_id, "ghost-token-id")


def test_list_tokens_returns_only_that_agents_tokens(token_service: AgentTokenService, agent_service: AgentService):
    a1 = agent_service.register_agent(RegisterAgentCommand(name="a1", permissions=set(), goals=[]))
    a2 = agent_service.register_agent(RegisterAgentCommand(name="a2", permissions=set(), goals=[]))
    token_service.issue_token(a1.agent_id, label="t1")
    token_service.issue_token(a1.agent_id, label="t2")
    token_service.issue_token(a2.agent_id, label="t3")

    tokens = token_service.list_tokens(a1.agent_id)

    assert len(tokens) == 2
    assert {t.label for t in tokens} == {"t1", "t2"}


def test_double_revoke_raises():
    token = AgentToken(agent_id="a", token_hash="h")
    token.revoke()
    with pytest.raises(TokenAlreadyRevoked):
        token.revoke()


# ---------- Token Scopes ----------


def test_issue_token_without_scopes_inherits_full_agent_permissions(
    token_service: AgentTokenService, agent_service: AgentService
):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="a", permissions={"read:memory", "write:memory"}, goals=[])
    )
    issued = token_service.issue_token(agent.agent_id)

    assert issued.token.scopes == frozenset({"read:memory", "write:memory"})


def test_issue_token_with_explicit_subset_scopes(token_service: AgentTokenService, agent_service: AgentService):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="a", permissions={"read:memory", "write:memory"}, goals=[])
    )
    issued = token_service.issue_token(agent.agent_id, scopes={"read:memory"})

    assert issued.token.scopes == frozenset({"read:memory"})


def test_issue_token_with_scope_exceeding_agent_permissions_raises(
    token_service: AgentTokenService, agent_service: AgentService
):
    agent = agent_service.register_agent(RegisterAgentCommand(name="a", permissions={"read:memory"}, goals=[]))

    with pytest.raises(ScopeExceedsAgentPermissions):
        token_service.issue_token(agent.agent_id, scopes={"read:memory", "write:memory"})


def test_get_effective_scopes_intersects_with_live_agent_permissions(
    token_service: AgentTokenService, agent_service: AgentService, agent_repo
):
    agent = agent_service.register_agent(
        RegisterAgentCommand(name="a", permissions={"read:memory", "write:memory"}, goals=[])
    )
    issued = token_service.issue_token(agent.agent_id)  # يرث الصلاحيتين معًا وقت الإصدار

    # تقليص صلاحيات الوكيل لاحقًا (مباشرة عبر المستودع، يحاكي أي آلية إدارية مستقبلية)
    live_agent = agent_repo.get(agent.agent_id)
    live_agent.permissions = {"read:memory"}
    agent_repo.update(live_agent)

    effective = token_service.get_effective_scopes(issued.token)

    assert effective == frozenset({"read:memory"})  # write:memory لم تعد فعلية رغم بقائها في scopes المخزَّنة
