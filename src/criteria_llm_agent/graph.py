"""
LangGraph implementation for criteria evaluation.

Provides AI-powered evaluation of grant application criteria using LangGraph
with support for multiple LLM providers. Uses Pydantic structured output
instead of JSON mode for better compatibility across all LLM providers.
"""
import os
import json
import time
from typing import Dict, Any, AsyncGenerator, TypedDict, List
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from .types import CriteriaScore, CriteriaEvaluationResult
from .model_factory import create_chat_model, get_model_provider
from .logger import evaluation_logger
from src.utils.model_factory import extract_text_content

import logging
logger = logging.getLogger(__name__)


class EvaluationState(TypedDict):
    """State for the evaluation graph."""
    criterion_id: int
    criterion_name: str
    criterion_description: str
    weight: float
    scoring_rules: Dict[str, Any]
    form_config: Dict[str, Any]
    user_answers: List[Dict[str, Any]]
    result: Dict[str, Any]


def create_evaluation_prompt(
    criterion_name: str,
    criterion_description: str,
    scoring_rules: Dict[str, Any],
    form_config: Dict[str, Any],
    user_answers: List[Dict[str, Any]]
) -> str:
    """
    Create a detailed prompt for criterion evaluation.
    
    Args:
        criterion_name: Name of the criterion
        criterion_description: Description of the criterion
        scoring_rules: Optional JSONB scoring rules
        form_config: Form configuration with field definitions
        user_answers: User's submitted answers with step_id, field_id, field_type, and value
        
    Returns:
        Formatted prompt for LLM evaluation
    """
    # Get form metadata
    form_title = form_config.get('title', 'Grant Application')
    form_description = form_config.get('description', '')
    
    # Build field labels map from form config for human-readable output
    field_labels = {}
    for step in form_config.get('steps', []):
        step_id = step.get('id', '')
        step_title = step.get('title', step_id)
        for field in step.get('fields', []):
            field_id = field.get('id', '')
            field_label = field.get('label', field_id)
            field_labels[f"{step_id}.{field_id}"] = {
                'step': step_title,
                'label': field_label
            }
    
    # Format answers in a minimal, readable format grouped by step
    current_step = None
    answers_formatted = []
    
    for answer in user_answers:
        step_id = answer.get('step_id', '')
        field_id = answer.get('field_id', '')
        value = answer.get('value', '')
        
        # Get human-readable labels
        key = f"{step_id}.{field_id}"
        field_info = field_labels.get(key, {'step': step_id, 'label': field_id})
        
        # Add step header if new step
        if step_id != current_step:
            if current_step is not None:
                answers_formatted.append("")  # Blank line between steps
            answers_formatted.append(f"## {field_info['step']}")
            current_step = step_id
        
        # Format value based on type
        if isinstance(value, str):
            formatted_value = value
        elif isinstance(value, (list, dict)):
            formatted_value = json.dumps(value, indent=2)
        else:
            formatted_value = str(value)
        
        answers_formatted.append(f"{field_info['label']}: {formatted_value}")
    
    answers_context = "\n".join(answers_formatted) if answers_formatted else "No answers provided"
    
    # Add scoring rules if available
    scoring_context = ""
    if scoring_rules:
        scoring_context = f"\n\nSCORING RULES: {json.dumps(scoring_rules, indent=2)}"
    
    prompt = f"""You are evaluating a blockchain/web3/crypto grant application against specific criteria.

CRITERION TO EVALUATE: {criterion_name}
DESCRIPTION: {criterion_description or 'No additional description provided'}{scoring_context}

FORM INFORMATION:
Title: {form_title}
Description: {form_description}

USER'S RESPONSES:
{answers_context}

EVALUATION TASK:
Carefully evaluate whether this application meets the criterion "{criterion_name}".
Based on the user's responses, assign ONE of the following scores:

- 0 points: Completely fails to meet the criterion
- 20 points: Minimal effort, significantly below expectations
- 33 points: Below expectations, major improvements needed
- 50 points: Meets basic expectations, but with notable gaps
- 66 points: Meets expectations with minor areas for improvement
- 80 points: Exceeds expectations in most aspects
- 100 points: Exceptional, fully exceeds all expectations

You MUST respond with ONLY a JSON object in this exact format:
{{
    "score": 0 | 20 | 33 | 50 | 66 | 80 | 100,
    "reasoning": "Your detailed explanation here"
}}

Requirements:
- score: Must be exactly one of these values: 0, 20, 33, 50, 66, 80, or 100 (no other values)
- reasoning: Clear explanation referencing specific answers from the user's responses

Be objective, fair, and specific in your reasoning. Quote or reference actual content from the user's responses to support your evaluation.
"""
    
    return prompt


