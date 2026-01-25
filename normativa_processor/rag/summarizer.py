from __future__ import annotations

from abc import ABC, abstractmethod
import re
from collections import Counter
from typing import Any


class SummarizationStrategy(ABC):
    @abstractmethod
    def summarize(self, text: str, max_words: int, context: dict[str, Any]) -> str:
        ...


class KeywordBasedSummarizer(SummarizationStrategy):
    def summarize(self, text: str, max_words: int, context: dict[str, Any]) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
        tags = context.get("tags", [])
        keywords = set(tags)
        scored: list[tuple[float, str]] = []
        for sentence in sentences:
            if not sentence.strip():
                continue
            score = 0.0
            lowered = sentence.lower()
            score += sum(2.0 for keyword in keywords if keyword in lowered)
            score += 5.0 * len(
                re.findall(r"\bdeve|devono|è vietato|obbligatorio|non può|divieto\b", lowered)
            )
            score += 4.0 * len(re.findall(r"\bsanzione|multa|ammenda|pena\b", lowered))
            score += 1.0 * len(re.findall(r"\d{4}-\d{2}-\d{2}|\d+%", lowered))
            if sentences.index(sentence) == 0:
                score += 3.0
            scored.append((score, sentence))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = []
        words_count = 0
        for _, sentence in scored:
            sentence_words = sentence.split()
            if words_count + len(sentence_words) <= max_words:
                selected.append(sentence)
                words_count += len(sentence_words)
            else:
                remaining = max_words - words_count
                if remaining > 5:
                    selected.append(" ".join(sentence_words[:remaining]) + "...")
                break
        return " ".join(selected)


class LexRankSummarizer(SummarizationStrategy):
    def summarize(self, text: str, max_words: int, context: dict[str, Any]) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
        if len(sentences) <= 3:
            return " ".join(sentences)

        def get_word_freq(sentence: str) -> Counter[str]:
            words = re.findall(r"\b\w+\b", sentence.lower())
            return Counter(words)

        freq_vectors = [get_word_freq(s) for s in sentences]

        def cosine_sim(v1: Counter[str], v2: Counter[str]) -> float:
            intersection = set(v1.keys()) & set(v2.keys())
            if not intersection:
                return 0.0
            numerator = sum(v1[w] * v2[w] for w in intersection)
            denominator = (sum(v1[w] ** 2 for w in v1) ** 0.5) * (sum(v2[w] ** 2 for w in v2) ** 0.5)
            return numerator / denominator if denominator > 0 else 0.0

        scores = []
        for i, _ in enumerate(sentences):
            score = sum(
                cosine_sim(freq_vectors[i], freq_vectors[j])
                for j in range(len(sentences))
                if i != j
            )
            scores.append((score, sentences[i]))

        scores.sort(reverse=True)
        selected = []
        words_count = 0
        for _, sentence in scores:
            words = sentence.split()
            if words_count + len(words) <= max_words:
                selected.append(sentence)
                words_count += len(words)
            else:
                break
        return " ".join(selected)


class SummarizerFactory:
    _strategies = {
        "keyword": KeywordBasedSummarizer,
        "lexrank": LexRankSummarizer,
    }

    @classmethod
    def create(cls, strategy: str = "keyword") -> SummarizationStrategy:
        strategy_class = cls._strategies.get(strategy, KeywordBasedSummarizer)
        return strategy_class()


def summarize_advanced(
    text: str,
    citation_key: str,
    max_words: int,
    tags: list[str],
    strategy: str = "keyword",
) -> str:
    summarizer = SummarizerFactory.create(strategy)
    context = {"tags": tags, "citation_key": citation_key}
    summary = summarizer.summarize(text, max_words, context)
    tag_text = ", ".join(tags[:3])
    prefix = f"[{citation_key}]"
    if tag_text:
        prefix += f" {tag_text}:"
    return f"{prefix} {summary}".strip()
