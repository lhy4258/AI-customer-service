from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROMPT_ATTACK_TERMS = (
    "忽略以上",
    "忽略之前",
    "忽略规则",
    "系统提示词",
    "system prompt",
    "developer message",
    "越狱",
    "jailbreak",
)


@dataclass(frozen=True)
class TrainingKnowledgeItem:
    label: str
    question_text: str
    answer_text: str
    retrieval_text: str


@dataclass(frozen=True)
class KnowledgeSearchHit:
    id: str
    question_text: str
    answer_text: str
    retrieval_text: str
    chunk_text: str
    dense_score: float
    sparse_score: float
    score: float
    metadata: dict[str, Any]


def build_retrieval_text(question_text: str, answer_text: str) -> str:
    return "\n".join(part for part in (question_text, answer_text) if part)


def parse_training_line(line: str) -> TrainingKnowledgeItem | None:
    columns = [column.strip() for column in line.rstrip("\n").split("\t")]
    if len(columns) < 3:
        return None
    label = columns[0]
    if label not in {"0", "1"}:
        return None
    case_text = "\n".join(column for column in columns[1:] if column)
    if not case_text:
        return None
    return TrainingKnowledgeItem(
        label=label,
        question_text="",
        answer_text="",
        retrieval_text=case_text,
    )


def parse_correct_qa_line(line: str) -> TrainingKnowledgeItem | None:
    columns = [column.strip() for column in line.rstrip("\n").split("\t")]
    if len(columns) != 2:
        return None
    context_text, reply_text = columns
    case_text = build_retrieval_text(context_text, reply_text)
    if not case_text:
        return None
    if context_text.lower() in {"question", "question_text", "问题"}:
        return None
    return TrainingKnowledgeItem(
        label="1",
        question_text="",
        answer_text="",
        retrieval_text=case_text,
    )


def build_training_knowledge_items(text: str) -> list[TrainingKnowledgeItem]:
    items: list[TrainingKnowledgeItem] = []
    for line in text.splitlines():
        item = parse_training_line(line)
        if item and item.label == "1":
            items.append(item)
    return items


def build_correct_qa_items(text: str) -> list[TrainingKnowledgeItem]:
    items: list[TrainingKnowledgeItem] = []
    for line in text.splitlines():
        item = parse_correct_qa_line(line)
        if item:
            items.append(item)
    return items


def extract_correct_answers(text: str) -> list[str]:
    answers = []
    for line in text.splitlines():
        columns = [column.strip() for column in line.rstrip("\n").split("\t")]
        if len(columns) >= 3 and columns[0] == "1" and columns[-1]:
            answers.append(columns[-1])
    return answers


def extract_correct_answers_file(source_path: str | Path, target_path: str | Path) -> dict[str, int | str]:
    source = Path(source_path)
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with source.open("r", encoding="utf-8") as source_file, target.open("w", encoding="utf-8", newline="\n") as target_file:
        for line in source_file:
            item = parse_training_line(line)
            if not item or item.label != "1":
                continue
            columns = [column.strip() for column in line.rstrip("\n").split("\t")]
            target_file.write(f"{columns[-1]}\n")
            written += 1

    return {"source": str(source), "target": str(target), "written": written}


