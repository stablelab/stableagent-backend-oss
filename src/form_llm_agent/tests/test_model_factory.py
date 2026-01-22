"""Test suite for the model factory supporting OpenAI, Anthropic, Gemini, and XAI models.

This test suite demonstrates and validates the model_factory module functionality
for creating chat models from different providers and interacting with them.
"""

import os
import asyncio
from langchain_core.messages import HumanMessage
from src.utils.model_factory import create_chat_model, is_anthropic_model, is_gemini_model, is_xai_model, get_model_provider


async def test_model_factory():
    """Test the model factory with different model configurations."""

    # Test model provider detection
    print("=== Model Provider Detection ===")
    test_models = [
        "gpt-4",
        "gpt-3.5-turbo",
        "claude-3-opus",
        "claude-3-sonnet",
        "claude-2.1",
        "claude-instant-1.2",
        "gemini-1.5-pro",
        "gemini-3-flash-preview",
        "gemini-1.0-pro",
        "grok-2",
        "grok-3-mini",
        "grok-beta"
    ]

    for model in test_models:
        provider = get_model_provider(model)
        is_anthropic = is_anthropic_model(model)
        is_gemini = is_gemini_model(model)
        is_xai = is_xai_model(model)
        print(f"{model:20} -> {provider:10} (Anthropic: {is_anthropic}, Gemini: {is_gemini}, XAI: {is_xai})")

    print("\n=== Model Creation Examples ===")

    # Example 1: Create OpenAI model (if API key is available)
    if os.getenv("OPENAI_API_KEY"):
        print("\nCreating OpenAI model...")
        try:
            openai_model = create_chat_model(
                model_name="gpt-3.5-turbo",
                temperature=0.3
            )
            print(f"✓ OpenAI model created: {type(openai_model).__name__}")

            # Test a simple query
            response = await openai_model.ainvoke([
                HumanMessage(
                    content="Hello! Please respond with just 'Hello from OpenAI!'")
            ])
            print(f"OpenAI Response: {response.content}")

        except Exception as e:
            print(f"✗ Failed to create OpenAI model: {e}")
    else:
        print("⚠ OPENAI_API_KEY not set, skipping OpenAI test")

    # Example 2: Create Anthropic model (if package and API key are available)
    from src.utils.model_factory import is_anthropic_available

    if is_anthropic_available() and os.getenv("ANTHROPIC_API_KEY"):
        print("\nCreating Anthropic model...")
        try:
            anthropic_model = create_chat_model(
                model_name="claude-3-haiku",
                temperature=0.3
            )
            print(
                f"✓ Anthropic model created: {type(anthropic_model).__name__}")

            # Test a simple query
            response = await anthropic_model.ainvoke([
                HumanMessage(
                    content="Hello! Please respond with just 'Hello from Anthropic!'")
            ])
            print(f"Anthropic Response: {response.content}")

        except Exception as e:
            print(f"✗ Failed to create Anthropic model: {e}")
    elif not is_anthropic_available():
        print("⚠ langchain-anthropic package not available, skipping Anthropic test")
    else:
        print("⚠ ANTHROPIC_API_KEY not set, skipping Anthropic test")

    # Example 3: Create Gemini model (if GCP is configured)
    gcp_configured = os.getenv(
        "GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
    if gcp_configured:
        print("\nCreating Gemini model...")
        try:
            gemini_model = create_chat_model(
                model_name="gemini-1.5-flash",
                temperature=0.3
            )
            print(f"✓ Gemini model created: {type(gemini_model).__name__}")

            # Test a simple query
            response = await gemini_model.ainvoke([
                HumanMessage(
                    content="Hello! Please respond with just 'Hello from Gemini!'")
            ])
            print(f"Gemini Response: {response.content}")

        except Exception as e:
            print(f"✗ Failed to create Gemini model: {e}")
    else:
        print("⚠ Google Cloud not configured, skipping Gemini test")

    # Example 4: Create XAI model (if API key is available)
    if os.getenv("X_AI_API_KEY"):
        print("\nCreating XAI (Grok) model...")
        try:
            xai_model = create_chat_model(
                model_name="grok-2",
                temperature=0.3
            )
            print(f"✓ XAI model created: {type(xai_model).__name__}")

            # Test a simple query
            response = await xai_model.ainvoke([
                HumanMessage(
                    content="Hello! Please respond with just 'Hello from Grok!'")
            ])
            print(f"XAI Response: {response.content}")

        except Exception as e:
            print(f"✗ Failed to create XAI model: {e}")
    else:
        print("⚠ X_AI_API_KEY not set, skipping XAI test")

    # Example 5: Using environment defaults
    print("\nUsing environment defaults...")
    try:
        # This will use DEFAULT_MODEL from environment or "gpt-4" as fallback
        default_model = create_chat_model(temperature=0.1)
        print(f"✓ Default model created: {type(default_model).__name__}")
    except Exception as e:
        print(f"✗ Failed to create default model: {e}")

    print("\n=== Model Factory Demo Complete ===")


def demo_tool_binding():
    """Demonstrate tool binding capabilities across different providers."""
    print("\n=== Tool Binding Demo ===")

    # Example tool definition (simplified)
    example_tools = [
        {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                }
            }
        }
    ]

    # Test different providers with tool binding
    test_configs = [
        ("gpt-3.5-turbo", "OpenAI"),
        ("claude-3-haiku", "Anthropic"),
        ("gemini-1.5-flash", "Gemini"),
        ("grok-2", "XAI")
    ]

    for model_name, provider_name in test_configs:
        try:
            # Note: This is a simplified example. In practice, you'd use proper LangChain tool definitions
            model_with_tools = create_chat_model(
                model_name=model_name,
                temperature=0.0,
                api_tools=None  # Would pass actual tool objects here
            )
            print(
                f"✓ {provider_name} model ({model_name}) with tools created successfully")
        except Exception as e:
            print(f"✗ {provider_name} tool binding failed: {e}")


