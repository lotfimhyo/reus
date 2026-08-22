# Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink
from api.schemas_chat import ChatResponse


def test_chat_response_preserves_actual_sources_only():
    response = ChatResponse.from_executor_result({"response": "إجابة", "sources": ["memory:evidence-7", "https://example.org/source", {"ignored": True}]})
    assert response.sources == ["memory:evidence-7", "https://example.org/source"]


def test_chat_response_does_not_invent_sources_for_plain_text():
    assert ChatResponse.from_executor_result("إجابة بسيطة").sources == []