def single_line_field(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\t", " ")).strip()


def extract_correct_qa_file(source_path: str | Path, target_path: str | Path) -> dict[str, int | str]:
    source = Path(source_path)
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with source.open("r", encoding="utf-8") as source_file, target.open("w", encoding="utf-8", newline="\n") as target_file:
        for line in source_file:
            item = parse_training_line(line)
            if not item or item.label != "1":
                continue
            columns = [column.strip() for column in line.rstrip("\n").split("\t")]
            context_text = single_line_field(" ".join(column for column in columns[1:-1] if column))
            reply_text = single_line_field(columns[-1])
            target_file.write(f"{context_text}\t{reply_text}\n")
            written += 1

    return {"source": str(source), "target": str(target), "written": written}


def build_upload_items(text: str) -> list[TrainingKnowledgeItem]:
    training_items = build_training_knowledge_items(text)
    if training_items:
        return training_items
    correct_qa_items = build_correct_qa_items(text)
    if correct_qa_items:
        return correct_qa_items

    items: list[TrainingKnowledgeItem] = []
    for index, chunk in enumerate(split_plain_text(text), start=1):
        items.append(
            TrainingKnowledgeItem(
                label="1",
                question_text="",
                answer_text="",
                retrieval_text=chunk,
            )
        )
    return items


def split_plain_text(text: str, max_chars: int = 700) -> list[str]:
    chunks: list[str] = []
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if len(current) + len(line) + 1 > max_chars and current:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}".strip() if current else line
    if current:
        chunks.append(current)
    return chunks


def content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def knowledge_sparse_text(item: TrainingKnowledgeItem) -> str:
    return item.retrieval_text


def normalize_text(text: str) -> str:
    normalized = text.lower()
    replacements = {
        "两": "二",
        "便宜": "少点 优惠",
        "能不能": "有没有 可以",
        "可以不": "可以",
        "发货": "发货 物流",
        "快递": "快递 物流",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


def sparse_vector(text: str) -> dict[str, float]:
    tokens = tokenize(text)
    if not tokens:
        return {}
    counts: dict[str, float] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0.0) + 1.0
    total = float(len(tokens))
    return {token: count / total for token, count in counts.items()}


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    tokens: list[str] = []
    tokens.extend(re.findall(r"[a-z0-9]+", normalized))
    tokens.extend(re.findall(r"[\u4e00-\u9fff]+", normalized))
    for part in re.split(r"\s+", normalized):
        part = part.strip("，。！？,.!?;；:：()（）[]【】\"'")
        if part:
            tokens.append(part)
    for char in normalized:
        if "\u4e00" <= char <= "\u9fff":
            tokens.append(char)
    return tokens


def lexical_search_text(text: str) -> str:
    return " ".join(tokenize(text))


def sparse_similarity(query: str, sparse: dict[str, float], fallback_text: str = "") -> float:
    query_sparse = sparse_vector(query)
    if not query_sparse:
        return 0.0
    if not sparse and fallback_text:
        sparse = sparse_vector(fallback_text)
    if not sparse:
        return 0.0
    query_terms = set(query_sparse)
    doc_terms = set(sparse)
    overlap = query_terms & doc_terms
    if not overlap:
        return 0.0
    weighted_overlap = sum(min(query_sparse[term], sparse[term]) for term in overlap)
    jaccard = len(overlap) / len(query_terms | doc_terms)
    return min(1.0, weighted_overlap * 4.0 + jaccard)


def dense_similarity(query: str, text: str) -> float:
    query_tokens = set(tokenize(query))
    text_tokens = set(tokenize(text))
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = query_tokens & text_tokens
    return len(overlap) / math.sqrt(len(query_tokens) * len(text_tokens))


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if left is None or right is None or len(left) == 0 or len(right) == 0 or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    cosine = sum(left_value * right_value for left_value, right_value in zip(left, right)) / (left_norm * right_norm)
    return max(0.0, min(1.0, cosine))


def hybrid_score(
    query: str,
    text: str,
    sparse: dict[str, float],
    dense_weight: float,
    sparse_weight: float,
    query_embedding: list[float] | None = None,
    dense_embedding: list[float] | None = None,
) -> tuple[float, float, float]:
    dense = (
        cosine_similarity(query_embedding, dense_embedding)
        if query_embedding is not None and dense_embedding is not None
        else dense_similarity(query, text)
    )
    sparse_score = sparse_similarity(query, sparse, fallback_text=text)
    return (dense * dense_weight) + (sparse_score * sparse_weight), dense, sparse_score


def has_prompt_attack(text: str) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in PROMPT_ATTACK_TERMS)
