"""
Database operations for criteria evaluation.

Handles fetching criteria, form configs, and user responses from the database.
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)


class CriteriaDatabase:
    """Database interface for criteria evaluation."""
    
    def __init__(self, db_connection):
        """
        Initialize database interface.
        
        Args:
            db_connection: Database connection object (e.g., psycopg2 connection)
        """
        self.conn = db_connection
    
    async def resolve_org_schema(self, org_id: int) -> str:
        """
        Resolve organisation ID to actual database schema name.
        
        Looks up the organisation by ID and returns the schema name
        from the organisations table.
        
        Args:
            org_id: Organisation ID
            
        Returns:
            str: Actual schema name from organisations.schema column
            
        Raises:
            ValueError: If organisation not found
        """
        cursor = self.conn.cursor()
        
        try:
            query = """
                SELECT schema 
                FROM public.organisations 
                WHERE id = %s
            """
            cursor.execute(query, [org_id])
            
            row = cursor.fetchone()
            if not row or not row[0]:
                raise ValueError(f"Organisation ID {org_id} not found or has no schema")
            
            schema_name = row[0]
            logger.info(f"Resolved org ID {org_id} to schema '{schema_name}'")
            return schema_name
            
        except Exception as e:
            logger.error(f"Failed to resolve org schema for ID {org_id}: {e}")
            raise
        finally:
            cursor.close()
    
    async def fetch_form_criteria(
        self, 
        org_schema: str, 
        form_id: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch all criteria attached to a form with their weights.
        
        Criteria are fetched from the grant_form_selected_criteria connection table,
        which defines which criteria are attached to the form and their weights.
        
        Args:
            org_schema: Organization schema name
            form_id: Form ID
            
        Returns:
            List of criteria dictionaries with id, name, description, scoring_rules, and weight
        """
        cursor = self.conn.cursor()
        
        try:
            # Fetch all criteria attached to this form via the connection table
            query = f"""
                SELECT 
                    c.id,
                    c.name,
                    c.description,
                    c.scoring_rules,
                    sc.weight
                FROM {org_schema}.grant_form_criteria c
                INNER JOIN {org_schema}.grant_form_selected_criteria sc 
                    ON c.id = sc.id_criteria
                WHERE sc.id_form = %s
                ORDER BY c.id
            """
            
            params = [form_id]
            
            cursor.execute(query, params)
            
            # Fetch and format results
            columns = [desc[0] for desc in cursor.description]
            results = []
            
            for row in cursor.fetchall():
                result = dict(zip(columns, row))
                # Convert Decimal to float for weight
                if isinstance(result.get('weight'), Decimal):
                    result['weight'] = float(result['weight'])
                results.append(result)
            
            logger.info(f"Fetched {len(results)} criteria for form {form_id} in org {org_schema}")
            return results
            
        except Exception as e:
            logger.error(f"Error fetching form criteria: {e}")
            raise
        finally:
            cursor.close()
    
    async def fetch_form_config(self, org_schema: str, form_id: int) -> Dict[str, Any]:
        """
        Fetch form configuration including field definitions.
        
        Args:
            org_schema: Organization schema name
            form_id: Form ID
            
        Returns:
            Form configuration dictionary
        """
        cursor = self.conn.cursor()
        
        try:
            query = f"""
                SELECT config
                FROM {org_schema}.grant_form
                WHERE form_id = %s
            """
            
            cursor.execute(query, [form_id])
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Form {form_id} not found in org {org_schema}")
            
            config = row[0]
            logger.info(f"Fetched config for form {form_id} in org {org_schema}")
            return config
            
        except Exception as e:
            logger.error(f"Error fetching form config: {e}")
            raise
        finally:
            cursor.close()
    
    async def fetch_user_answers(
        self, 
        org_schema: str, 
        form_id: int, 
        user_id: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch all answers submitted by a user for a form.
        
        Returns answers in a minimal format for AI evaluation, extracting values
        from the JSONB answer column and organizing by step and field.
        
        Args:
            org_schema: Organization schema name
            form_id: Form ID
            user_id: User ID
            
        Returns:
            List of answer dictionaries with step_id, field_id, field_type, and value
        """
        cursor = self.conn.cursor()
        
        try:
            query = f"""
                SELECT 
                    step_id,
                    field_id,
                    answer->>'type' as field_type,
                    answer->'value' as value
                FROM {org_schema}.grant_form_answers
                WHERE id_form = %s 
                  AND id_user = %s 
                  AND existent = true
                ORDER BY step_id, field_id
            """
            
            cursor.execute(query, [form_id, user_id])
            
            # Fetch and format results
            columns = [desc[0] for desc in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            logger.info(f"Fetched {len(results)} answers for user {user_id}, form {form_id} in org {org_schema}")
            
            # Log the formatted answers being passed to AI evaluation
            logger.info(f"\n{'='*80}\n📋 USER ANSWERS FETCHED (for AI evaluation)\n{'='*80}")
            logger.info(f"Organization: {org_schema}")
            logger.info(f"Form ID: {form_id}")
            logger.info(f"User ID: {user_id}")
            logger.info(f"Total Answers: {len(results)}")
            logger.info(f"\nFormatted Answers:")
            for i, answer in enumerate(results, 1):
                logger.info(f"  {i}. [{answer.get('step_id')}] {answer.get('field_id')} ({answer.get('field_type')}): {answer.get('value')}")
            logger.info(f"{'='*80}\n")
            
            return results
            
        except Exception as e:
            logger.error(f"Error fetching user answers: {e}")
            raise
        finally:
            cursor.close()
    
    async def fetch_evaluation_context(
        self,
        org_schema: str,
        form_id: int,
        user_id: int
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
        """
        Fetch all data needed for criteria evaluation in a single call.
        
        Fetches all criteria attached to the form (from the connection table),
        the form configuration, and the user's submitted answers.
        
        Args:
            org_schema: Organization schema name
            form_id: Form ID
            user_id: User ID
            
        Returns:
            Tuple of (criteria, form_config, user_answers)
        """
        criteria = await self.fetch_form_criteria(org_schema, form_id)
        form_config = await self.fetch_form_config(org_schema, form_id)
        user_answers = await self.fetch_user_answers(org_schema, form_id, user_id)
        
        return criteria, form_config, user_answers
