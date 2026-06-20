from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.knowledge_base import extract_correct_answers_file, extract_correct_qa_file


DEFAULT_SOURCE = Path(r"C:\Users\36183\Desktop\语料\E-commerce dataset\train.txt")
DEFAULT_TARGET = Path(__file__).resolve().parents[1] / "data" / "correct_answer.txt"
DEFAULT_QA_TARGET = Path(__file__).resolve().parents[1] / "data" / "correct_qa.txt"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract label=1 customer-service answers from train.txt.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--qa-target", type=Path, default=DEFAULT_QA_TARGET)
    args = parser.parse_args()

    answer_result = extract_correct_answers_file(args.source, args.target)
    qa_result = extract_correct_qa_file(args.source, args.qa_target)
    print(f"source={answer_result['source']}")
    print(f"answer_target={answer_result['target']}")
    print(f"answer_written={answer_result['written']}")
    print(f"qa_target={qa_result['target']}")
    print(f"qa_written={qa_result['written']}")


if __name__ == "__main__":
    main()
