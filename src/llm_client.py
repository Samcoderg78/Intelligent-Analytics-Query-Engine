"""
Thin wrapper around the Gemini API (Google AI Studio).

This project uses GenAI in two places:
  1. intent_parser.py asks the model to turn a natural language question
     into the structured intent JSON the rest of the pipeline runs on.
  2. explain.py asks the model to turn that same structured intent + the
     result into a short, readable explanation.

Both call points go through ask_json() / ask_text() below so there is one
place that knows how to talk to the API, and one place that decides what
to do when the API isn't available (no key, no network, rate limit, bad
response, etc). Everything upstream just gets a Python value back either
way - it doesn't need to know whether that value came from the model or
from the rule-based fallback.

Uses Gemini's free tier (no billing required) via Google AI Studio.
Get a key at https://aistudio.google.com -> "Get API key", then:
    export GEMINI_API_KEY="AIza..."
"""

import json
import os

import requests

MODEL = "gemini-3.6-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def is_available():
    return bool(os.environ.get("GEMINI_API_KEY"))


def _call(system_prompt, user_prompt, json_mode, max_tokens):
    api_key = os.environ.get("GEMINI_API_KEY")
    body = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            # this task is simple pattern extraction, not multi-step reasoning,
            # so thinking is switched off - otherwise thinking tokens are billed
            # against the same maxOutputTokens budget and can silently crowd out
            # the actual answer
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    response = requests.post(
        API_URL,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def ask_json(system_prompt, user_prompt, max_tokens=500):
    """Sends a prompt, expects a JSON object back. Returns None on any
    failure so the caller can fall back to the rule-based path instead of
    crashing the whole run over one flaky query."""
    if not is_available():
        return None
    try:
        text = _call(system_prompt, user_prompt, json_mode=True, max_tokens=max_tokens).strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception:
        return None


def ask_text(system_prompt, user_prompt, max_tokens=300):
    if not is_available():
        return None
    try:
        return _call(system_prompt, user_prompt, json_mode=False, max_tokens=max_tokens).strip()
    except Exception:
        return None