async def evaluate_criterion_node(state: EvaluationState) -> Dict[str, Any]:
    """
    Evaluate a single criterion using LLM with structured output.
    
    Uses Pydantic schema for structured output instead of JSON mode,
    which provides better compatibility across all LLM providers.
    
    Returns a score of 0, 50, or 100 based on how well the criterion is met.
    """
    criterion_id = state["criterion_id"]
    criterion_name = state["criterion_name"]
    criterion_description = state["criterion_description"]
    weight = state["weight"]
    scoring_rules = state.get("scoring_rules", {})
    form_config = state["form_config"]
    user_answers = state["user_answers"]
    
    logger.info(f"Evaluating criterion {criterion_id}: {criterion_name}")
    
    # Get model configuration
    model_name = (
        os.environ.get("CRITERIA_AGENT_MODEL") or
        os.environ.get("FORM_MODEL") or
        os.environ.get("DEFAULT_MODEL", "gpt-3.5-turbo")
    )
    
    temperature = float(os.environ.get("CRITERIA_AGENT_TEMPERATURE", "0.3"))
    provider = get_model_provider(model_name)
    
    # Log model selection
    evaluation_logger.log_model_info(model_name, provider, temperature)
    evaluation_logger.log_llm_call_start(criterion_name)
    
    try:
        # Create model with explicit handling for temperature-sensitive models
        # Some models (o1-preview, o1-mini) only support temperature=1
        model_supports_custom_temp = not model_name.startswith('o1')
        
        if model_supports_custom_temp:
            model = create_chat_model(
                model_name=model_name,
                temperature=temperature,
                json_mode=False
            )
        else:
            # Models like o1-preview only support default temperature
            logger.info(f"Model {model_name} requires default temperature (1.0)")
            evaluation_logger.logger.info(
                f"ℹ️  Using default temperature for {model_name}"
            )
            model = create_chat_model(
                model_name=model_name,
                temperature=1.0,
                json_mode=False
            )
        
        # Create evaluation prompt
        prompt = create_evaluation_prompt(
            criterion_name=criterion_name,
            criterion_description=criterion_description,
            scoring_rules=scoring_rules,
            form_config=form_config,
            user_answers=user_answers
        )
        
        # Log the complete prompt being sent to the AI
        logger.info(f"\n{'='*80}\n📝 PROMPT FOR AI EVALUATION - {criterion_name}\n{'='*80}\n{prompt}\n{'='*80}\n")
        
        # Get LLM evaluation - parse response manually (more compatible than with_structured_output)
        start_time = time.time()
        response = await model.ainvoke([HumanMessage(content=prompt)])
        duration_ms = (time.time() - start_time) * 1000
        
        # Log LLM response
        evaluation_logger.log_llm_call_complete(criterion_name, duration_ms)
        
        # Parse response content
        if hasattr(response, 'content'):
            content = extract_text_content(response.content)
        else:
            content = str(response)
        
        # Log the AI's response
        logger.info(f"\n{'='*80}\n🤖 AI RESPONSE - {criterion_name}\n{'='*80}\n{content}\n{'='*80}\n")
        
        # Extract JSON from response (handle markdown code blocks)
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            content = content.split('```')[1].split('```')[0].strip()
        
        # Parse JSON
        try:
            result_data = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from text
            import re
            json_match = re.search(r'\{[^}]*"score"[^}]*"reasoning"[^}]*\}', content, re.DOTALL)
            if json_match:
                result_data = json.loads(json_match.group(0))
            else:
                raise ValueError(f"Could not parse JSON from response: {content[:200]}")
        
        # Validate with Pydantic
        criteria_score = CriteriaScore(**result_data)
        score = criteria_score.score
        reasoning = criteria_score.reasoning
        
        # Validate score
        if score not in [0, 20, 33, 50, 66, 80, 100]:
            logger.warning(f"Invalid score {score} from LLM, defaulting to 0")
            score = 0
            reasoning = f"Invalid score received from AI: {score}. Defaulted to 0."
        
        # Calculate weighted score
        weighted_score = score * weight
        
        # Log the score
        evaluation_logger.log_criterion_score(
            criterion_name, score, weight, weighted_score, duration_ms
        )
        
        # Create result
        evaluation_result = {
            "criterion_id": criterion_id,
            "criterion_name": criterion_name,
            "criterion_description": criterion_description,
            "raw_score": score,
            "weight": weight,
            "weighted_score": weighted_score,
            "reasoning": reasoning,
            "is_error": False,
            "error_message": None
        }
        
        logger.info(f"Criterion {criterion_id} evaluated: score={score}, weighted={weighted_score:.2f}")
        
        return {"result": evaluation_result}
        
    except Exception as e:
        logger.error(f"Error evaluating criterion {criterion_id}: {e}", exc_info=True)
        evaluation_logger.log_criterion_error(criterion_name, str(e))
        
        # Return error result
        error_result = {
            "criterion_id": criterion_id,
            "criterion_name": criterion_name,
            "criterion_description": criterion_description,
            "raw_score": 0,
            "weight": weight,
            "weighted_score": 0.0,
            "reasoning": "Error occurred during evaluation",
            "is_error": True,
            "error_message": str(e)
        }
        
        return {"result": error_result}


