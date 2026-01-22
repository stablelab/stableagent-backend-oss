"""
Simple LangGraph implementation using the project's LLM factory.

Provides a minimal example graph that processes field IDs and returns
structured responses using the configured LLM provider and model.
Uses the project's LLM factory for consistent provider/model handling.
Includes comprehensive performance logging with colored console output.
"""
import os
import json
import uuid
import time
from typing import Dict, Any, AsyncGenerator, TypedDict
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from .types import LangGraphResult
from .json_extractor import extract_and_validate_langgraph_result
from src.utils.model_factory import create_chat_model, get_model_provider, extract_text_content
from .performance_logger import performance_logger, track_operation


class GraphState(TypedDict):
    """Simple state for the example graph."""
    field_id: str
    messages: list
    result: Dict[str, Any]


async def process_field_node(state: GraphState) -> Dict[str, Any]:
    """
    Process field ID using the configured LLM model via new model factory.

    Creates a structured response based on the field ID input.
    Uses the form LLM agent's model factory supporting OpenAI, Anthropic, Gemini, and XAI.

    Environment Variables:
        FORM_AGENT_MODEL or FORM_MODEL: Specific model to use (e.g., "gpt-4", "claude-3-opus")
        FORM_AGENT_TEMPERATURE: Temperature setting (default: 0.3)
        FORM_AGENT_JSON_MODE: Enable JSON mode for compatible models (default: true)
        DEFAULT_MODEL: Fallback model if form-specific not set (default: "gpt-4")
    """
    field_id = state["field_id"]

    # Start performance tracking for the entire field processing operation
    with track_operation(
        operation="field_processing",
        field_id=field_id
    ) as operation_id:

        # Get model from environment or use defaults
        # Priority: FORM_AGENT_MODEL -> FORM_MODEL -> DEFAULT_MODEL -> fallback
        model_name = (
            os.environ.get("FORM_AGENT_MODEL") or
            os.environ.get("FORM_MODEL") or
            os.environ.get("DEFAULT_MODEL", "gpt-4")
        )

        # Get temperature setting
        temperature = float(os.environ.get("FORM_AGENT_TEMPERATURE", "0.3"))

        # Determine if we should use JSON mode for structured output
        use_json_mode = os.environ.get(
            "FORM_AGENT_JSON_MODE", "true").lower() == "true"

        # Get provider for logging
        provider = get_model_provider(model_name)

        # Log model selection
        performance_logger.log_model_selection(
            model_name, provider, temperature, use_json_mode)

        # Track model creation time
        model_creation_id = performance_logger.start_operation(
            "model_creation",
            field_id=field_id,
            model_name=model_name,
            provider=provider
        )

        try:
            # Initialize model using the new model factory
            model = create_chat_model(
                model_name=model_name,
                temperature=temperature,
                json_mode=use_json_mode
            )
            performance_logger.finish_operation(
                model_creation_id, success=True)
        except Exception as e:
            performance_logger.finish_operation(
                model_creation_id,
                success=False,
                error_message=str(e)
            )
            raise

        # Create a prompt for generating structured response
        if use_json_mode:
            # For JSON mode models, request structured output directly
            prompt = f"""
You are a friendly form helper! Analyze field ID: {field_id}

Generate concise, fun but respectful advice for someone filling out this form field. Be maximally brief and helpful.

JSON format:
{{
    "id": "advice_{field_id}",
    "field_id": "{field_id}",
    "response": "Your super concise, friendly advice (max 2 sentences)",
    "type": "advice",
    "is_error": false
}}

Focus on:
- What to enter or fix
- Common mistakes to avoid
- Quick validation tips

Keep it short, friendly, and actionable! Think "helpful friend giving quick tips."
"""
        else:
            # For non-JSON mode models, request JSON in the content
            prompt = f"""
You are a friendly form helper! Analyze field ID: {field_id}

Give super concise, fun but respectful advice for someone filling out this form. Be maximally brief!

JSON format only:
{{
    "id": "advice_{field_id}",
    "field_id": "{field_id}",
    "response": "Your concise, friendly advice (max 2 sentences)",
    "type": "advice", 
    "is_error": false
}}

Focus on what to enter, what to fix, or common mistakes. Keep it short and helpful!
"""

        # Log API call start
        performance_logger.log_api_call_start(
            provider, model_name, len(prompt))

        # Track the API call timing
        api_call_start = time.time()

        try:
            # Get response from model
            response = await model.ainvoke([HumanMessage(content=prompt)])

            # Calculate API call duration
            api_call_duration = (time.time() - api_call_start) * 1000

            # Determine response length
            response_length = 0
            if hasattr(response, 'content'):
                response_length = len(str(response.content))
            elif isinstance(response, dict):
                response_length = len(json.dumps(response))
            else:
                response_length = len(str(response))

            # Log API call completion
            performance_logger.log_api_call_complete(
                provider, model_name, response_length, api_call_duration)

            # Handle different response formats based on JSON mode
            if use_json_mode and isinstance(response, dict):
                # Direct structured output from JSON mode
                result_data = response
                # Ensure required fields are present with correct format
                if "id" not in result_data:
                    result_data["id"] = f"advice_{field_id}"
                if "field_id" not in result_data:
                    result_data["field_id"] = field_id
                if "is_error" not in result_data:
                    result_data["is_error"] = False
            elif hasattr(response, 'content'):
                # Parse from content attribute
                result_data = extract_and_validate_langgraph_result(
                    text=extract_text_content(response.content),
                    field_id=field_id
                )
            else:
                # Fallback parsing
                result_data = extract_and_validate_langgraph_result(
                    text=str(response),
                    field_id=field_id
                )

        except Exception as e:
            # Calculate API call duration even for errors
            api_call_duration = (time.time() - api_call_start) * 1000

        # Enhanced error handling with model context
        result_data = {
            "id": f"advice_{field_id}",
            "field_id": field_id,
            "response": f"Error processing field {field_id} with {provider} model {model_name}: {str(e)}",
            "type": "issue",
            "is_error": True,
            "is_clear": False,
            "server_error": True
        }

        # Log the error with performance context
        performance_logger.logger.error(
            f"API call failed after {api_call_duration:.1f}ms: {str(e)} (model: {provider}/{model_name})"
        )

        return {"result": result_data}


