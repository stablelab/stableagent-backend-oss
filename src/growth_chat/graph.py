"""
LangGraph workflow for Growth Chat Super Graph.

Implements a planner that creates multi-step execution plans to orchestrate:
- knowledge_hub_agent: For RAG-based knowledge queries
- app_automation_agent: For team management actions
- research_agent: For DAO governance research
- forse_analyzer_agent: For Forse data analysis
- onboarding_agent: For onboarding flows
- conversation: For greetings and general chat
"""
import os
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from src.forse_analyze_agent.graph import forse_agent_graph
from src.utils.checkpointer import get_checkpointer
from src.utils.logger import logger
from src.utils.model_factory import create_chat_model, extract_text_content

from .app_automation_agent.graph import create_app_automation_graph
from .knowledge_base_agent.graph import create_knowledge_hub_graph
from .onboarding_agent.graph import create_onboarding_graph
from .prompts import (CONVERSATION_PROMPT_TEMPLATE, PLANNER_PROMPT,
                      SUGGEST_QUERIES_PROMPT, SUMMARIZER_PROMPT)
from .research_agent.graph import create_research_agent_graph
from .schemas import (AGENT_TYPE_MAP, AgentType, GrowthChatState, PlanOutput,
                      PlanStep, SuggestedQueriesOutput, UserInfo)
from .utils import (filter_empty_messages, format_plan_message,
                    get_plan_message_removals, get_tool_message_removals)

# Shared checkpointer at module level
_SHARED_CHECKPOINTER = get_checkpointer()

# Maximum steps allowed in a plan (controlled by env var)
MAX_PLANNER_STEPS = int(os.getenv("MAX_PLANNER_STEPS", "3"))


### Planner Node ###

