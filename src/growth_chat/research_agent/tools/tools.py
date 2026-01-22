"""Tool factory for Research Agent.

Creates and returns all tools for the Research Agent.
"""
from typing import List

from langchain_core.tools import BaseTool

from src.utils.logger import logger


def create_research_tools() -> List[BaseTool]:
    """Create all research agent tools.
    
    Returns a list of tools for:
    - Proposal search (Snapshot, Tally)
    - Active proposals (currently running votes)
    - Forum search (Discourse)
    - Social search (Telegram, Discord)
    - Vote tools (lookup, voter stats, proposal stats, VP trends, top voters)
    - GitHub (repos, commits, stats, board)
    - DAO catalog
    - Token prices
    - Web search (fallback)
    - ENS resolution
    - Chain resolution (blockchain metadata)
    - Code execution (E2B sandbox + Claude Sonnet)
    """
    logger.info("[ResearchTools] Starting tool initialization...")
    tools = []
    
    # Core data source tools with semantic search
    try:
        from .discourse_tool import DiscourseSearchTool
        tools.append(DiscourseSearchTool())
        logger.info("[ResearchTools] Loaded DiscourseSearchTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load DiscourseSearchTool: {e}")
    
    try:
        from .snapshot_tool import SnapshotProposalsTool
        tools.append(SnapshotProposalsTool())
        logger.info("[ResearchTools] Loaded SnapshotProposalsTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load SnapshotProposalsTool: {e}")
    
    try:
        from .tally_tool import TallyProposalsTool
        tools.append(TallyProposalsTool())
        logger.info("[ResearchTools] Loaded TallyProposalsTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load TallyProposalsTool: {e}")
    
    try:
        from .proposal_results_tool import ProposalResultsTool
        tools.append(ProposalResultsTool())
        logger.info("[ResearchTools] Loaded ProposalResultsTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load ProposalResultsTool: {e}")
    
    try:
        from .active_proposals_tool import ActiveProposalsTool
        tools.append(ActiveProposalsTool())
        logger.info("[ResearchTools] Loaded ActiveProposalsTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load ActiveProposalsTool: {e}")
    
    try:
        from .github_tool import GitHubReposTool, GitHubCommitsTool, GitHubStatsTool, GitHubBoardTool
        tools.append(GitHubReposTool())
        logger.info("[ResearchTools] Loaded GitHubReposTool")
        tools.append(GitHubCommitsTool())
        logger.info("[ResearchTools] Loaded GitHubCommitsTool")
        tools.append(GitHubStatsTool())
        logger.info("[ResearchTools] Loaded GitHubStatsTool")
        tools.append(GitHubBoardTool())
        logger.info("[ResearchTools] Loaded GitHubBoardTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load GitHub tools: {e}")
    
    try:
        from .telegram_tool import TelegramSearchTool
        tools.append(TelegramSearchTool())
        logger.info("[ResearchTools] Loaded TelegramSearchTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load TelegramSearchTool: {e}")
    
    try:
        from .discord_tool import DiscordSearchTool
        tools.append(DiscordSearchTool())
        logger.info("[ResearchTools] Loaded DiscordSearchTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load DiscordSearchTool: {e}")
    
    try:
        from .votes_tool import (
            VotesLookupTool,
            VoterStatsTool,
            ProposalVoteStatsTool,
            VotingPowerTrendsTool,
            TopVotersTool,
        )
        tools.append(VotesLookupTool())
        logger.info("[ResearchTools] Loaded VotesLookupTool")
        tools.append(VoterStatsTool())
        logger.info("[ResearchTools] Loaded VoterStatsTool")
        tools.append(ProposalVoteStatsTool())
        logger.info("[ResearchTools] Loaded ProposalVoteStatsTool")
        tools.append(VotingPowerTrendsTool())
        logger.info("[ResearchTools] Loaded VotingPowerTrendsTool")
        tools.append(TopVotersTool())
        logger.info("[ResearchTools] Loaded TopVotersTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load voting tools: {e}")
    
    # Supporting tools (wrappers and utilities)
    try:
        from .dao_catalog_tool import DAOCatalogTool
        tools.append(DAOCatalogTool())
        logger.info("[ResearchTools] Loaded DAOCatalogTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load DAOCatalogTool: {e}")
    
    try:
        from .token_price_tool import TokenPriceTool
        tools.append(TokenPriceTool())
        logger.info("[ResearchTools] Loaded TokenPriceTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load TokenPriceTool: {e}")
    
    try:
        from .ens_tool import ENSResolverTool
        tools.append(ENSResolverTool())
        logger.info("[ResearchTools] Loaded ENSResolverTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load ENSResolverTool: {e}")
    
    try:
        from .chain_resolver_tool import ChainResolverTool
        tools.append(ChainResolverTool())
        logger.info("[ResearchTools] Loaded ChainResolverTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load ChainResolverTool: {e}")
    
    try:
        from .web_search_tool import WebSearchTool
        tools.append(WebSearchTool())
        logger.info("[ResearchTools] Loaded WebSearchTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load WebSearchTool: {e}")
    
    # Code execution tool (uses Claude Sonnet + E2B sandbox)
    try:
        from .code_execute_tool import CodeExecuteTool
        tools.append(CodeExecuteTool())
        logger.info("[ResearchTools] Loaded CodeExecuteTool")
    except Exception as e:
        logger.error(f"[ResearchTools] Failed to load CodeExecuteTool: {e}")
    
    if tools:
        tool_names = [t.name for t in tools]
        logger.info(f"[ResearchTools] Successfully loaded {len(tools)} tools: {tool_names}")
    else:
        logger.error("[ResearchTools] WARNING: No tools were loaded! The agent will have no capabilities.")
    
    return tools

