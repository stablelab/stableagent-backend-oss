# Form LLM Agent

A minimal LangGraph setup framework that integrates with FastAPI for processing field IDs and streaming structured results.

## Features

- **FastAPI Integration**: Gated API endpoint with authentication
- **LangGraph Streaming**: Yields structured results in real-time
- **Multi-Provider LLM Support**: Integrated model factory supporting OpenAI, Anthropic, Gemini, and XAI
- **Automatic Provider Detection**: Models are automatically routed to the correct provider based on model name
- **Type Safety**: Structured response format with Pydantic models
- **Error Handling**: Comprehensive error handling and fallback responses

## Quick Start

### 1. Installation

The module is designed to work within the existing StableAgent backend project. Ensure you have the required dependencies:

```bash
pip install langgraph langchain-google-vertexai
```

### 2. Model Configuration

Configure your preferred LLM model using environment variables:

```bash
# Model Selection (in priority order)
FORM_AGENT_MODEL=claude-3-opus     # Highest priority - form-specific model
FORM_MODEL=gpt-4                   # Medium priority - general form model  
DEFAULT_MODEL=gemini-1.5-pro       # Lowest priority - global fallback

# Model Settings
FORM_AGENT_TEMPERATURE=0.3         # Temperature setting (default: 0.3)
FORM_AGENT_JSON_MODE=true          # Enable JSON mode for compatible models

# Provider API Keys
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key  
X_AI_API_KEY=your_xai_key
GOOGLE_CLOUD_PROJECT=your_gcp_project
```

### 3. Authentication

The endpoint uses the existing project authentication system. Ensure you have `STABLELAB_TOKEN` set in your environment.

### 4. Usage

#### Main Processing Endpoints

**Simple Field Processing:**
```bash
GET /form/process?field_id=your_field_id
Authorization: Bearer your_token
```

**Enhanced Form Context Processing:**
```bash
POST /form/process
Authorization: Bearer your_token
Content-Type: application/json

{
  "id_requested": "title",
  "form": {
    "title": "Your Form Title",
    "steps": [
      {
        "fields": [
          {
            "id": "title",
            "type": "text",
            "label": "Project Title",
            "props": {
              "evaluationInstructions": "Check if title is clear and specific..."
            },
            "validation": {"required": true, "maxLength": 100}
          }
        ]
      }
    ]
  }
}
```

#### Configuration Endpoints

```bash
# Check health and current model config
GET /form/health

# List all supported models
GET /form/models
Authorization: Bearer your_token

# Get detailed configuration
GET /form/config  
Authorization: Bearer your_token
```

#### Example Response Stream

```
data: {"id": "user_email", "response": "Email validation should include format checking and domain verification", "type": "advice", "is_error": false}

data: [DONE]
```

### 4. Integration

The router is automatically included in the main FastAPI application under the `/form` prefix when the module is available.

## Module Structure

```
form_llm_agent/
├── __init__.py          # Module initialization
├── types.py             # Response type definitions
├── graph.py             # LangGraph implementation
├── router.py            # FastAPI router
├── main.py              # Main module exports
├── example.py           # Usage example
└── README.md            # This file
```

## Response Format

All responses follow the `LangGraphResult` format:

```python
{
    "id": str,           # Field identifier
    "response": str,     # Analysis or advice text
    "type": "issue" | "advice",  # Response type
    "is_error": bool     # Error indicator
}
```

## Error Handling

The system provides multiple layers of error handling:

1. **Graph-level errors**: Caught and returned as error responses
2. **Streaming errors**: Handled gracefully with error results
3. **Authentication errors**: Standard HTTP 401/500 responses
4. **Validation errors**: HTTP 400 for invalid inputs

## Configuration

The module uses the following environment variables:

**Authentication:**
- `STABLELAB_TOKEN`: API authentication token (required)

**Model Selection (priority order):**
- `FORM_AGENT_MODEL`: Specific model for form agent (highest priority)
- `FORM_MODEL`: General form model (medium priority)  
- `DEFAULT_MODEL`: Global model fallback (lowest priority, default: "gpt-4")

**Model Configuration:**
- `FORM_AGENT_TEMPERATURE`: Temperature setting (default: 0.3)
- `FORM_AGENT_JSON_MODE`: Enable JSON mode for structured output (default: true)

**Provider Credentials:**
- `OPENAI_API_KEY`: Required for OpenAI models (gpt-4, gpt-3.5-turbo, etc.)
- `ANTHROPIC_API_KEY`: Required for Anthropic models (claude-3-opus, claude-3-sonnet, etc.)
- `X_AI_API_KEY`: Required for XAI models (grok-4-fast-reasoning, grok-4-fast-non-reasoning, grok-code-fast-1, etc.)
- `GOOGLE_CLOUD_PROJECT`: Required for Gemini models (gemini-3-flash-preview-lite, gemini-3-flash-preview, etc.)
- `VERTEX_LOCATION`: Optional location for Vertex AI (default: us-central1)
- `XAI_BASE_URL`: Optional custom base URL for XAI API

**Google Cloud Authentication (Gemini):**
- Gemini models use **Google Cloud JSON authentication** via `.gcloud.json` file
- No API key required - uses service account credentials
- Automatically loads from `common_settings` configuration

## Example Usage

### Basic Field Processing
```python
from form_llm_agent import stream_field_processing

async for result in stream_field_processing("user_email"):
    print(f"Result: {result.response}")
```

### Using the Model Factory Directly
```python
from form_llm_agent import create_chat_model, get_model_provider

# Create a model for any provider
model = create_chat_model("claude-3-opus", temperature=0.5)
provider = get_model_provider("claude-3-opus")  # Returns "anthropic"

# Use with tools and JSON mode
json_model = create_chat_model("gpt-4", json_mode=True, temperature=0.1)
```

### Environment Configuration Examples
```bash
# Use Claude for form processing
export FORM_AGENT_MODEL="claude-3-opus"
export ANTHROPIC_API_KEY="your_key"

# Use Gemini with custom settings (Google Cloud JSON auth)
export FORM_MODEL="gemini-1.5-pro"
export FORM_AGENT_TEMPERATURE="0.5"
export GOOGLE_CLOUD_PROJECT="your_project"
# Ensure .gcloud.json file is present for authentication

# Use XAI Grok
export DEFAULT_MODEL="grok-2"
export X_AI_API_KEY="your_key"
```

## Health Check

A health check endpoint is available at `/form/health` for monitoring system status.
