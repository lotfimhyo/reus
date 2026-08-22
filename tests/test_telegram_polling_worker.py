# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from infrastructure.telegram_polling_worker import TelegramPollingWorker


class FakeTelegramClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_message(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))

    def get_updates(self, offset=None, timeout=25):
        return []


class FakeTelegramService:
    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.handled: list[tuple[str, str]] = []
        self.delivery_callback = None

    def set_delivery_callback(self, callback) -> None:
        self.delivery_callback = callback

    def handle_incoming_message(self, chat_id: str, text: str) -> str:
        self.handled.append((chat_id, text))
        return self.reply


def test_start_registers_delivery_callback():
    client = FakeTelegramClient()
    service = FakeTelegramService()
    worker = TelegramPollingWorker(client=client, service=service)

    worker.start()
    try:
        assert service.delivery_callback is not None
    finally:
        worker.stop()


def test_handle_update_dispatches_text_message_and_sends_ack():
    client = FakeTelegramClient()
    service = FakeTelegramService(reply="تم الاستلام")
    worker = TelegramPollingWorker(client=client, service=service)

    update = {"update_id": 1, "message": {"chat": {"id": 99}, "text": "مرحبا"}}
    worker._handle_update(update)

    assert service.handled == [("99", "مرحبا")]
    assert client.sent == [("99", "تم الاستلام")]


def test_handle_update_ignores_non_text_updates():
    client = FakeTelegramClient()
    service = FakeTelegramService()
    worker = TelegramPollingWorker(client=client, service=service)

    worker._handle_update({"update_id": 1, "edited_message": {"chat": {"id": 1}}})
    worker._handle_update({"update_id": 2, "message": {"chat": {"id": 1}}})  # بلا "text"

    assert service.handled == []
    assert client.sent == []


def test_offset_advances_past_processed_update():
    client = FakeTelegramClient()
    service = FakeTelegramService()
    worker = TelegramPollingWorker(client=client, service=service)

    worker._handle_update({"update_id": 7, "message": {"chat": {"id": 1}, "text": "x"}})

    assert worker._offset == 8


def test_delivery_callback_forwards_to_client_send_message():
    client = FakeTelegramClient()
    service = FakeTelegramService()
    worker = TelegramPollingWorker(client=client, service=service)
    worker.start()
    try:
        service.delivery_callback("chat-1", "نتيجة نهائية")
        assert client.sent == [("chat-1", "نتيجة نهائية")]
    finally:
        worker.stop()
