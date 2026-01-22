"""
Test runner for Form LLM Agent tests.

This script provides a convenient way to run all tests for the form LLM agent
with proper environment setup and reporting.
"""

import os
import sys
import asyncio
import argparse
from typing import List, Optional


def setup_test_environment():
    """Set up the test environment with default values."""
    # Set default test configuration
    if not os.environ.get('FORM_AGENT_MODEL'):
        os.environ['FORM_AGENT_MODEL'] = 'gpt-3.5-turbo'
    if not os.environ.get('FORM_AGENT_TEMPERATURE'):
        os.environ['FORM_AGENT_TEMPERATURE'] = '0.4'
    if not os.environ.get('FORM_AGENT_JSON_MODE'):
        os.environ['FORM_AGENT_JSON_MODE'] = 'true'


def check_api_keys():
    """Check which API keys are available for testing."""
    available_providers = []

    if os.environ.get("OPENAI_API_KEY"):
        available_providers.append("OpenAI")
    if os.environ.get("ANTHROPIC_API_KEY"):
        available_providers.append("Anthropic")
    if os.environ.get("GOOGLE_CLOUD_PROJECT"):
        available_providers.append("Gemini")
    if os.environ.get("X_AI_API_KEY"):
        available_providers.append("XAI")

    return available_providers


async def run_integration_tests():
    """Run the integration tests."""
    print("🧪 Running Integration Tests")
    print("=" * 50)

    try:
        from .test_integration import run_comprehensive_test
        await run_comprehensive_test()
        return True
    except Exception as e:
        print(f"❌ Integration tests failed: {str(e)}")
        return False


async def run_model_factory_tests():
    """Run the model factory tests."""
    print("\n🏭 Running Model Factory Tests")
    print("=" * 50)

    try:
        from .test_model_factory import test_model_factory, demo_tool_binding, demo_json_mode

        # Run async tests
        await test_model_factory()

        # Run sync tests
        demo_tool_binding()
        await demo_json_mode()

        return True
    except Exception as e:
        print(f"❌ Model factory tests failed: {str(e)}")
        return False


async def run_performance_tests():
    """Run the performance logging tests."""
    print("\n⚡ Running Performance Logging Tests")
    print("=" * 50)

    try:
        from .test_performance_logging import run_performance_tests

        # Run performance tests
        await run_performance_tests()

        return True
    except Exception as e:
        print(f"❌ Performance tests failed: {str(e)}")
        return False


async def run_fast_models_tests():
    """Run the fast models parallel tests."""
    print("\n🏎️ Running Fast Models Parallel Tests")
    print("=" * 50)

    try:
        from .test_fast_models_parallel import run_comprehensive_fast_model_tests

        # Run fast models tests
        await run_comprehensive_fast_model_tests()

        return True
    except Exception as e:
        print(f"❌ Fast models tests failed: {str(e)}")
        return False


async def run_post_endpoint_tests():
    """Run the POST endpoint tests."""
    print("\n📮 Running POST Endpoint Tests")
    print("=" * 50)

    try:
        from .test_post_endpoint import run_post_endpoint_tests

        # Run POST endpoint tests
        await run_post_endpoint_tests()

        return True
    except Exception as e:
        print(f"❌ POST endpoint tests failed: {str(e)}")
        return False


def print_test_environment_info():
    """Print information about the test environment."""
    print("🔧 Test Environment Information")
    print("=" * 50)

    # Model configuration
    model_name = os.environ.get('FORM_AGENT_MODEL', 'Not set')
    temperature = os.environ.get('FORM_AGENT_TEMPERATURE', 'Not set')
    json_mode = os.environ.get('FORM_AGENT_JSON_MODE', 'Not set')

    print(f"Model: {model_name}")
    print(f"Temperature: {temperature}")
    print(f"JSON Mode: {json_mode}")

    # Available providers
    available_providers = check_api_keys()
    if available_providers:
        print(f"Available Providers: {', '.join(available_providers)}")
    else:
        print("⚠️  No API keys detected - some tests will be skipped")

    print()


async def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(description="Run Form LLM Agent tests")
    parser.add_argument(
        "--test",
        choices=["all", "integration", "model-factory",
                 "performance", "fast-models", "post-endpoint"],
        default="all",
        help="Which tests to run (default: all)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--skip-env-check",
        action="store_true",
        help="Skip API key environment check"
    )

    args = parser.parse_args()

    # Setup
    setup_test_environment()

    print("🚀 Form LLM Agent Test Suite")
    print("=" * 50)

    if not args.skip_env_check:
        print_test_environment_info()

    results = []

    # Run tests based on selection
    if args.test in ["all", "integration"]:
        success = await run_integration_tests()
        results.append(("Integration Tests", success))

    if args.test in ["all", "model-factory"]:
        success = await run_model_factory_tests()
        results.append(("Model Factory Tests", success))

    if args.test in ["all", "performance"]:
        success = await run_performance_tests()
        results.append(("Performance Tests", success))

    if args.test in ["all", "fast-models"]:
        success = await run_fast_models_tests()
        results.append(("Fast Models Tests", success))

    if args.test in ["all", "post-endpoint"]:
        success = await run_post_endpoint_tests()
        results.append(("POST Endpoint Tests", success))

    # Print results summary
    print("\n📊 Test Results Summary")
    print("=" * 50)

    total_tests = len(results)
    passed_tests = sum(1 for _, success in results if success)

    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{test_name}: {status}")

    print(f"\nTotal: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("🎉 All tests passed!")
        return 0
    else:
        print("💥 Some tests failed!")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test runner failed: {str(e)}")
        sys.exit(1)
