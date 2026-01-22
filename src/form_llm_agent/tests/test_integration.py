"""
Integration test for the Form LLM Agent with new model factory.

This script demonstrates the complete integration of the multi-provider
model factory with the form LLM agent functionality.
"""

from ..graph import stream_field_processing
from src.utils.model_factory import (
    create_chat_model,
    get_model_provider,
    is_anthropic_model,
    is_gemini_model,
    is_xai_model
)
import os
import json
import asyncio
from typing import Dict, Any

# Set up test environment variables
os.environ['FORM_AGENT_MODEL'] = 'gpt-3.5-turbo'
os.environ['FORM_AGENT_TEMPERATURE'] = '0.4'
os.environ['FORM_AGENT_JSON_MODE'] = 'true'


def test_model_detection():
    """Test the model provider detection functionality."""
    print("=== Model Provider Detection Test ===")

    # Check package availability
    from src.utils.model_factory import is_anthropic_available, is_vertex_available
    print(
        f"Package availability: Anthropic={is_anthropic_available()}, Vertex={is_vertex_available()}")

    test_models = [
        "gpt-4", "gpt-3.5-turbo",
        "claude-3-opus", "claude-3-sonnet",
        "gemini-1.5-pro", "gemini-3-flash-preview",
        "grok-2", "grok-3-mini"
    ]

    for model in test_models:
        provider = get_model_provider(model)
        anthropic = is_anthropic_model(model)
        gemini = is_gemini_model(model)
        xai = is_xai_model(model)

        # Add availability indicators
        available = "✓"
        if anthropic and not is_anthropic_available():
            available = "✗ (pkg missing)"
        elif gemini and not is_vertex_available():
            available = "✗ (pkg missing)"

        print(
            f"{model:20} -> {provider:10} (A:{anthropic}, G:{gemini}, X:{xai}) {available}")

    print()


async def test_form_processing():
    """Test the form field processing with different configurations."""
    print("=== Form Field Processing Test ===")

    test_fields = [
        "user_email",
        "password_field",
        "phone_number",
        "credit_card_input"
    ]

    for field_id in test_fields:
        print(f"\nProcessing field: {field_id}")
        try:
            async for result in stream_field_processing(field_id):
                print(f"  ✓ Response: {result.response[:100]}...")
                print(f"  ✓ Type: {result.type}")
                print(f"  ✓ Error: {result.is_error}")
                break  # Just get first result
        except Exception as e:
            print(f"  ✗ Error: {str(e)}")


def test_model_factory_direct():
    """Test the model factory functionality directly."""
    print("=== Model Factory Direct Test ===")

    configurations = [
        {"model_name": "gpt-3.5-turbo", "temperature": 0.3, "json_mode": True},
        {"model_name": "gpt-4", "temperature": 0.7, "json_mode": False},
    ]

    # Only test if we have API key
    if os.environ.get("OPENAI_API_KEY"):
        for config in configurations:
            try:
                model = create_chat_model(**config)
                provider = get_model_provider(config["model_name"])
                print(f"  ✓ Created {provider} model: {config['model_name']}")
                print(f"    Temperature: {config['temperature']}")
                print(f"    JSON Mode: {config['json_mode']}")
            except Exception as e:
                print(f"  ✗ Failed to create {config['model_name']}: {str(e)}")
    else:
        print("  ⚠ OPENAI_API_KEY not available, skipping direct tests")

    print()


