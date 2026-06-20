import unittest
from datetime import datetime, timedelta, timezone

from app.services.customer_service import CustomerServiceFacade
from app.services.demo_data import build_demo_service
from app.services.entities import ConversationStatus


class CustomerServiceCoreTests(unittest.TestCase):
    def setUp(self):
        self.service = build_demo_service()

    def test_demo_data_has_only_conversation_storage(self):
        summary = self.service.data_summary()

        self.assertEqual(
            summary,
            {
                "conversations": 0,
                "handoff_tickets": 0,
                "corrections": 0,
                "ai_call_logs": 0,
            },
        )
        self.assertNotIn("products", summary)
        self.assertNotIn("orders", summary)
        self.assertNotIn("policies", summary)
        self.assertNotIn("knowledge_chunks", summary)

    def test_chat_requires_retrieved_context_without_catalog_lookup(self):
        response = self.service.chat(
            customer_id="customer-001",
            content="SKU-0001 适合什么人，订单什么时候发货？",
        )

        self.assertEqual(response["status"], ConversationStatus.AI_ACTIVE.value)
        self.assertFalse(response["handoff_requested"])
        self.assertTrue(response["handoff_suggested"])
        self.assertEqual(response["confidence"], 0.0)
        self.assertEqual(response["citations"], [])
        self.assertEqual(response["chunks"], [])
        self.assertIn("资料中没有找到依据", response["answer"])
        self.assertNotIn("SKU-0001 属于", response["answer"])
        self.assertEqual(self.service.data_summary()["ai_call_logs"], 1)

    def test_chat_returns_clarification_for_short_contextless_question(self):
        self.service.ingest_training_corpus(
            "train-sample.txt",
            "1\t这件商品什么时候发货\t亲亲 这件商品会尽快安排发货\n",
        )

        response = self.service.chat(
            customer_id="customer-001",
            content="这个呢？",
        )

        self.assertTrue(response["answer"].startswith("我需要再确认一下"))
        self.assertFalse(response["handoff_suggested"])
        self.assertEqual(response["confidence"], 0.0)
        self.assertEqual(response["chunks"], [])
        self.assertEqual(self.service.data_summary()["ai_call_logs"], 1)
        ai_message = self.service.repository.list_messages(response["conversation_id"])[-1]
        self.assertEqual(ai_message.metadata["retrieval"]["clarification"]["action"], "clarify")

    def test_chat_rewrites_contextual_question_before_retrieval(self):
        self.service.ingest_training_corpus(
            "train-sample.txt",
            "1\t这件商品什么时候发货\t亲亲 这件商品会尽快安排发货\n",
        )

        first = self.service.chat(
            customer_id="customer-001",
            content="我想问这件商品什么时候发货",
        )
        response = self.service.chat(
            customer_id="customer-001",
            conversation_id=first["conversation_id"],
            content="那这个呢？",
        )

        self.assertIn("发货", response["answer"])
        ai_message = self.service.repository.list_messages(response["conversation_id"])[-1]
        retrieval = ai_message.metadata["retrieval"]
        self.assertEqual(retrieval["contextualization"]["action"], "rewrite")
        self.assertIn("这件商品什么时候发货", retrieval["contextualization"]["rewritten_query"])
        self.assertEqual(retrieval["contextualization"]["recent_messages_count"], 2)
        self.assertIn("那这个呢？", retrieval["contextualization"]["original_query"])
        self.assertGreater(len(retrieval["hits"]), 0)

    def test_explicit_handoff_creates_ticket_and_stops_ai_answer(self):
        response = self.service.chat(
            customer_id="customer-002",
            content="我要转人工，投诉人工处理",
        )

        self.assertTrue(response["handoff_requested"])
        self.assertEqual(response["status"], ConversationStatus.HANDOFF_REQUESTED.value)
        self.assertEqual(response["answer"], "已为你转接人工客服，请稍候。")

        tickets = self.service.list_handoff_tickets()
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]["conversation_id"], response["conversation_id"])

    def test_generic_chat_does_not_create_ticket_without_handoff_intent(self):
        response = self.service.chat(
            customer_id="customer-003",
            content="请告诉我今天黄金期货和火星天气的关系",
        )

        self.assertFalse(response["handoff_requested"])
        self.assertFalse(response["handoff_suggested"])
        self.assertEqual(response["status"], ConversationStatus.AI_ACTIVE.value)
        self.assertEqual(self.service.list_handoff_tickets(), [])
        self.assertIn("我需要再确认一下", response["answer"])

    def test_human_support_backend_claims_replies_and_closes(self):
        handoff = self.service.chat(
            customer_id="customer-004",
            content="找客服，我要人工处理",
        )
        ticket = self.service.list_handoff_tickets()[0]

        claimed = self.service.claim_ticket(ticket["id"])
        self.assertEqual(claimed["status"], "claimed")
        self.assertEqual(
            set(claimed),
            {"id", "conversation_id", "status", "requested_reason", "requested_at", "accepted_at", "closed_at"},
        )

        reply = self.service.human_reply(
            conversation_id=handoff["conversation_id"],
            content="您好，我已经看到您的诉求，会继续协助处理。",
        )
        self.assertEqual(reply["sender_type"], "human")
        self.assertEqual(reply["sender_id"], "human-support")

        closed = self.service.close_by_human_support(
            conversation_id=handoff["conversation_id"],
            reason="resolved",
        )
        self.assertEqual(closed["status"], ConversationStatus.HUMAN_CLOSED.value)
        conversation = self.service.get_conversation(handoff["conversation_id"])
        self.assertEqual(conversation["close_reason"], "resolved")

    def test_idle_close_only_closes_ai_active_conversations(self):
        ai_response = self.service.chat(
            customer_id="customer-005",
            content="你好，我想咨询一下",
        )
        handoff_response = self.service.chat(
            customer_id="customer-006",
            content="转人工",
        )

        old = datetime.now(timezone.utc) - timedelta(seconds=70)
        self.service.repository.force_last_message_at(ai_response["conversation_id"], old)
        self.service.repository.force_last_message_at(handoff_response["conversation_id"], old)

        result = self.service.auto_close_idle_ai_sessions(datetime.now(timezone.utc))

        self.assertEqual(result["closed"], [ai_response["conversation_id"]])
        ai_conversation = self.service.get_conversation(ai_response["conversation_id"])
        handoff_conversation = self.service.get_conversation(handoff_response["conversation_id"])
        self.assertEqual(ai_conversation["status"], ConversationStatus.AUTO_CLOSED.value)
        self.assertEqual(handoff_conversation["status"], ConversationStatus.HANDOFF_REQUESTED.value)


class EmptyServiceTests(unittest.TestCase):
    def test_empty_service_can_be_constructed_for_api_injection(self):
        service = CustomerServiceFacade.empty()

        self.assertEqual(service.data_summary()["conversations"], 0)


if __name__ == "__main__":
    unittest.main()
