# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

"""
Application Layer: AgentTokenService.
حالات الاستخدام: إصدار رمز جديد لوكيل (يتحقق من وجود الوكيل أولًا، ومن أن أي
نطاق مطلوب لا يتجاوز صلاحيات الوكيل الحالية)، سرد رموز وكيل (بلا نص صافٍ أو
hash — بيانات وصفية فقط)، إلغاء رمز، والتحقق من رمز عند المصادقة (يُستخدم من
infrastructure/security.py على حدود HTTP).
"""
from __future__ import annotations

from dataclasses import dataclass

from domain.agent_token import AgentToken, ScopeExceedsAgentPermissions
from domain.agent_token_repository import AgentTokenNotFound, AgentTokenRepository
from domain.repositories import AgentRepository
from infrastructure.token_hashing import generate_plaintext_token, hash_token


@dataclass
class IssuedToken:
    token: AgentToken
    plaintext: str  # يُعرَض للمستدعي مرة واحدة فقط؛ لا يُخزَّن في أي مكان بعد هذه اللحظة


class AgentTokenService:
    def __init__(self, token_repo: AgentTokenRepository, agent_repo: AgentRepository) -> None:
        self._tokens = token_repo
        self._agents = agent_repo

    def issue_token(self, agent_id: str, label: str = "", scopes: set[str] | None = None) -> IssuedToken:
        agent = self._agents.get(agent_id)  # يرفع AgentNotFound إن لم يكن الوكيل موجودًا

        if scopes is None:
            # لا نطاق مُحدَّد صراحة => يرث الرمز كل صلاحيات الوكيل الحالية (السلوك السابق، متوافق للخلف)
            effective_scopes = frozenset(agent.permissions)
        else:
            requested = frozenset(scopes)
            excess = requested - agent.permissions
            if excess:
                raise ScopeExceedsAgentPermissions(excess)
            effective_scopes = requested

        plaintext = generate_plaintext_token()
        token = AgentToken(agent_id=agent_id, token_hash=hash_token(plaintext), label=label, scopes=effective_scopes)
        self._tokens.add(token)
        return IssuedToken(token=token, plaintext=plaintext)

    def list_tokens(self, agent_id: str) -> list[AgentToken]:
        self._agents.get(agent_id)
        return self._tokens.list_by_agent(agent_id)

    def revoke_token(self, agent_id: str, token_id: str) -> AgentToken:
        matching = [t for t in self._tokens.list_by_agent(agent_id) if t.token_id == token_id]
        if not matching:
            raise AgentTokenNotFound(token_id)
        token = matching[0]
        token.revoke()
        self._tokens.update(token)
        return token

    def authenticate(self, plaintext: str) -> AgentToken | None:
        """
        يتحقق من رمز وارد في طلب HTTP. يُعيد None لأي سبب فشل (غير موجود، مُلغى)
        بدل رفع استثناء، لأن هذا مسار تحقق متكرر على حدود الشبكة، وليس خطأ داخليًا.
        """
        token = self._tokens.get_by_hash(hash_token(plaintext))
        if token is None or token.revoked:
            return None
        token.mark_used()
        self._tokens.update(token)
        return token

    def get_effective_scopes(self, token: AgentToken) -> frozenset[str]:
        """
        تقاطع نطاق الرمز المخزَّن مع صلاحيات الوكيل **الحالية** (وليس وقت الإصدار).
        هذا يضمن أن تقليص صلاحيات وكيل لاحقًا يُقلّص تلقائيًا الحد الأقصى الفعلي
        لكل رموزه القديمة أيضًا، دون الحاجة لإعادة إصدارها — دفاع متعدد الطبقات.
        """
        agent = self._agents.get(token.agent_id)
        return token.scopes & agent.permissions
