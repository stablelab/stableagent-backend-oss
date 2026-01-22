import logging
from src.agent.delegate.llm_provider import LLMManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class ReActReasoner:
    """Applies ReAct-style reasoning to governance proposals using LLM."""

    def __init__(self, provider_name=None, model_name=None, temperature=None, llm_timeout=60, **kwargs):
        # Remove unrelated kwargs
        kwargs.pop("data_utility", None)

        self.llm = LLMManager(
            provider_name=provider_name,
            model_name=model_name,
            temperature=temperature,
            llm_timeout=llm_timeout,
            **kwargs
        )
        self.provider = provider_name or self.llm.get_provider_info()['provider']
        self.model = model_name or self.llm.get_provider_info()['model_info']['model']

    def reason(self, proposal_text: str, context_text: str, voting_options: list[str]) -> dict:
        history = []
        max_steps = 5
        decision = "Abstain"
        full_trace = []

        # Step 0: Initialize conversation
        prompt = self.build_prompt(proposal_text, context_text, voting_options)
        history.append(prompt)

        for step in range(max_steps):
            logger.info(f"Step {step + 1} reasoning...")
            
            step_input = "\n".join(history)
            response = self.llm.generate_from_prompt(step_input)

            parsed = self.parse_step(response, voting_options)
            obs = None  # <-- Always reset this at the start of the loop

            # Log LLM output and parsed details
            logger.debug(f"LLM output (step {step + 1}):\n{response}")
            logger.debug(f"Parsed action: {parsed.get('action')}")
            logger.debug(f"Final decision: {parsed.get('final_decision')}")

            # Append the LLM response to the conversation history
            history.append(response)

            # If there's an action, execute it and append the observation
            if parsed.get("action"):
                allowed_actions = {"summarizeproposal", "searchhistory", "lookupdiscussion"}
                action_lower = parsed["action"].lower()
                if action_lower not in allowed_actions:
                    raise ValueError(f"Unknown action: {parsed['action']}")

                obs = self.execute_action(parsed["action"], proposal_text, context_text)
                # Escape curly braces in observation to prevent format string errors
                obs_escaped = obs.replace("{", "{{").replace("}", "}}")
                history.append(f"Observation: {obs_escaped}")

            # Append the structured trace (after action and observation)
            full_trace.append({
                "step": step + 1,
                "input": step_input,
                "output": response,
                "action": parsed.get("action"),
                "observation": obs
            })

            # Stop if a final decision is found
            if parsed.get("final_decision"):
                decision = parsed["final_decision"]
                break

        # Extract justification from the final output
        justification = self._extract_justification(full_trace, history)
        
        return {
            "output": "\n\n".join([str(step["output"]) for step in full_trace]),  # ✅ join just the LLM outputs
            "reasoning": "\n".join(history),
            "decision": decision,
            "justification": justification,  # Add structured justification
            "trace": full_trace
        }

    def reason_streaming(self, proposal_text: str, context_text: str, voting_options: list[str]):
        """Streaming version of the reasoning process that yields intermediate results."""
        import time
        from datetime import datetime, timezone
        
        def _now_iso():
            return datetime.now(timezone.utc).isoformat()
        
        history = []
        max_steps = 5
        decision = "Abstain"
        full_trace = []

        # Send initial status
        yield {
            "type": "analysis.started",
            "proposal_text": proposal_text[:200] + "..." if len(proposal_text) > 200 else proposal_text,
            "voting_options": voting_options,
            "timestamp": _now_iso()
        }

        # Step 0: Initialize conversation
        prompt = self.build_prompt(proposal_text, context_text, voting_options)
        history.append(prompt)

        yield {
            "type": "reasoning.initialized",
            "timestamp": _now_iso()
        }

        for step in range(max_steps):
            logger.info(f"Step {step + 1} reasoning...")
            
            # Send step start
            yield {
                "type": "reasoning.step.started",
                "step": step + 1,
                "max_steps": max_steps,
                "timestamp": _now_iso()
            }
            
            step_input = "\n".join(history)
            response = self.llm.generate_from_prompt(step_input)

            parsed = self.parse_step(response, voting_options)
            obs = None

            # Send step progress
            yield {
                "type": "reasoning.step.progress",
                "step": step + 1,
                "action": parsed.get("action"),
                "thought": parsed.get("thought", "")[:200] + "..." if parsed.get("thought") and len(parsed.get("thought", "")) > 200 else parsed.get("thought", ""),
                "timestamp": _now_iso()
            }

            # Log LLM output and parsed details
            logger.debug(f"LLM output (step {step + 1}):\n{response}")
            logger.debug(f"Parsed action: {parsed.get('action')}")
            logger.debug(f"Final decision: {parsed.get('final_decision')}")

            # Append the LLM response to the conversation history
            history.append(response)

            # If there's an action, execute it and append the observation
            if parsed.get("action"):
                allowed_actions = {"summarizeproposal", "searchhistory", "lookupdiscussion"}
                action_lower = parsed["action"].lower()
                if action_lower not in allowed_actions:
                    raise ValueError(f"Unknown action: {parsed['action']}")

                # Send action execution start
                yield {
                    "type": "reasoning.action.started",
                    "step": step + 1,
                    "action": parsed["action"],
                    "timestamp": _now_iso()
                }

                obs = self.execute_action(parsed["action"], proposal_text, context_text)
                # Escape curly braces in observation to prevent format string errors
                obs_escaped = obs.replace("{", "{{").replace("}", "}}")
                history.append(f"Observation: {obs_escaped}")

                # Send action execution complete
                yield {
                    "type": "reasoning.action.completed",
                    "step": step + 1,
                    "action": parsed["action"],
                    "observation_preview": obs[:100] + "..." if len(obs) > 100 else obs,
                    "timestamp": _now_iso()
                }

            # Append the structured trace (after action and observation)
            full_trace.append({
                "step": step + 1,
                "input": step_input,
                "output": response,
                "action": parsed.get("action"),
                "observation": obs
            })

            # Send step completion
            yield {
                "type": "reasoning.step.completed",
                "step": step + 1,
                "final_decision": parsed.get("final_decision"),
                "timestamp": _now_iso()
            }

            # Stop if a final decision is found
            if parsed.get("final_decision"):
                decision = parsed["final_decision"]
                break

        # Extract justification from the final output
        justification = self._extract_justification(full_trace, history)
        
        # Send final results
        yield {
            "type": "analysis.completed",
            "decision": decision,
            "justification": justification,
            "total_steps": len(full_trace),
            "timestamp": _now_iso()
        }


    def build_prompt(self, proposal_text: str, context_text: str, voting_options: list[str]) -> str:
        """Construct a ReAct reasoning prompt."""
        options_str = "\n".join(f"- {opt}" for opt in voting_options)

        # Escape curly braces in the text to prevent format string errors
        proposal_text_escaped = proposal_text.replace("{", "{{").replace("}", "}}")
        context_text_escaped = context_text.replace("{", "{{").replace("}", "}}")

        prompt = f"""
You are an expert governance analyst using step-by-step reasoning and actions to decide how a delegate should vote on a proposal.

## Proposal:
{proposal_text_escaped}

## Related Context:
{context_text_escaped}

## Voting Options (you MUST choose EXACTLY ONE):
{options_str}

Use the ReAct format:
- Thought: Reflect on what information is needed.
- Action: [SearchHistory | LookupDiscussion | SummarizeProposal]
- Observation: What you learned from the action.
Repeat if needed. End with:

- Final Thought: Coherent justification for your decision.
- Final Decision: [EXACTLY ONE OPTION FROM THE LIST ABOVE - DO NOT MODIFY THE TEXT]

CRITICAL RULES:
1. You MUST select EXACTLY ONE voting option from the list above
2. Copy the option text EXACTLY as shown (including any trailing spaces)
3. Do NOT create custom options or combine multiple options
4. Do NOT list multiple options separated by commas

Start your reasoning. At each step, stop after a single Action and Observation, then wait for the next input. Do not output Final Decision until you are confident.
Thought: Let's understand what this proposal is trying to do...
"""
        return prompt

    def _extract_justification(self, full_trace: list, history: list) -> str:
        """Extract the final thought/justification from the reasoning trace."""
        # Look for "Final Thought:" in the last few steps
        justification = ""
        
        # Check the trace for final thought
        for step in reversed(full_trace):
            if step.get("output"):
                lines = step["output"].strip().splitlines()
                for line in lines:
                    if line.startswith("Final Thought:"):
                        justification = line.split(":", 1)[1].strip()
                        break
                if justification:
                    break
        
        # If not found in trace, check history
        if not justification:
            for entry in reversed(history):
                lines = entry.strip().splitlines()
                for line in lines:
                    if line.startswith("Final Thought:"):
                        justification = line.split(":", 1)[1].strip()
                        break
                if justification:
                    break
        
        # If still not found, try to extract from the last reasoning step
        if not justification and full_trace:
            last_output = full_trace[-1].get("output", "")
            # Look for any reasoning pattern
            lines = last_output.strip().splitlines()
            thought_lines = []
            for line in lines:
                if line.startswith("Thought:") or line.startswith("Final Thought:"):
                    thought_content = line.split(":", 1)[1].strip() if ":" in line else line
                    thought_lines.append(thought_content)
            
            if thought_lines:
                justification = " ".join(thought_lines)
        
        return justification if justification else "Analysis completed based on proposal content and context."

    def parse_response(self, text: str, voting_options: list[str]) -> dict:
        """Extract the reasoning trace and final decision from LLM output."""
        decision = "Abstain"
        reasoning_lines = []
        lines = text.strip().splitlines()

        for line in lines:
            if line.startswith("Final Decision:"):
                decision_raw = line.split(":", 1)[1].strip().lower()
                for opt in voting_options:
                    if decision_raw == opt.lower():
                        decision = opt
                        break
            elif line.startswith("Thought:") or line.startswith("Action:") or line.startswith("Observation:") or line.startswith("Final Thought:"):
                reasoning_lines.append(line)

        return {
            "output": text.strip(),
            "reasoning": "\n".join(reasoning_lines),
            "decision": decision
        }
    
    def parse_step(self, text: str, voting_options: list[str]) -> dict:
        result = {"action": None, "final_decision": None}

        for line in text.strip().splitlines():
            if line.startswith("Action:"):
                result["action"] = line.split(":", 1)[1].strip()
            elif line.startswith("Final Decision:"):
                raw = line.split(":", 1)[1].strip()
                
                # First try exact match (case-sensitive)
                if raw in voting_options:
                    result["final_decision"] = raw
                else:
                    # Try case-insensitive match
                    raw_lower = raw.lower()
                    for opt in voting_options:
                        if raw_lower == opt.lower():
                            result["final_decision"] = opt
                            break
                    
                    # If still no match, check if it's a partial match or contains commas
                    if result["final_decision"] is None:
                        if "," in raw:
                            # This is a multi-choice response, which we need to handle
                            # For now, log a warning and default to first option or abstain
                            logger.warning(f"Multi-choice decision detected: {raw}. This should not happen with updated prompt.")
                            # Try to extract the first valid option
                            choices = [choice.strip() for choice in raw.split(",")]
                            for choice in choices:
                                for opt in voting_options:
                                    if choice.lower() == opt.lower():
                                        result["final_decision"] = opt
                                        break
                                if result["final_decision"]:
                                    break
                        
                        # If still no match, use fallback
                        if result["final_decision"] is None:
                            # Try to find the best match using substring matching
                            for opt in voting_options:
                                if opt.lower() in raw_lower or raw_lower in opt.lower():
                                    result["final_decision"] = opt
                                    break
                            
                            # Final fallback - use raw decision but log warning
                            if result["final_decision"] is None:
                                logger.warning(f"Could not match decision '{raw}' to any voting option. Available options: {voting_options}")
                                result["final_decision"] = raw
        
        return result

    def execute_action(self, action: str, proposal_text: str, context_text: str) -> str:
        action = action.lower()

        if action == "summarizeproposal":
            return self.summarize_proposal(proposal_text)
        elif action == "lookupdiscussion":
            return self.lookup_discussion(context_text)
        elif action == "searchhistory":
            return self.search_history(proposal_text)
        else:
            return "Unknown action."

    def summarize_proposal(self, text_to_summarize: str) -> str:
        # Call LLM to summarize
        # Escape curly braces to prevent format string errors
        text_escaped = text_to_summarize.replace("{", "{{").replace("}", "}}")
        return self.llm.generate_from_prompt(f"Summarize this:\n\n{text_escaped}")

    def lookup_discussion(self, context_text: str) -> str:
        # Summarize context
        # Escape curly braces to prevent format string errors
        context_escaped = context_text.replace("{", "{{").replace("}", "}}")
        return self.llm.generate_from_prompt(f"Summarize relevant discussion:\n\n{context_escaped}")

    def search_history(self, proposal_text: str) -> str:
        # This could call embedding_agent.get_similar_content or something similar
        return "Historical proposals show similar funding efforts."
