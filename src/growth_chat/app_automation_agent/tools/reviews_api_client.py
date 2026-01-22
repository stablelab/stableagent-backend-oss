"""
HTTP client for Applications & Reviews API endpoints.

Handles all API communication with proper authentication and error handling.
Extends BaseAPIClient.
"""
from typing import Any, Dict, Optional

import httpx

from .base_api_client import APIError, BaseAPIClient
from .schemas import (
    Applicant,
    ApplicantsListResponse,
    FormCriteria,
    FormCriteriaListResponse,
    GetSubmissionForReviewResponse,
    MyVotesResponse,
    ProgramStatsResponse,
    ReviewQueueResponse,
    ScoringRules,
    SubmissionForReview,
    SubmissionWithEvaluationResponse,
    TiebreakerResponse,
    UpdateStatusResponse,
    Vote,
    VoteCounts,
    VoteResponse,
    VoteWithContext,
    VoteWithReviewer,
)


class ReviewsAPIClient(BaseAPIClient):
    """Client for interacting with Applications & Reviews API endpoints."""
    
    def __init__(self, base_url: str = None):
        """
        Initialize the Reviews API client with a longer timeout.
        
        Args:
            base_url: Base URL for the API (default from GROWTH_BACKEND_URL env var)
        """
        # Longer timeout for review queue operations
        super().__init__(base_url=base_url, timeout=60.0)
    
    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        Handle API response with review-specific error messages.
        
        Extends base handler with user-friendly error messages for review operations.
        """
        if response.status_code == 204:
            return {"success": True}
        
        try:
            data = response.json()
        except Exception:
            data = {"error": "Failed to parse response", "raw": response.text}
        
        if response.status_code >= 400:
            error_msg = data.get("error", "Unknown error")
            if isinstance(data, dict) and "message" in data:
                error_msg = data["message"]
            
            # Provide user-friendly error messages for review operations
            if response.status_code == 400:
                details = data.get("details", {})
                if details:
                    error_msg = f"Invalid request: {details}"
                else:
                    error_msg = data.get("error", "Bad request")
            elif response.status_code == 401:
                error_msg = "Authentication required"
            elif response.status_code == 403:
                error_msg = data.get("error", "You don't have permission to perform this action")
            elif response.status_code == 404:
                error_msg = data.get("error", "Resource not found")
            elif response.status_code >= 500:
                error_msg = "Server error, please try again"
            
            raise APIError(error_msg, response.status_code, data)
        
        return data
    
    # ==================
    # Applicants Endpoints (from /programs)
    # ==================
    
    def list_all_applicants(
        self,
        auth_token: str,
        org_slug: Optional[str] = None,
    ) -> ApplicantsListResponse:
        """
        List all applicants across all programs in the organization.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            ApplicantsListResponse with list of all applicants
        """
        url = f"{self.base_url}/api/programs/all-applicants"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        applicants = []
        for app in data.get("applicants", []):
            applicants.append(Applicant(
                userId=app.get("userId"),
                email=app.get("email"),
                handle=app.get("handle"),
                teamId=app.get("teamId"),
                teamName=app.get("teamName"),
                formId=app.get("formId"),
                formName=app.get("formName"),
                programId=app.get("programId"),
                programName=app.get("programName"),
                status=app.get("status", "submitted"),
                submittedAt=app.get("submittedAt"),
                submissionTitle=app.get("submissionTitle"),
            ))
        
        return ApplicantsListResponse(applicants=applicants)
    
    def list_program_applicants(
        self,
        program_id: int,
        auth_token: str,
        org_slug: Optional[str] = None,
    ) -> ApplicantsListResponse:
        """
        List applicants for a specific program.
        
        Args:
            program_id: Program ID
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            ApplicantsListResponse with list of applicants for the program
        """
        url = f"{self.base_url}/api/programs/{program_id}/applicants"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        applicants = []
        for app in data.get("applicants", []):
            applicants.append(Applicant(
                userId=app.get("userId"),
                email=app.get("email"),
                handle=app.get("handle"),
                teamId=app.get("teamId"),
                teamName=app.get("teamName"),
                formId=app.get("formId"),
                formName=app.get("formName"),
                programId=program_id,
                status=app.get("status", "submitted"),
            ))
        
        return ApplicantsListResponse(applicants=applicants)
    
    def get_submission_details(
        self,
        form_id: int,
        user_id: int,
        team_id: int,
        auth_token: str,
        org_slug: Optional[str] = None,
    ) -> SubmissionWithEvaluationResponse:
        """
        Get full submission details with all form answers and optional AI evaluation.
        
        Args:
            form_id: Form ID
            user_id: User ID who submitted
            team_id: Team ID associated with submission
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            SubmissionWithEvaluationResponse with full submission and optional evaluation
        """
        url = f"{self.base_url}/api/programs/applicant-submission"
        params: Dict[str, Any] = {
            "formId": form_id,
            "userId": user_id,
            "teamId": team_id,
        }
        if org_slug:
            params["org"] = org_slug
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        return SubmissionWithEvaluationResponse(**data)
    
    def get_program_stats(
        self,
        program_id: int,
        auth_token: str,
        org_slug: Optional[str] = None,
    ) -> ProgramStatsResponse:
        """
        Get program statistics including applicant counts and budget.
        
        Args:
            program_id: Program ID
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            ProgramStatsResponse with stats and budget info
        """
        url = f"{self.base_url}/api/programs/{program_id}/stats"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        return ProgramStatsResponse(**data)
    
    def update_applicant_status(
        self,
        program_id: int,
        user_id: int,
        form_id: int,
        status: str,
        auth_token: str,
        org_slug: Optional[str] = None,
        team_id: Optional[int] = None,
    ) -> UpdateStatusResponse:
        """
        Update an applicant's status (approve, reject, etc.).
        
        Args:
            program_id: Program ID
            user_id: User ID of the applicant
            form_id: Form ID of the submission
            status: New status (pending, approved, rejected)
            auth_token: Privy authentication token
            org_slug: Organization slug
            team_id: Optional team ID
            
        Returns:
            UpdateStatusResponse with result
        """
        url = f"{self.base_url}/api/programs/{program_id}/applicants/{user_id}/status"
        params = {"org": org_slug} if org_slug else {}
        
        body: Dict[str, Any] = {
            "status": status,
            "formId": form_id,
        }
        if team_id is not None:
            body["teamId"] = team_id
        
        response = self.client.patch(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body,
        )
        data = self._handle_response(response)
        
        return UpdateStatusResponse(**data)
    
    # ==================
    # Reviews Endpoints
    # ==================
    
    def get_review_queue(
        self,
        auth_token: str,
        org_slug: Optional[str] = None,
        program_id: Optional[int] = None,
        pending_only: bool = False,
        ties_only: bool = False,
        resolved_only: bool = False,
    ) -> ReviewQueueResponse:
        """
        Get the review queue for the authenticated reviewer.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Organization slug
            program_id: Optional program ID to filter by
            pending_only: Only show pending submissions
            ties_only: Only show tied submissions (for tiebreakers)
            resolved_only: Only show resolved submissions
            
        Returns:
            ReviewQueueResponse with list of submissions to review
        """
        url = f"{self.base_url}/api/reviews/review-queue"
        params: Dict[str, Any] = {}
        if org_slug:
            params["org"] = org_slug
        if program_id is not None:
            params["programId"] = program_id
        if pending_only:
            params["pendingOnly"] = "true"
        if ties_only:
            params["tiesOnly"] = "true"
        if resolved_only:
            params["resolvedOnly"] = "true"
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        # Parse submissions
        submissions = []
        for sub in data.get("submissions", []):
            # Parse vote counts
            vote_counts_data = sub.get("voteCounts", {})
            vote_counts = VoteCounts(
                totalReviewers=vote_counts_data.get("totalReviewers", 0),
                votesNeeded=vote_counts_data.get("votesNeeded", 0),
                approvesCount=vote_counts_data.get("approvesCount", 0),
                rejectsCount=vote_counts_data.get("rejectsCount", 0),
                totalVotes=vote_counts_data.get("totalVotes", 0),
            )
            
            # Parse my vote if present
            my_vote = None
            if sub.get("myVote"):
                mv = sub["myVote"]
                my_vote = Vote(
                    id=mv.get("id"),
                    submission_id=mv.get("submission_id"),
                    reviewer_id=mv.get("reviewer_id"),
                    vote=mv.get("vote"),
                    comment=mv.get("comment"),
                    voted_at=mv.get("voted_at"),
                )
            
            # Parse all votes if present
            all_votes = None
            if sub.get("allVotes"):
                all_votes = []
                for v in sub["allVotes"]:
                    all_votes.append(VoteWithReviewer(
                        id=v.get("id"),
                        reviewerId=v.get("reviewerId"),
                        reviewerName=v.get("reviewerName"),
                        reviewerHandle=v.get("reviewerHandle"),
                        reviewerEmail=v.get("reviewerEmail"),
                        vote=v.get("vote"),
                        comment=v.get("comment"),
                        votedAt=v.get("votedAt"),
                    ))
            
            submissions.append(SubmissionForReview(
                id=sub.get("id"),
                formId=sub.get("formId"),
                formName=sub.get("formName"),
                programId=sub.get("programId"),
                programName=sub.get("programName"),
                teamId=sub.get("teamId"),
                teamName=sub.get("teamName"),
                submissionTitle=sub.get("submissionTitle"),
                userId=sub.get("userId"),
                userHandle=sub.get("userHandle"),
                userEmail=sub.get("userEmail"),
                status=sub.get("status"),
                reviewStatus=sub.get("reviewStatus"),
                submittedAt=sub.get("submittedAt"),
                requestedAmount=sub.get("requestedAmount"),
                aiScore=sub.get("aiScore"),
                voteCounts=vote_counts,
                myVote=my_vote,
                allVotes=all_votes,
            ))
        
        return ReviewQueueResponse(submissions=submissions, total=data.get("total", len(submissions)))
    
    def get_submission_for_review(
        self,
        submission_id: str,
        auth_token: str,
        org_slug: Optional[str] = None,
    ) -> GetSubmissionForReviewResponse:
        """
        Get a single submission for review by its UUID.
        
        Args:
            submission_id: Submission UUID
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            GetSubmissionForReviewResponse with the submission
        """
        url = f"{self.base_url}/api/reviews/submissions/{submission_id}"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        # Parse the submission similarly to get_review_queue
        sub = data.get("submission", {})
        
        vote_counts_data = sub.get("voteCounts", {})
        vote_counts = VoteCounts(
            totalReviewers=vote_counts_data.get("totalReviewers", 0),
            votesNeeded=vote_counts_data.get("votesNeeded", 0),
            approvesCount=vote_counts_data.get("approvesCount", 0),
            rejectsCount=vote_counts_data.get("rejectsCount", 0),
            totalVotes=vote_counts_data.get("totalVotes", 0),
        )
        
        my_vote = None
        if sub.get("myVote"):
            mv = sub["myVote"]
            my_vote = Vote(
                id=mv.get("id"),
                submission_id=mv.get("submission_id"),
                reviewer_id=mv.get("reviewer_id"),
                vote=mv.get("vote"),
                comment=mv.get("comment"),
                voted_at=mv.get("voted_at"),
            )
        
        all_votes = None
        if sub.get("allVotes"):
            all_votes = []
            for v in sub["allVotes"]:
                all_votes.append(VoteWithReviewer(
                    id=v.get("id"),
                    reviewerId=v.get("reviewerId"),
                    reviewerName=v.get("reviewerName"),
                    reviewerHandle=v.get("reviewerHandle"),
                    reviewerEmail=v.get("reviewerEmail"),
                    vote=v.get("vote"),
                    comment=v.get("comment"),
                    votedAt=v.get("votedAt"),
                ))
        
        submission = SubmissionForReview(
            id=sub.get("id"),
            formId=sub.get("formId"),
            formName=sub.get("formName"),
            programId=sub.get("programId"),
            programName=sub.get("programName"),
            teamId=sub.get("teamId"),
            teamName=sub.get("teamName"),
            submissionTitle=sub.get("submissionTitle"),
            userId=sub.get("userId"),
            userHandle=sub.get("userHandle"),
            userEmail=sub.get("userEmail"),
            status=sub.get("status"),
            reviewStatus=sub.get("reviewStatus"),
            submittedAt=sub.get("submittedAt"),
            requestedAmount=sub.get("requestedAmount"),
            aiScore=sub.get("aiScore"),
            voteCounts=vote_counts,
            myVote=my_vote,
            allVotes=all_votes,
        )
        
        return GetSubmissionForReviewResponse(submission=submission)
    
    def submit_vote(
        self,
        submission_id: str,
        vote: str,
        comment: str,
        auth_token: str,
        org_slug: Optional[str] = None,
    ) -> VoteResponse:
        """
        Submit a vote on a submission.
        
        Args:
            submission_id: Submission UUID
            vote: Vote type ("approve" or "reject")
            comment: Rationale for the vote (5-500 characters)
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            VoteResponse with result and updated vote counts
        """
        url = f"{self.base_url}/api/reviews/vote"
        params = {"org": org_slug} if org_slug else {}
        
        body = {
            "submissionId": submission_id,
            "vote": vote,
            "comment": comment,
        }
        
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body,
        )
        data = self._handle_response(response)
        
        # Parse vote
        vote_data = data.get("vote", {})
        parsed_vote = Vote(
            id=vote_data.get("id"),
            submission_id=vote_data.get("submission_id"),
            reviewer_id=vote_data.get("reviewer_id"),
            vote=vote_data.get("vote"),
            comment=vote_data.get("comment"),
            voted_at=vote_data.get("voted_at"),
        )
        
        # Parse vote counts
        vote_counts_data = data.get("voteCounts", {})
        vote_counts = VoteCounts(
            totalReviewers=vote_counts_data.get("totalReviewers", 0),
            votesNeeded=vote_counts_data.get("votesNeeded", 0),
            approvesCount=vote_counts_data.get("approvesCount", 0),
            rejectsCount=vote_counts_data.get("rejectsCount", 0),
            totalVotes=vote_counts_data.get("totalVotes", 0),
        )
        
        return VoteResponse(
            ok=data.get("ok", True),
            vote=parsed_vote,
            reviewStatus=data.get("reviewStatus"),
            voteCounts=vote_counts,
            budgetWarning=data.get("budgetWarning"),
        )
    
    def submit_tiebreaker(
        self,
        submission_id: str,
        vote: str,
        comment: str,
        auth_token: str,
        org_slug: Optional[str] = None,
    ) -> TiebreakerResponse:
        """
        Submit a tiebreaker decision on a tied submission.
        
        Args:
            submission_id: Submission UUID
            vote: Vote type ("approve" or "reject")
            comment: Rationale for the decision (5-500 characters)
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            TiebreakerResponse with result
        """
        url = f"{self.base_url}/api/reviews/tiebreaker"
        params = {"org": org_slug} if org_slug else {}
        
        body = {
            "submissionId": submission_id,
            "vote": vote,
            "comment": comment,
        }
        
        response = self.client.post(
            url,
            headers=self._get_headers(auth_token),
            params=params,
            json=body,
        )
        data = self._handle_response(response)
        
        return TiebreakerResponse(
            ok=data.get("ok", True),
            decision=data.get("decision"),
            reviewStatus=data.get("reviewStatus"),
        )
    
    def get_my_votes(
        self,
        auth_token: str,
        org_slug: Optional[str] = None,
    ) -> MyVotesResponse:
        """
        Get the authenticated user's voting history.
        
        Args:
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            MyVotesResponse with list of votes
        """
        url = f"{self.base_url}/api/reviews/my-votes"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        votes = []
        for v in data.get("votes", []):
            votes.append(VoteWithContext(
                id=v.get("id"),
                submission_id=v.get("submission_id"),
                reviewer_id=v.get("reviewer_id"),
                vote=v.get("vote"),
                comment=v.get("comment"),
                voted_at=v.get("voted_at"),
                formName=v.get("formName"),
                programName=v.get("programName"),
                teamName=v.get("teamName"),
                submissionStatus=v.get("submissionStatus"),
                reviewStatus=v.get("reviewStatus"),
            ))
        
        return MyVotesResponse(votes=votes, total=data.get("total", len(votes)))
    
    # ==================
    # Criteria Endpoints
    # ==================
    
    def list_form_criteria(
        self,
        form_id: int,
        auth_token: str,
        org_slug: Optional[str] = None,
    ) -> FormCriteriaListResponse:
        """
        Get evaluation criteria attached to a form with weights.
        
        Args:
            form_id: Form ID
            auth_token: Privy authentication token
            org_slug: Organization slug
            
        Returns:
            FormCriteriaListResponse with list of criteria
        """
        url = f"{self.base_url}/api/criteria/forms/{form_id}/criteria"
        params = {"org": org_slug} if org_slug else {}
        
        response = self.client.get(url, headers=self._get_headers(auth_token), params=params)
        data = self._handle_response(response)
        
        criteria = []
        for c in data.get("criteria", []):
            # Parse scoring rules if present
            scoring_rules = None
            if c.get("scoringRules"):
                sr = c["scoringRules"]
                scoring_rules = ScoringRules(
                    scale=sr.get("scale", "0-100"),
                    factors=sr.get("factors", []),
                )
            
            criteria.append(FormCriteria(
                id=c.get("id"),
                name=c.get("name"),
                description=c.get("description"),
                weight=c.get("weight"),
                scoring_rules=scoring_rules,
            ))
        
        return FormCriteriaListResponse(criteria=criteria)
