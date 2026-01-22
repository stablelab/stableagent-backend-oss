"""
LangChain tools for Applications & Review Management.

Provides tools for listing applicants, viewing submissions, searching applications,
and voting on submissions with approval requirements.
"""
from typing import Any, List, Optional, Type

from pydantic import BaseModel

from src.utils.logger import logger

from .base import APIBaseTool
from .schemas import (
    GetMyVotesInput,
    GetReviewQueueInput,
    GetSubmissionDetailsInput,
    GetSubmissionForReviewInput,
    ListApplicantsInput,
    ListProgramApplicantsInput,
    SearchApplicationsInput,
    TiebreakerInput,
    UpdateApplicantStatusInput,
    VoteInput,
)
from .reviews_api_client import ReviewsAPIClient


# ==================
# Base Tool Class
# ==================

class ReviewAPIBaseTool(APIBaseTool):
    """Base class for review API tools. Extends APIBaseTool with Reviews-specific client."""
    
    org_slug: str = ""
    _client: Optional[ReviewsAPIClient] = None

    def _get_client(self) -> ReviewsAPIClient:
        """Get shared Reviews API client instance."""
        if self._client is None:
            self._client = ReviewsAPIClient()
        return self._client


# ==================
# Read-Only Tools
# ==================

class ListAllApplicantsTool(ReviewAPIBaseTool):
    """Tool for listing all applicants across all programs."""
    
    name: str = "list_all_applicants"
    description: str = """List all applicants across all grant programs in the organization.
Returns: list of applicants with user info, team, form, program, status, and submission title.
Optionally filter by status (draft, submitted, under_review, approved, rejected)."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = ListApplicantsInput
    
    def _run_tool(self, status_filter: Optional[str] = None) -> str:
        """List all applicants."""
        client = self._get_client()
        result = client.list_all_applicants(self.auth_token, self.org_slug)
        
        applicants = result.applicants
        
        # Apply status filter if provided
        if status_filter:
            applicants = [a for a in applicants if a.status == status_filter]
        
        if not applicants:
            if status_filter:
                return f"No applicants found with status '{status_filter}'."
            return "No applicants found in this organization."
        
        # Group by program for better readability
        by_program: dict = {}
        for app in applicants:
            prog_name = app.programName or f"Program {app.programId}"
            if prog_name not in by_program:
                by_program[prog_name] = []
            by_program[prog_name].append(app)
        
        output = f"Found {len(applicants)} applicant(s) across {len(by_program)} program(s):\n\n"
        
        for prog_name, prog_applicants in by_program.items():
            output += f"## {prog_name}\n"
            for app in prog_applicants:
                title = app.submissionTitle or "(no title)"
                team = app.teamName or f"Team {app.teamId}"
                user = app.handle or app.email or f"User {app.userId}"
                output += f"- **{title}** by {team} ({user})\n"
                output += f"  Status: {app.status}"
                if app.submittedAt:
                    output += f" | Submitted: {app.submittedAt[:10]}"
                output += f"\n  Form ID: {app.formId}, Team ID: {app.teamId}, User ID: {app.userId}\n"
            output += "\n"
        
        return output


class ListProgramApplicantsTool(ReviewAPIBaseTool):
    """Tool for listing applicants for a specific program."""
    
    name: str = "list_program_applicants"
    description: str = """List all applicants for a specific grant program.
Input: program_id (int) - The program ID to list applicants for.
Returns: list of applicants with user info, team, form, and status."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = ListProgramApplicantsInput
    
    def _run_tool(self, program_id: int) -> str:
        """List program applicants."""
        client = self._get_client()
        result = client.list_program_applicants(program_id, self.auth_token, self.org_slug)
        
        applicants = result.applicants
        if not applicants:
            return f"No applicants found for program ID {program_id}."
        
        output = f"Found {len(applicants)} applicant(s) for program ID {program_id}:\n\n"
        
        for app in applicants:
            team = app.teamName or f"Team {app.teamId}"
            user = app.handle or app.email or f"User {app.userId}"
            output += f"- **{team}** ({user})\n"
            output += f"  Status: {app.status} | Form: {app.formName or app.formId}\n"
            output += f"  User ID: {app.userId}, Team ID: {app.teamId}, Form ID: {app.formId}\n"
        
        return output


