"""Voting tools for Research Agent.

Searches individual vote records, voter stats, and voting power trends.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from .base import ResearchBaseTool
from .database_client import ResearchDatabaseClient
from .schemas.common_schemas import (
    DATE_DESCRIPTION,
    ProposalVoteStatsInput,
    TopVotersInput,
    VoterStatsInput,
    VotingPowerTrendsInput,
)


class VotesSearchInput(BaseModel):
    """Input for votes lookup."""
    proposal_id: str = Field("", description="Filter by proposal ID (get from snapshot_proposals or tally_proposals). Leave empty to search all.")
    voter: str = Field("", description="Filter by voter address (Ethereum address). Leave empty to search all.")
    dao_id: str = Field("", description="Filter by DAO identifier (space_id for Snapshot, tally_id for on-chain). Leave empty for all.")
    start_date: str = Field("", description=f"Filter votes cast after this date. {DATE_DESCRIPTION} Leave empty for no filter.")
    end_date: str = Field("", description=f"Filter votes cast before this date. {DATE_DESCRIPTION} Leave empty for no filter.")
    limit: int = Field(50, ge=1, le=200, description="Maximum results to return")


class VotesLookupTool(ResearchBaseTool):
    """Lookup individual vote records.
    
    Queries the unified_votelist table for voting data.
    Can filter by proposal, voter address, or DAO.
    """
    
    name: str = "votes_lookup"
    description: str = """Lookup individual vote records from governance votes.

INPUT:
- proposal_id: Filter by proposal ID (get ID from snapshot_proposals or tally_proposals first)
- voter: Filter by voter/delegate address (Ethereum address, use ens_resolver to convert ENS names)
- dao_id: Filter by DAO identifier
- start_date/end_date: Filter by date range (YYYY-MM-DD format)
- limit: Max results (default 50)

RETURNS: Vote records with voter, choice, voting power, reason, and timestamp.

USE FOR: Delegate analysis, voting patterns, voter history, proposal vote breakdown, delegate rewards analysis.

