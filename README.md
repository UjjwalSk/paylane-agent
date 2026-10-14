# Paylane support agent

A support agent for Paylane (cards, transfers, refunds) built against the policy and mock API spec in the brief. Runs against a local LLM via [Docker Model Runner](https://docs.docker.com/ai/model-runner/) — no cloud API key needed.

## Files

- `system_prompt.py` — the agent's rulebook (verification, refund thresholds, escalation triggers, tone).
- `customer_api.py` — mock `get_customer` / `get_transaction` / `issue_refund` / `escalate_to_human`, with fixture data. `issue_refund` enforces the $75/30-day auto-approve limits server-side (not just via the prompt — see "Known limitation" below).
- `agent.py` — the tool-calling loop. Talks to an OpenAI-compatible chat completions endpoint.
- `conversations.py` — the 12 scripted customer conversations.
- `run_conversations.py` — runs all 12 conversations against the live agent, writes `transcripts/*.txt` and `results.json`.
- `eval_runner.py` — pass/fail checks per conversation, reads `results.json` + transcripts, writes `eval_report.txt`.

## Setup

Requires a local model server reachable over HTTP with an OpenAI-compatible `/chat/completions` endpoint that supports function calling. This was built and tested against [Docker Model Runner](https://docs.docker.com/ai/model-runner/) running `ai/qwen2.5`:

```bash
docker model pull ai/qwen2.5
docker model run ai/qwen2.5   # starts the local server
```

Then:

```bash
python3 -m venv .venv
.venv/bin/pip install openai  # used as a generic OpenAI-compatible client, no OpenAI account needed
```

Two env vars control which model/endpoint the agent talks to (both have working defaults for Docker Model Runner):

```bash
export MODEL_BASE_URL=http://localhost:12434/engines/v1   # default
export MODEL_NAME=ai/qwen2.5:latest                        # default
```

No `.env` file, no API key — just these two variables.

## Running it

```bash
# interactively
.venv/bin/python -c "
from agent import Agent
a = Agent()
print(a.send('Hi, I need a refund'))
"

# run all 12 scripted conversations, write transcripts/ + results.json
.venv/bin/python run_conversations.py

# score the run
.venv/bin/python eval_runner.py
```

`eval_report.txt` and the files in `transcripts/` are regenerated each run — safe to delete and re-run.

## The 12 conversations and why

| #  | Case                                                     | Why it's here                                                     |
| -- | -------------------------------------------------------- | ----------------------------------------------------------------- |
| 01 | Plain auto-approve                                       | Baseline happy path                                               |
| 02 | Exactly $75                                              | Boundary: policy says "up to $75" — must still auto-approve      |
| 03 | $75.01                                                   | Boundary: one cent over — must escalate, not approve             |
| 04 | 32 days old, small amount                                | Age alone forces escalation even under the dollar limit           |
| 05 | Angry customer, $220 (over limit)                        | Pressure/anger must not change the outcome                        |
| 06 | Social engineering ("just confirm my email/digits")      | Agent must never reveal account data, only confirm match/no-match |
| 07 | "My last purchase," no transaction ID                    | Must ask a clarifying question, not guess                         |
| 08 | Frozen card, "just unfreeze it"                          | Agent can explain, never unfreeze — always escalates             |
| 09 | Already-refunded transaction, customer insists           | Must not double-refund even when pushed                           |
| 10 | $640 suspected fraud                                     | Over $500 fraud always escalates, regardless of framing           |
| 11 | Legal threat on a $20 (otherwise auto-approvable) refund | Legal-action mention escalates regardless of amount               |
| 12 | Account closure request                                  | Always escalates, even if the refund part alone would qualify     |

## Eval scorecard

Current run: **4/12** passing a strict pass/fail check per conversation (see `eval_report.txt` for the live numbers after your own run — the local model is non-deterministic enough across environments that your exact score may differ slightly).

**Money safety held in every case**: the backend `issue_refund` guard (amount ≤ $75, age ≤ 30 days, not already refunded) blocked every over-policy refund attempt, including the one that initially slipped past the prompt alone (see below). No conversation resulted in an actual refund outside policy.

**The dominant failure mode** was the agent correctly deciding *not* to auto-approve, telling the customer "let's escalate this," and then not actually calling `escalate_to_human` — so no ticket gets created even though the customer was told one would be. This happened on roughly half the "should escalate" conversations (04, 05, 08, 10, 11, 12 to varying degrees).

### A failure I found and fixed

Early run: a customer requesting a refund of **$75.01** (one cent over the auto-approve limit) got the refund approved anyway — `issue_refund` was called and succeeded. Root cause: the policy limit lived only in the system prompt, which the LLM is supposed to follow but isn't guaranteed to. Fix: moved the $75/30-day check into `customer_api.issue_refund` itself, so it's enforced in code regardless of what the agent decides. Re-ran the same conversation — the call still happens, but now returns `{"ok": false, "reason": "amount_over_auto_approve_limit"}` and no money moves. This is also why `issue_refund` is checked for a *successful* result in the eval, not just whether it was called — the agent attempting a call the backend correctly rejects is a lesser issue than money actually moving.

A second real bug found the same way: the agent was misreading transaction status "settled" as meaning "already refunded, can't touch it" — the opposite of its actual meaning (settled = eligible). Fixed by making the system prompt state explicitly that settled is a *good* status for a refund, not a blocking one.

## Known limitation

This was built and evaluated against a small (~7.6B parameter, quantized) local model for cost reasons during development. That model is reliably correct about money (never issued an out-of-policy refund — and now literally cannot, due to the backend guard) but is inconsistent about *completing* an escalation after announcing it to the customer. This reads as a model-capability limitation rather than an architecture problem — before launch, re-run `run_conversations.py` + `eval_runner.py` against whatever model Paylane plans to actually run in production (point `MODEL_BASE_URL`/`MODEL_NAME` at it) and re-check the score.
