"""
Smart Protocol Comparison Tool

Intelligently routes comparison queries to the most efficient strategy:
1. Aggregate stats (fast, high-level)
2. Aspect-specific queries (targeted)
3. Detailed comparison (hierarchical summarization)
"""

import os
import time
import re
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool
from src.services.database import DatabaseService
from src.services.gemini_embeddings import EmbeddingsService
from src.utils.logger import logger
from src.llm.factory import create_tool_chat_model


class SmartComparisonInput(BaseModel):
    """Input for smart protocol comparison."""
    protocols: List[str] = Field(description="List of protocol names to compare (e.g., ['compound', 'aave', 'arbitrum'])")
    query: str = Field(description="The user's comparison query (used to determine best strategy)")
    comparison_aspects: Optional[List[str]] = Field(
        default=None,
        description="Optional specific aspects to compare (e.g., ['governance', 'treasury'])"
    )


class SmartComparisonTool(BaseTool):
    """
    Intelligently chooses the best comparison strategy based on query type.
    
    Strategies:
    1. AGGREGATE: High-level stats (governance metrics, voting patterns)
       - Use for: "compare governance", "which DAO is more active", "voting participation"
       - Speed: ~1-2s, Cost: Low
    
    2. ASPECT: Targeted queries for specific topics
       - Use for: "compare treasury management", "grant programs", "tokenomics"
       - Speed: ~2-3s, Cost: Medium
    
    3. DETAILED: Full analysis with proposal summaries
       - Use for: "detailed comparison", "recent proposals", "comprehensive analysis"
       - Speed: ~5-8s, Cost: High
    """
    
    name: str = "smart_protocol_compare"
    description: str = """
    Intelligently compare multiple protocols using the optimal strategy.
    Automatically chooses between aggregate stats, aspect-specific queries, or detailed analysis
    based on the user's query. Faster and more cost-effective than always fetching all proposals.
    
    Use this for any multi-protocol comparison query.
    """
    args_schema: type[BaseModel] = SmartComparisonInput
    
    def __init__(self):
        super().__init__()
        self._embedding_service = None
    
    def _get_embedding_service(self) -> EmbeddingsService:
        """Lazy load embedding service."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingsService()
        return self._embedding_service
    
    def _classify_query(self, query: str, aspects: Optional[List[str]]) -> Literal["aggregate", "aspect", "detailed"]:
        """
        Classify query to determine best strategy.
        
        Returns:
            "aggregate": High-level stats comparison
            "aspect": Specific aspect comparison
            "detailed": Full proposal analysis
        """
        query_lower = query.lower()
        
        # Keywords for aggregate strategy (fast, high-level)
        aggregate_keywords = [
            "governance", "voting", "participation", "active", "activity",
            "how many", "count", "statistics", "metrics", "overview",
            "general", "high-level", "summary", "comparison", "which dao",
            "more active", "less active", "popular"
        ]
        
        # Keywords for detailed strategy (slow, comprehensive)
        detailed_keywords = [
            "detailed", "comprehensive", "in-depth", "thorough", "complete",
            "recent proposals", "latest proposals", "all proposals",
            "analyze", "examine", "investigate", "deep dive"
        ]
        
        # Specific aspects that warrant targeted queries
        aspect_keywords = [
            "treasury", "grant", "funding", "budget", "allocation",
            "tokenomics", "staking", "rewards", "incentive",
            "technical", "upgrade", "integration", "security"
        ]
        
        # Check for detailed keywords first (highest priority)
        if any(keyword in query_lower for keyword in detailed_keywords):
            logger.info("SmartCompare: Classified as DETAILED (comprehensive analysis needed)")
            return "detailed"
        
        # Check for specific aspects
        has_aspect = False
        if aspects:
            has_aspect = True
        else:
            has_aspect = any(keyword in query_lower for keyword in aspect_keywords)
        
        if has_aspect:
            logger.info("SmartCompare: Classified as ASPECT (specific topic comparison)")
            return "aspect"
        
        # Check for aggregate keywords (default for most comparisons)
        if any(keyword in query_lower for keyword in aggregate_keywords):
            logger.info("SmartCompare: Classified as AGGREGATE (high-level stats)")
            return "aggregate"
        
        # Default to aggregate for general comparisons
        logger.info("SmartCompare: Defaulting to AGGREGATE (general comparison)")
        return "aggregate"
    
    def _run(self, protocols: List[str], query: str, comparison_aspects: Optional[List[str]] = None) -> Dict[str, Any]:
        """Execute smart comparison with automatic strategy selection."""
        
        if not protocols:
            return {"error": "No protocols specified for comparison."}
        
        if len(protocols) == 1:
            return {"error": f"Only one protocol ({protocols[0]}) specified. Need at least 2 for comparison."}
        
        logger.info(f"SmartCompare: Comparing {len(protocols)} protocols: {protocols}")
        logger.info(f"SmartCompare: Query: {query}")
        
        start_time = time.perf_counter()
        
        # Classify query to determine strategy
        strategy = self._classify_query(query, comparison_aspects)
        
        # Route to appropriate strategy
        if strategy == "aggregate":
            result = self._aggregate_comparison(protocols, query)
        elif strategy == "aspect":
            result = self._aspect_comparison(protocols, query, comparison_aspects)
        else:  # detailed
            result = self._detailed_comparison(protocols, query, comparison_aspects)
        
        elapsed = time.perf_counter() - start_time
        
        # Add metadata
        result["strategy_used"] = strategy
        result["total_elapsed_seconds"] = round(elapsed, 2)
        result["protocols_compared"] = protocols
        
        logger.info(f"SmartCompare: Completed using {strategy.upper()} strategy in {elapsed:.2f}s")
        
        return result
    
    def _aggregate_comparison(self, protocols: List[str], query: str) -> Dict[str, Any]:
        """
        Strategy 1: Pre-aggregated statistics comparison (fastest).
        
        Use for: High-level comparisons, governance metrics, activity levels.
        """
        logger.info("SmartCompare: Executing AGGREGATE strategy")
        
        # Build protocol filter
        protocol_conditions = " OR ".join([f"dao_id ILIKE '%{p}%'" for p in protocols])
        
        # Aggregate query with governance metrics
        sql = f"""
        WITH protocol_stats AS (
            SELECT 
                dao_id,
                COUNT(*) as total_proposals,
                COUNT(*) FILTER (WHERE state = 'executed') as executed_count,
                COUNT(*) FILTER (WHERE state = 'defeated') as defeated_count,
                COUNT(*) FILTER (WHERE state = 'active') as active_count,
                ROUND(AVG(for_votes + against_votes)::numeric, 0) as avg_total_votes,
                ROUND(AVG(for_votes::numeric / NULLIF(for_votes + against_votes, 0) * 100), 1) as avg_approval_rate,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '3 months') as recent_3m_count,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '6 months') as recent_6m_count,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 year') as recent_1y_count,
                MAX(created_at) as most_recent_proposal,
                MIN(created_at) as oldest_proposal,
                MODE() WITHIN GROUP (ORDER BY source) as primary_platform
            FROM internal.unified_proposals
            WHERE ({protocol_conditions})
              AND created_at > NOW() - INTERVAL '2 years'
            GROUP BY dao_id
        ),
        protocol_topics AS (
            SELECT 
                dao_id,
                COUNT(*) FILTER (WHERE title ILIKE '%treasury%' OR body ILIKE '%treasury%') as treasury_proposals,
                COUNT(*) FILTER (WHERE title ILIKE '%grant%' OR body ILIKE '%grant%') as grant_proposals,
                COUNT(*) FILTER (WHERE title ILIKE '%governance%' OR body ILIKE '%governance%') as governance_proposals,
                COUNT(*) FILTER (WHERE title ILIKE '%technical%' OR title ILIKE '%upgrade%') as technical_proposals
            FROM internal.unified_proposals
            WHERE ({protocol_conditions})
              AND created_at > NOW() - INTERVAL '1 year'
            GROUP BY dao_id
        )
        SELECT 
            ps.*,
            pt.treasury_proposals,
            pt.grant_proposals,
            pt.governance_proposals,
            pt.technical_proposals
        FROM protocol_stats ps
        LEFT JOIN protocol_topics pt ON ps.dao_id = pt.dao_id
        ORDER BY ps.total_proposals DESC
        """
        
        try:
            results = DatabaseService.query_database(None, sql)
            
            if not results:
                return {
                    "error": f"No data found for protocols: {', '.join(protocols)}",
                    "suggestion": "Check protocol names or try a different time period"
                }
            
            # Build comparison summary
            summary_lines = [
                "## Protocol Comparison - Aggregate Statistics",
                "",
                f"**Protocols analyzed**: {', '.join([r['dao_id'] for r in results])}",
                f"**Time period**: Last 2 years",
                f"**Data points**: {len(results)} protocols",
                ""
            ]
            
            # Add detailed stats for each protocol
            for row in results:
                dao = row['dao_id']
                summary_lines.extend([
                    f"### {dao.title()}",
                    f"- **Total proposals**: {row['total_proposals']}",
                    f"- **Execution rate**: {row['executed_count']}/{row['total_proposals']} ({round(row['executed_count']/row['total_proposals']*100, 1) if row['total_proposals'] > 0 else 0}%)",
                    f"- **Average participation**: {int(row['avg_total_votes']) if row['avg_total_votes'] else 0:,} votes",
                    f"- **Average approval**: {row['avg_approval_rate']}%",
                    f"- **Recent activity (3m)**: {row['recent_3m_count']} proposals",
                    f"- **Primary platform**: {row['primary_platform']}",
                    f"- **Most recent**: {row['most_recent_proposal']}",
                    "",
                    "**Topic breakdown (last 1 year)**:",
                    f"- Treasury: {row['treasury_proposals']} proposals",
                    f"- Grants: {row['grant_proposals']} proposals",
                    f"- Governance: {row['governance_proposals']} proposals",
                    f"- Technical: {row['technical_proposals']} proposals",
                    ""
                ])
            
            return {
                "comparison_summary": "\n".join(summary_lines),
                "detailed_stats": results,
                "data_source": "aggregated_metrics"
            }
            
        except Exception as e:
            logger.error(f"SmartCompare: Aggregate strategy failed: {e}")
            return {"error": f"Aggregate comparison failed: {str(e)}"}
    
    def _aspect_comparison(self, protocols: List[str], query: str, aspects: Optional[List[str]]) -> Dict[str, Any]:
        """
        Strategy 2: Aspect-specific targeted comparison (medium speed).
        
        Use for: Specific topics like treasury, grants, tokenomics.
        """
        logger.info("SmartCompare: Executing ASPECT strategy")
        
        # Extract aspects from query if not provided
        if not aspects:
            aspects = self._extract_aspects(query)
        
        if not aspects:
            logger.warning("SmartCompare: No aspects found, falling back to aggregate")
            return self._aggregate_comparison(protocols, query)
        
        logger.info(f"SmartCompare: Focusing on aspects: {aspects}")
        
        # Build aspect-specific search terms
        aspect_terms = " OR ".join([f"title ILIKE '%{a}%' OR body ILIKE '%{a}%'" for a in aspects])
        protocol_conditions = " OR ".join([f"dao_id ILIKE '%{p}%'" for p in protocols])
        
        # Aspect-focused query
        sql = f"""
        SELECT 
            dao_id,
            proposal_id,
            title,
            LEFT(body, 500) as body_preview,
            state,
            created_at,
            source,
            for_votes,
            against_votes,
            link
        FROM internal.unified_proposals
        WHERE ({protocol_conditions})
          AND ({aspect_terms})
          AND created_at > NOW() - INTERVAL '1 year'
        ORDER BY created_at DESC
        LIMIT 30
        """
        
        try:
            results = DatabaseService.query_database(None, sql)
            
            if not results:
                return {
                    "error": f"No {', '.join(aspects)} proposals found for {', '.join(protocols)}",
                    "suggestion": "Try broadening your search or different aspects"
                }
            
            # Group by protocol
            grouped = {}
            for row in results:
                dao = row['dao_id']
                if dao not in grouped:
                    grouped[dao] = []
                grouped[dao].append(row)
            
            # Build comparison summary
            summary_lines = [
                f"## Protocol Comparison - {', '.join(aspects).title()} Focus",
                "",
                f"**Protocols**: {', '.join(protocols)}",
                f"**Aspects**: {', '.join(aspects)}",
                f"**Found**: {len(results)} relevant proposals",
                ""
            ]
            
            for dao, proposals in grouped.items():
                summary_lines.extend([
                    f"### {dao.title()} ({len(proposals)} proposals)",
                    ""
                ])
                
                # Show top 3 proposals
                for i, prop in enumerate(proposals[:3], 1):
                    summary_lines.extend([
                        f"**{i}. {prop['title']}**",
                        f"- Status: {prop['state']}",
                        f"- Created: {prop['created_at']}",
                        f"- Votes: {int(prop['for_votes'] or 0):,} for, {int(prop['against_votes'] or 0):,} against",
                        ""
                    ])
                
                if len(proposals) > 3:
                    summary_lines.append(f"*... and {len(proposals) - 3} more proposals*\n")
            
            return {
                "comparison_summary": "\n".join(summary_lines),
                "proposals_by_protocol": grouped,
                "total_proposals": len(results),
                "aspects_analyzed": aspects,
                "data_source": "aspect_specific_proposals"
            }
            
        except Exception as e:
            logger.error(f"SmartCompare: Aspect strategy failed: {e}")
            return {"error": f"Aspect comparison failed: {str(e)}"}
    
    def _detailed_comparison(self, protocols: List[str], query: str, aspects: Optional[List[str]]) -> Dict[str, Any]:
        """
        Strategy 3: Detailed comparison with proposal analysis (slowest, most comprehensive).
        
        Use for: Detailed analysis, recent proposals, comprehensive reviews.
        Note: This is a lightweight version. For full parallel execution, consider implementing
        a dedicated parallel comparison tool.
        """
        logger.info("SmartCompare: Executing DETAILED strategy (lightweight)")
        
        if not aspects:
            aspects = ["governance", "proposals", "activity"]
        
        protocol_conditions = " OR ".join([f"dao_id ILIKE '%{p}%'" for p in protocols])
        aspect_terms = " OR ".join([f"title ILIKE '%{a}%' OR body ILIKE '%{a}%'" for a in aspects])
        
        # Fetch detailed proposals for all protocols
        sql = f"""
        SELECT 
            dao_id,
            proposal_id,
            title,
            LEFT(body, 300) as body_preview,
            state,
            created_at,
            source,
            for_votes,
            against_votes,
            link
        FROM internal.unified_proposals
        WHERE ({protocol_conditions})
          AND ({aspect_terms})
          AND created_at > NOW() - INTERVAL '1 year'
        ORDER BY created_at DESC
        LIMIT 50
        """
        
        try:
            from src.services.database import DatabaseService
            results = DatabaseService.query_database(None, sql)
            
            if not results:
                return {
                    "error": f"No proposals found for {', '.join(protocols)}",
                    "suggestion": "Try broadening your search or different aspects"
                }
            
            # Group by protocol
            grouped = {}
            for row in results:
                dao = row['dao_id']
                if dao not in grouped:
                    grouped[dao] = []
                grouped[dao].append(row)
            
            # Build detailed comparison
            summary_lines = [
                f"## Detailed Protocol Comparison",
                "",
                f"**Protocols**: {', '.join(protocols)}",
                f"**Aspects**: {', '.join(aspects)}",
                f"**Total proposals**: {len(results)}",
                ""
            ]
            
            for dao, proposals in grouped.items():
                summary_lines.extend([
                    f"### {dao.title()} ({len(proposals)} proposals)",
                    ""
                ])
                
                # Show top 5 proposals
                for i, prop in enumerate(proposals[:5], 1):
                    summary_lines.extend([
                        f"**{i}. {prop['title']}**",
                        f"- Status: {prop['state']}",
                        f"- Created: {prop['created_at']}",
                        f"- Votes: {int(prop['for_votes'] or 0):,} for, {int(prop['against_votes'] or 0):,} against",
                        ""
                    ])
                
                if len(proposals) > 5:
                    summary_lines.append(f"*... and {len(proposals) - 5} more proposals*\n")
            
            return {
                "comparison_summary": "\n".join(summary_lines),
                "proposals_by_protocol": grouped,
                "total_proposals": len(results),
                "note": "Detailed strategy: Full proposal analysis",
                "data_source": "full_proposal_analysis",
                "strategy_used": "detailed"
            }
            
        except Exception as e:
            logger.error(f"SmartCompare: Detailed strategy failed: {e}")
            return {"error": f"Detailed comparison failed: {str(e)}"}
    
    def _extract_aspects(self, query: str) -> List[str]:
        """Extract comparison aspects from query text."""
        query_lower = query.lower()
        
        aspect_map = {
            "treasury": ["treasury", "fund", "funding", "budget"],
            "grants": ["grant", "funding", "allocation"],
            "governance": ["governance", "voting", "delegation"],
            "tokenomics": ["token", "tokenomics", "economics"],
            "staking": ["stake", "staking", "reward"],
            "technical": ["technical", "upgrade", "integration", "protocol"],
            "security": ["security", "audit", "risk"],
        }
        
        found_aspects = []
        for aspect, keywords in aspect_map.items():
            if any(keyword in query_lower for keyword in keywords):
                found_aspects.append(aspect)
        
        return found_aspects
    
    async def _arun(self, protocols: List[str], query: str, comparison_aspects: Optional[List[str]] = None) -> Dict[str, Any]:
        """Async version - not implemented yet."""
        return self._run(protocols, query, comparison_aspects)