class GetSubmissionDetailsTool(ReviewAPIBaseTool):
    """Tool for getting full submission details with all form answers."""
    
    name: str = "get_submission_details"
    description: str = """Get the full submission details including all form answers.
Input: form_id, user_id, team_id (all int) - Identifies the specific submission.
Returns: complete submission with form config, user/team info, and all answers.
Use this to see what an applicant submitted."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetSubmissionDetailsInput
    
    def _run_tool(self, form_id: int, user_id: int, team_id: int) -> str:
        """Get submission details."""
        client = self._get_client()
        result = client.get_submission_details(form_id, user_id, team_id, self.auth_token, self.org_slug)
        
        sub = result.submission
        output = f"# Submission Details\n\n"
        
        # Form info
        if sub.form:
            output += f"**Form:** {sub.form.name or 'Unnamed'} (ID: {sub.form.id})\n"
            if sub.form.program_name:
                output += f"**Program:** {sub.form.program_name}\n"
        
        # Team info
        if sub.team:
            output += f"**Team:** {sub.team.name or 'Unknown'} (ID: {sub.team.id})\n"
            if sub.team.members:
                output += f"**Members:** {len(sub.team.members)}\n"
                for m in sub.team.members[:5]:  # Limit to first 5
                    output += f"  - {m.handle or m.email} ({m.role})\n"
        
        # User info
        if sub.user:
            output += f"**Submitted by:** {sub.user.handle or sub.user.email} (ID: {sub.user.id})\n"
        
        output += f"**Status:** {sub.status}\n"
        if sub.submitted_at:
            output += f"**Submitted:** {sub.submitted_at}\n"
        
        # Form answers
        output += "\n## Form Answers\n\n"
        if sub.answers:
            for field_id, value in sub.answers.items():
                # Skip internal fields
                if field_id.startswith("_"):
                    continue
                # Format the value
                if isinstance(value, dict):
                    value_str = str(value.get("value", value))
                elif isinstance(value, list):
                    value_str = ", ".join(str(v) for v in value)
                else:
                    value_str = str(value) if value else "(empty)"
                
                # Truncate long values
                if len(value_str) > 500:
                    value_str = value_str[:500] + "..."
                
                output += f"**{field_id}:** {value_str}\n\n"
        else:
            output += "(No answers found)\n"
        
        # AI Evaluation if present
        if result.evaluation:
            ev = result.evaluation
            output += f"\n## AI Evaluation\n\n"
            output += f"**Score:** {ev.normalized_score:.1f}/100\n"
            if ev.reasoning:
                output += f"**Summary:** {ev.reasoning[:300]}...\n" if len(ev.reasoning or "") > 300 else f"**Summary:** {ev.reasoning}\n"
        
        return output


class GetReviewQueueTool(ReviewAPIBaseTool):
    """Tool for getting the reviewer's queue of submissions to review."""
    
    name: str = "get_review_queue"
    description: str = """Get the review queue - submissions awaiting your review.
Optional filters:
- program_id: Filter to a specific program
- pending_only: Only show pending (not yet resolved) submissions
- ties_only: Only show tied submissions (for tiebreakers)
Returns: list of submissions with vote counts and your current vote status."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetReviewQueueInput
    
    def _run_tool(
        self,
        program_id: Optional[int] = None,
        pending_only: bool = False,
        ties_only: bool = False,
    ) -> str:
        """Get review queue."""
        client = self._get_client()
        result = client.get_review_queue(
            self.auth_token,
            self.org_slug,
            program_id=program_id,
            pending_only=pending_only,
            ties_only=ties_only,
        )
        
        submissions = result.submissions
        if not submissions:
            if ties_only:
                return "No tied submissions awaiting tiebreaker decision."
            if pending_only:
                return "No pending submissions to review."
            return "Your review queue is empty."
        
        # Group by program for cleaner display
        by_program: dict = {}
        for sub in submissions:
            prog_name = sub.programName or f"Program {sub.programId}"
            if prog_name not in by_program:
                by_program[prog_name] = []
            by_program[prog_name].append(sub)
        
        output = f"📋 **Review Queue** — {len(submissions)} submission(s)\n\n"
        
        for prog_name, prog_subs in by_program.items():
            output += f"### {prog_name}\n\n"
            
            for sub in prog_subs:
                title = sub.submissionTitle or "(Untitled)"
                team = sub.teamName or f"Team {sub.teamId}"
                vc = sub.voteCounts
                
                # Status indicator
                if sub.reviewStatus == "awaiting_tiebreaker":
                    status_icon = "⚖️"
                elif sub.reviewStatus == "approved":
                    status_icon = "✅"
                elif sub.reviewStatus == "rejected":
                    status_icon = "❌"
                else:
                    status_icon = "⏳"
                
                # Your vote indicator
                if sub.myVote:
                    my_vote = "✅" if sub.myVote.vote == "approve" else "❌"
                else:
                    my_vote = "—"
                
                # Build compact line
                output += f"{status_icon} **{title}**\n"
                output += f"   {team}"
                
                # Key metrics inline
                metrics = []
                if sub.requestedAmount:
                    metrics.append(f"${sub.requestedAmount:,.0f}")
                if sub.aiScore is not None:
                    metrics.append(f"AI {sub.aiScore:.0f}")
                metrics.append(f"✅{vc.approvesCount}/❌{vc.rejectsCount}")
                metrics.append(f"You: {my_vote}")
                
                output += f" — {' | '.join(metrics)}\n"
                output += f"   `{sub.id}`\n\n"
        
        return output


class GetSubmissionForReviewTool(ReviewAPIBaseTool):
    """Tool for getting a single submission for review by its UUID."""
    
    name: str = "get_submission_for_review"
    description: str = """Get detailed review information for a specific submission including the full application.
