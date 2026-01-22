# Criteria LLM Agent

AI-powered criteria evaluation for blockchain/web3/crypto grant applications using LangGraph and multi-provider LLM support.

## Overview

The Criteria LLM Agent automatically evaluates grant application submissions against predefined criteria, providing objective AI-powered scoring. Each criterion is evaluated independently and assigned a score of **0, 50, or 100 points**, which is then multiplied by the criterion's weight and aggregated into a final score.

## Features

- **AI-Powered Evaluation**: Uses LangGraph with multi-provider LLM support (OpenAI, Anthropic, Gemini, XAI)
- **Weighted Scoring**: Each criterion has a configurable weight multiplier
- **Three-Level Scoring**: Simple 0/50/100 point system for consistent evaluation
- **Parallel Processing**: Evaluates multiple criteria concurrently for speed
- **Batch Evaluation**: Process multiple submissions efficiently
- **Detailed Reasoning**: AI provides explanations for each score
- **Error Handling**: Comprehensive error handling with graceful degradation

## Architecture

```
criteria_llm_agent/
├── __init__.py              # Module initialization
├── types.py                 # Pydantic models for requests/responses
├── model_factory.py         # LLM model factory (reuses form_llm_agent)
├── database.py              # Database operations for fetching data
├── graph.py                 # LangGraph implementation for evaluation
├── evaluator.py             # Main orchestrator for evaluation workflow
├── router.py                # FastAPI endpoints
└── README.md                # This file
```

## Database Schema

The agent works with the following database tables (in organization schemas):

### `grant_form_criteria`
Stores criteria definitions:
- `id`: Criterion ID
- `name`: Criterion name
- `description`: What the criterion evaluates
- `scoring_rules`: Optional JSONB with additional rules

### `grant_form_selected_criteria`
Links criteria to forms with weights:
- `id_form`: Form ID
- `id_criteria`: Criterion ID
- `weight`: Weight multiplier (e.g., 1.0, 0.5, 2.0)

### `grant_form_answers`
User submissions:
- `id_form`: Form ID
- `id_field`: Field number
- `id_user`: User ID
- `answer`: User's response (text or JSON)

### `grant_form`
Form configurations:
- `form_id`: Form ID
- `config`: JSONB with form structure and field definitions

## Installation

The module is designed to work within the existing StableAgent backend project:

```bash
# Install dependencies (if not already installed)
pip install langgraph langchain-openai langchain-anthropic langchain-google-vertexai pydantic
```

## Configuration

Configure using environment variables:

```bash
# Model Selection (in priority order)
CRITERIA_AGENT_MODEL=gpt-4         # Highest priority - criteria-specific model
FORM_MODEL=gpt-3.5-turbo          # Medium priority - general form model
DEFAULT_MODEL=claude-3-opus        # Lowest priority - global fallback

# Model Settings
CRITERIA_AGENT_TEMPERATURE=0.3     # Temperature (default: 0.3)
CRITERIA_AGENT_JSON_MODE=true     # Enable JSON mode (default: true)

# Provider API Keys
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
X_AI_API_KEY=your_xai_key
GOOGLE_CLOUD_PROJECT=your_gcp_project
```

## API Endpoints

### Evaluate Single Submission

Evaluate all criteria for one user's form submission:

```bash
POST /criteria/evaluate
Authorization: Bearer your_token
Content-Type: application/json

{
  "org": "polygon",
  "form_id": 123,
  "user_id": 456,
  "criteria_ids": [1, 2, 3]  // Optional: specific criteria to evaluate
}
```

**Response:**
```json
{
  "form_id": 123,
  "user_id": 456,
  "total_weighted_score": 425.0,
  "max_possible_score": 500.0,
  "normalized_score": 85.0,
  "criteria_evaluations": [
    {
      "criterion_id": 1,
      "criterion_name": "Technical Feasibility",
      "criterion_description": "Project demonstrates strong technical approach",
      "raw_score": 100,
      "weight": 2.0,
      "weighted_score": 200.0,
      "reasoning": "The application clearly outlines...",
      "is_error": false,
      "error_message": null
    },
    {
      "criterion_id": 2,
      "criterion_name": "Community Impact",
      "criterion_description": "Project benefits the ecosystem",
      "raw_score": 50,
      "weight": 1.5,
      "weighted_score": 75.0,
      "reasoning": "While the project has potential...",
      "is_error": false,
      "error_message": null
    }
  ],
  "evaluation_timestamp": "2025-09-30T12:34:56.789Z"
}
```

### Batch Evaluation

Evaluate multiple submissions efficiently:

```bash
POST /criteria/evaluate/batch
Authorization: Bearer your_token
Content-Type: application/json

{
  "org": "polygon",
  "form_id": 123,
  "user_ids": [456, 457, 458],
  "criteria_ids": null  // null evaluates all criteria
}
```

**Response:** Array of `AggregatedScore` objects

### Health Check

```bash
GET /criteria/health
```

### Configuration

```bash
GET /criteria/config
Authorization: Bearer your_token
```

## Scoring System

### Score Levels

Each criterion is evaluated using a three-level system:

| Score | Meaning | Description |
|-------|---------|-------------|
| **0** | Does NOT meet | The submission fails to meet the criterion |
| **50** | PARTIALLY meets | The submission partially satisfies the criterion |
| **100** | FULLY meets | The submission fully satisfies the criterion |

