"""Run all 12 scripted conversations against the live agent, save transcripts + tool call logs.

Usage: python run_conversations.py
Requires GEMINI_API_KEY in the environment.
"""

import json
import os

from agent import Agent
from conversations import CONVERSATIONS

OUT_DIR = "transcripts"


def run_all() -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}

    for name, convo in CONVERSATIONS.items():
        agent = Agent()
        lines = [f"# {name}", f"# {convo['description']}", ""]

        for msg in convo["messages"]:
            reply = agent.send(msg)
            lines.append(f"CUSTOMER: {msg}")
            lines.append(f"AGENT: {reply}")
            lines.append("")

        transcript = "\n".join(lines)
        with open(os.path.join(OUT_DIR, f"{name}.txt"), "w") as f:
            f.write(transcript)

        results[name] = {
            "description": convo["description"],
            "tool_calls": agent.tool_calls,
        }
        print(f"ran {name}: {len(agent.tool_calls)} tool call(s)")

    with open("results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    return results


if __name__ == "__main__":
    run_all()
    print(f"\nDone. Transcripts in {OUT_DIR}/, tool-call log in results.json")