Input: submission_id (string UUID) - The submission ID from the review queue.
Returns: full application answers, voting status, and review context."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetSubmissionForReviewInput
    
    def _run_tool(self, submission_id: str) -> str:
        """Get submission for review with full application details."""
        import json
        
        client = self._get_client()
        result = client.get_submission_for_review(submission_id, self.auth_token, self.org_slug)
        
        sub = result.submission
        title = sub.submissionTitle or "(Untitled Application)"
        team = sub.teamName or f"Team {sub.teamId}"
        program = sub.programName or f"Program {sub.programId}"
        user = sub.userHandle or sub.userEmail or f"User {sub.userId}"
        
        # Fetch full application details for preview data
        key_answers = []
        milestones = []
        data_sources = []
        full_sub = None
        full_result = None
        
        try:
            full_result = client.get_submission_details(
                sub.formId, sub.userId, sub.teamId,
                self.auth_token, self.org_slug
            )
            full_sub = full_result.submission
            
            # Get form config to get proper field labels
            form_config = full_sub.form.config if full_sub.form and full_sub.form.config else None
            field_labels = {}
            
            if form_config and "steps" in form_config:
                for step in form_config.get("steps", []):
                    step_title = step.get("title", "")
                    for field in step.get("fields", []):
                        field_id = field.get("id")
                        field_labels[field_id] = {
                            "label": field.get("label", field_id),
                            "step": step_title,
                            "type": field.get("type", "text"),
                        }
            
            # Extract key answers for preview (first 6 non-internal fields)
            if full_sub.answers:
                for field_id, value in full_sub.answers.items():
                    if field_id.startswith("_"):
                        continue
                    if len(key_answers) >= 6:
                        break
                    
                    field_info = field_labels.get(field_id, {"label": field_id, "type": "text"})
                    
                    # Format the value
                    if isinstance(value, dict):
                        display_value = str(value.get("value", value))
                    elif isinstance(value, list):
                        display_value = ", ".join(str(v) for v in value) if value else "—"
                    elif value is None or value == "":
                        display_value = "—"
                    else:
                        display_value = str(value)
                    
                    key_answers.append({
                        "label": field_info["label"],
                        "value": display_value[:200] + "..." if len(display_value) > 200 else display_value,
                        "type": field_info["type"],
                    })
            
            # Extract milestones if available
            if hasattr(full_sub, 'milestoneAnswers') and full_sub.milestoneAnswers:
                for m in full_sub.milestoneAnswers:
                    milestones.append({
                        "milestone_type": m.milestone_type if hasattr(m, 'milestone_type') else m.get("milestone_type", "custom"),
                        "title": m.title if hasattr(m, 'title') else m.get("title"),
                        "success_value": m.success_value if hasattr(m, 'success_value') else m.get("success_value"),
                        "status": m.status if hasattr(m, 'status') else m.get("status"),
                    })
            
            # Extract data sources if available
            if hasattr(full_sub, 'data_sources') and full_sub.data_sources:
                for ds in full_sub.data_sources:
                    data_sources.append({
                        "type": ds.type if hasattr(ds, 'type') else ds.get("type", "unknown"),
                        "value": ds.value if hasattr(ds, 'value') else ds.get("value", ""),
                        "label": ds.label if hasattr(ds, 'label') else ds.get("label"),
                    })
                    
        except Exception as e:
            logger.warning(f"Could not fetch full submission details for preview: {e}")
        
        # Build preview data JSON block for frontend
        preview_data = {
            "__preview_type": "application",
            "submissionId": sub.id,
            "title": sub.submissionTitle,
            "teamName": sub.teamName,
            "programName": sub.programName,
            "formName": sub.formName,
            "submittedAt": sub.submittedAt,
            "requestedAmount": sub.requestedAmount,
            "aiScore": sub.aiScore,
            "reviewStatus": sub.reviewStatus,
            "voteCounts": {
                "approvesCount": sub.voteCounts.approvesCount,
                "rejectsCount": sub.voteCounts.rejectsCount,
                "votesNeeded": sub.voteCounts.votesNeeded,
                "totalVotes": sub.voteCounts.totalVotes,
            },
            "myVote": {"vote": sub.myVote.vote} if sub.myVote else None,
            "keyAnswers": key_answers,
            "milestones": milestones if milestones else None,
            "dataSources": data_sources if data_sources else None,
        }
        
        # Start output with JSON preview block (hidden from display, parsed by frontend)
        output = f"```application-preview\n{json.dumps(preview_data)}\n```\n\n"
        
        # Human-readable header
        output += f"# {title}\n\n"
        output += f"📋 **{team}** → {program}\n"
        output += f"👤 Submitted by {user}"
        if sub.submittedAt:
            output += f" on {sub.submittedAt[:10]}"
        output += "\n"
        
        # Compact key info line
        key_info = []
        if sub.requestedAmount:
            key_info.append(f"💰 ${sub.requestedAmount:,.0f}")
        if sub.aiScore is not None:
            key_info.append(f"🤖 AI: {sub.aiScore:.0f}/100")
        key_info.append(f"📊 {sub.reviewStatus}")
        output += " | ".join(key_info) + "\n"
        
        # Compact voting status (single line unless there are votes to show)
        vc = sub.voteCounts
        vote_str = f"✅ {vc.approvesCount}" if vc.approvesCount else "✅ 0"
        vote_str += f" / ❌ {vc.rejectsCount}" if vc.rejectsCount else " / ❌ 0"
        vote_str += f" (need {vc.votesNeeded})"
        
        if sub.myVote:
            my_vote_icon = "✅" if sub.myVote.vote == "approve" else "❌"
            vote_str += f" — You: {my_vote_icon}"
        else:
            vote_str += " — You: ⏳ pending"
        
        output += f"🗳️ {vote_str}\n"
        
        # Application content section
        output += "\n---\n\n## Application Content\n\n"
        
        if full_sub:
            # Get form config to get proper field labels
            form_config = full_sub.form.config if full_sub.form and full_sub.form.config else None
            field_labels = {}
            
            if form_config and "steps" in form_config:
                for step in form_config.get("steps", []):
                    step_title = step.get("title", "")
                    for field in step.get("fields", []):
                        field_id = field.get("id")
                        field_labels[field_id] = {
                            "label": field.get("label", field_id),
                            "step": step_title,
                            "type": field.get("type", "text"),
                        }
            
            # Group answers by step
            answers_by_step: dict = {}
            if full_sub.answers:
                for field_id, value in full_sub.answers.items():
                    # Skip internal fields
                    if field_id.startswith("_"):
                        continue
                    
                    field_info = field_labels.get(field_id, {"label": field_id, "step": "Other", "type": "text"})
                    step_name = field_info["step"] or "Application"
                    
                    if step_name not in answers_by_step:
                        answers_by_step[step_name] = []
                    
                    # Format the value
                    if isinstance(value, dict):
                        display_value = str(value.get("value", value))
                    elif isinstance(value, list):
                        if all(isinstance(v, str) for v in value):
                            display_value = ", ".join(value)
                        else:
                            display_value = ", ".join(str(v) for v in value)
                    elif value is None or value == "":
                        display_value = "—"
                    else:
                        display_value = str(value)
                    
                    # Truncate very long values
                    if len(display_value) > 800:
                        display_value = display_value[:800] + "... [truncated]"
                    
                    answers_by_step[step_name].append({
                        "label": field_info["label"],
                        "value": display_value,
                        "type": field_info["type"],
                    })
            
            # Output answers grouped by step
            if answers_by_step:
                for step_name, fields in answers_by_step.items():
                    output += f"### {step_name}\n\n"
                    for field in fields:
                        # Multi-line values get their own block
                        if "\n" in field["value"] or len(field["value"]) > 200:
                            output += f"**{field['label']}:**\n{field['value']}\n\n"
                        else:
                            output += f"**{field['label']}:** {field['value']}\n"
                    output += "\n"
            else:
                output += "*No application answers available.*\n\n"
            
            # Milestones section if present
            if milestones:
                output += "---\n\n### 🎯 Milestones\n\n"
                for m in milestones:
                    m_type = m.get("milestone_type", "custom")
                    m_title = m.get("title") or m_type.upper()
                    m_value = m.get("success_value")
                    if m_value:
                        output += f"- **{m_title}**: Target ${m_value:,.0f}\n"
                    else:
                        output += f"- **{m_title}**\n"
                output += "\n"
            
            # Data sources section if present
            if data_sources:
                output += "---\n\n### 🔗 Data Sources\n\n"
                for ds in data_sources:
                    ds_type = ds.get("type", "unknown")
                    ds_label = ds.get("label") or ds_type
                    ds_value = ds.get("value", "")
                    # Truncate long values
                    if len(ds_value) > 50:
                        ds_value = ds_value[:50] + "..."
                    output += f"- **{ds_label}** ({ds_type}): `{ds_value}`\n"
                output += "\n"
            
            # AI Evaluation if present
            if full_result and full_result.evaluation:
                ev = full_result.evaluation
                output += f"---\n\n### 🤖 AI Evaluation\n"
                output += f"**Score:** {ev.normalized_score:.0f}/100\n"
                if ev.reasoning:
                    reasoning = ev.reasoning[:400] + "..." if len(ev.reasoning or "") > 400 else ev.reasoning
                    output += f"**Summary:** {reasoning}\n"
                
                # Criterion scores if available
                if ev.criterion_scores:
                    output += "\n**Criteria Breakdown:**\n"
                    for cs in ev.criterion_scores[:5]:  # Limit to top 5
                        name = cs.criterion_name or f"Criterion {cs.criterion_id}"
                        output += f"- {name}: {cs.raw_score:.0f}"
                        if cs.weight != 1.0:
                            output += f" (×{cs.weight})"
                        output += "\n"
                output += "\n"
        else:
            output += f"*Could not load full application content. Use `get_submission_details` with form_id={sub.formId}, user_id={sub.userId}, team_id={sub.teamId} for full details.*\n\n"
        
        # Show other votes only if they exist (compact)
        if sub.allVotes and len(sub.allVotes) > 0:
            output += "---\n\n### Other Reviewer Votes\n"
            for v in sub.allVotes:
                reviewer = v.reviewerHandle or v.reviewerEmail or f"Reviewer {v.reviewerId}"
                vote_icon = "✅" if v.vote == "approve" else "❌"
                output += f"- {vote_icon} **{reviewer}**"
                if v.comment:
                    comment_short = v.comment[:80] + "..." if len(v.comment) > 80 else v.comment
                    output += f": \"{comment_short}\""
                output += "\n"
        
        # Add submission ID at bottom for reference
        output += f"\n---\n*ID: `{sub.id}`*"
        
        return output


