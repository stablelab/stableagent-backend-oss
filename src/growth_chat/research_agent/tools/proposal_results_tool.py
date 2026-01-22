"""Proposal Results Tool - Query voting outcomes from Snapshot and Tally.

This tool returns structured proposal outcomes including:
- Voting state (passed/failed/active)
- Choices and their scores (for elections)
- Vote counts for each option
- Winner identification for closed proposals

Database Tables Used:
- snapshot.proposallist: Full Snapshot data with choices/scores arrays
  Columns: proposal_id, dao_id, title, state, choices (text[]), scores (numeric[]),
           created (unix), start, ends, scores_total, quorum, body
  
- internal.unified_proposal_embeddings: Unified view of Tally + other on-chain data
  Columns: source, proposal_id, dao_id, topic_id, title, created_at, ends_at
  , choices, scores, scores_total, quorum, state, body, embedding, embedding_model_id

Search Strategy (cascading):
1. Proposal ID exact match (BIP-821, AIP-123 patterns)
2. AND keyword search (all terms must match)
3. OR keyword search (any term matches)
4. Regex pattern search (PostgreSQL ~* operator)
5. Semantic search (embedding-based, last resort)
"""
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from src.services.connection_pool import get_connection_pool
from src.utils.logger import logger

from .base import SemanticSearchTool
from .database_client import is_proposal_id_query


class ProposalResultsInput(BaseModel):
    """Input schema for proposal results lookup."""
    query: str = Field(
        ..., 
        description="Search query for proposal title/topic (e.g., 'OpCo election', 'treasury allocation')"
    )
    dao_id: str = Field(
        "", 
        description="DAO identifier - snapshot space (e.g., 'arbitrumfoundation.eth') or tally slug. Leave empty for all."
    )
    state: str = Field(
        "", 
        description="Filter by state: 'closed', 'active', 'executed', 'defeated'. Leave empty for all states."
    )
    limit: int = Field(
        5, 
        description="Maximum number of results (1-10)"
    )


