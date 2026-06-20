import unittest

from fastapi.testclient import TestClient

from app.api.deps import get_customer_service
from app.main import create_app
from app.services.demo_data import build_demo_service


class RealtimeWebSocketTests(unittest.TestCase):
    def setUp(self):
        self.service = build_demo_service()
        self.app = create_app()
        self.app.dependency_overrides[get_customer_service] = lambda: self.service
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_websocket_receives_human_reply_for_conversation(self):
        chat = self.client.post(
            "/api/v1/customer-service/chat",
            json={
                "customer_id": "customer-001",
                "conversation_id": None,
                "content": "我要转人工，人工处理",
            },
        ).json()
        ticket = self.client.get("/api/v1/customer-service/admin/handoff-tickets").json()[0]
        self.client.post(f"/api/v1/customer-service/admin/handoff-tickets/{ticket['id']}/claim")

        with self.client.websocket_connect(
            f"/api/v1/customer-service/ws/conversations/{chat['conversation_id']}"
        ) as websocket:
            ready = websocket.receive_json()
            self.assertEqual(ready["event"], "connected")
            self.assertEqual(ready["conversation_id"], chat["conversation_id"])

            self.client.post(
                f"/api/v1/customer-service/admin/conversations/{chat['conversation_id']}/reply",
                json={"content": "您好，人工客服已收到您的问题。"},
            )

            event = websocket.receive_json()
            self.assertEqual(event["event"], "message")
            self.assertEqual(event["conversation_id"], chat["conversation_id"])
            self.assertEqual(event["message"]["sender_type"], "human")
            self.assertEqual(event["message"]["content"], "您好，人工客服已收到您的问题。")


if __name__ == "__main__":
    unittest.main()