class GetMyVotesTool(ReviewAPIBaseTool):
    """Tool for getting the user's voting history."""
    
    name: str = "get_my_votes"
    description: str = """Get your voting history across all submissions.
Returns: list of your votes with submission context (form, program, team, outcome)."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = GetMyVotesInput
    
    def _run_tool(self) -> str:
        """Get my votes."""
        client = self._get_client()
        result = client.get_my_votes(self.auth_token, self.org_slug)
        
        votes = result.votes
        if not votes:
            return "You haven't voted on any submissions yet."
        
        output = f"Your voting history ({len(votes)} vote(s)):\n\n"
        
        for v in votes:
            team = v.teamName or "Unknown Team"
            program = v.programName or "Unknown Program"
            form = v.formName or "Unknown Form"
            
            output += f"- **{team}** ({program})\n"
            output += f"  Your vote: {v.vote} | Submission: {v.submissionStatus} | Review: {v.reviewStatus}\n"
            if v.comment:
                comment_short = v.comment[:80] + "..." if len(v.comment) > 80 else v.comment
                output += f"  Rationale: \"{comment_short}\"\n"
            output += f"  Voted: {v.voted_at[:10] if v.voted_at else 'Unknown'}\n"
        
        return output


class SearchApplicationsTool(ReviewAPIBaseTool):
    """Tool for searching applications by keyword - searches program names, form names, team names, and titles."""
    
    name: str = "search_applications"
    description: str = """Search applications by keyword - searches across program names, form names, team names, and submission titles.