def create_simple_graph() -> StateGraph:
    """
    Create a simple LangGraph with one processing node.

    Returns:
        StateGraph configured for field processing
    """
    # Create graph
    graph = StateGraph(GraphState)

    # Add nodes
    graph.add_node("process_field", process_field_node)

    # Set entry point
    graph.set_entry_point("process_field")

    # Add edges
    graph.add_edge("process_field", END)

    return graph.compile()


async def stream_field_processing(field_id: str) -> AsyncGenerator[LangGraphResult, None]:
    """
    Stream processing results for a given field ID.

    Includes comprehensive performance logging with streaming metrics.

    Args:
        field_id: The field identifier to process

    Yields:
        LangGraphResult objects with processing results
    """
    # Start streaming performance tracking
    streaming_start_time = time.time()
    performance_logger.log_streaming_start(field_id)

    chunk_count = 0

    try:
        # Track the overall streaming operation
        with track_operation(
            operation="stream_field_processing",
            field_id=field_id
        ) as streaming_operation_id:

            # Create and run the graph
            graph = create_simple_graph()

            # Initial state
            initial_state = {
                "field_id": field_id,
                "messages": [],
                "result": {}
            }

            # Execute graph (this will trigger the field processing with its own logging)
            final_state = await graph.ainvoke(initial_state)

            # Extract result and yield
            result_data = final_state.get("result", {})

            # Validate and yield result
            try:
                result = LangGraphResult(**result_data)

                # Log streaming chunk
                chunk_count += 1
                chunk_size = len(json.dumps(result.model_dump()))
                performance_logger.log_streaming_chunk(
                    field_id, chunk_size, chunk_count)

                yield result
            except Exception as e:
                # Fallback error result
                error_result = LangGraphResult(
                    id=field_id,
                    field_id=field_id,
                    response=f"Failed to create valid result: {str(e)}",
                    type="issue",
                    is_error=True,
                    is_clear=False,
                    server_error=True
                )

                # Log error chunk
                chunk_count += 1
                chunk_size = len(json.dumps(error_result.model_dump()))
                performance_logger.log_streaming_chunk(
                    field_id, chunk_size, chunk_count)

                yield error_result

    except Exception as e:
        # Top-level error handling
        error_result = LangGraphResult(
            id=field_id,
            field_id=field_id,
            response=f"Graph execution failed: {str(e)}",
            type="issue",
            is_error=True,
            is_clear=False,
            server_error=True
        )

        # Log error chunk
        chunk_count += 1
        chunk_size = len(json.dumps(error_result.model_dump()))
        performance_logger.log_streaming_chunk(
            field_id, chunk_size, chunk_count)

        yield error_result

    finally:
        # Log streaming completion with final highlighted time
        total_duration_ms = (time.time() - streaming_start_time) * 1000
        performance_logger.log_streaming_complete(
            field_id, chunk_count, total_duration_ms)