def create_evaluation_graph() -> StateGraph:
    """
    Create a LangGraph for criterion evaluation.
    
    Returns:
        Compiled StateGraph for evaluating a single criterion
    """
    graph = StateGraph(EvaluationState)
    
    # Add evaluation node
    graph.add_node("evaluate_criterion", evaluate_criterion_node)
    
    # Set entry point
    graph.set_entry_point("evaluate_criterion")
    
    # Add edge to end
    graph.add_edge("evaluate_criterion", END)
    
    return graph.compile()


async def evaluate_single_criterion(
    criterion_id: int,
    criterion_name: str,
    criterion_description: str,
    weight: float,
    scoring_rules: Dict[str, Any],
    form_config: Dict[str, Any],
    user_answers: List[Dict[str, Any]]
) -> CriteriaEvaluationResult:
    """
    Evaluate a single criterion against user's form responses.
    
    Args:
        criterion_id: ID of the criterion
        criterion_name: Name of the criterion
        criterion_description: Description of the criterion
        weight: Weight multiplier for this criterion
        scoring_rules: Optional scoring rules (JSONB)
        form_config: Form configuration
        user_answers: User's submitted answers
        
    Returns:
        CriteriaEvaluationResult with score and reasoning
    """
    graph = create_evaluation_graph()
    
    initial_state = {
        "criterion_id": criterion_id,
        "criterion_name": criterion_name,
        "criterion_description": criterion_description,
        "weight": weight,
        "scoring_rules": scoring_rules or {},
        "form_config": form_config,
        "user_answers": user_answers,
        "result": {}
    }
    
    # Execute graph
    final_state = await graph.ainvoke(initial_state)
    
    # Extract and validate result
    result_data = final_state.get("result", {})
    
    return CriteriaEvaluationResult(**result_data)