Input: query (string) - Search term (e.g., 'bitcoin security', 'DeFi', 'NFT', 'Web3 Innovation')
Optional: program_id (int) - Limit search to a specific program
Returns: matching applications with relevance to the query.

Use this FIRST when user asks about applications by topic, program name, or keyword. Don't ask for clarification - just search."""
    requires_approval: bool = False
    args_schema: Type[BaseModel] = SearchApplicationsInput
    
    def _run_tool(self, query: str, program_id: Optional[int] = None) -> str:
        """Search applications by keyword."""
        client = self._get_client()
        
        # Get all applicants (or program-specific)
        if program_id:
            result = client.list_program_applicants(program_id, self.auth_token, self.org_slug)
        else:
            result = client.list_all_applicants(self.auth_token, self.org_slug)
        
        query_lower = query.lower()
        matches = []
        
        for app in result.applicants:
            # Check if query matches title, team name, or user info
            searchable = " ".join(filter(None, [
                app.submissionTitle,
                app.teamName,
                app.handle,
                app.email,
                app.formName,
                app.programName,
            ])).lower()
            
            if query_lower in searchable:
                matches.append(app)
        
        if not matches:
            scope = f" in program {program_id}" if program_id else ""
            return f"No applications found matching '{query}'{scope}."
        
        output = f"Found {len(matches)} application(s) matching '{query}':\n\n"
        
        for app in matches:
            title = app.submissionTitle or "(no title)"
            team = app.teamName or f"Team {app.teamId}"
            program = app.programName or f"Program {app.programId}"
            
            output += f"- **{title}** by {team}\n"
            output += f"  Program: {program} | Status: {app.status}\n"
            output += f"  Form ID: {app.formId}, Team ID: {app.teamId}, User ID: {app.userId}\n"
        
        return output