TIPS:
- To analyze a specific proposal, first get proposal_id from snapshot_proposals or tally_proposals
- For delegate activity, filter by voter address
- Use ens_resolver to convert ENS names (e.g., 'vitalik.eth') to addresses
- Combine with date filters to analyze voting over time periods
- For delegate rewards, look at voting power and participation rates"""
    args_schema: Type[BaseModel] = VotesSearchInput
    _db_client: Optional[ResearchDatabaseClient] = None
    
    def _get_db_client(self) -> ResearchDatabaseClient:
        """Get or create the database client."""
        if self._db_client is None:
            self._db_client = ResearchDatabaseClient()
        return self._db_client
    
    def _run_tool(
        self,
        proposal_id: str = "",
        voter: str = "",
        dao_id: str = "",
        start_date: str = "",
        end_date: str = "",
        limit: int = 50,
        **kwargs: Any,
    ) -> str:
        """Execute votes lookup."""
        client = self._get_db_client()
        
        # Allow date-only queries for DAO activity over time
        if not proposal_id and not voter and not dao_id and not start_date and not end_date:
            return "Please provide at least one filter: proposal_id, voter address, dao_id, or date range"
        
        # Convert empty strings to None
        results = client.search_votes(
            proposal_id=proposal_id if proposal_id else None,
            voter=voter if voter else None,
            dao_id=dao_id if dao_id else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            limit=limit,
        )
        
        if not results:
            filter_msg = []
            if proposal_id:
                filter_msg.append(f"proposal '{proposal_id}'")
            if voter:
                filter_msg.append(f"voter '{voter}'")
            if dao_id:
                filter_msg.append(f"DAO '{dao_id}'")
            if start_date or end_date:
                filter_msg.append(f"date range {start_date or 'any'} to {end_date or 'now'}")
            msg = f"No votes found for " + " and ".join(filter_msg)
            msg += "\n\nTIP: Try getting proposal IDs from snapshot_proposals or tally_proposals first."
            return msg
        
        # Compute aggregates
        total_vp_sum = sum(float(v.get("vp", 0) or 0) for v in results)
        daos_voted_set = set(v.get("dao_id") for v in results if v.get("dao_id"))
        
        # Prepare preview data for frontend cards
        recent_votes = []
        for v in results[:8]:
            choice_val = v.get("choice", "Unknown")
            # Determine if "for" or "against" style vote
            choice_str = str(choice_val).lower() if choice_val else ""
            is_for = choice_str in ("1", "for", "yes", "yae") or "for" in choice_str
            recent_votes.append({"choice": "for" if is_for else "against"})
        
        preview_data = {
            "voter": voter if voter else None,
            "proposal_id": proposal_id if proposal_id else None,
            "dao_id": dao_id if dao_id else None,
            "total_votes": len(results),
            "total_vp": total_vp_sum,
            "daos_count": len(daos_voted_set),
            "recent_votes": recent_votes,
        }
        
        # Format results
        output = [f"Found {len(results)} votes:\n"]
        
        # Aggregate stats if filtering by proposal
        if proposal_id:
            total_vp = 0
            choice_breakdown = {}
            for v in results:
                vp = float(v.get("vp", 0) or 0)
                total_vp += vp
                choice = str(v.get("choice", "Unknown"))
                choice_breakdown[choice] = choice_breakdown.get(choice, 0) + vp
            
            output.append("**Vote Breakdown:**")
            for choice, vp in sorted(choice_breakdown.items(), key=lambda x: x[1], reverse=True):
                pct = (vp / total_vp * 100) if total_vp > 0 else 0
                output.append(f"  - {choice}: {self._format_vp(vp)} ({pct:.1f}%)")
            output.append(f"  - Total VP: {self._format_vp(total_vp)}")
            output.append("")
        
        # Aggregate stats if filtering by voter (delegate analysis)
        if voter and not proposal_id:
            output.append("**Delegate Activity Summary:**")
            output.append(f"  - Total votes cast: {len(results)}")
            output.append(f"  - Total voting power used: {self._format_vp(total_vp_sum)}")
            output.append(f"  - DAOs participated in: {len(daos_voted_set)}")
            output.append("")
        
        # Show individual votes
        output.append("**Individual Votes:**")
        for i, vote in enumerate(results[:20], 1):  # Limit display
            voter_addr = vote.get("voter", "Unknown")
            choice = vote.get("choice", "Unknown")
            vp = vote.get("vp", 0)
            reason = vote.get("reason", "")
            created = vote.get("created", "")
            vote_dao = vote.get("dao_id", "")
            
            # Truncate voter address for display
            voter_display = f"{voter_addr[:8]}...{voter_addr[-6:]}" if len(voter_addr) > 16 else voter_addr
            
            line = f"{i}. {voter_display} voted **{choice}** with {self._format_vp(vp)}"
            if vote_dao and not dao_id:
                line += f" ({vote_dao})"
            if reason:
                line += f"\n   Reason: {reason[:100]}..."
            output.append(line)
        
        if len(results) > 20:
            output.append(f"\n... and {len(results) - 20} more votes")
        
        # Combine preview block with text summary
        preview_block = self._format_preview_block("votes", preview_data)
        return preview_block + "\n\n" + "\n".join(output)
    
    def _format_vp(self, vp: Any) -> str:
        """Format voting power for readability."""
        if vp is None:
            return "0"
        try:
            v = float(vp)
            if v >= 1_000_000:
                return f"{v/1_000_000:.2f}M"
            elif v >= 1_000:
                return f"{v/1_000:.1f}K"
            else:
                return f"{v:.2f}"
        except (ValueError, TypeError):
            return str(vp)


def _format_vp_helper(vp: Any) -> str:
    """Format voting power for readability (standalone function)."""
    if vp is None:
        return "0"
    try:
        v = float(vp)
        if v >= 1_000_000:
            return f"{v/1_000_000:.2f}M"
        elif v >= 1_000:
            return f"{v/1_000:.1f}K"
        else:
            return f"{v:.2f}"
    except (ValueError, TypeError):
        return str(vp)


class VoterStatsTool(ResearchBaseTool):
    """Get aggregated voting statistics for a specific voter/delegate.
    
    Analyzes a voter's activity across DAOs including participation rate,
    total voting power used, and choice patterns.
    """
    
    name: str = "voter_stats"
    description: str = """Get voting statistics for a specific delegate/voter.

