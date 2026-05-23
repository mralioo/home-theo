"""
Triage agent — embodies the dispatcher persona (Persona 2).
Job: turn unstructured raw_text into a structured Diagnosis.

Runs in two modes:
  * LLM mode (USE_LLM=1): uses an ADK LlmAgent for nuanced classification.
  * Fallback mode (default): keyword heuristics, zero external calls. This
    guarantees the demo runs even with no API key / no network.
"""
from __future__ import annotations

import os

from app.core.schemas import Diagnosis, IssueCategory, Sentiment, Urgency

_KEYWORDS = {
    IssueCategory.heating: ["heat", "heizung", "warm", "boiler", "radiator", "cold"],
    IssueCategory.plumbing: ["water", "leak", "wasser", "toilet", "pipe", "flood", "drain"],
    IssueCategory.electrical: ["power", "strom", "light", "electric", "outlet", "fuse"],
    IssueCategory.elevator: ["elevator", "lift", "aufzug"],
    IssueCategory.access_keys: ["key", "schlüssel", "lock", "locked", "access", "door"],
    IssueCategory.cleaning: ["clean", "dirty", "staircase", "treppenhaus", "garbage", "trash"],
    IssueCategory.financial: ["invoice", "cost", "rechnung", "pay", "bill", "charge"],
    IssueCategory.legal: ["legal", "lawyer", "contract", "vertrag", "sue", "rights"],
}

_EMERGENCY = ["fire", "feuer", "flood", "flooding", "no heat", "burst", "gas", "smoke"]
_ANGRY = ["unacceptable", "ridiculous", "angry", "furious", "third time", "again", "!!!"]


def _classify_category(text: str) -> IssueCategory:
    t = text.lower()
    best, score = IssueCategory.other, 0
    for cat, words in _KEYWORDS.items():
        hits = sum(1 for w in words if w in t)
        if hits > score:
            best, score = cat, hits
    return best


def _classify_urgency(text: str, category: IssueCategory) -> Urgency:
    t = text.lower()
    if any(w in t for w in _EMERGENCY):
        return Urgency.emergency
    if category in (IssueCategory.heating, IssueCategory.elevator):
        return Urgency.high
    if category in (IssueCategory.plumbing, IssueCategory.electrical):
        return Urgency.high
    return Urgency.normal


def _classify_sentiment(text: str) -> Sentiment:
    t = text.lower()
    if any(w in t for w in _ANGRY):
        return Sentiment.angry
    if "please" in t or "thank" in t:
        return Sentiment.calm
    return Sentiment.neutral


def triage_fallback(raw_text: str, hint_sentiment: Sentiment | None) -> Diagnosis:
    category = _classify_category(raw_text)
    urgency = _classify_urgency(raw_text, category)
    sentiment = hint_sentiment or _classify_sentiment(raw_text)
    summary = raw_text.strip()[:140]
    return Diagnosis(
        category=category,
        urgency=urgency,
        sentiment=sentiment,
        summary=summary,
        confidence=0.6,
    )


def triage(raw_text: str, hint_sentiment: Sentiment | None = None) -> Diagnosis:
    if os.environ.get("USE_LLM") == "1":
        try:
            from app.agents.llm_triage import triage_llm  # lazy import
            return triage_llm(raw_text, hint_sentiment)
        except Exception as exc:  # never let the demo die on a model error
            print(f"[triage] LLM failed, using fallback: {exc}")
    return triage_fallback(raw_text, hint_sentiment)
