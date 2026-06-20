from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.deps import get_customer_service


def main() -> None:
    service = get_customer_service()
    print(json.dumps(service.data_summary(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