INPUT:
- voter: Voter address (required). Use ens_resolver to convert ENS names.
- dao_id: Filter to specific DAO (optional)
- start_date/end_date: Filter by date range (YYYY-MM-DD)

RETURNS: Total votes, total VP used, DAOs participated in, choice patterns, recent activity.

USE FOR: Delegate analysis, participation rates, voting patterns, delegate rewards evaluation."""
    args_schema: Type[BaseModel] = VoterStatsInput
    _db_client: Optional[ResearchDatabaseClient] = None
    
    def _get_db_client(self) -> ResearchDatabaseClient:
        if self._db_client is None:
            self._db_client = ResearchDatabaseClient()
        return self._db_client
    
    def _run_tool(
        self,
        voter: str,
        dao_id: str = "",
        start_date: str = "",
        end_date: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute voter stats query."""
        client = self._get_db_client()
        
        stats = client.get_voter_stats(
            voter=voter,
            dao_id=dao_id if dao_id else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
        )
        
        if stats["total_votes"] == 0:
            return f"No voting activity found for voter '{voter}'" + (f" in DAO '{dao_id}'" if dao_id else "")
        
        output = [f"## Voter Statistics: {voter[:10]}...{voter[-6:]}\n"]
        
        if dao_id:
            output.append(f"**DAO**: {dao_id}")
        if start_date or end_date:
            output.append(f"**Period**: {start_date or 'all time'} to {end_date or 'now'}")
        output.append("")
        
        output.append("### Summary")
        output.append(f"- **Total Votes Cast**: {int(stats['total_votes']):,}")
        output.append(f"- **Total Voting Power Used**: {_format_vp_helper(stats['total_vp'])}")
        output.append(f"- **DAOs Participated In**: {int(stats['daos_count'])}")
        
        # Format timestamps (convert Decimal to int for fromtimestamp)
        if stats.get("first_vote"):
            first_date = datetime.fromtimestamp(int(stats["first_vote"])).strftime("%Y-%m-%d")
            output.append(f"- **First Vote**: {first_date}")
        if stats.get("last_vote"):
            last_date = datetime.fromtimestamp(int(stats["last_vote"])).strftime("%Y-%m-%d")
            output.append(f"- **Last Vote**: {last_date}")
        output.append("")
        
        # DAOs breakdown
        if stats.get("daos"):
            output.append("### DAOs")
            for dao in stats["daos"][:5]:
                dao_name = dao.get("dao_id", "Unknown")
                vote_count = dao.get("vote_count", 0)
                dao_vp = dao.get("total_vp", 0)
                output.append(f"- **{dao_name}**: {vote_count} votes, {_format_vp_helper(dao_vp)} VP")
            output.append("")
        
        # Recent votes
        if stats.get("recent_votes"):
            output.append("### Recent Votes")
            for i, vote in enumerate(stats["recent_votes"], 1):
                proposal = vote.get("proposal", "")[:20] + "..."
                choice = vote.get("choice", "Unknown")
                vp = vote.get("vp", 0)
                vote_dao = vote.get("dao_id", "")
                output.append(f"{i}. {proposal} - **{choice}** with {_format_vp_helper(vp)} ({vote_dao})")
        
        preview_data = {
            "voter": voter,
            "total_votes": stats["total_votes"],
            "total_vp": stats["total_vp"],
            "daos_count": stats["daos_count"],
        }
        preview_block = self._format_preview_block("voter-stats", preview_data)
        return preview_block + "\n\n" + "\n".join(output)