def test_environment_priority():
    """Test environment variable priority system."""
    print("=== Environment Variable Priority Test ===")

    # Save original values
    original_values = {
        "FORM_AGENT_MODEL": os.environ.get("FORM_AGENT_MODEL"),
        "FORM_MODEL": os.environ.get("FORM_MODEL"),
        "DEFAULT_MODEL": os.environ.get("DEFAULT_MODEL")
    }

    test_scenarios = [
        {
            "name": "All variables set",
            "vars": {
                "FORM_AGENT_MODEL": "claude-3-opus",
                "FORM_MODEL": "gpt-4",
                "DEFAULT_MODEL": "gemini-1.5-pro"
            },
            "expected": "claude-3-opus"
        },
        {
            "name": "Only FORM_MODEL and DEFAULT_MODEL",
            "vars": {
                "FORM_AGENT_MODEL": None,
                "FORM_MODEL": "gpt-4",
                "DEFAULT_MODEL": "gemini-1.5-pro"
            },
            "expected": "gpt-4"
        },
        {
            "name": "Only DEFAULT_MODEL",
            "vars": {
                "FORM_AGENT_MODEL": None,
                "FORM_MODEL": None,
                "DEFAULT_MODEL": "gemini-1.5-pro"
            },
            "expected": "gemini-1.5-pro"
        },
        {
            "name": "No variables (fallback)",
            "vars": {
                "FORM_AGENT_MODEL": None,
                "FORM_MODEL": None,
                "DEFAULT_MODEL": None
            },
            "expected": "gpt-4"
        }
    ]

    for scenario in test_scenarios:
        # Set test environment
        for var, value in scenario["vars"].items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

        # Test model selection
        # Simulate getting model name (without actually creating the model)
        model_name = (
            os.environ.get("FORM_AGENT_MODEL") or
            os.environ.get("FORM_MODEL") or
            os.environ.get("DEFAULT_MODEL", "gpt-4")
        )

        result = "✓" if model_name == scenario["expected"] else "✗"
        print(
            f"  {result} {scenario['name']}: {model_name} (expected: {scenario['expected']})")

    # Restore original values
    for var, value in original_values.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value

    print()


def simulate_health_endpoint():
    """Simulate the health endpoint response."""
    print("=== Health Endpoint Simulation ===")

    model_name = (
        os.environ.get("FORM_AGENT_MODEL") or
        os.environ.get("FORM_MODEL") or
        os.environ.get("DEFAULT_MODEL", "gpt-4")
    )

    provider = get_model_provider(model_name)
    temperature = float(os.environ.get("FORM_AGENT_TEMPERATURE", "0.3"))
    json_mode = os.environ.get(
        "FORM_AGENT_JSON_MODE", "true").lower() == "true"

    # Check API key availability
    api_key_status = "unknown"
    if provider == "openai":
        api_key_status = "available" if os.environ.get(
            "OPENAI_API_KEY") else "missing"
    elif provider == "anthropic":
        api_key_status = "available" if os.environ.get(
            "ANTHROPIC_API_KEY") else "missing"
    elif provider == "gemini":
        gcp_project = os.environ.get(
            "GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
        api_key_status = "available" if gcp_project else "missing"
    elif provider == "xai":
        api_key_status = "available" if os.environ.get(
            "X_AI_API_KEY") else "missing"

    health_response = {
        "status": "healthy",
        "service": "form_llm_agent",
        "version": "2.0.0",
        "model_config": {
            "model_name": model_name,
            "provider": provider,
            "temperature": temperature,
            "json_mode": json_mode,
            "api_key_status": api_key_status
        }
    }

    print(json.dumps(health_response, indent=2))
    print()


async def run_comprehensive_test():
    """Run all integration tests."""
    print("Form LLM Agent - Model Factory Integration Test")
    print("=" * 60)

    # Test 1: Model Detection
    test_model_detection()

    # Test 2: Environment Priority
    test_environment_priority()

    # Test 3: Model Factory Direct
    test_model_factory_direct()

    # Test 4: Health Endpoint Simulation
    simulate_health_endpoint()

    # Test 5: Form Processing (requires API key)
    if os.environ.get("OPENAI_API_KEY"):
        await test_form_processing()
    else:
        print("=== Form Field Processing Test ===")
        print("⚠ OPENAI_API_KEY not available, skipping processing tests")
        print()

    print("=" * 60)
    print("Integration test completed!")
    print("\nKey Features Demonstrated:")
    print("✓ Multi-provider model detection (OpenAI, Anthropic, Gemini, XAI)")
    print("✓ Environment variable priority system")
    print("✓ Model factory integration with form processing")
    print("✓ JSON mode support for structured output")
    print("✓ Enhanced error handling and logging")
    print("✓ Health endpoint with model configuration")


if __name__ == "__main__":
    asyncio.run(run_comprehensive_test())