async def planner_node(state: GrowthChatState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Planner node that creates an execution plan using LLM.
    
    Analyzes the conversation history and creates a plan.
    Most requests need only 1 step. Complex requests that require output
    from one agent as input to another get 2-3 steps.
    
    Args:
        state: Current graph state with messages
        config: RunnableConfig with callbacks for LangSmith tracing
        
    Returns:
        Updated state with plan, current_step_index, and which_agent set
    """
    messages = filter_empty_messages(state.get("messages", []))
    
    if not messages:
        logger.warning("Planner node received empty messages, defaulting to conversation")
        default_plan = [{"agent_type": "conversation", "task_description": "Greet the user"}]
        return {
            "plan": default_plan,
            "current_step_index": 0,
            "which_agent": AgentType.CONVERSATION,
        }

    # Format conversation history
    conversation_parts = []
    for msg in messages[:-1]:  # All but last message
        if isinstance(msg, HumanMessage):
            role = "User"
        elif isinstance(msg, AIMessage):
            role = "Assistant"
        else:
            continue
        content = extract_text_content(msg.content) if hasattr(msg, "content") else ""
        if content:
            conversation_parts.append(f"{role}: {content}")
    
    conversation_history = "\n".join(conversation_parts) if conversation_parts else "No prior conversation."
    
    # Get latest message
    latest_msg = messages[-1]
    latest_msg_content = extract_text_content(latest_msg.content) if hasattr(latest_msg, "content") else ""
    
    # Create planner prompt
    prompt = PLANNER_PROMPT.format(
        max_steps=MAX_PLANNER_STEPS,
        conversation_history=conversation_history,
        latest_message=latest_msg_content
    )
    
    try:
        # Create LLM for planning
        llm = create_chat_model(
            model_name=os.getenv("GROWTH_CHAT_ROUTER_MODEL", "gemini-3-flash-preview"),
            temperature=float(os.getenv("GROWTH_CHAT_ROUTER_TEMPERATURE", "0.0"))
        )
        
        # Get plan with structured output
        structured_llm = llm.with_structured_output(PlanOutput)
        result: PlanOutput = await structured_llm.ainvoke([HumanMessage(content=prompt)], config=config)
        
        logger.info(f"Planner raw output: {result}")
        logger.info(f"Planner steps count: {len(result.steps) if result.steps else 0}")
        
        # Convert to PlanStep format and validate
        plan: List[PlanStep] = []
        for step in result.steps[:MAX_PLANNER_STEPS]:  # Enforce max steps
            agent = step.agent.lower() if step.agent else "conversation"
            task = step.task or ""
            
            # Validate agent type
            if agent not in AGENT_TYPE_MAP:
                logger.warning(f"Unknown agent type '{agent}', defaulting to conversation")
                agent = "conversation"
            
            plan.append({
                "agent_type": agent,
                "task_description": task
            })
        
        # Ensure we have at least one step
        if not plan:
            plan = [{"agent_type": "conversation", "task_description": "Handle the user's request"}]
        
        # Set which_agent to the first step's agent
        first_agent_type = AGENT_TYPE_MAP.get(plan[0]["agent_type"], AgentType.CONVERSATION)
        
        logger.info(f"Planner created {len(plan)}-step plan for message: '{latest_msg_content[:50]}'.")
        for i, step in enumerate(plan):
            logger.info(f"  Step {i+1}: {step['agent_type']} - {step['task_description'][:50]}")
        
        # Inject plan instruction for the first agent
        plan_message = HumanMessage(content=format_plan_message(plan, step_idx=0))
        
        return {
            "messages": [plan_message],
            "plan": plan,
            "current_step_index": 0,
            "which_agent": first_agent_type,
        }
            
    except Exception as e:
        logger.error(f"Planner failed: {e}", exc_info=True)
        # Default to conversation on error
        default_plan = [{"agent_type": "conversation", "task_description": "Handle the user's request"}]
        return {
            "plan": default_plan,
            "current_step_index": 0,
            "which_agent": AgentType.CONVERSATION,
        }


def route_to_agent(state: GrowthChatState) -> str:
    """Route to the current agent based on which_agent field."""
    return state.get("which_agent").value + "_agent"


### Post-Agent Node ###

async def post_agent_node(state: GrowthChatState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Post-agent node that handles transitions between plan steps.
    
    After an agent completes:
    1. Increments the step counter
    2. If more steps remain, sets which_agent for next step
    3. If plan complete, signals to proceed to summarizer
    
    Note: No context injection needed - agents can see previous AIMessages in history.
    
    Args:
        state: Current graph state
        config: RunnableConfig with callbacks for LangSmith tracing
        
    Returns:
        Updated state with incremented step index and next agent info
    """
    plan = state.get("plan", [])
    current_step_index = state.get("current_step_index", 0)
    
    # Move to next step
    next_step_index = current_step_index + 1
    
    # Remove old plan messages and tool messages to avoid confusing subsequent agents
    messages = state.get("messages", [])
    removals = get_plan_message_removals(messages) + get_tool_message_removals(messages)
    
    # Check if there are more steps
    if next_step_index < len(plan):
        next_step = plan[next_step_index]
        next_agent_type = AGENT_TYPE_MAP.get(next_step["agent_type"], AgentType.CONVERSATION)
        
        logger.info(f"Post-agent: Moving to step {next_step_index + 1}/{len(plan)}: {next_agent_type.value}")
        
        # Inject plan instruction for the next agent
        plan_message = HumanMessage(content=format_plan_message(plan, step_idx=next_step_index))
        
        return {
            "messages": removals + [plan_message],
            "current_step_index": next_step_index,
            "which_agent": next_agent_type,
        }
    
    # Plan complete
    logger.info(f"Post-agent: Plan complete after {len(plan)} step(s)")
    return {
        "messages": removals,
        "current_step_index": next_step_index,
        "which_agent": None,  # Signal that we're done
    }


def route_after_agent(state: GrowthChatState) -> str:
    """
    Route after post_agent_node.
    
    If which_agent is set, route to that agent.
    If which_agent is None, route to summarizer (plan complete).
    """
    if state.get("which_agent") is None:
        return "summarizer"
    return state.get("which_agent").value + "_agent"


### Summarizer Node ###

async def summarizer_node(state: GrowthChatState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Summarizer node that creates a comprehensive final response.
    
    Reviews the entire conversation history and synthesizes a user-friendly
    final answer that includes all relevant information from the agent steps.
    
    Args:
        state: Current graph state with all messages from the conversation
        config: RunnableConfig with callbacks for LangSmith tracing
        
    Returns:
        Updated state with the summarized response added to messages
    """
    messages = state.get("messages", [])
    
    if not messages:
        logger.warning("Summarizer node received no messages")
        return {
            "messages": [AIMessage(content="I couldn't generate a response. Please try again.")]
        }
    
    # Build the full conversation history for context
    conversation_parts = []
    latest_query = ""
    
    for msg in messages:
        if isinstance(msg, HumanMessage):
            content = extract_text_content(msg.content) if hasattr(msg, "content") else ""
            if content and not content.startswith("[PLAN]:"):
                conversation_parts.append(f"User: {content}")
                # Capture the latest user query (last HumanMessage)
                latest_query = content
        elif isinstance(msg, AIMessage):
            content = extract_text_content(msg.content) if hasattr(msg, "content") else ""
            if content:
                conversation_parts.append(f"Agent Output: {content}")
    
    conversation_history = "\n\n".join(conversation_parts) if conversation_parts else "No conversation history."
    
    # Create the summarizer prompt
    prompt = SUMMARIZER_PROMPT.format(
        conversation_history=conversation_history,
        latest_query=latest_query or "No query found."
    )
    
    try:
        # Create LLM for summarization
        llm = create_chat_model(
            model_name=os.getenv("GROWTH_CHAT_SUMMARIZER_MODEL", os.getenv("GROWTH_CHAT_ROUTER_MODEL", "gemini-3-flash-preview")),
            temperature=float(os.getenv("GROWTH_CHAT_SUMMARIZER_TEMPERATURE", "0.3"))
        )
        
        # Generate the summarized response
        response = await llm.ainvoke([HumanMessage(content=prompt)], config=config)
        answer = extract_text_content(response.content)
        
        logger.info(f"Summarizer generated response: '{answer[:100]}'...")
        
        return {
            "messages": [AIMessage(content=answer)]
        }
        
    except Exception as e:
        logger.error(f"Summarizer node failed: {e}", exc_info=True)
        # Fall back to last AI message if summarization fails
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                content = extract_text_content(msg.content)
                if content:
                    return {"messages": [AIMessage(content=content)]}
        
        return {
            "messages": [AIMessage(content="I encountered an error generating the response. Please try again.")]
        }


### Conversation Node ###

async def conversation_node(state: GrowthChatState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Node for handling basic conversation like greetings and explaining capabilities.
    
    Uses the LLM to generate a natural conversational response.
    
    Args:
        state: Current graph state with messages
        config: RunnableConfig with callbacks for LangSmith tracing
        
    Returns:
        Updated state with AI response added to messages
    """
    messages = filter_empty_messages(state.get("messages", []))
    
    try:
        # Create LLM for conversation
        llm = create_chat_model(
            model_name=os.environ.get("KNOWLEDGE_AGENT_MODEL", "gemini-3-flash-preview"),
            temperature=0.7  # Slightly higher temp for more natural conversation
        )
        
        # Create chain with prompt template
        chain = CONVERSATION_PROMPT_TEMPLATE | llm
        
        # Generate response (pass config for LangSmith tracing)
        response = await chain.ainvoke({"messages": messages}, config=config)
        answer = extract_text_content(response.content)
        
        logger.info(f"Conversation node generated response: '{answer[:100]}'...")
        
        return {
            "messages": [AIMessage(content=answer)]
        }
        
    except Exception as e:
        logger.error(f"Conversation node failed: {e}", exc_info=True)
        fallback_response = "Hello! I'm your Growth Chat assistant. I can help you search our Knowledge Hub for information or manage your teams. How can I assist you today?"
        return {
            "messages": [AIMessage(content=fallback_response)]
        }


### Suggest Queries Node ###

async def suggest_queries_node(state: GrowthChatState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Node that generates suggested follow-up queries based on conversation history.
    
    Uses structured output to ensure the LLM always returns valid JSON with
    the correct schema: {"suggested_queries": [...]}.
    
    For onboarding flows, returns hardcoded suggestions without calling the LLM.
    
    Args:
        state: Current graph state with messages
        config: RunnableConfig with callbacks for LangSmith tracing
        
    Returns:
        Updated state with suggested_queries field set
    """
    # Check if we came from onboarding agent - return hardcoded suggestions
    if state.get("which_agent") == AgentType.ONBOARDING:
        logger.info("Suggest queries: Using hardcoded onboarding suggestions")
        return {
            "suggested_queries": [
                "Continue with next onboarding step",
                "Skip this step"
            ]
        }
    
    messages = filter_empty_messages(state.get("messages", []))
    
    if len(messages) < 2:
        # Not enough conversation history to make meaningful suggestions
        return {"suggested_queries": []}
    
    try:
        # Format conversation history
        conversation_parts = []
        for msg in messages[:-1]:  # All but last message
            if isinstance(msg, HumanMessage):
                role = "User"
            elif isinstance(msg, AIMessage):
                role = "Assistant"
            else:
                continue
            content = extract_text_content(msg.content) if hasattr(msg, "content") else ""
            conversation_parts.append(f"{role}: {content}") if content else None
        
        conversation_history = "\n".join(conversation_parts) if conversation_parts else "No prior conversation."
        
        # Get the latest response (should be an AI message)
        latest_msg = messages[-1]
        latest_msg_content = extract_text_content(latest_msg.content) if hasattr(latest_msg, "content") else ""
        
        # Create the suggestion prompt
        prompt = SUGGEST_QUERIES_PROMPT.format(
            conversation_history=conversation_history,
            latest_response=latest_msg_content
        )
        
        # Create LLM with structured output for guaranteed JSON schema
        llm = create_chat_model(
            model_name=os.getenv("GROWTH_CHAT_ROUTER_MODEL", "gemini-3-flash-preview"),  # Use same fast model as router
            temperature=0.7  # Slightly higher temp for variety
        )
        structured_llm = llm.with_structured_output(SuggestedQueriesOutput)
        
        # Get suggestions with structured output (pass config for LangSmith tracing)
        result: SuggestedQueriesOutput = await structured_llm.ainvoke([HumanMessage(content=prompt)], config=config)
        
        # Limit to 4 suggestions
        suggestions = result.suggested_queries[:4]
        
        logger.info(f"Suggest queries node generated {len(suggestions)} suggestions")
        
        return {"suggested_queries": suggestions}
        
    except Exception as e:
        logger.error(f"Suggest queries node failed: {e}", exc_info=True)
        return {"suggested_queries": []}


### Growth Chat Graph ###

def create_growth_chat_graph(
    auth_token: str,
    org_id: int,
    org_slug: str,
    org_schema: str = "",
    knowledge_visibility: Optional[str] = None,
    user_info: Optional[UserInfo] = None,
):
    """
    Create and compile the Growth Chat super graph.
    
    Graph structure:
    planner → [conditional] → agent → post_agent → [conditional] → next_agent OR suggest_queries → END
    
    The planner creates a multi-step plan (1-N steps). After each agent executes,
    post_agent_node checks if there are more steps and routes accordingly.
    
    Args:
        auth_token: Authentication token for admin tools
        org_id: Organization ID for admin tools
        org_slug: Organization slug for admin tools
        org_schema: Organization database schema name for Knowledge Hub
        knowledge_visibility: Visibility filter for knowledge hub ("public" or None for all)
        user_info: User information (id, handle, email, display_name)
    Returns:
        Compiled graph with shared checkpointer
    """
    # Create the super graph
    graph = StateGraph(GrowthChatState)
    
    graph.add_node("planner", planner_node)
    graph.add_node("post_agent", post_agent_node)
    graph.add_node("conversation_agent", conversation_node)
    
    knowledge_hub_agent = create_knowledge_hub_graph(
        org_schema=org_schema,
        org_id=org_id,
        visibility=knowledge_visibility,
        auth_token=auth_token,
        org_slug=org_slug,
    )
    graph.add_node("knowledge_hub_agent", knowledge_hub_agent)

    app_automation_agent = create_app_automation_graph(
        auth_token, org_id, org_slug, user_info=user_info
    )
    graph.add_node("app_automation_agent", app_automation_agent)

    onboarding_agent = create_onboarding_graph(
        auth_token, org_id, org_slug, user_info=user_info
    )
    graph.add_node("onboarding_agent", onboarding_agent)
    graph.add_node("forse_analyzer_agent", forse_agent_graph)

    research_agent = create_research_agent_graph(
        user_id=user_info.get('id') if user_info else None,
        org_slug=org_slug,
        auth_token=auth_token,
    )
    graph.add_node("research_agent", research_agent)

    graph.add_node("suggest_queries", suggest_queries_node)
    graph.add_node("summarizer", summarizer_node)

    graph.set_entry_point("planner")

    graph.add_conditional_edges(
        "planner",
        route_to_agent,
        {agent+"_agent": agent+"_agent" for agent in AGENT_TYPE_MAP}
    )
    
    for agent in AGENT_TYPE_MAP:
        if agent == "onboarding":
            continue
        graph.add_edge(agent + "_agent", "post_agent")
    
    # Onboarding agent is a special case. It should not be followed by any other agent, feed the answer directly to the user.
    graph.add_edge("onboarding_agent", "suggest_queries")
        
    # post_agent routes to next agent or summarizer (when plan complete)
    graph.add_conditional_edges(
        "post_agent",
        route_after_agent,
        {**{agent+"_agent": agent+"_agent" for agent in AGENT_TYPE_MAP}, **{"summarizer": "summarizer"}}
    )
    
    # summarizer produces the final answer, then suggest_queries
    graph.add_edge("summarizer", "suggest_queries")
    graph.add_edge("suggest_queries", END)

    return graph.compile(checkpointer=_SHARED_CHECKPOINTER)