async def stream_field_processing_with_context(
    field_id: str,
    field_label: str = "",
    field_type: str = "text",
    field_description: str = "",
    evaluation_instructions: str = "",
    validation_rules: Dict[str, Any] = None,
    current_value: Any = None
) -> AsyncGenerator[LangGraphResult, None]:
    """
    Stream processing results for a field with enhanced context and evaluation instructions.

    This function provides more targeted advice by using the complete field context,
    including evaluation instructions, validation rules, and field metadata.

    Args:
        field_id: The field identifier to process
        field_label: Human-readable label for the field
        field_type: Type of field (text, select, textarea, etc.)
        field_description: Description of the field's purpose
        evaluation_instructions: Specific instructions for evaluating this field
        validation_rules: Validation constraints for the field

    Yields:
        LangGraphResult objects with enhanced, context-aware advice
    """
    if validation_rules is None:
        validation_rules = {}

    # Start streaming performance tracking
    streaming_start_time = time.time()
    performance_logger.log_streaming_start(field_id)

    chunk_count = 0

    try:
        # Track the overall streaming operation with context
        with track_operation(
            operation="enhanced_stream_field_processing",
            field_id=field_id
        ) as streaming_operation_id:

            # Get model configuration
            model_name = (
                os.environ.get("FORM_AGENT_MODEL") or
                os.environ.get("FORM_MODEL") or
                os.environ.get("DEFAULT_MODEL", "gpt-4")
            )

            temperature = float(os.environ.get(
                "FORM_AGENT_TEMPERATURE", "0.3"))
            use_json_mode = os.environ.get(
                "FORM_AGENT_JSON_MODE", "true").lower() == "true"
            provider = get_model_provider(model_name)

            # Log enhanced model selection
            performance_logger.log_model_selection(
                model_name, provider, temperature, use_json_mode)

            # Create model
            model_creation_id = performance_logger.start_operation(
                "enhanced_model_creation",
                field_id=field_id,
                model_name=model_name,
                provider=provider
            )

            try:
                model = create_chat_model(
                    model_name=model_name,
                    temperature=temperature,
                    json_mode=use_json_mode
                )
                performance_logger.finish_operation(
                    model_creation_id, success=True)
            except Exception as e:
                performance_logger.finish_operation(
                    model_creation_id,
                    success=False,
                    error_message=str(e)
                )
                raise

            # Create enhanced prompt with evaluation instructions and current value
            enhanced_prompt = create_enhanced_field_prompt(
                field_id=field_id,
                field_label=field_label,
                field_type=field_type,
                field_description=field_description,
                evaluation_instructions=evaluation_instructions,
                validation_rules=validation_rules,
                use_json_mode=use_json_mode,
                current_value=current_value
            )

            # Log API call start
            performance_logger.log_api_call_start(
                provider, model_name, len(enhanced_prompt))

            # Track the API call timing
            api_call_start = time.time()

            try:
                # Get response from model
                response = await model.ainvoke([HumanMessage(content=enhanced_prompt)])

                # Calculate API call duration
                api_call_duration = (time.time() - api_call_start) * 1000

                # Determine response length
                response_length = 0
                if hasattr(response, 'content'):
                    response_length = len(str(response.content))
                elif isinstance(response, dict):
                    response_length = len(json.dumps(response))
                else:
                    response_length = len(str(response))

                # Log API call completion
                performance_logger.log_api_call_complete(
                    provider, model_name, response_length, api_call_duration)

                # Handle different response formats based on JSON mode
                if use_json_mode and isinstance(response, dict):
                    result_data = response
                    # Ensure required fields are present with correct format
                    if "id" not in result_data:
                        result_data["id"] = f"advice_{field_id}"
                    if "field_id" not in result_data:
                        result_data["field_id"] = field_id
                    if "is_error" not in result_data:
                        result_data["is_error"] = False
                elif hasattr(response, 'content'):
                    result_data = extract_and_validate_langgraph_result(
                        text=extract_text_content(response.content),
                        field_id=field_id
                    )
                else:
                    result_data = extract_and_validate_langgraph_result(
                        text=str(response),
                        field_id=field_id
                    )

                # Validate and yield result
                try:
                    result = LangGraphResult(**result_data)

                    # Log streaming chunk
                    chunk_count += 1
                    chunk_size = len(json.dumps(result.model_dump()))
                    performance_logger.log_streaming_chunk(
                        field_id, chunk_size, chunk_count)

                    yield result

                except Exception as e:
                    # Fallback error result
                    error_result = LangGraphResult(
                        id=field_id,
                        field_id=field_id,
                        response=f"Failed to create enhanced result: {str(e)}",
                        type="issue",
                        is_error=True,
                        is_clear=False,
                        server_error=True
                    )

                    chunk_count += 1
                    chunk_size = len(json.dumps(error_result.model_dump()))
                    performance_logger.log_streaming_chunk(
                        field_id, chunk_size, chunk_count)

                    yield error_result

            except Exception as e:
                # Calculate API call duration even for errors
                api_call_duration = (time.time() - api_call_start) * 1000

                # Enhanced error handling
                error_result = LangGraphResult(
                    id=field_id,
                    field_id=field_id,
                    response=f"Enhanced processing failed: {str(e)}",
                    type="issue",
                    is_error=True,
                    is_clear=False,
                    server_error=True
                )

                # Log the error with performance context
                performance_logger.logger.error(
                    f"Enhanced API call failed after {api_call_duration:.1f}ms: {str(e)} (model: {provider}/{model_name})"
                )

                chunk_count += 1
                chunk_size = len(json.dumps(error_result.model_dump()))
                performance_logger.log_streaming_chunk(
                    field_id, chunk_size, chunk_count)

                yield error_result

    except Exception as e:
        # Top-level error handling
        error_result = LangGraphResult(
            id=field_id,
            field_id=field_id,
            response=f"Enhanced graph execution failed: {str(e)}",
            type="issue",
            is_error=True,
            is_clear=False,
            server_error=True
        )

        chunk_count += 1
        chunk_size = len(json.dumps(error_result.model_dump()))
        performance_logger.log_streaming_chunk(
            field_id, chunk_size, chunk_count)

        yield error_result

    finally:
        # Log streaming completion with final highlighted time
        total_duration_ms = (time.time() - streaming_start_time) * 1000
        performance_logger.log_streaming_complete(
            field_id, chunk_count, total_duration_ms)


