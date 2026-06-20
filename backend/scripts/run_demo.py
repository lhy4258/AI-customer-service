from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.deps import get_customer_service


def dump(title: str, payload: dict | list) -> None:
    print(f"\n## {title}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    service = get_customer_service()
    dump("initial summary", service.data_summary())

    ai_reply = service.chat("customer-001", "你好，我想咨询一下")
    dump("AI conversation answer", ai_reply)

    handoff = service.chat("customer-002", "我要转人工，人工处理")
    dump("handoff request", handoff)

    tickets = service.list_handoff_tickets()
    dump("pending tickets", tickets)

    ticket = next(item for item in tickets if item["conversation_id"] == handoff["conversation_id"])
    claimed = service.claim_ticket(ticket["id"])
    dump("claim ticket", claimed)

    human_reply = service.human_reply(
        handoff["conversation_id"],
        "您好，我已接入，会先核对您的诉求并给出处理方案。",
    )
    dump("human reply", human_reply)

    correction = service.record_correction(
        question_id="demo-question-001",
        bad_answer="错误答案示例",
        fixed_answer="正确答案应围绕客户当前诉求回答。",
        reason="answer_quality",
    )
    dump("correction", correction)

    closed = service.close_by_human_support(handoff["conversation_id"], "resolved")
    dump("human close", closed)


if __name__ == "__main__":
    main()
