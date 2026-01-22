from typing import Optional, List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.tools.context_expander_tool import ContextExpanderTool
from src.tools.sql_generator_tool import SQLQueryTool
from src.tools.dao_catalog_tool import DaoCatalogTool
from src.llm.factory import create_chat_model
from src.tools.sota_web_search import SotaWebSearchTool
from src.tools.vertex_search_tool import VertexSearchTool
from src.tools.ens_resolver_tool import ENSResolverTool
from src.tools.chain_resolver_tool import ChainResolverTool
from src.tools.coingecko_price_tool import CoinGeckoPriceTool
from src.tools.etherscan_tool import EtherscanTool
from src.tools.datetime_tool import CurrentDateTimeTool
from src.tools.smart_comparison_tool import SmartComparisonTool
from src.prompts.system_prompts import STABLESEARCH_SYSTEM


def build_default_tools() -> List:
    return [
        # Core query tools
        ContextExpanderTool(),         # expand query context (helps with semantic search)
        SQLQueryTool(),                # generates and executes SQL (includes proposal suggestion fallback)
        SmartComparisonTool(),         # intelligent multi-DAO comparison with auto-routing
        
        # Supporting data tools
        DaoCatalogTool(),              # list supported DAOs
        CoinGeckoPriceTool(),          # pricing: spot, series, token-by-contract, search
        EtherscanTool(),               # Etherscan/Etherscan-family explorer data
        ENSResolverTool(),             # ENS ↔ address lookups
        ChainResolverTool(),           # chain id/name/slug lookups
        CurrentDateTimeTool(),         # current date/time utility
        
        # Optional Vertex AI Search (if enabled)
        VertexSearchTool(),            # searches your configured Discovery Engine data store

        # Last resort (open web providers via API keys)
        SotaWebSearchTool(),           # web search fallback (async tool) – keep last
    ]


# Legacy run_agentic_query removed in favor of LangGraph endpoints


def answer_with_context(user_query: str, context: str, provider: Optional[str] = None, model_id: Optional[str] = None) -> str:
    system_text = "\n".join(STABLESEARCH_SYSTEM)
    safe_system_text = system_text.replace("{", "{{" ).replace("}", "}}")
    prompt = ChatPromptTemplate.from_messages([
        ("system", safe_system_text),
        ("human", "User query: {q}\n\nContext: {c}\n\nWrite a comprehensive answer based on the provided context. If context is insufficient, say so, then answer best-effort."),
    ])
    llm = create_chat_model(provider=provider, model=model_id)
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"q": user_query, "c": context})