def create_enhanced_field_prompt(
    field_id: str,
    field_label: str,
    field_type: str,
    field_description: str,
    evaluation_instructions: str,
    validation_rules: Dict[str, Any],
    use_json_mode: bool,
    current_value: Any = None
) -> str:
    """
    Create an enhanced prompt using field context and evaluation instructions.

    Args:
        field_id: Field identifier
        field_label: Human-readable field label
        field_type: Field type (text, select, etc.)
        field_description: Field description
        evaluation_instructions: Specific evaluation guidance
        validation_rules: Validation constraints
        use_json_mode: Whether to format for JSON mode

    Returns:
        Enhanced prompt string with context and evaluation instructions
    """
    # Build validation context
    validation_context = []
    if validation_rules.get("required"):
        validation_context.append("required field")
    if validation_rules.get("minLength"):
        validation_context.append(f"min {validation_rules['minLength']} chars")
    if validation_rules.get("maxLength"):
        validation_context.append(f"max {validation_rules['maxLength']} chars")
    if validation_rules.get("min"):
        validation_context.append(f"min value {validation_rules['min']}")

    validation_info = f" ({', '.join(validation_context)})" if validation_context else ""

    # Add current value context if provided
    current_value_context = ""
    if current_value is not None:
        current_value_context = f"\nCURRENT VALUE: \"{current_value}\""

    # Create context-aware prompt
    if use_json_mode:
        prompt = f"""
You are a friendly form helper for a blockchain & web3 & crypto grants management platform! Analyze this specific form field:

Field: "{field_label}" (ID: {field_id})
Type: {field_type}{validation_info}
Purpose: {field_description}{current_value_context}

EVALUATION INSTRUCTIONS: {evaluation_instructions}

CONTEXT: You are helping users with grant applications on a blockchain & web3 & crypto grants management platform. All responses should be framed within this context to provide relevant, domain-specific guidance.

{"Provide specific feedback on the current value based on evaluation instructions. If the value looks good, you can return an empty response." if current_value is not None else "Generate super concise, friendly advice for someone filling out this field."}

JSON format:
{{
    "id": "advice_{field_id}",
    "field_id": "{field_id}",
    "response": "{"Your specific feedback on the current value (leave empty if value is acceptable)" if current_value is not None else "Your targeted, concise advice based on evaluation instructions (max 2 sentences)"}",
    "type": "advice",
    "is_error": false,
    "is_clear": {"true if current value meets evaluation criteria, false if it needs improvement" if current_value is not None else "false"},
    "server_error": false,
    "note": null
}}

{"Focus on what's wrong with the current value or leave response empty if it's acceptable." if current_value is not None else "Focus on the specific evaluation criteria and help the user succeed!"}
"""
    else:
        prompt = f"""
You are a friendly form helper for a blockchain & web3 & crypto grants management platform! Analyze this form field:

Field: "{field_label}" (ID: {field_id})
Type: {field_type}{validation_info}
Purpose: {field_description}{current_value_context}

EVALUATION INSTRUCTIONS: {evaluation_instructions}

CONTEXT: You are helping users with grant applications on a blockchain & web3 & crypto grants management platform. All responses should be framed within this context to provide relevant, domain-specific guidance.

{"Provide specific feedback on the current value based on evaluation instructions. If the value looks good, you can return an empty response." if current_value is not None else "Give targeted, concise advice based on the evaluation instructions above."}

JSON format only:
{{
    "id": "advice_{field_id}",
    "field_id": "{field_id}",
    "response": "{"Your specific feedback on the current value (leave empty if value is acceptable)" if current_value is not None else "Your targeted advice based on evaluation instructions (max 2 sentences)"}",
    "type": "advice",
    "is_error": false,
    "is_clear": {"true if current value meets evaluation criteria, false if it needs improvement" if current_value is not None else "false"},
    "server_error": false,
    "note": null
}}

{"Focus on what's wrong with the current value or leave response empty if it's acceptable." if current_value is not None else "Use the evaluation instructions to provide specific, helpful guidance!"}
"""

    return prompt
