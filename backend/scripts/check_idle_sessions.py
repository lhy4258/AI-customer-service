from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.deps import get_customer_service


def main() -> None:
    service = get_customer_service()
    response = service.chat("customer-009", "你好，我想咨询一下")
    service.repository.force_last_message_at(
        response["conversation_id"],
        datetime.now(timezone.utc) - timedelta(seconds=70),
    )
    result = service.auto_close_idle_ai_sessions(datetime.now(timezone.utc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