# ==================
# Mutating Tools (Require Approval)
# ==================

class VoteApproveTool(ReviewAPIBaseTool):
    """Tool for voting to approve a submission."""
    
    name: str = "vote_approve"
    description: str = """Vote to APPROVE a submission.
Input:
- submission_id (string UUID) - The submission to vote on
- comment (string, 5-500 chars) - Your rationale for approving
Requires user approval before the vote is submitted."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = VoteInput
    
    def _run_tool(self, submission_id: str, comment: str) -> str:
        """Vote to approve."""
        client = self._get_client()
        result = client.submit_vote(submission_id, "approve", comment, self.auth_token, self.org_slug)
        
        vc = result.voteCounts
        output = f"Successfully voted to **approve** submission `{submission_id}`.\n\n"
        output += f"**New review status:** {result.reviewStatus}\n"
        output += f"**Vote counts:** {vc.approvesCount} approve, {vc.rejectsCount} reject\n"
        
        if result.budgetWarning:
            output += f"\n⚠️ **Budget Warning:** {result.budgetWarning}\n"
        
        return output


class VoteRejectTool(ReviewAPIBaseTool):
    """Tool for voting to reject a submission."""
    
    name: str = "vote_reject"
    description: str = """Vote to REJECT a submission.
Input:
- submission_id (string UUID) - The submission to vote on
- comment (string, 5-500 chars) - Your rationale for rejecting
Requires user approval before the vote is submitted."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = VoteInput
    
    def _run_tool(self, submission_id: str, comment: str) -> str:
        """Vote to reject."""
        client = self._get_client()
        result = client.submit_vote(submission_id, "reject", comment, self.auth_token, self.org_slug)
        
        vc = result.voteCounts
        output = f"Successfully voted to **reject** submission `{submission_id}`.\n\n"
        output += f"**New review status:** {result.reviewStatus}\n"
        output += f"**Vote counts:** {vc.approvesCount} approve, {vc.rejectsCount} reject\n"
        
        return output


