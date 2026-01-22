"""
Example usage of the Criteria LLM Agent.

Demonstrates how to use the criteria evaluation system for grant applications.
"""
import asyncio
import os
from typing import Dict, Any

# Set up environment for example
os.environ.setdefault('CRITERIA_AGENT_MODEL', 'gpt-3.5-turbo')
os.environ.setdefault('CRITERIA_AGENT_TEMPERATURE', '0.3')
os.environ.setdefault('CRITERIA_AGENT_JSON_MODE', 'true')


async def example_single_evaluation():
    """
    Example: Evaluate a single submission.
    
    This shows how to evaluate all criteria for one user's form submission.
    """
    print("=" * 60)
    print("Example 1: Single Submission Evaluation")
    print("=" * 60)
    
    from .evaluator import CriteriaEvaluator
    from .database import CriteriaDatabase
    
    # Mock database connection (replace with actual connection)
    # db_connection = get_your_database_connection()
    
    print("\nNote: This example requires a real database connection.")
    print("Replace 'db_connection' with your actual database setup.")
    
    # Example usage pattern:
    # database = CriteriaDatabase(db_connection)
    # evaluator = CriteriaEvaluator(database)
    # 
    # result = await evaluator.evaluate_submission(
    #     org_schema="polygon",
    #     form_id=123,
    #     user_id=456
    # )
    # 
    # print(f"\nEvaluation Results:")
    # print(f"Normalized Score: {result.normalized_score:.2f}%")
    # print(f"Total Weighted Score: {result.total_weighted_score:.2f}")
    # print(f"Max Possible Score: {result.max_possible_score:.2f}")
    # 
    # print(f"\nIndividual Criteria Evaluations:")
    # for eval_result in result.criteria_evaluations:
    #     print(f"\n  Criterion: {eval_result.criterion_name}")
    #     print(f"  Raw Score: {eval_result.raw_score}/100")
    #     print(f"  Weight: {eval_result.weight}")
    #     print(f"  Weighted Score: {eval_result.weighted_score:.2f}")
    #     print(f"  Reasoning: {eval_result.reasoning[:100]}...")


async def example_batch_evaluation():
    """
    Example: Batch evaluation of multiple submissions.
    
    This shows how to efficiently evaluate multiple users' submissions.
    """
    print("\n" + "=" * 60)
    print("Example 2: Batch Evaluation")
    print("=" * 60)
    
    from .evaluator import CriteriaEvaluator
    from .database import CriteriaDatabase
    
    print("\nNote: This example requires a real database connection.")
    
    # Example usage pattern:
    # database = CriteriaDatabase(db_connection)
    # evaluator = CriteriaEvaluator(database)
    # 
    # results = await evaluator.evaluate_batch_submissions(
    #     org_schema="polygon",
    #     form_id=123,
    #     user_ids=[456, 457, 458]
    # )
    # 
    # print(f"\nEvaluated {len(results)} submissions:")
    # for result in results:
    #     print(f"\n  User {result.user_id}:")
    #     print(f"    Score: {result.normalized_score:.2f}%")
    #     print(f"    Criteria Evaluated: {len(result.criteria_evaluations)}")


async def example_api_usage():
    """
    Example: Using the API endpoints.
    
    This shows how to call the REST API for criteria evaluation.
    """
    print("\n" + "=" * 60)
    print("Example 3: API Usage")
    print("=" * 60)
    
    print("\nSingle Evaluation Request:")
    print("""
    curl -X POST "http://localhost:8000/criteria/evaluate" \\
      -H "Authorization: Bearer your_token" \\
      -H "Content-Type: application/json" \\
      -d '{
        "org": "polygon",
        "form_id": 123,
        "user_id": 456
      }'
    """)
    
    print("\nBatch Evaluation Request:")
    print("""
    curl -X POST "http://localhost:8000/criteria/evaluate/batch" \\
      -H "Authorization: Bearer your_token" \\
      -H "Content-Type: application/json" \\
      -d '{
        "org": "polygon",
        "form_id": 123,
        "user_ids": [456, 457, 458]
      }'
    """)


async def example_model_configuration():
    """
    Example: Model configuration and provider selection.
    
    Shows how to configure different LLM providers.
    """
    print("\n" + "=" * 60)
    print("Example 4: Model Configuration")
    print("=" * 60)
    
    from .model_factory import get_model_provider
    
    # Test model provider detection
    test_models = [
        "gpt-4",
        "claude-3-opus",
        "gemini-1.5-pro",
        "grok-2"
    ]
    
    print("\nModel Provider Detection:")
    for model in test_models:
        provider = get_model_provider(model)
        print(f"  {model:<20} -> {provider}")
    
    print("\nEnvironment Variables:")
    print("  CRITERIA_AGENT_MODEL     - Specific model for criteria evaluation")
    print("  FORM_MODEL               - Fallback to form model")
    print("  DEFAULT_MODEL            - Global fallback")
    print("  CRITERIA_AGENT_TEMPERATURE - Model temperature (default: 0.3)")
    print("  CRITERIA_AGENT_JSON_MODE   - Enable JSON mode (default: true)")


def example_mock_data():
    """
    Example: Mock data structures.
    
    Shows the expected data formats for testing.
    """
    print("\n" + "=" * 60)
    print("Example 5: Mock Data Structures")
    print("=" * 60)
    
    print("\nExample Criterion:")
    criterion = {
        "id": 1,
        "name": "Technical Feasibility",
        "description": "Project demonstrates strong technical approach and implementation plan",
        "weight": 2.0,
        "scoring_rules": {
            "focus_areas": ["architecture", "security", "scalability"]
        }
    }
    print(f"  {criterion}")
    
    print("\nExample Form Config:")
    form_config = {
        "formId": "grant-application-v1",
        "title": "Grant Application Form",
        "steps": [
            {
                "id": "technical",
                "title": "Technical Details",
                "fields": [
                    {
                        "id": "architecture",
                        "type": "textarea",
                        "label": "Technical Architecture"
                    }
                ]
            }
        ]
    }
    print(f"  {form_config}")
    
    print("\nExample User Answers:")
    answers = [
        {"id_field": 1, "answer": "We use a microservices architecture..."},
        {"id_field": 2, "answer": "Security is implemented through..."}
    ]
    print(f"  {answers}")
    
    print("\nExample Evaluation Result:")
    result = {
        "criterion_id": 1,
        "criterion_name": "Technical Feasibility",
        "raw_score": 100,
        "weight": 2.0,
        "weighted_score": 200.0,
        "reasoning": "The application demonstrates excellent technical approach...",
        "is_error": False
    }
    print(f"  {result}")


async def main():
    """Run all examples."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 12 + "Criteria LLM Agent Examples" + " " * 19 + "║")
    print("╚" + "=" * 58 + "╝")
    
    await example_single_evaluation()
    await example_batch_evaluation()
    await example_api_usage()
    await example_model_configuration()
    example_mock_data()
    
    print("\n" + "=" * 60)
    print("Examples Complete!")
    print("=" * 60)
    print("\nNext Steps:")
    print("1. Set up database connection in router.py")
    print("2. Configure environment variables for LLM provider")
    print("3. Integrate router into your FastAPI app")
    print("4. Test with actual form submissions")
    print("\nFor more information, see README.md")
    print()


if __name__ == "__main__":
    asyncio.run(main())