class ProposalResultsTool(SemanticSearchTool):
    """Look up proposal voting outcomes and results.
    
    Returns structured data about proposal votes including:
    - Final state (passed/failed/active)
    - Choices and scores (for multi-option votes like elections)
    - Winner marked with 🏆 for closed proposals
    
    Use this tool for:
    - "Who won the X election?"
    - "Did proposal Y pass?"
    - "What were the voting results for Z?"
    - "How many votes did the OpCo election get?"
    
    Search cascade: AND keywords -> OR keywords -> regex -> semantic
    """
    
    name: str = "proposal_results"
    description: str = """Look up proposal voting OUTCOMES and RESULTS.
Returns: state (passed/failed), choices with vote counts, winner identification.

Use for questions about:
- Who won/got elected
- Did a proposal pass or fail
- What were the voting results
- How many votes did each option receive

Input: query (topic to search), optional dao_id, optional state filter
Example: proposal_results(query="OpCo election", dao_id="arbitrumfoundation.eth")"""
    args_schema: Type[BaseModel] = ProposalResultsInput
    
    def _run_tool(
        self,
        query: str,
        dao_id: str = "",
        state: str = "",
        limit: int = 5,
        **kwargs: Any,
    ) -> str:
        """Execute proposal results lookup."""
        limit = max(1, min(10, limit))
        
        try:
            # Convert empty strings to None
            results = self._search_proposal_results(
                query=query,
                dao_id=dao_id if dao_id else None,
                state=state if state else None,
                limit=limit,
            )
            
            if not results:
                return f"No proposal results found for '{query}'" + (f" in {dao_id}" if dao_id else "")
            
            return self._format_results(results, query)
            
        except Exception as e:
            logger.error(f"[ProposalResultsTool] Error: {e}", exc_info=True)
            return f"Error searching proposal results: {str(e)}"
    
    def _search_proposal_results(
        self,
        query: str,
        dao_id: Optional[str],
        state: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Search for proposal results using cascading strategy.
        
        Search cascade:
        1. Proposal ID exact match (BIP-821, AIP-123 patterns)
        2. AND keyword search (all terms must match)
        3. OR keyword search (any term matches)
        4. Regex pattern search (PostgreSQL ~* operator)
        5. Semantic search (embedding-based, last resort)
        """
        pool = get_connection_pool()
        conn = pool.get_connection()
        
        try:
            cursor = conn.cursor()
            
            # Build search conditions - escape single quotes
            safe_query = query.replace("'", "''")
            search_terms = safe_query.split()
            
            # DAO filter
            dao_filter = ""
            if dao_id:
                safe_dao = dao_id.replace("'", "''")
                dao_filter = f" AND (dao_id = '{safe_dao}' OR dao_id ILIKE '%{safe_dao}%')"
            
            # State filter
            state_filter = ""
            if state:
                safe_state = state.replace("'", "''")
                state_filter = f" AND LOWER(state) = LOWER('{safe_state}')"
            
            # 1. For proposal ID queries (BIP-821, AIP-123), try exact title match first
            if is_proposal_id_query(query):
                logger.info(f"[ProposalResultsTool] Step 1: Proposal ID query '{query}', trying exact title match")
                exact_title_where = f"(title ILIKE '%{safe_query}%' OR title ~* '\\[?{safe_query}\\]?')"
                results = self._execute_search(cursor, exact_title_where, dao_filter, state_filter, limit)
                if results:
                    logger.info(f"[ProposalResultsTool] Found {len(results)} results via proposal ID match")
                    return self._enrich_results(cursor, results)
            
            # 2. AND keyword search (all terms must match)
            logger.info(f"[ProposalResultsTool] Step 2: AND keyword search for terms: {search_terms}")
            and_conditions = [f"title ILIKE '%{term}%'" for term in search_terms]
            and_where = " AND ".join(and_conditions) if and_conditions else "TRUE"
            results = self._execute_search(cursor, and_where, dao_filter, state_filter, limit)
            if results:
                logger.info(f"[ProposalResultsTool] Found {len(results)} results via AND keyword match")
                return self._enrich_results(cursor, results)
            
            # 3. OR keyword search (any term matches)
            logger.info(f"[ProposalResultsTool] Step 3: OR keyword search for terms: {search_terms}")
            or_conditions = [f"title ILIKE '%{term}%'" for term in search_terms]
            or_where = "(" + " OR ".join(or_conditions) + ")" if or_conditions else "TRUE"
            results = self._execute_search(cursor, or_where, dao_filter, state_filter, limit)
            if results:
                logger.info(f"[ProposalResultsTool] Found {len(results)} results via OR keyword match")
                return self._enrich_results(cursor, results)
            
            # 4. Regex pattern search (PostgreSQL ~* operator - case insensitive)
            logger.info(f"[ProposalResultsTool] Step 4: Regex pattern search for: {search_terms}")
            # Build regex pattern: term1|term2|term3
            regex_pattern = "|".join(search_terms)
            regex_where = f"title ~* '{regex_pattern}'"
            results = self._execute_search(cursor, regex_where, dao_filter, state_filter, limit)
            if results:
                logger.info(f"[ProposalResultsTool] Found {len(results)} results via regex match")
                return self._enrich_results(cursor, results)
            
            # 5. Semantic search (last resort)
            logger.info(f"[ProposalResultsTool] Step 5: Semantic search for: {query}")
            results = self._semantic_search(query, dao_id, state, limit)
            if results:
                logger.info(f"[ProposalResultsTool] Found {len(results)} results via semantic search")
                return results
            
            logger.info(f"[ProposalResultsTool] No results found after all search strategies")
            return []
            
        finally:
            pool.return_connection(conn)
    
    def _execute_search(
        self,
        cursor,
        title_where: str,
        dao_filter: str,
        state_filter: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Execute keyword-based search on both snapshot.proposallist and unified_proposals."""
        results = []
        
        # Query snapshot.proposallist first (has choices/scores arrays)
        snapshot_sql = f"""
            SELECT 
                'snapshot' as source,
                proposal_id,
                dao_id,
                title,
                state,
                choices,
                scores,
                scores_total,
                to_timestamp(created) as created_at,
                to_timestamp(ends) as ends_at,
                quorum,
                link
            FROM snapshot.proposallist
            WHERE {title_where} {dao_filter} {state_filter}
            ORDER BY created DESC
            LIMIT {limit}
        """
        
        try:
            cursor.execute(snapshot_sql)
            columns = [desc[0] for desc in cursor.description]
            snapshot_rows = cursor.fetchall()
            results = [dict(zip(columns, row)) for row in snapshot_rows]
        except Exception as e:
            logger.warning(f"[ProposalResultsTool] Snapshot query failed: {e}")
        
        # If not enough results, also check unified_proposals for Tally data
        if len(results) < limit:
            remaining = limit - len(results)
            
            unified_sql = f"""
                SELECT 
                    source,
                    proposal_id,
                    dao_id,
                    title,
                    state,
                    choices,
                    scores,
                    scores_total,
                    created_at,
                    ends_at,
                    quorum,
                    topic_id as discourse_topic_id,
                    link
                FROM internal.unified_proposal_embeddings
                WHERE source != 'snapshot' 
                  AND {title_where} {dao_filter} {state_filter}
                ORDER BY created_at DESC
                LIMIT {remaining}
            """
            
            try:
                cursor.execute(unified_sql)
                columns = [desc[0] for desc in cursor.description]
                unified_rows = cursor.fetchall()
                results.extend([dict(zip(columns, row)) for row in unified_rows])
            except Exception as e:
                logger.warning(f"[ProposalResultsTool] Unified proposals query failed: {e}")
        
        return results
    
    def _semantic_search(
        self,
        query: str,
        dao_id: Optional[str],
        state: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Use semantic search via database_client as last resort."""
        try:
            client = self._get_db_client()
            
            # Search proposals using semantic search
            semantic_results = client.search_proposals(
                query=query,
                dao_id=dao_id,
                state=state,
                limit=limit,
            )
            
            if not semantic_results:
                return []
            
            # Convert semantic results to the format expected by this tool
            # Need to enrich with choices/scores from snapshot if available
            pool = get_connection_pool()
            conn = pool.get_connection()
            
            try:
                cursor = conn.cursor()
                enriched_results = []
                
                for sr in semantic_results:
                    prop_id = sr.get('proposal_id')
                    source = sr.get('source', 'snapshot')
                    
                    if source == 'snapshot' and prop_id:
                        # Try to get full data from snapshot.proposallist
                        safe_prop_id = prop_id.replace("'", "''")
                        sql = f"""
                            SELECT 
                                'snapshot' as source,
                                proposal_id,
                                dao_id,
                                title,
                                state,
                                choices,
                                scores,
                                scores_total,
                                to_timestamp(created) as created_at,
                                to_timestamp(ends) as ends_at,
                                quorum,
                                link
                            FROM snapshot.proposallist
                            WHERE proposal_id = '{safe_prop_id}'
                            LIMIT 1
                        """
                        cursor.execute(sql)
                        columns = [desc[0] for desc in cursor.description]
                        row = cursor.fetchone()
                        if row:
                            enriched_results.append(dict(zip(columns, row)))
                            continue
                    
                    # Use the semantic result as-is with proper field mapping
                    enriched_results.append({
                        'source': source,
                        'proposal_id': prop_id,
                        'dao_id': sr.get('dao_id'),
                        'title': sr.get('title'),
                        'state': sr.get('state'),
                        'choices': sr.get('choices'),
                        'scores': sr.get('scores'),
                        'scores_total': sum(int(s) for s in sr.get('scores') if (isinstance(s, int) or (isinstance(s, str) and s.isdigit()))),
                        'created_at': sr.get('created_at'),
                        'ends_at': sr.get('ends_at'),
                        'quorum': None,
                        'link': sr.get('link'),
                        'discourse_topic_id': sr.get('discourse_topic_id'),
                    })
                
                # Enrich with votelist data
                return self._enrich_results(cursor, enriched_results)
                
            finally:
                pool.return_connection(conn)
                
        except Exception as e:
            logger.error(f"[ProposalResultsTool] Semantic search failed: {e}", exc_info=True)
            return []
    
    def _enrich_results(
        self,
        cursor,
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Enrich results with vote data from votelist when scores are missing."""
        for result in results:
            scores_total = result.get('scores_total')
            if not scores_total or float(scores_total or 0) == 0:
                prop_id = result.get('proposal_id')
                source = result.get('source', 'snapshot')
                dao_id = result.get('dao_id', 'TRUE')
                if prop_id:
                    vote_data = self._get_votes_for_proposal(cursor, prop_id, source, dao_id)
                    if vote_data:
                        result.update(vote_data)
        return results
    
    def _get_votes_for_proposal(
        self,
        cursor,
        proposal_id: str,
        source: str,
        dao_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get aggregated vote counts from votelist for a proposal.
        
        Used when snapshot.proposallist scores are missing/zero.
        """
        safe_prop_id = proposal_id.replace("'", "''")
        safe_dao_id = dao_id.replace("'", "''")
        
        # On-chain proposal IDs often start at 1 and are reused across many DAOs
        # Note: Added dao_id filter to ensure we only get votes for the correct DAO
        # First get total count and VP
        count_sql = f"""
        SELECT 
            COUNT(*) as vote_count,
            COALESCE(SUM(vp), 0) as total_vp
        FROM internal.unified_votelist
        WHERE proposal = '{safe_prop_id}'
            AND (
                space ILIKE '%{safe_dao_id}%'
                OR dao_name ILIKE '%{safe_dao_id}%'
            )
        """
        
        try:
            cursor.execute(count_sql)
            count_row = cursor.fetchone()
            
            if not count_row or not count_row[0] or count_row[0] == 0:
                return None
            
            vote_count, total_vp = count_row
            
            # Get vote breakdown by choice
            breakdown_sql = f"""
                SELECT 
                    COALESCE(choice::text, 'Unknown') as choice_key,
                    COUNT(*) as num_votes,
                    COALESCE(SUM(vp), 0) as choice_vp
                FROM internal.unified_votelist
                WHERE proposal = '{safe_prop_id}'
                  AND (
                      space ILIKE '%{safe_dao_id}%'
                      OR dao_name ILIKE '%{safe_dao_id}%'
                  )
                GROUP BY choice
                ORDER BY choice_vp DESC
            """
            cursor.execute(breakdown_sql)
            breakdown_rows = cursor.fetchall()
            
            choice_breakdown = {}
            for row in breakdown_rows:
                choice_key, num_votes, choice_vp = row
                choice_breakdown[str(choice_key)] = float(choice_vp or 0)
            
            logger.info(f"[ProposalResultsTool] Found {vote_count} votes from votelist for {proposal_id}")
            
            return {
                "scores_total": float(total_vp or 0),
                "vote_count": vote_count,
                "choice_breakdown": choice_breakdown,
                "has_votelist_data": True,
            }
        except Exception as e:
            logger.warning(f"[ProposalResultsTool] Error getting votes for {proposal_id}: {e}")
        
        return None
    
    def _format_results(self, results: List[Dict[str, Any]], query: str) -> str:
        """Format proposal results into readable output with winner identification."""
        # Prepare preview data for frontend cards
        preview_data = []
        for r in results:
            state = r.get('state', 'unknown')
            source = r.get('source', 'unknown')
            dao = r.get('dao_id', '')
            prop_id = r.get('proposal_id', '')
            
            # Build link
            link = r.get('link')
            if not link:
                if source == 'snapshot' and dao and prop_id:
                    link = f"https://snapshot.org/#/{dao}/proposal/{prop_id}"
                elif source == 'tally' and dao and prop_id:
                    link = f"https://www.tally.xyz/gov/{dao}/proposal/{prop_id}"
            
            preview_data.append({
                "id": prop_id,
                "title": r.get('title', 'Untitled'),
                "source": source,
                "dao_id": dao,
                "state": state,
                # "for_votes": r.get('for_votes'),  # maker for, aga, abs null only if we have multiple options
                # "against_votes": r.get('against_votes'), # add abstain 

                "choices": r.get('choices'),
                "scores": r.get('scores'),
                "scores_total": r.get('scores_total'),
                "vote_count": r.get('vote_count'),
                "choice_breakdown": r.get('choice_breakdown'),
                "created_at": str(r.get('created_at'))[:10] if r.get('created_at') else None,
                "link": link,
            })
    # choices and scores same  or dived sep for
        output_parts = [f"**Proposal Results for '{query}':**\n"]
        
        for i, r in enumerate(results, 1):
            # Basic info
            output_parts.append(f"\n### {i}. {r.get('title', 'Untitled')}")
            output_parts.append(f"- **Source**: {r.get('source', 'unknown').capitalize()}")
            output_parts.append(f"- **DAO**: {r.get('dao_id', 'N/A')}")
            
            # State with interpretation
            state = r.get('state', 'unknown')
            state_display = self._interpret_state(state)
            output_parts.append(f"- **Status**: {state_display}")
            
            # Dates
            created = r.get('created_at')
            if created:
                output_parts.append(f"- **Created**: {str(created)[:10]}")
            
            ends = r.get('ends_at')
            if ends:
                output_parts.append(f"- **Voting Ended**: {str(ends)[:10]}")
            
            # Check if we have vote data from votelist (enriched)
            choice_breakdown = r.get('choice_breakdown')
            vote_count = r.get('vote_count')
            
            if choice_breakdown and isinstance(choice_breakdown, dict):
                # Use enriched votelist data
                output_parts.append("\n**Voting Results** (from individual votes):")
                total_vp = sum(float(v or 0) for v in choice_breakdown.values())
                
                # Sort by voting power
                sorted_choices = sorted(
                    choice_breakdown.items(), 
                    key=lambda x: float(x[1] or 0), 
                    reverse=True
                )
                
                for choice_key, vp in sorted_choices:
                    pct = (float(vp or 0) / total_vp * 100) if total_vp > 0 else 0
                    output_parts.append(f"  - **Choice {choice_key}**: {self._format_number(vp)} ({pct:.1f}%)")
                
                if vote_count:
                    output_parts.append(f"  - **Vote Count**: {vote_count} voters")
            
            # Check if this is an election/multi-choice (has choices array)
            elif r.get('choices') and r.get('scores'):
                choices = r.get('choices')
                scores = r.get('scores')
                if len(choices) > 0:
                    output_parts.append("\n**Voting Results:**")
                    self._format_choices_scores(output_parts, choices, scores, state)
            else:
                # Fall back to for/against format (Tally data)
                for_votes = r.get('for_votes')
                against_votes = r.get('against_votes')
                abstain_votes = r.get('abstain_votes')
                
                if for_votes is not None or against_votes is not None:
                    output_parts.append("\n**Voting Results:**")
                    self._format_for_against(output_parts, for_votes, against_votes, abstain_votes, state)
            
            # Total votes
            scores_total = r.get('scores_total')
            if scores_total:
                output_parts.append(f"- **Total Voting Power**: {self._format_number(scores_total)}")
            
            # Quorum
            quorum = r.get('quorum')
            if quorum and float(quorum) > 0:
                output_parts.append(f"- **Quorum**: {self._format_number(quorum)}")
            
            # Link
            link = r.get('link')
            if link:
                output_parts.append(f"- **Link**: [{link}]({link})")
            else:
                # Construct link
                source = r.get('source', '')
                dao = r.get('dao_id', '')
                prop_id = r.get('proposal_id', '')
                if source == 'snapshot' and dao and prop_id:
                    output_parts.append(f"- **Link**: [View on Snapshot](https://snapshot.org/#/{dao}/proposal/{prop_id})")
                elif source == 'tally' and dao and prop_id:
                    output_parts.append(f"- **Link**: [View on Tally](https://www.tally.xyz/gov/{dao}/proposal/{prop_id})")
            
            output_parts.append(f"- **Proposal ID**: `{r.get('proposal_id', 'N/A')}`")
        
        # Combine preview block with text summary
        preview_block = self._format_preview_block("proposal", preview_data)
        return preview_block + "\n\n" + "\n".join(output_parts)
    
    def _format_choices_scores(
        self, 
        output_parts: List[str], 
        choices: List[str], 
        scores: List[float], 
        state: str
    ) -> None:
        """Format multi-choice voting results with winner identification."""
        # Handle array types from PostgreSQL
        if isinstance(choices, str):
            choices = choices.strip('{}').split(',') if choices.startswith('{') else [choices]
        if isinstance(scores, str):
            scores_str = scores.strip('{}')
            scores = [float(s.strip()) if s.strip() else 0 for s in scores_str.split(',')]
        
        if not isinstance(choices, (list, tuple)):
            choices = list(choices) if choices else []
        if not isinstance(scores, (list, tuple)):
            scores = list(scores) if scores else []
        
        if len(choices) != len(scores) or len(choices) == 0:
            return
        
        # Calculate total
        total = sum(float(s) for s in scores if s)
        
        # Sort by score descending
        pairs = sorted(zip(choices, scores), key=lambda x: float(x[1]) if x[1] else 0, reverse=True)
        
        # Identify winner (first place after sorting) for closed votes
        is_closed = state and state.lower() in ('closed', 'executed', 'succeeded', 'defeated')
        winner_choice = pairs[0][0] if pairs and is_closed and float(pairs[0][1]) > 0 else None
        
        for choice, score in pairs:
            score_val = float(score) if score else 0
            pct = (score_val / total * 100) if total > 0 else 0
            
            # Mark winner
            winner_marker = " 🏆 **WINNER**" if choice == winner_choice else ""
            output_parts.append(f"  - **{choice}**: {self._format_number(score_val)} ({pct:.1f}%){winner_marker}")
    
    def _format_for_against(
        self,
        output_parts: List[str],
        for_votes: Optional[float],
        against_votes: Optional[float],
        abstain_votes: Optional[float],
        state: str,
    ) -> None:
        """Format for/against/abstain voting results."""
        for_val = float(for_votes) if for_votes else 0
        against_val = float(against_votes) if against_votes else 0
        abstain_val = float(abstain_votes) if abstain_votes else 0
        
        total = for_val + against_val + abstain_val
        
        # Check if value looks like wei (very large number)
        if for_val >= 1e18:
            for_val = for_val / 1e18
            against_val = against_val / 1e18
            abstain_val = abstain_val / 1e18
            total = total / 1e18
        
        is_closed = state and state.lower() in ('closed', 'executed', 'succeeded', 'defeated')
        passed = for_val > against_val
        
        for_pct = (for_val / total * 100) if total > 0 else 0
        against_pct = (against_val / total * 100) if total > 0 else 0
        abstain_pct = (abstain_val / total * 100) if total > 0 else 0
        
        for_marker = " 🏆 **PASSED**" if is_closed and passed else ""
        against_marker = " ❌ **REJECTED**" if is_closed and not passed else ""
        
        output_parts.append(f"  - **For**: {self._format_number(for_val)} ({for_pct:.1f}%){for_marker}")
        output_parts.append(f"  - **Against**: {self._format_number(against_val)} ({against_pct:.1f}%){against_marker}")
        if abstain_val > 0:
            output_parts.append(f"  - **Abstain**: {self._format_number(abstain_val)} ({abstain_pct:.1f}%)")
    
    def _format_number(self, value: Any) -> str:
        """Format large numbers for readability."""
        if value is None:
            return "N/A"
        try:
            v = float(value)
            if v >= 1_000_000_000:
                return f"{v/1_000_000_000:.2f}B"
            elif v >= 1_000_000:
                return f"{v/1_000_000:.2f}M"
            elif v >= 1_000:
                return f"{v/1_000:.1f}K"
            else:
                return f"{v:,.0f}"
        except (ValueError, TypeError):
            return str(value)
    
    def _interpret_state(self, state: str) -> str:
        """Interpret proposal state into user-friendly display."""
        if not state:
            return "Unknown"
        
        state_lower = state.lower()
        
        if state_lower in ('closed', 'executed', 'succeeded'):
            return f"✅ {state.upper()} (Completed)"
        elif state_lower in ('defeated', 'failed', 'rejected'):
            return f"❌ {state.upper()} (Failed)"
        elif state_lower in ('active', 'pending'):
            return f"🔄 {state.upper()} (In Progress)"
        elif state_lower in ('canceled', 'cancelled'):
            return f"⛔ CANCELED"
        else:
            return state.upper()
