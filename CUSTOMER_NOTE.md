Subject: Support agent — status before launch

Hi,

Here's where the support agent stands.

**What it does**
It handles refunds, verification, and frozen-card questions for cards/transfers. Before it looks at anything account-related, it asks for the email and last 4 card digits and checks them — if they don't match, it won't go further. For refunds, it checks the amount and how old the purchase is, and only approves on the spot if the purchase is $75 or less and under 30 days old. Everything else — bigger refunds, older purchases, legal threats, suspected fraud over $500, account closures, frozen-card unfreeze requests — gets handed to a person instead of being resolved by the bot.

**What it won't do**
It will never read a customer's email or card number back to them, even if they ask nicely. It won't refund the same purchase twice. It won't unfreeze a card itself — only a human can do that. And the money-side rule is enforced twice: once in how the agent is told to behave, and once in the actual refund system itself, so even if the agent gets confused, it physically can't push through a refund that breaks the $75/30-day limits. I tested this directly — pushed a refund request $0.01 over the limit — and the system blocked it both times.

**What I'd want from you before this goes live**
Two things, honestly.

First: I built and tested this against a small model running locally on my machine (not a hosted service), mostly to avoid API costs during testing. It handled money correctly every time, but it's inconsistent on follow-through — a few times it told the customer "let's get this to a human" and then didn't actually create the escalation ticket. The customer sees a reasonable-sounding answer, but no human ever gets looped in. I'd want to re-run this against whichever model you're planning to actually use in production before launch, since a bigger model may well not have this issue — this might be specific to the small test model, not an issue with the agent's design.

Second: I'd like you to tell me what should happen if the agent says it's escalating but the actual ticket creation fails — right now it just moves on. Should it retry, apologize and ask the customer to call in, or something else? That's a judgment call I don't want to make for you.

Happy to walk through the test conversations and the failures I caught — the eval report is a one-pager, 4-sentence summary at the bottom.

Thanks,
Ujjwal
