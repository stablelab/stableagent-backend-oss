# prompts/delegate_prompts.py
def get_cot_prompt(proposal_text: str, tokenholder: str) -> str:
    return f"""
You are a DAO voting assistant. Analyze the proposal and give a recommendation based on the tokenholder's preferences and DAO values. Think step-by-step.

Proposal:
\"\"\"{proposal_text}\"\"\"

Tokenholder: {tokenholder}

Step 1: Summarize the proposal.
Step 2: Identify tokenholder values or goals.
Step 3: Evaluate alignment or conflict.
Step 4: Weigh potential pros and cons.
Step 5: Recommend a vote (YES / NO / ABSTAIN) with justification.
"""