class TiebreakerApproveTool(ReviewAPIBaseTool):
    """Tool for tiebreaker to approve a tied submission."""
    
    name: str = "tiebreaker_approve"
    description: str = """Tiebreaker decision: APPROVE a tied submission.
Only available for designated tiebreakers when a submission has equal approve/reject votes.
Input:
- submission_id (string UUID) - The tied submission
- comment (string, 5-500 chars) - Your rationale
Requires user approval before the decision is submitted."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = TiebreakerInput
    
    def _run_tool(self, submission_id: str, comment: str) -> str:
        """Tiebreaker approve."""
        client = self._get_client()
        result = client.submit_tiebreaker(submission_id, "approve", comment, self.auth_token, self.org_slug)
        
        output = f"Tiebreaker decision: **APPROVED** submission `{submission_id}`.\n\n"
        output += f"**Final review status:** {result.reviewStatus}\n"
        
        return output


class TiebreakerRejectTool(ReviewAPIBaseTool):
    """Tool for tiebreaker to reject a tied submission."""
    
    name: str = "tiebreaker_reject"
    description: str = """Tiebreaker decision: REJECT a tied submission.
Only available for designated tiebreakers when a submission has equal approve/reject votes.
Input:
- submission_id (string UUID) - The tied submission
- comment (string, 5-500 chars) - Your rationale
Requires user approval before the decision is submitted."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = TiebreakerInput
    
    def _run_tool(self, submission_id: str, comment: str) -> str:
        """Tiebreaker reject."""
        client = self._get_client()
        result = client.submit_tiebreaker(submission_id, "reject", comment, self.auth_token, self.org_slug)
        
        output = f"Tiebreaker decision: **REJECTED** submission `{submission_id}`.\n\n"
        output += f"**Final review status:** {result.reviewStatus}\n"
        
        return output


class UpdateApplicantStatusTool(ReviewAPIBaseTool):
    """Tool for updating an applicant's status directly."""
    
    name: str = "update_applicant_status"
    description: str = """Directly update an applicant's status (bypass voting).
Use for admin overrides or when formal voting isn't required.
Input:
- program_id (int) - The program ID
- user_id (int) - The applicant's user ID
- form_id (int) - The form ID
- status (string) - New status: 'pending', 'approved', or 'rejected'
- team_id (int, optional) - Team ID if applicable
Requires user approval before the status is changed."""
    requires_approval: bool = True
    args_schema: Type[BaseModel] = UpdateApplicantStatusInput
    
    def _run_tool(
        self,
        program_id: int,
        user_id: int,
        form_id: int,
        status: str,
        team_id: Optional[int] = None,
    ) -> str:
        """Update applicant status."""
        client = self._get_client()
        result = client.update_applicant_status(
            program_id,
            user_id,
            form_id,
            status,
            self.auth_token,
            self.org_slug,
            team_id,
        )
        
        output = f"Successfully updated applicant status to **{result.status}**.\n"
        
        if result.projectCreated:
            output += f"\n✅ Project created (ID: {result.projectId})\n"
        elif result.error:
            output += f"\n⚠️ Note: {result.error}\n"
        
        return output


# ==================
# Tool Factory
# ==================

def create_review_tools(auth_token: str, org_slug: str = "") -> List[ReviewAPIBaseTool]:
    """
    Create all review management tools with the given auth token and org context.
    
    Args:
        auth_token: Privy authentication token
        org_slug: Organization slug
        
    Returns:
        List of review tool instances
    """
    tools = [
        # Read-only tools
        ListAllApplicantsTool(auth_token=auth_token, org_slug=org_slug),
        ListProgramApplicantsTool(auth_token=auth_token, org_slug=org_slug),
        GetSubmissionDetailsTool(auth_token=auth_token, org_slug=org_slug),
        GetReviewQueueTool(auth_token=auth_token, org_slug=org_slug),
        GetSubmissionForReviewTool(auth_token=auth_token, org_slug=org_slug),
        GetMyVotesTool(auth_token=auth_token, org_slug=org_slug),
        SearchApplicationsTool(auth_token=auth_token, org_slug=org_slug),
        # Mutating tools (require approval)
        VoteApproveTool(auth_token=auth_token, org_slug=org_slug),
        VoteRejectTool(auth_token=auth_token, org_slug=org_slug),
        TiebreakerApproveTool(auth_token=auth_token, org_slug=org_slug),
        TiebreakerRejectTool(auth_token=auth_token, org_slug=org_slug),
        UpdateApplicantStatusTool(auth_token=auth_token, org_slug=org_slug),
    ]
    
    return tools

