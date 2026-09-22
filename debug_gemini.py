"""
Tests the explanation call (ask_text equivalent) specifically, since the
JSON intent-parsing call has already been confirmed working separately.

Run with:
    python debug_gemini_explain.py
"""

import os
import json
import requests

api_key = os.environ.get("GEMINI_API_KEY")
MODEL = "gemini-3.6-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

SYSTEM_PROMPT = """You write a two sentence explanation of how an analytics
question was answered. First sentence: what the question was asking for, in plain
words. Second sentence: what calculation produced the result. Be specific about
which fields/filters were used. No preamble, no markdown, just the two sentences."""

USER_PROMPT = (
    "Question: Total sales in India for March\n"
    "Parsed as: {'metric': 'revenue', 'filters': {'country': 'India', 'month': '2024-03'}}\n"
    "SQL executed: SELECT SUM(revenue) AS revenue FROM sales_v WHERE country = 'India' AND month = '2024-03';\n"
    "Result: 108.0"
)

body = {
    "contents": [{"role": "user", "parts": [{"text": USER_PROMPT}]}],
    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
    "generationConfig": {
        "maxOutputTokens": 300,
        "thinkingConfig": {"thinkingBudget": 0},
    },
}

response = requests.post(
    API_URL,
    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
    json=body,
    timeout=30,
)

print("HTTP status:", response.status_code)
print("\nFull raw response body:")
print(json.dumps(response.json(), indent=2))

print("\n--- Attempting extraction the same way llm_client.py does ---")
data = response.json()
try:
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    print("Extracted text:", repr(text))
except Exception as e:
    print("FAILED to extract:", type(e).__name__, e)