import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from support_ai.tools.kb_search import search


def test_kb_articles_load_and_search():
    articles, matched_ids = search("billing", "I was charged twice")
    assert articles
    assert matched_ids
    assert all(a.category == "billing" for a in articles)


def test_tickets_dataset_has_five_tickets():
    tickets_path = Path(__file__).resolve().parents[1] / "data" / "tickets.json"
    tickets = json.loads(tickets_path.read_text())
    assert len(tickets) == 5
    assert {t["id"] for t in tickets} == {
        "TCK-001", "TCK-002", "TCK-003", "TCK-004", "TCK-005",
    }