class ProposalVoteStatsTool(ResearchBaseTool):
    """Get detailed voting breakdown for a specific proposal.
    
    Analyzes vote distribution, top voters, and participation for a proposal.
    """
    
    name: str = "proposal_vote_stats"
    description: str = """Get detailed voting statistics for a specific proposal.

INPUT:
- proposal_id: Proposal ID (required). Get from snapshot_proposals or tally_proposals.
- dao_id: DAO identifier (optional, helps narrow search)

RETURNS: Total voters, total VP, vote breakdown by choice, top voters, VP distribution.

USE FOR: Proposal analysis, vote breakdown, identifying key voters, participation metrics."""
    args_schema: Type[BaseModel] = ProposalVoteStatsInput
    _db_client: Optional[ResearchDatabaseClient] = None
    
    def _get_db_client(self) -> ResearchDatabaseClient:
        if self._db_client is None:
            self._db_client = ResearchDatabaseClient()
        return self._db_client
    
    def _run_tool(
        self,
        proposal_id: str,
        dao_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute proposal vote stats query."""
        client = self._get_db_client()
        
        stats = client.get_proposal_vote_stats(
            proposal_id=proposal_id,
            dao_id=dao_id if dao_id else None,
        )
        
        if stats["total_voters"] == 0:
            return f"No votes found for proposal '{proposal_id}'" + (f" in DAO '{dao_id}'" if dao_id else "")
        
        output = [f"## Proposal Vote Analysis\n"]
        output.append(f"**Proposal**: {proposal_id[:30]}...")
        if dao_id:
            output.append(f"**DAO**: {dao_id}")
        output.append("")
        
        output.append("### Summary")
        output.append(f"- **Total Voters**: {int(stats['total_voters']):,}")
        output.append(f"- **Total Voting Power**: {_format_vp_helper(stats['total_vp'])}")
        output.append(f"- **Average VP per Voter**: {_format_vp_helper(stats['avg_vp'])}")
        output.append(f"- **Median VP**: {_format_vp_helper(stats['median_vp'])}")
        output.append(f"- **Max VP (Single Voter)**: {_format_vp_helper(stats['max_vp'])}")
        output.append("")
        
        # Vote breakdown
        if stats.get("vote_breakdown"):
            output.append("### Vote Breakdown")
            total_vp = stats["total_vp"]
            for choice_data in stats["vote_breakdown"]:
                choice = choice_data.get("choice_raw", "Unknown")
                voters = choice_data.get("voter_count", 0)
                vp = float(choice_data.get("total_vp", 0) or 0)
                pct = (vp / total_vp * 100) if total_vp > 0 else 0
                output.append(f"- **{choice}**: {voters} voters, {_format_vp_helper(vp)} VP ({pct:.1f}%)")
            output.append("")
        
        # Top voters
        if stats.get("top_voters"):
            output.append("### Top Voters by VP")
            for i, voter in enumerate(stats["top_voters"][:5], 1):
                addr = voter.get("voter", "Unknown")
                addr_display = f"{addr[:8]}...{addr[-6:]}" if len(addr) > 16 else addr
                choice = voter.get("choice", "Unknown")
                vp = voter.get("vp", 0)
                reason = voter.get("reason", "")
                line = f"{i}. **{addr_display}** - {choice} with {_format_vp_helper(vp)}"
                if reason:
                    line += f"\n   Reason: {reason[:80]}..."
                output.append(line)
        
        preview_data = {
            "proposal_id": proposal_id,
            "total_voters": stats["total_voters"],
            "total_vp": stats["total_vp"],
            "vote_breakdown": stats.get("vote_breakdown", []),
        }
        preview_block = self._format_preview_block("proposal-vote-stats", preview_data)
        return preview_block + "\n\n" + "\n".join(output)


class VotingPowerTrendsTool(ResearchBaseTool):
    """Track voting power changes over time for one or more voters.
    
    Shows how voters' VP has changed across votes, useful for tracking
    delegation changes and VP growth. Supports comparing multiple addresses.
    """
    
    name: str = "voting_power_trends"
    description: str = """Track voting power changes over time for one or more voters.

INPUT:
- voters: Voter address(es) - single address or comma-separated list (e.g., '0x123...,0x456...')
- dao_id: Filter to specific DAO (optional)
- start_date/end_date: Filter period (default: 6 months)

RETURNS: VP per vote over time, monthly averages, VP change percentage for each voter.

USE FOR: Tracking delegation changes, VP growth/decline, comparing multiple delegates.

TIPS:
- Use ens_resolver first to convert ENS names to addresses
- For comparing delegates, provide multiple addresses separated by commas
- Results show each voter's stats side by side for easy comparison"""
    args_schema: Type[BaseModel] = VotingPowerTrendsInput
    _db_client: Optional[ResearchDatabaseClient] = None
    
    def _get_db_client(self) -> ResearchDatabaseClient:
        if self._db_client is None:
            self._db_client = ResearchDatabaseClient()
        return self._db_client
    
    def _format_voter_stats(self, voter: str, stats: Dict[str, Any], dao_id: str, start_date: str, end_date: str) -> List[str]:
        """Format stats for a single voter."""
        output = []
        
        voter_display = f"{voter[:10]}...{voter[-6:]}" if len(voter) > 18 else voter
        output.append(f"## Voting Power Trends: {voter_display}\n")
        
        if dao_id:
            output.append(f"**DAO**: {dao_id}")
        if start_date or end_date:
            output.append(f"**Period**: {start_date or 'all time'} to {end_date or 'now'}")
        output.append("")
        
        output.append("### Summary")
        output.append(f"- **Total Votes**: {stats['total_votes']}")
        if stats.get("first_vp"):
            output.append(f"- **First Recorded VP**: {_format_vp_helper(stats['first_vp'])}")
        if stats.get("last_vp"):
            output.append(f"- **Most Recent VP**: {_format_vp_helper(stats['last_vp'])}")
        if stats.get("vp_change_pct") is not None:
            change = stats["vp_change_pct"]
            direction = "+" if change >= 0 else ""
            output.append(f"- **VP Change**: {direction}{change:.1f}%")
        output.append("")
        
        # Monthly trends
        if stats.get("monthly_trends"):
            output.append("### Monthly Trends")
            for month_data in stats["monthly_trends"][:6]:
                month = month_data.get("month", "")
                if month:
                    month_str = month.strftime("%Y-%m") if isinstance(month, datetime) else str(month)[:7]
                    vote_count = month_data.get("vote_count", 0)
                    avg_vp = month_data.get("avg_vp", 0)
                    max_vp = month_data.get("max_vp", 0)
                    output.append(f"- **{month_str}**: {vote_count} votes, avg VP: {_format_vp_helper(avg_vp)}, max: {_format_vp_helper(max_vp)}")
            output.append("")
        
        # Recent votes with VP
        if stats.get("votes"):
            output.append("### Recent Votes (VP Over Time)")
            for i, vote in enumerate(stats["votes"][-10:], 1):  # Last 10
                proposal = vote.get("proposal", "")[:20] + "..."
                vp = vote.get("vp", 0)
                vote_dao = vote.get("dao_id", "")
                created = vote.get("created")
                date_str = ""
                if created:
                    date_str = datetime.fromtimestamp(int(created)).strftime("%Y-%m-%d")
                output.append(f"{i}. {date_str} | {_format_vp_helper(vp)} VP | {vote_dao} | {proposal}")
        
        return output
    
    def _run_tool(
        self,
        voters: str,
        dao_id: str = "",
        start_date: str = "",
        end_date: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute voting power trends query for one or more voters."""
        client = self._get_db_client()
        
        # Parse voters - support comma-separated list
        voter_list = [v.strip() for v in voters.split(",") if v.strip()]
        
        if not voter_list:
            return "Please provide at least one voter address."
        
        # Single voter - use original method for backward compatibility
        if len(voter_list) == 1:
            voter = voter_list[0]
            stats = client.get_voting_power_trends(
                voter=voter,
                dao_id=dao_id if dao_id else None,
                start_date=start_date if start_date else None,
                end_date=end_date if end_date else None,
            )
            
            if stats["total_votes"] == 0:
                return f"No voting activity found for voter '{voter}'" + (f" in DAO '{dao_id}'" if dao_id else "")
            
            output = self._format_voter_stats(voter, stats, dao_id, start_date, end_date)
            
            preview_data = {
                "voter": voter,
                "total_votes": stats["total_votes"],
                "first_vp": stats.get("first_vp"),
                "last_vp": stats.get("last_vp"),
                "vp_change_pct": stats.get("vp_change_pct"),
            }
            preview_block = self._format_preview_block("vp-trends", preview_data)
            return preview_block + "\n\n" + "\n".join(output)
        
        # Multiple voters - use batch query
        all_stats = client.get_voting_power_trends_multi(
            voters=voter_list,
            dao_id=dao_id if dao_id else None,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
        )
        
        if not all_stats:
            return f"No voting activity found for any of the {len(voter_list)} voters" + (f" in DAO '{dao_id}'" if dao_id else "")
        
        # Build comparison summary
        output = [f"# Voting Power Comparison: {len(voter_list)} Voters\n"]
        
        if dao_id:
            output.append(f"**DAO**: {dao_id}")
        if start_date or end_date:
            output.append(f"**Period**: {start_date or 'all time'} to {end_date or 'now'}")
        output.append("")
        
        # Summary table
        output.append("## Quick Comparison\n")
        output.append("| Voter | Total Votes | First VP | Latest VP | Change |")
        output.append("|-------|-------------|----------|-----------|--------|")
        
        preview_voters = []
        voters_with_data = 0
        
        for voter in voter_list:
            voter_key = voter.lower()
            stats = all_stats.get(voter_key, {})
            
            voter_display = f"{voter[:8]}...{voter[-4:]}" if len(voter) > 14 else voter
            total_votes = stats.get("total_votes", 0)
            first_vp = stats.get("first_vp")
            last_vp = stats.get("last_vp")
            change_pct = stats.get("vp_change_pct")
            
            first_str = _format_vp_helper(first_vp) if first_vp else "N/A"
            last_str = _format_vp_helper(last_vp) if last_vp else "N/A"
            change_str = f"{'+' if change_pct >= 0 else ''}{change_pct:.1f}%" if change_pct is not None else "N/A"
            
            output.append(f"| {voter_display} | {total_votes} | {first_str} | {last_str} | {change_str} |")
            
            if total_votes > 0:
                voters_with_data += 1
            
            preview_voters.append({
                "voter": voter,
                "total_votes": total_votes,
                "first_vp": first_vp,
                "last_vp": last_vp,
                "vp_change_pct": change_pct,
            })
        
        output.append("")
        
        if voters_with_data == 0:
            output.append("**No voting activity found for any of the provided addresses.**")
        else:
            # Detailed stats for each voter with activity
            output.append("---\n")
            for voter in voter_list:
                voter_key = voter.lower()
                stats = all_stats.get(voter_key, {})
                
                if stats.get("total_votes", 0) > 0:
                    voter_output = self._format_voter_stats(voter, stats, dao_id, start_date, end_date)
                    output.extend(voter_output)
                    output.append("\n---\n")
        
        preview_data = {
            "voters": preview_voters,
            "total_voters": len(voter_list),
            "voters_with_activity": voters_with_data,
        }
        preview_block = self._format_preview_block("vp-trends-multi", preview_data)
        return preview_block + "\n\n" + "\n".join(output)


def _format_tenure(first_vote_ts: Any) -> str:
    """Format first vote timestamp as tenure string (e.g., 'Since 2021-08')."""
    if not first_vote_ts:
        return "N/A"
    try:
        from datetime import datetime
        ts = int(first_vote_ts)
        dt = datetime.fromtimestamp(ts)
        return f"Since {dt.strftime('%Y-%m')}"
    except (ValueError, TypeError):
        return "N/A"


def _format_last_active(last_vote_ts: Any) -> str:
    """Format last vote timestamp as last active string (e.g., 'Last: 2024-12-15')."""
    if not last_vote_ts:
        return "N/A"
    try:
        from datetime import datetime
        ts = int(last_vote_ts)
        dt = datetime.fromtimestamp(ts)
        return f"Last: {dt.strftime('%Y-%m-%d')}"
    except (ValueError, TypeError):
        return "N/A"


def _format_vp_change(vp_change_pct: Any) -> str:
    """Format VP change percentage with +/- sign."""
    if vp_change_pct is None:
        return "N/A"
    try:
        pct = float(vp_change_pct)
        if pct >= 0:
            return f"+{pct:.1f}%"
        else:
            return f"{pct:.1f}%"
    except (ValueError, TypeError):
        return "N/A"


class TopVotersTool(ResearchBaseTool):
    """Get top voters/delegates leaderboard for a DAO.
    
    Ranks voters by activity (vote count), current voting power, average VP, or tenure.
    """
    
    name: str = "top_voters"
    description: str = """Get top voters/delegates leaderboard for a DAO.

INPUT:
- dao_id: DAO identifier (required). Use dao_catalog to find the snapshot_id.
- metric: "votes" (count), "voting_power" (current VP), "avg_vp" (avg VP per vote), "tenure" (longest active)
- start_date/end_date: Filter period
- limit: Number of top voters (default 20)

RETURNS: Ranked list of top voters with:
- Vote count and percentage
- Current VP (from latest vote) and percentage
- Average VP per vote
- VP change since first vote (+/-%)
- Tenure (first vote date)
- Governance concentration stats

USE FOR: Finding key delegates, governance concentration analysis, leaderboards, tracking delegate growth.

IMPORTANT: VP shown is the voter's CURRENT voting power (from their most recent vote), not cumulative."""
    args_schema: Type[BaseModel] = TopVotersInput
    _db_client: Optional[ResearchDatabaseClient] = None
    
    def _get_db_client(self) -> ResearchDatabaseClient:
        if self._db_client is None:
            self._db_client = ResearchDatabaseClient()
        return self._db_client
    
    def _run_tool(
        self,
        dao_id: str,
        metric: str = "votes",
        start_date: str = "",
        end_date: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> str:
        """Execute top voters query."""
        client = self._get_db_client()
        
        stats = client.get_top_voters(
            dao_id=dao_id,
            metric=metric,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            limit=limit,
        )
        
        if stats["total_votes"] == 0:
            return f"No voting activity found for DAO '{dao_id}'"
        
        # Metric labels
        metric_labels = {
            "votes": "Vote Count",
            "voting_power": "Current Voting Power",
            "avg_vp": "Average VP per Vote",
            "tenure": "Tenure (Longest Active)"
        }
        ranking_label = metric_labels.get(metric, "Voting Power")
        
        output = [f"## Top Voters in {dao_id}\n"]
        output.append(f"**Ranked by**: {ranking_label}")
        if start_date or end_date:
            output.append(f"**Period**: {start_date or 'all time'} to {end_date or 'now'}")
        output.append("")
        
        # DAO Summary
        output.append("### DAO Summary")
        output.append(f"- **Total Votes Cast**: {int(stats['total_votes']):,}")
        total_latest_vp = stats.get('total_latest_vp', 0)
        output.append(f"- **Combined Current VP** (top {limit}): {_format_vp_helper(total_latest_vp)}")
        output.append("")
        
        # Concentration Stats
        top_voters = stats.get("top_voters", [])
        if top_voters and total_latest_vp > 0:
            output.append("### Concentration")
            # Calculate top 5 and top 10 concentration
            top_5_vp = sum(float(v.get("latest_vp", 0) or 0) for v in top_voters[:5])
            top_10_vp = sum(float(v.get("latest_vp", 0) or 0) for v in top_voters[:10])
            top_5_pct = (top_5_vp / total_latest_vp * 100) if total_latest_vp > 0 else 0
            top_10_pct = (top_10_vp / total_latest_vp * 100) if total_latest_vp > 0 else 0
            output.append(f"- Top 5 control **{top_5_pct:.1f}%** of VP")
            if len(top_voters) >= 10:
                output.append(f"- Top 10 control **{top_10_pct:.1f}%** of VP")
            output.append("")
        
        output.append(f"### Top {len(top_voters)} Voters")
        
        # Batch resolve ENS names for all addresses
        addresses = [v.get("voter", "") for v in top_voters if v.get("voter")]
        ens_map = client.batch_resolve_ens(addresses)
        
        for i, voter in enumerate(top_voters, 1):
            addr = voter.get("voter", "Unknown")
            addr_lower = addr.lower() if addr else ""
            ens_name = ens_map.get(addr_lower)
            
            # Format display: show ENS name if available, otherwise truncated address
            if ens_name:
                addr_display = f"{ens_name}"
                addr_suffix = f" ({addr[:6]}...{addr[-4:]})" if len(addr) > 12 else ""
            else:
                addr_display = f"{addr[:8]}...{addr[-6:]}" if len(addr) > 16 else addr
                addr_suffix = ""
            
            vote_count = voter.get("vote_count", 0)
            latest_vp = voter.get("latest_vp", 0)  # Current VP from most recent vote
            avg_vp = voter.get("avg_vp", 0)
            vp_change_pct = voter.get("vp_change_pct")
            first_vote = voter.get("first_vote")
            last_vote = voter.get("last_vote")
            vote_pct = voter.get("vote_pct", 0)
            vp_pct = voter.get("vp_pct", 0)
            
            output.append(f"**{i}. {addr_display}**{addr_suffix}")
            
            # Always show core stats
            output.append(f"   - Current VP: {_format_vp_helper(latest_vp)} ({vp_pct:.1f}%)")
            output.append(f"   - Votes: {int(vote_count):,} ({vote_pct:.1f}%) | Avg VP: {_format_vp_helper(avg_vp)}")
            output.append(f"   - VP Change: {_format_vp_change(vp_change_pct)} | {_format_tenure(first_vote)} | {_format_last_active(last_vote)}")
        
        preview_data = {
            "dao_id": dao_id,
            "total_votes": stats["total_votes"],
            "total_latest_vp": total_latest_vp,
            "metric": metric,
            "top_voters": [
                {
                    "voter": v.get("voter", ""),
                    "ens_name": ens_map.get(v.get("voter", "").lower()),
                    "vote_count": v.get("vote_count", 0),
                    "latest_vp": v.get("latest_vp", 0),
                    "avg_vp": v.get("avg_vp", 0),
                    "vp_change_pct": v.get("vp_change_pct"),
                    "first_vote": v.get("first_vote"),
                    "last_vote": v.get("last_vote"),
                }
                for v in top_voters[:5]
            ],
        }
        preview_block = self._format_preview_block("top-voters", preview_data)
        return preview_block + "\n\n" + "\n".join(output)