async def demo_json_mode():
    """Demonstrate JSON mode capabilities with actual test calls."""
    print("\n=== JSON Mode Demo ===")

    # Test JSON mode with compatible models
    compatible_models = ["gpt-3.5-turbo", "grok-2"]

    # Example JSON schema for testing
    test_prompt = """
    Please respond with a JSON object containing information about a fictional product.
    The JSON should have this structure:
    {
        "product_name": "string",
        "price": number,
        "category": "string", 
        "in_stock": boolean,
        "features": ["string1", "string2"],
        "rating": number
    }
    
    Create a fictional product with realistic details.
    """

    for model_name in compatible_models:
        provider = get_model_provider(model_name)

        # Check if we have the necessary API key
        api_key_available = False
        if provider == "openai" and os.getenv("OPENAI_API_KEY"):
            api_key_available = True
        elif provider == "xai" and os.getenv("X_AI_API_KEY"):
            api_key_available = True

        if not api_key_available:
            print(
                f"⚠ {provider.upper()} API key not available, skipping {model_name} JSON test")
            continue

        try:
            # Create model with JSON mode
            json_model = create_chat_model(
                model_name=model_name,
                temperature=0.0,
                json_mode=True
            )
            print(
                f"✓ {provider.upper()} model ({model_name}) with JSON mode created")

            # Test actual JSON response
            print(f"  Testing JSON response from {model_name}...")
            response = await json_model.ainvoke([
                HumanMessage(content=test_prompt)
            ])

            # Handle different response formats
            try:
                import json

                # Check if response is already parsed (structured output) or needs parsing
                if isinstance(response, dict):
                    # Response is already structured (JSON mode worked)
                    parsed_json = response
                    print(f"  ✓ Structured JSON response received directly")
                elif hasattr(response, 'content'):
                    # Response has content attribute, try to parse it
                    parsed_json = json.loads(response.content)
                    print(f"  ✓ Valid JSON response parsed from content")
                else:
                    # Fallback: treat response as JSON string
                    parsed_json = json.loads(str(response))
                    print(f"  ✓ Valid JSON response parsed from string")

                # Display parsed results
                print(f"    Product: {parsed_json.get('product_name', 'N/A')}")
                print(f"    Price: ${parsed_json.get('price', 'N/A')}")
                print(f"    Category: {parsed_json.get('category', 'N/A')}")
                print(f"    In Stock: {parsed_json.get('in_stock', 'N/A')}")
                print(
                    f"    Features: {len(parsed_json.get('features', []))} items")
                print(f"    Rating: {parsed_json.get('rating', 'N/A')}/5")

                # Show full JSON (formatted)
                print(f"  Full JSON response:")
                print(f"    {json.dumps(parsed_json, indent=2)}")

            except (json.JSONDecodeError, AttributeError, TypeError) as e:
                print(f"  ✗ Response processing failed: {e}")
                print(f"  Response type: {type(response)}")
                print(f"  Response: {str(response)[:200]}...")

        except Exception as e:
            print(f"✗ JSON mode test failed for {model_name}: {e}")

        print()  # Add spacing between model tests

    # Test with a more complex JSON schema
    print("=== Complex JSON Schema Test ===")
    complex_prompt = """
    Generate a JSON object representing a user profile with the following structure:
    {
        "user": {
            "id": number,
            "name": "string",
            "email": "string",
            "preferences": {
                "theme": "light|dark",
                "notifications": boolean,
                "language": "string"
            },
            "activity": {
                "last_login": "ISO date string",
                "login_count": number,
                "achievements": ["string1", "string2"]
            }
        },
        "metadata": {
            "created_at": "ISO date string",
            "version": "string"
        }
    }
    """

    # Test with the first available model
    test_model = None
    test_provider = None

    for model_name in compatible_models:
        provider = get_model_provider(model_name)
        if ((provider == "openai" and os.getenv("OPENAI_API_KEY")) or
                (provider == "xai" and os.getenv("X_AI_API_KEY"))):
            test_model = model_name
            test_provider = provider
            break

    if test_model:
        try:
            complex_json_model = create_chat_model(
                model_name=test_model,
                temperature=0.1,
                json_mode=True
            )

            print(
                f"Testing complex JSON schema with {test_provider.upper()} ({test_model})...")
            response = await complex_json_model.ainvoke([
                HumanMessage(content=complex_prompt)
            ])

            try:
                import json

                # Handle different response formats for complex JSON
                if isinstance(response, dict):
                    parsed_json = response
                    print("✓ Complex structured JSON response received directly")
                elif hasattr(response, 'content'):
                    parsed_json = json.loads(response.content)
                    print("✓ Complex JSON response parsed from content")
                else:
                    parsed_json = json.loads(str(response))
                    print("✓ Complex JSON response parsed from string")

                print("✓ Complex JSON schema response received:")
                print(
                    f"  User ID: {parsed_json.get('user', {}).get('id', 'N/A')}")
                print(
                    f"  User Name: {parsed_json.get('user', {}).get('name', 'N/A')}")
                print(
                    f"  Theme: {parsed_json.get('user', {}).get('preferences', {}).get('theme', 'N/A')}")
                print(
                    f"  Login Count: {parsed_json.get('user', {}).get('activity', {}).get('login_count', 'N/A')}")
                print(
                    f"  Achievements: {len(parsed_json.get('user', {}).get('activity', {}).get('achievements', []))}")

            except (json.JSONDecodeError, AttributeError, TypeError) as e:
                print(f"✗ Complex JSON parsing failed: {e}")
                print(f"  Response type: {type(response)}")
                print(f"  Response: {str(response)[:200]}...")

        except Exception as e:
            print(f"✗ Complex JSON test failed: {e}")
    else:
        print("⚠ No API keys available for complex JSON test")

    # Note: JSON mode not supported for Anthropic and Gemini
    print("\nNote: JSON mode is only supported for OpenAI and XAI models")
    print("Anthropic and Gemini models can still produce JSON, but without guaranteed formatting.")


if __name__ == "__main__":
    """Run the model factory examples."""
    print("Model Factory Example")
    print("=" * 50)

    # Run async demo
    asyncio.run(test_model_factory())

    # Run tool binding demo
    demo_tool_binding()

    # Run JSON mode demo
    asyncio.run(demo_json_mode())

    print("\nTo use this example:")
    print("1. Set OPENAI_API_KEY environment variable for OpenAI models")
    print("2. Set ANTHROPIC_API_KEY environment variable for Anthropic models")
    print("3. Set GOOGLE_CLOUD_PROJECT and configure GCP credentials for Gemini models")
    print("4. Set X_AI_API_KEY environment variable for XAI (Grok) models")
    print("5. Optionally set DEFAULT_MODEL to change the default model")
    print("6. Run: python -m src.form_llm_agent.model_factory_example")
    print("\nSupported model examples:")
    print("  OpenAI: gpt-4, gpt-3.5-turbo, gpt-4o")
    print("  Anthropic: claude-3-opus, claude-3-sonnet, claude-3-haiku")
    print("  Gemini: gemini-1.5-pro, gemini-3-flash-preview, gemini-1.0-pro")
    print("  XAI: grok-2, grok-3-mini, grok-beta")