### Weighted Scoring

Each criterion has a weight that acts as a multiplier:

```
weighted_score = raw_score × weight
```

**Examples:**
- Criterion with weight 1.0 and score 100 → weighted score = 100
- Criterion with weight 2.0 and score 50 → weighted score = 100
- Criterion with weight 0.5 and score 100 → weighted score = 50

### Final Score

The normalized score (0-100%) is calculated as:

```
normalized_score = (total_weighted_score / max_possible_score) × 100
```

**Example:**
```
Criteria:
1. Technical (weight: 2.0, score: 100) → 200
2. Impact (weight: 1.5, score: 50) → 75
3. Budget (weight: 1.0, score: 100) → 100

Total weighted score: 375
Max possible score: 450 (2.0×100 + 1.5×100 + 1.0×100)
Normalized score: (375/450) × 100 = 83.33%
```

## Usage Examples

### Python Integration

```python
from criteria_llm_agent.evaluator import CriteriaEvaluator
from criteria_llm_agent.database import CriteriaDatabase

# Initialize (assuming you have a DB connection)
database = CriteriaDatabase(db_connection)
evaluator = CriteriaEvaluator(database)

# Evaluate a single submission
result = await evaluator.evaluate_submission(
    org_schema="polygon",
    form_id=123,
    user_id=456
)

print(f"Normalized Score: {result.normalized_score:.2f}%")
for eval_result in result.criteria_evaluations:
    print(f"- {eval_result.criterion_name}: {eval_result.raw_score}/100")
    print(f"  Reasoning: {eval_result.reasoning}")

# Batch evaluation
results = await evaluator.evaluate_batch_submissions(
    org_schema="polygon",
    form_id=123,
    user_ids=[456, 457, 458]
)

for result in results:
    print(f"User {result.user_id}: {result.normalized_score:.2f}%")
```

### cURL Examples

**Single Evaluation:**
```bash
curl -X POST "http://localhost:8000/criteria/evaluate" \
  -H "Authorization: Bearer your_token" \
  -H "Content-Type: application/json" \
  -d '{
    "org": "polygon",
    "form_id": 123,
    "user_id": 456
  }'
```

**Batch Evaluation:**
```bash
curl -X POST "http://localhost:8000/criteria/evaluate/batch" \
  -H "Authorization: Bearer your_token" \
  -H "Content-Type: application/json" \
  -d '{
    "org": "polygon",
    "form_id": 123,
    "user_ids": [456, 457, 458]
  }'
```

## Integration with Form LLM Agent

This module complements the Form LLM Agent:

- **Form LLM Agent**: Provides real-time field-level advice during form completion
- **Criteria LLM Agent**: Evaluates completed submissions against predefined criteria

Both use the same model factory for consistent LLM provider support.

## Error Handling

The agent handles errors gracefully:

1. **Individual Criterion Errors**: If one criterion fails, others continue
2. **Error Responses**: Failed evaluations get `is_error: true` with score 0
3. **Database Errors**: Properly surfaced with appropriate HTTP status codes
4. **LLM Errors**: Caught and logged with fallback responses

## Performance

- **Parallel Processing**: All criteria are evaluated concurrently
- **Batch Support**: Multiple submissions can be processed efficiently
- **Streaming**: Future support for streaming results planned
- **Caching**: Consider caching form configs for repeated evaluations

## Model Provider Support

Supports the same providers as Form LLM Agent:

| Provider | Models | API Key Required |
|----------|--------|------------------|
| OpenAI | gpt-4, gpt-3.5-turbo, gpt-4o | `OPENAI_API_KEY` |
| Anthropic | claude-3-opus, claude-3-sonnet | `ANTHROPIC_API_KEY` |
| Gemini | gemini-1.5-pro, gemini-3-flash-preview | Google Cloud JSON auth |
| XAI | grok-2, grok-3-mini | `X_AI_API_KEY` |

## TODO / Future Enhancements

- [ ] Integrate database connection with main application
- [ ] Add result persistence (save evaluation results to database)
- [ ] Implement result streaming for real-time updates
- [ ] Add support for custom scoring rubrics
- [ ] Add comparative analysis across submissions
- [ ] Add audit logging for evaluations
- [ ] Add support for criteria dependencies
- [ ] Add confidence scores for AI evaluations
- [ ] Add manual override capability for scores

## Testing

```bash
# Run tests (to be implemented)
python -m pytest src/criteria_llm_agent/tests/

# Test single evaluation
python -m criteria_llm_agent.tests.test_evaluation

# Test batch processing
python -m criteria_llm_agent.tests.test_batch
```

## Troubleshooting

### "Database connection needs to be integrated"

The `get_database_connection()` function in `router.py` needs to be implemented to connect with your actual database setup.

### "No criteria found for form"

Ensure criteria are attached to the form via `grant_form_selected_criteria` table.

### "Form not found"

Verify the form_id exists in the `grant_form` table for the specified org schema.

### LLM API Errors

Check that appropriate API keys are set for your chosen model provider.

## Contributing

When extending this module:

1. Maintain consistency with Form LLM Agent patterns
2. Add comprehensive logging for debugging
3. Update type definitions in `types.py`
4. Add tests for new functionality
5. Update this README with new features

## License

Part of the StableAgent Backend project.
