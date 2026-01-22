"""
Main evaluator orchestrator for criteria evaluation.

Coordinates the evaluation of all criteria for a form submission,
aggregating results into a final score. Includes comprehensive logging
for progress tracking.
"""
import asyncio
import time
from datetime import datetime
from typing import List, Optional
import logging

from .types import CriteriaEvaluationResult, AggregatedScore
from .database import CriteriaDatabase
from .graph import evaluate_single_criterion
from .logger import evaluation_logger

logger = logging.getLogger(__name__)


class CriteriaEvaluator:
    """
    Orchestrates the evaluation of multiple criteria for a form submission.
    
    Manages fetching data, running evaluations in parallel, and aggregating scores.
    """
    
    def __init__(self, database: CriteriaDatabase):
        """
        Initialize evaluator with database interface.
        
        Args:
            database: CriteriaDatabase instance for data access
        """
        self.database = database
    
    async def _evaluate_with_schema(
        self,
        org_schema: str,
        org_identifier: str,
        form_id: int,
        user_id: int,
        team_id: Optional[int] = None
    ) -> AggregatedScore:
        """
        Internal method that evaluates with a pre-resolved schema.
        
        Args:
            org_schema: Actual database schema name (already resolved)
            org_identifier: Original org identifier (for logging)
            form_id: Form ID to evaluate
            user_id: User whose submission to evaluate
            team_id: Optional team ID associated with the evaluation
            
        Returns:
            AggregatedScore with all evaluation results and final score
        """
        # Log evaluation start
        evaluation_logger.log_evaluation_start(org_identifier, form_id, user_id)
        
        start_time = datetime.utcnow()
        start_time_perf = time.time()
        
        # Fetch all required data
        evaluation_logger.log_data_fetch_start()
        criteria, form_config, user_answers = await self.database.fetch_evaluation_context(
            org_schema=org_schema,
            form_id=form_id,
            user_id=user_id
        )
        evaluation_logger.log_data_fetch_complete(len(criteria), len(user_answers))
        
        if not criteria:
            logger.warning(f"No criteria found for form {form_id}")
            return AggregatedScore(
                form_id=form_id,
                user_id=user_id,
                team_id=team_id,
                total_weighted_score=0.0,
                max_possible_score=0.0,
                normalized_score=0.0,
                criteria_evaluations=[],
                evaluation_timestamp=start_time.isoformat()
            )
        
        logger.info(f"Evaluating {len(criteria)} criteria in parallel")
        
        # Create evaluation tasks for all criteria
        tasks = []
        for idx, criterion in enumerate(criteria, 1):
            # Log each criterion being evaluated
            evaluation_logger.log_criteria_evaluation_start(
                criterion['id'],
                criterion['name'],
                idx,
                len(criteria)
            )
            
            task = evaluate_single_criterion(
                criterion_id=criterion['id'],
                criterion_name=criterion['name'],
                criterion_description=criterion.get('description'),
                weight=criterion['weight'],
                scoring_rules=criterion.get('scoring_rules'),
                form_config=form_config,
                user_answers=user_answers
            )
            tasks.append(task)
        
        # Execute all evaluations in parallel
        evaluation_logger.log_aggregation_start(len(criteria))
        evaluation_results: List[CriteriaEvaluationResult] = await asyncio.gather(*tasks)
        
        # Calculate aggregated scores
        total_weighted_score = sum(r.weighted_score for r in evaluation_results)
        max_possible_score = sum(100 * r.weight for r in evaluation_results)
        
        # Calculate normalized score (0-100 scale)
        if max_possible_score > 0:
            normalized_score = (total_weighted_score / max_possible_score) * 100
        else:
            normalized_score = 0.0
        
        # Calculate total duration
        duration_seconds = time.time() - start_time_perf
        
        # Log completion with detailed metrics
        evaluation_logger.log_evaluation_complete(
            total_weighted_score,
            max_possible_score,
            normalized_score,
            duration_seconds
        )
        
        logger.info(
            f"Evaluation complete: total_weighted={total_weighted_score:.2f}, "
            f"max_possible={max_possible_score:.2f}, normalized={normalized_score:.2f}%"
        )
        
        # Create aggregated result
        aggregated_result = AggregatedScore(
            form_id=form_id,
            user_id=user_id,
            team_id=team_id,
            total_weighted_score=total_weighted_score,
            max_possible_score=max_possible_score,
            normalized_score=normalized_score,
            criteria_evaluations=evaluation_results,
            evaluation_timestamp=start_time.isoformat()
        )
        
        return aggregated_result
    
    async def evaluate_submission(
        self,
        org_id: int,
        form_id: int,
        user_id: int,
        team_id: Optional[int] = None
    ) -> AggregatedScore:
        """
        Evaluate all criteria for a user's form submission.
        
        Public method that resolves the org ID to schema name.
        
        Args:
            org_id: Organization ID
            form_id: Form ID to evaluate
            user_id: User whose submission to evaluate
            team_id: Optional team ID associated with the evaluation
            
        Returns:
            AggregatedScore with all evaluation results and final score
        """
        # Resolve org ID to actual schema name
        org_schema = await self.database.resolve_org_schema(org_id)
        
        # Call internal method with resolved schema
        return await self._evaluate_with_schema(org_schema, org_id, form_id, user_id, team_id)
    
    async def evaluate_batch_submissions(
        self,
        org_id: int,
        form_id: int,
        user_ids: List[int],
        team_id: Optional[int] = None
    ) -> List[AggregatedScore]:
        """
        Evaluate multiple submissions for the same form.
        
        Criteria are automatically fetched from the grant_form_selected_criteria
        connection table for the specified form.
        
        Args:
            org_id: Organization ID
            form_id: Form ID to evaluate
            user_ids: List of user IDs whose submissions to evaluate
            team_id: Optional team ID associated with the evaluations
            
        Returns:
            List of AggregatedScore results, one per user
        """
        # Resolve org ID to actual schema name (once for the batch)
        org_schema = await self.database.resolve_org_schema(org_id)
        
        # Log batch start
        evaluation_logger.log_batch_evaluation_start(org_id, form_id, len(user_ids))
        
        start_time_perf = time.time()
        
        # Create evaluation tasks for all users using internal method
        tasks = [
            self._evaluate_with_schema(org_schema, org_id, form_id, user_id, team_id)
            for user_id in user_ids
        ]
        
        # Execute all evaluations in parallel
        results = await asyncio.gather(*tasks)
        
        # Calculate duration and log completion
        duration_seconds = time.time() - start_time_perf
        evaluation_logger.log_batch_complete(len(results), duration_seconds)
        
        logger.info(f"Batch evaluation complete for {len(results)} users")
        
        return results
