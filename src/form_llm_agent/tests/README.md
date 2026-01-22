# Form LLM Agent Tests

This directory contains comprehensive tests for the Form LLM Agent with multi-provider model factory support.

## Test Structure

```
tests/
├── __init__.py                    # Test package initialization
├── README.md                     # This file
├── run_tests.py                  # Test runner script with CLI options
├── test_integration.py             # Integration tests for the complete system
├── test_model_factory.py           # Model factory tests and examples
├── test_performance_logging.py     # Performance logging and response time tests
└── test_fast_models_parallel.py    # Parallel tests for fastest recent models
```

## Test Files

### `test_integration.py`
Comprehensive integration tests that validate:
- ✅ Multi-provider model detection (OpenAI, Anthropic, Gemini, XAI)
- ✅ Environment variable priority system
- ✅ Model factory integration with form processing
- ✅ JSON mode support for structured output
- ✅ Enhanced error handling and logging
- ✅ Health endpoint simulation

### `test_model_factory.py`
Model factory specific tests including:
- ✅ Provider detection for all supported models
- ✅ Model creation across all providers
- ✅ JSON mode functionality with actual API calls
- ✅ Tool binding demonstrations
- ✅ Complex JSON schema validation

### `test_performance_logging.py`
Performance logging and response time tests featuring:
- ✅ **Colored console output** with green highlighted final response times
- ✅ **Multi-model performance comparison** (OpenAI, Anthropic, Gemini, XAI)
- ✅ **Environment variable testing** with priority system validation
- ✅ **Fast model testing** (GPT-4o Mini, GPT-3.5 Turbo, Gemini Flash models)
- ✅ **Response time categorization** (EXCELLENT < 100ms, GOOD < 500ms, SLOW < 3s, etc.)
- ✅ **Streaming performance metrics** with chunk tracking
- ✅ **Concurrent operation handling** and load testing
- ✅ **API call timing** with detailed performance breakdowns

### `test_fast_models_parallel.py`
Parallel performance tests for the fastest recent models featuring:
- ✅ **Latest Gemini 2.5 Flash models** (2.5 Flash-Lite, 2.5 Flash, 2.0 Flash-Lite)
- ✅ **Grok 4 integration** (latest xAI model from docs.x.ai)
- ✅ **Parallel execution** for maximum testing efficiency
- ✅ **Google Cloud JSON authentication** for Gemini models
- ✅ **Performance comparison** across all providers
- ✅ **Provider-specific analysis** with average response times
- ✅ **Success rate tracking** and comprehensive results display

### `run_tests.py`
Test runner that provides:
- ✅ Environment setup and validation
- ✅ API key detection and reporting
- ✅ Selective test execution
- ✅ Results summary and reporting

## Running Tests

### Quick Start
```bash
# Run all tests
python -m src.form_llm_agent.tests.run_tests

# Run specific test suites
python -m src.form_llm_agent.tests.run_tests --test integration
python -m src.form_llm_agent.tests.run_tests --test model-factory
python -m src.form_llm_agent.tests.run_tests --test performance
python -m src.form_llm_agent.tests.run_tests --test fast-models

# Verbose output
python -m src.form_llm_agent.tests.run_tests --verbose
```

### Individual Test Files
```bash
# Run integration tests directly
python -m src.form_llm_agent.tests.test_integration

# Run model factory tests directly  
python -m src.form_llm_agent.tests.test_model_factory

# Run performance logging tests directly
python -m src.form_llm_agent.tests.test_performance_logging

# Run fast models parallel tests directly
python -m src.form_llm_agent.tests.test_fast_models_parallel
```

## Environment Setup

### Required Environment Variables
```bash
# API Keys (at least one required for full testing)
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
X_AI_API_KEY=your_xai_key
GOOGLE_CLOUD_PROJECT=your_gcp_project

# Optional Configuration
FORM_AGENT_MODEL=gpt-3.5-turbo      # Default test model
FORM_AGENT_TEMPERATURE=0.4          # Default test temperature
FORM_AGENT_JSON_MODE=true           # Enable JSON mode
```

### Provider-Specific Setup

#### OpenAI
```bash
export OPENAI_API_KEY="your_openai_api_key"
```

#### Anthropic
```bash
export ANTHROPIC_API_KEY="your_anthropic_api_key"
```

#### Google Gemini
```bash
export GOOGLE_CLOUD_PROJECT="your_project_id"
# Ensure Google Cloud credentials are configured
```

#### XAI (Grok)
```bash
export X_AI_API_KEY="your_xai_api_key"
export XAI_BASE_URL="https://api.x.ai/v1"  # Optional
```

## Test Coverage

### ✅ Core Functionality
- [x] Model provider detection
- [x] Environment variable priority
- [x] Model creation and configuration
- [x] Error handling and fallbacks

### ✅ Multi-Provider Support
- [x] OpenAI (GPT models)
- [x] Anthropic (Claude models)  
- [x] Google Gemini (Vertex AI)
- [x] XAI (Grok models)

### ✅ Advanced Features
- [x] JSON mode structured output
- [x] Tool binding capabilities
- [x] Temperature and parameter control
- [x] API key validation

### ✅ Integration Testing
- [x] Form field processing
- [x] Health endpoint simulation
- [x] Router functionality
- [x] Real API interactions

## Expected Test Output

### Successful Run
```
🚀 Form LLM Agent Test Suite
==================================================
🔧 Test Environment Information
Model: gpt-3.5-turbo
Temperature: 0.4
JSON Mode: true
Available Providers: OpenAI, XAI

🧪 Running Integration Tests
=== Model Provider Detection Test ===
gpt-4                -> openai     (A:False, G:False, X:False)
claude-3-opus        -> anthropic  (A:True, G:False, X:False)
...

📊 Test Results Summary
Integration Tests: ✅ PASSED
Model Factory Tests: ✅ PASSED

Total: 2/2 tests passed
🎉 All tests passed!
```

## Troubleshooting

### Common Issues

1. **Missing API Keys**
   - Tests will skip providers without API keys
   - Set at least `OPENAI_API_KEY` for basic testing

2. **Import Errors**
   - Ensure you're running from the project root
   - Check that all dependencies are installed

3. **Google Cloud Setup**
   - Ensure `GOOGLE_CLOUD_PROJECT` is set
   - Verify Google Cloud credentials are configured

### Debug Mode
```bash
# Run with verbose output
python -m src.form_llm_agent.tests.run_tests --verbose

# Skip environment check
python -m src.form_llm_agent.tests.run_tests --skip-env-check
```

## Contributing

When adding new tests:
1. Follow the existing test structure
2. Add proper docstrings and comments
3. Include both positive and negative test cases
4. Update this README if adding new test files
5. Ensure tests work with and without API keys
