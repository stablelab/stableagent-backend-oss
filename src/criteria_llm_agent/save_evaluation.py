"""
Save AI evaluation results to the database in normalized 3NF format.

This module handles persisting evaluation results without storing redundant
data like weights and weighted scores (calculated dynamically via view).
"""
import logging
from typing import Any, Dict
from .types import AggregatedScore

logger = logging.getLogger(__name__)


async def save_evaluation_result(
    db_connection: Any,
    org_schema: str,
    evaluation: AggregatedScore
) -> int:
    """
    Save AI evaluation results to the database in normalized format.
    
    Stores results in 3NF:
    - grant_form_ai_evaluations: Aggregated scores
    - grant_form_ai_criterion_scores: Individual criterion scores (no weight/weighted_score)
    
    Weights and weighted scores are dynamically calculated via the
    grant_form_ai_evaluation_details view.
    
    Args:
        db_connection: Database connection object
        org_schema: Organization schema name
        evaluation: AggregatedScore result from evaluation
        
    Returns:
        int: ID of the created evaluation record
        
    Raises:
        Exception: If database operation fails
    """
    cursor = db_connection.cursor()
    
    try:
        # Insert main evaluation record
        insert_evaluation_query = f"""
            INSERT INTO {org_schema}.grant_form_ai_evaluations (
                id_form,
                id_user,
                team_id,
                total_weighted_score,
                max_possible_score,
                normalized_score,
                reasoning,
                evaluated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        
        cursor.execute(
            insert_evaluation_query,
            [
                evaluation.form_id,
                evaluation.user_id,
                evaluation.team_id,
                evaluation.total_weighted_score,
                evaluation.max_possible_score,
                evaluation.normalized_score,
                evaluation.reasoning,
                evaluation.evaluation_timestamp
            ]
        )
        
        evaluation_id = cursor.fetchone()[0]
        logger.info(f"Created evaluation record {evaluation_id} for user {evaluation.user_id}, form {evaluation.form_id}")
        
        # Insert individual criterion scores (without weight/weighted_score)
        insert_criterion_query = f"""
            INSERT INTO {org_schema}.grant_form_ai_criterion_scores (
                evaluation_id,
                id_criteria,
                raw_score,
                reasoning,
                is_error,
                error_message
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """
        
        for criterion_eval in evaluation.criteria_evaluations:
            cursor.execute(
                insert_criterion_query,
                [
                    evaluation_id,
                    criterion_eval.criterion_id,
                    criterion_eval.raw_score,
                    criterion_eval.reasoning,
                    criterion_eval.is_error,
                    criterion_eval.error_message
                ]
            )
        
        # Commit the transaction
        db_connection.commit()
        
        logger.info(
            f"Saved {len(evaluation.criteria_evaluations)} criterion scores "
            f"for evaluation {evaluation_id}"
        )
        
        logger.info(f"\n{'='*80}\n💾 EVALUATION SAVED TO DATABASE\n{'='*80}")
        logger.info(f"Evaluation ID: {evaluation_id}")
        logger.info(f"Organization: {org_schema}")
        logger.info(f"Form ID: {evaluation.form_id}")
        logger.info(f"User ID: {evaluation.user_id}")
        logger.info(f"Normalized Score: {evaluation.normalized_score:.2f}%")
        logger.info(f"Criteria Evaluated: {len(evaluation.criteria_evaluations)}")
        logger.info(f"{'='*80}\n")
        
        return evaluation_id
        
    except Exception as e:
        # Rollback on error
        db_connection.rollback()
        logger.error(f"Failed to save evaluation results: {e}", exc_info=True)
        raise
    finally:
        cursor.close()


async def get_latest_evaluation(
    db_connection: Any,
    org_schema: str,
    form_id: int,
    user_id: int
) -> Dict[str, Any]:
    """
    Retrieve the most recent evaluation for a user's submission.
    
    Uses the grant_form_ai_evaluation_details view to get complete data
    with weights and weighted scores calculated dynamically.
    
    Args:
        db_connection: Database connection object
        org_schema: Organization schema name
        form_id: Form ID
        user_id: User ID
        
    Returns:
        dict: Evaluation data with all criterion scores
        
    Raises:
        Exception: If database operation fails
    """
    cursor = db_connection.cursor()
    
    try:
        # Query the view for the latest evaluation
        query = f"""
            SELECT 
                evaluation_id,
                form_id,
                user_id,
                total_weighted_score,
                max_possible_score,
                normalized_score,
                reasoning,
                evaluation_timestamp,
                criterion_score_id,
                criterion_id,
                criterion_name,
                criterion_description,
                raw_score,
                weight,
                criterion_reasoning,
                is_error,
                error_message
            FROM {org_schema}.grant_form_ai_evaluation_details
            WHERE form_id = %s AND user_id = %s
            ORDER BY evaluation_timestamp DESC, criterion_score_id ASC
        """
        
        cursor.execute(query, [form_id, user_id])
        
        # Fetch all rows
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        if not rows:
            return None
        
        # Group by evaluation (in case there are multiple)
        # Return the most recent one
        first_row = rows[0]
        evaluation_id = first_row['evaluation_id']
        
        # Build the result structure
        result = {
            'evaluation_id': evaluation_id,
            'form_id': first_row['form_id'],
            'user_id': first_row['user_id'],
            'total_weighted_score': float(first_row['total_weighted_score']),
            'max_possible_score': float(first_row['max_possible_score']),
            'normalized_score': float(first_row['normalized_score']),
            'reasoning': first_row['reasoning'],
            'evaluation_timestamp': first_row['evaluation_timestamp'].isoformat() if first_row['evaluation_timestamp'] else None,
            'criteria_evaluations': []
        }
        
        # Add all criterion evaluations for this evaluation_id
        for row in rows:
            if row['evaluation_id'] == evaluation_id and row['criterion_id']:
                result['criteria_evaluations'].append({
                    'criterion_id': row['criterion_id'],
                    'criterion_name': row['criterion_name'],
                    'criterion_description': row['criterion_description'],
                    'raw_score': row['raw_score'],
                    'weight': float(row['weight']) if row['weight'] else 1.0,
                    'weighted_score': float(row['weight'] * row['raw_score']) if row['weight'] and row['raw_score'] else 0.0,
                    'reasoning': row['criterion_reasoning'],
                    'is_error': row['is_error'],
                    'error_message': row['error_message']
                })
        
        logger.info(f"Retrieved evaluation {evaluation_id} for user {user_id}, form {form_id}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to retrieve evaluation: {e}", exc_info=True)
        raise
    finally:
        cursor.close()

