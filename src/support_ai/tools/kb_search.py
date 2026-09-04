"""Deterministic, embedding-free knowledge base search.

Category filter + keyword-overlap scoring only. No vector DB, no randomness,
so behavior is fully reproducible across runs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from support_ai.models import KBArticle

_KB_PATH = Path(__file__).resolve().parents[3] / "kb" / "articles.json"

_STOPWORDS = {
    "a", "an", "the", "is", "was", "were", "i", "my", "me", "to", "for",
    "of", "on", "in", "and", "or", "it", "this", "that", "how", "do", "does",
}


class KBSearchError(Exception):
    pass


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def load_articles() -> list[KBArticle]:
    raw = json.loads(_KB_PATH.read_text())
    return [KBArticle(**item) for item in raw]


def search(category: str, query: str, top_k: int = 3) -> tuple[list[KBArticle], list[str]]:
    """Returns (matched_articles, matched_ids), ranked by keyword overlap.

    Falls back to all articles in the category (unranked) if no keyword
    overlap is found, so callers always get *some* candidates to work with.
    """
    articles = load_articles()
    query_tokens = _tokenize(query)

    candidates = [a for a in articles if a.category == category]
    if not candidates:
        candidates = articles

    scored = []
    for article in candidates:
        article_tokens = _tokenize(article.title + " " + article.content)
        overlap = len(query_tokens & article_tokens)
        scored.append((overlap, article))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    if scored and scored[0][0] == 0:
        top = candidates[:top_k]
    else:
        top = [article for _, article in scored[:top_k]]

    return top, [a.id for a in top]
