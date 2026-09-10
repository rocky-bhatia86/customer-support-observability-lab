#!/usr/bin/env python3
"""One-time (or re-run-anytime) seed: pushes the quality checker's v1/v2
system prompts into Langfuse Prompt Management, so the "last week's
prompt bump" (Failure D) is a real, inspectable prompt version history
in the Langfuse UI instead of two Python string constants.

Safe to re-run -- each run creates a new version under the same labels;
QualityCheckerAgent always fetches by label, so it picks up whichever
version currently holds that label.

Usage:
    python scripts/seed_prompts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()

from langfuse import Langfuse

PROMPT_NAME = "quality_checker_system_prompt"

_V1_TEXT = (
    "You are a quality reviewer for customer support responses. Given the "
    "customer ticket, the supporting information gathered for it, and a "
    "draft reply, decide whether the draft is good enough to send.\n\n"
    "Accept the draft if it: is relevant to the ticket, is grounded in the "
    "provided information (no invented policy or invented data), and "
    "reasonably addresses the customer's main question, even if some minor "
    "detail is phrased generally rather than with an exact number.\n\n"
    "Respond ONLY with JSON: {\"verdict\": \"ACCEPT\" or "
    "\"REJECT_AND_RETRIEVE\", \"reason\": \"short reason\"}."
)

_V2_TEXT = (
    "You are a strict quality reviewer for customer support responses. "
    "Given the customer ticket, the supporting information gathered for it, "
    "and a draft reply, decide whether the draft is good enough to send.\n\n"
    "Apply a strict standard. REJECT_AND_RETRIEVE unless ALL of the "
    "following hold:\n"
    "1. The draft addresses every distinct question or issue raised in the "
    "ticket, with no part left unanswered.\n"
    "2. Whenever the customer asks for an exact number, date, or timeframe, "
    "the draft provides that exact figure. A vague phrase like 'a few "
    "business days' does NOT satisfy a request for an exact number and "
    "must be rejected.\n"
    "3. The draft explicitly references which source (KB article id, "
    "account record, or incident id) supports each claim.\n\n"
    "Respond ONLY with JSON: {\"verdict\": \"ACCEPT\" or "
    "\"REJECT_AND_RETRIEVE\", \"reason\": \"short reason\"}."
)


def main():
    lf = Langfuse()

    v1 = lf.create_prompt(name=PROMPT_NAME, prompt=_V1_TEXT, labels=["v1"], type="text")
    print(f"Seeded '{PROMPT_NAME}' version {v1.version} with label 'v1'")

    v2 = lf.create_prompt(name=PROMPT_NAME, prompt=_V2_TEXT, labels=["v2"], type="text")
    print(f"Seeded '{PROMPT_NAME}' version {v2.version} with label 'v2'")

    lf.flush()
    print(f"\nView/edit these at {lf.base_url if hasattr(lf, 'base_url') else 'your Langfuse project'} under Prompts.")


if __name__ == "__main__":
    main()
