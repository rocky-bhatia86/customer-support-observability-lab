from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Category = Literal["billing", "bug", "how-to"]
Verdict = Literal["ACCEPT", "REJECT_AND_RETRIEVE"]
Status = Literal["RESOLVED", "ESCALATED_MAX_ITERATIONS"]


@dataclass
class Ticket:
    id: str
    text: str


@dataclass
class KBArticle:
    id: str
    category: str
    title: str
    content: str


@dataclass
class RetrievalResult:
    query: str
    category: str
    articles: list[KBArticle]
    matched_ids: list[str]
    error: str | None = None
    retried: bool = False


@dataclass
class DraftResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


@dataclass
class CheckerVerdict:
    verdict: Verdict
    reason: str
    prompt_tokens: int
    completion_tokens: int


@dataclass
class WorkflowStep:
    iteration: int
    agent: str
    action: str
    detail: str
    elapsed_seconds: float
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class WorkflowResult:
    ticket_id: str
    category: str
    status: Status
    final_response: str
    iterations: int
    elapsed_seconds: float
    steps: list[WorkflowStep] = field(default_factory=list)

    @property
    def total_prompt_tokens(self) -> int:
        return sum(s.prompt_tokens for s in self.steps)

    @property
    def total_completion_tokens(self) -> int:
        return sum(s.completion_tokens for s in self.steps)
