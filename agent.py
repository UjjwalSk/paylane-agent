"""Paylane support agent: OpenAI-compatible function-calling loop over the 4 mock tools.

Runs against a local model served by Docker Model Runner (or any OpenAI-compatible
chat completions endpoint) — no API key needed. Configure via env vars:
  MODEL_BASE_URL (default http://localhost:12434/engines/v1)
  MODEL_NAME     (default ai/qwen2.5:latest)
"""

import json
import os
import re

from openai import OpenAI

import customer_api
from system_prompt import SYSTEM_PROMPT

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LAST4_RE = re.compile(r"(?<!\$)\b\d{4}\b")

BASE_URL = os.environ.get("MODEL_BASE_URL", "http://localhost:12434/engines/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "ai/qwen2.5:latest")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_customer",
            "description": "Look up a customer by email on file.",
            "parameters": {
                "type": "object",
                "properties": {"email": {"type": "string"}},
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transaction",
            "description": "Look up a specific transaction for a customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "txn_id": {"type": "string"},
                },
                "required": ["customer_id", "txn_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "issue_refund",
            "description": "Issue a refund for a transaction. Only call when policy allows auto-approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "txn_id": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["txn_id", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Hand off this issue to a human support agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["customer_id", "summary"],
            },
        },
    },
]

TOOL_IMPLS = {
    "get_transaction": customer_api.get_transaction,
    "issue_refund": customer_api.issue_refund,
    "escalate_to_human": customer_api.escalate_to_human,
}

MAX_TOOL_HOPS = 6  # backstop against a runaway tool-call loop


def _last_stated_4digits(user_texts: list[str]) -> str | None:
    """Pull the most recent standalone 4-digit sequence the customer has typed.

    Found via eval: the small local model is unreliable at comparing two 4-digit
    strings for equality itself (it flips between "verified"/"doesn't match" on
    identical digits depending on phrasing). So verification math is done here in
    code — the model is only ever shown the resulting bool, never asked to compare
    digits. See eval_runner.py / README for the before/after.
    """
    matches = [m for text in user_texts for m in LAST4_RE.findall(text)]
    return matches[-1] if matches else None


class Agent:
    """One conversation's worth of state: message history + tool call log."""

    def __init__(self, client: OpenAI | None = None):
        self.client = client or OpenAI(base_url=BASE_URL, api_key="not-needed")
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.tool_calls: list[dict] = []  # [{name, args, result}] across the whole conversation

    def _get_customer_verified(self, email: str) -> dict:
        """get_customer, but with identity verification computed in code, not by the LLM.

        Returns only {id, name, status, verified} — card_last4 and the raw email
        are never sent back to the model, which also satisfies the "never reveal
        card digits or email" policy by construction.
        """
        raw = customer_api.get_customer(email)
        if "error" in raw:
            return raw
        user_texts = [m["content"] for m in self.messages if m.get("role") == "user" and m.get("content")]
        stated = _last_stated_4digits(user_texts)
        verified = stated is not None and stated == raw["card_last4"]
        return {"id": raw["id"], "name": raw["name"], "status": raw["status"], "verified": verified}

    def send(self, user_message: str) -> str:
        """Send one customer message, run any tool calls to completion, return the agent's reply text."""
        self.messages.append({"role": "user", "content": user_message})

        for _ in range(MAX_TOOL_HOPS):
            resp = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=self.messages,
                tools=TOOLS,
                temperature=0,
            )
            msg = resp.choices[0].message
            self.messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                return msg.content or ""

            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments)
                if tc.function.name == "get_customer":
                    result = self._get_customer_verified(**args)
                else:
                    impl = TOOL_IMPLS[tc.function.name]
                    result = impl(**args)
                self.tool_calls.append({"name": tc.function.name, "args": args, "result": result})
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                })

        return "(agent stopped: too many tool calls in one turn)"
