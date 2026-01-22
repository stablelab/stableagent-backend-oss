from langchain_openai import ChatOpenAI
from langgraph_supervisor import create_supervisor

from src.forse_analyze_agent.graph import forse_agent_graph
from src.growth_chat.knowledge_base_agent.graph import \
    create_knowledge_hub_graph as create_rag_graph_knowledge_base_agent
from src.supervisor_agent.supervisor_prompt import SUPERVISOR_PROMPT

knowledge_agent = create_rag_graph_knowledge_base_agent()

# Create supervisor workflow
workflow = create_supervisor(
    [forse_agent_graph, knowledge_agent],
    model=ChatOpenAI(model="gpt-5-nano"),
    prompt=SUPERVISOR_PROMPT,
)


# Compile the supervisor app
supervisor_app = workflow.compile()
