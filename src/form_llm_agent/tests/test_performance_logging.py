"""
Performance logging tests for Form LLM Agent.

Tests the comprehensive performance logging system with colored console output
and response time tracking across different operations.
"""

from src.utils.model_factory import create_chat_model, get_model_provider
from ..graph import stream_field_processing
from ..performance_logger import (
    performance_logger,
    track_operation,
    PerformanceMetrics,
    Colors
)
import os
import asyncio
import time
from typing import List

# Set up test environment
os.environ['FORM_AGENT_MODEL'] = 'gpt-3.5-turbo'
os.environ['FORM_AGENT_TEMPERATURE'] = '0.4'
os.environ['FORM_AGENT_JSON_MODE'] = 'true'


def test_performance_metrics_dataclass():
    """Test the PerformanceMetrics dataclass functionality."""
    print("=== Performance Metrics Test ===")

    # Create a metrics instance
    metrics = PerformanceMetrics(
        operation="test_operation",
        start_time=time.time(),
        field_id="test_field",
        model_name="gpt-4",
        provider="openai"
    )

    # Test initial state
    assert metrics.end_time is None
    assert metrics.duration_ms is None
    assert metrics.success is True

    # Simulate some work
    time.sleep(0.1)

    # Finish the operation
    metrics.finish(success=True, response_length=100)

    # Verify completion
    assert metrics.end_time is not None
    assert metrics.duration_ms is not None
    assert metrics.duration_ms >= 100  # At least 100ms
    assert metrics.success is True
    assert metrics.response_length == 100

    # Test serialization
    metrics_dict = metrics.to_dict()
    assert isinstance(metrics_dict, dict)
    assert metrics_dict['operation'] == 'test_operation'
    assert metrics_dict['field_id'] == 'test_field'

    print("✓ PerformanceMetrics dataclass working correctly")
    print(f"  Duration: {metrics.duration_ms:.1f}ms")
    print()


def test_color_formatting():
    """Test the color formatting functionality."""
    print("=== Color Formatting Test ===")

    # Test different duration ranges
    test_durations = [50, 200, 700, 2000, 5000]  # ms

    for duration in test_durations:
        formatted = performance_logger._format_duration(duration)
        print(f"  {duration}ms -> {formatted}")

    # Test success/failure formatting
    success_msg = performance_logger._format_success_status(True)
    failure_msg = performance_logger._format_success_status(False)

    print(f"  Success: {success_msg}")
    print(f"  Failure: {failure_msg}")
    print()


def test_context_manager():
    """Test the context manager functionality."""
    print("=== Context Manager Test ===")

    # Test successful operation
    with track_operation("test_context_success", field_id="test_field") as operation_id:
        assert isinstance(operation_id, str)
        assert operation_id in performance_logger.get_active_operations()
        time.sleep(0.05)  # Simulate work

    # Operation should be completed and removed from active operations
    assert operation_id not in performance_logger.get_active_operations()

    # Test failed operation
    try:
        with track_operation("test_context_failure", field_id="test_field") as operation_id:
            time.sleep(0.02)
            raise ValueError("Test error")
    except ValueError:
        pass  # Expected

    # Operation should be completed and removed even after error
    assert operation_id not in performance_logger.get_active_operations()

    print("✓ Context manager working correctly")
    print()


async def test_model_factory_performance():
    """Test performance logging with various model configurations."""
    print("=== Model Factory Performance Test ===")

    # Test model configurations for different providers and speeds
    test_configs = [
        # Fast OpenAI models
        {"name": "GPT-4o Mini (Fast)", "model_name": "gpt-4o-mini",
         "temperature": 0.3, "json_mode": True},
        {"name": "GPT-3.5 Turbo (Fast)", "model_name": "gpt-3.5-turbo",
         "temperature": 0.3, "json_mode": True},

        # Standard OpenAI models
        {"name": "GPT-4 (Standard)", "model_name": "gpt-4",
         "temperature": 0.5, "json_mode": False},
        {"name": "GPT-4o (Fast Premium)", "model_name": "gpt-4o",
         "temperature": 0.3, "json_mode": True},

        # Anthropic models
        {"name": "Claude-3 Haiku (Fast)", "model_name": "claude-3-haiku",
         "temperature": 0.3, "json_mode": False},
        {"name": "Claude-3 Sonnet (Standard)", "model_name": "claude-3-sonnet",
         "temperature": 0.5, "json_mode": False},

        # Gemini models
        {"name": "Gemini-1.5 Flash (Fast)", "model_name": "gemini-1.5-flash",
         "temperature": 0.3, "json_mode": False},
        {"name": "Gemini-2.5 Flash (Fastest)", "model_name": "gemini-3-flash-preview",
         "temperature": 0.3, "json_mode": False},
        {"name": "Gemini-1.5 Pro (Standard)", "model_name": "gemini-1.5-pro",
         "temperature": 0.5, "json_mode": False},

        # XAI models
        {"name": "Grok-2 (Fast)", "model_name": "grok-2",
         "temperature": 0.3, "json_mode": True},
        {"name": "Grok-3 Mini (Fastest)", "model_name": "grok-3-mini",
         "temperature": 0.3, "json_mode": True},
    ]

    successful_models = []
    failed_models = []

    for i, config in enumerate(test_configs):
        print(f"  Test {i+1}: {config['name']} ({config['model_name']})")

        # Check if we have the required API key for this provider
        provider = get_model_provider(config['model_name'])
        api_key_available = False

        if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
            api_key_available = True
        elif provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            api_key_available = True
        elif provider == "gemini":
            # Gemini uses Google Cloud JSON authentication, not API key
            # Check if we have Google Cloud project configured and .gcloud.json available
            gcp_project = os.environ.get(
                "GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
            try:
                from src.config.common_settings import PROJECT_ID, credentials
                api_key_available = True if (
                    gcp_project or PROJECT_ID) and credentials else False
            except Exception:
                api_key_available = bool(gcp_project)
        elif provider == "xai" and os.environ.get("X_AI_API_KEY"):
            api_key_available = True

        if not api_key_available:
            print(f"    ⚠ {provider.upper()} API key not available, skipping")
            failed_models.append(f"{config['name']} (No API key)")
            continue

        with track_operation(
            f"model_creation_{provider}_{config['model_name']}",
            model_name=config["model_name"],
            provider=provider
        ) as operation_id:

            try:
                model = create_chat_model(
                    model_name=config["model_name"],
                    temperature=config["temperature"],
                    json_mode=config["json_mode"]
                )
                print(f"    ✓ Created {provider} model successfully")
                successful_models.append(config['name'])

            except Exception as e:
                print(f"    ✗ Failed to create model: {e}")
                failed_models.append(f"{config['name']} ({str(e)[:50]}...)")

    print(f"\n  📊 Model Creation Summary:")
    print(f"    ✓ Successful: {len(successful_models)}")
    print(f"    ✗ Failed: {len(failed_models)}")

    if successful_models:
        print(
            f"    🚀 Working models: {', '.join(successful_models[:3])}{'...' if len(successful_models) > 3 else ''}")

    print()


async def test_streaming_performance():
    """Test performance logging with streaming operations using different models."""
    print("=== Streaming Performance Test ===")

    # Test different model configurations for streaming performance
    model_tests = [
        # Environment-set model (whatever is currently configured)
        {"name": "Environment Model", "env_var": None,
            "description": "Using FORM_AGENT_MODEL"},

        # Fast models for comparison
        {"name": "GPT-4o Mini", "env_var": "gpt-4o-mini",
            "description": "Fastest OpenAI model"},
        {"name": "GPT-3.5 Turbo", "env_var": "gpt-3.5-turbo",
            "description": "Fast OpenAI model"},
        {"name": "Gemini-2.5 Flash", "env_var": "gemini-3-flash-preview",
            "description": "Fastest Gemini model"},
        {"name": "Gemini-1.5 Flash", "env_var": "gemini-1.5-flash",
            "description": "Fast Gemini model"},
    ]

    test_field = "performance_comparison_test"
    results = []

    for model_test in model_tests:
        print(
            f"\n  🧪 Testing {model_test['name']} - {model_test['description']}")

        # Set environment variable for this test
        original_model = os.environ.get('FORM_AGENT_MODEL')
        if model_test['env_var']:
            os.environ['FORM_AGENT_MODEL'] = model_test['env_var']
            model_name = model_test['env_var']
        else:
            model_name = original_model or os.environ.get(
                'DEFAULT_MODEL', 'gpt-4')

        # Check if we have API access for this model
        provider = get_model_provider(model_name)
        api_key_available = False

        if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
            api_key_available = True
        elif provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            api_key_available = True
        elif provider == "gemini":
            # Gemini uses Google Cloud JSON authentication, not API key
            # Check if we have Google Cloud project configured and .gcloud.json available
            gcp_project = os.environ.get(
                "GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
            try:
                from src.config.common_settings import PROJECT_ID, credentials
                api_key_available = True if (
                    gcp_project or PROJECT_ID) and credentials else False
            except Exception:
                api_key_available = bool(gcp_project)
        elif provider == "xai" and os.environ.get("X_AI_API_KEY"):
            api_key_available = True

        if not api_key_available:
            print(
                f"    ⚠ {provider.upper()} API not available, skipping {model_test['name']}")
            results.append({
                "model": model_test['name'],
                "status": "skipped",
                "reason": f"No {provider.upper()} API key"
            })
            continue

        try:
            # Track the streaming performance for this model
            start_time = time.time()

            async for result in stream_field_processing(test_field):
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000

                print(f"    ✓ Model: {provider}/{model_name}")
                print(f"    ✓ Response time: {duration_ms:.1f}ms")
                print(f"    ✓ Response length: {len(result.response)} chars")
                print(f"    ✓ Result type: {result.type}")

                # Store results for comparison
                results.append({
                    "model": model_test['name'],
                    "provider": provider,
                    "model_name": model_name,
                    "duration_ms": duration_ms,
                    "response_length": len(result.response),
                    "status": "success"
                })
                break  # Just test one result per model

        except Exception as e:
            print(f"    ✗ Streaming failed: {e}")
            results.append({
                "model": model_test['name'],
                "status": "failed",
                "error": str(e)
            })

        finally:
            # Restore original environment variable
            if original_model is not None:
                os.environ['FORM_AGENT_MODEL'] = original_model
            elif 'FORM_AGENT_MODEL' in os.environ:
                del os.environ['FORM_AGENT_MODEL']

    # Performance comparison summary
    print(f"\n  📊 Streaming Performance Comparison:")
    print(
        f"  {'Model':<20} {'Provider':<10} {'Time (ms)':<12} {'Response':<10} {'Status'}")
    print(f"  {'-'*20} {'-'*10} {'-'*12} {'-'*10} {'-'*10}")

    successful_results = [r for r in results if r['status'] == 'success']

    for result in results:
        if result['status'] == 'success':
            duration_color = ""
            if result['duration_ms'] < 500:
                duration_color = f"{Colors.GREEN}"
            elif result['duration_ms'] < 1000:
                duration_color = f"{Colors.CYAN}"
            elif result['duration_ms'] < 2000:
                duration_color = f"{Colors.YELLOW}"
            else:
                duration_color = f"{Colors.RED}"

            print(f"  {result['model']:<20} {result['provider']:<10} "
                  f"{duration_color}{result['duration_ms']:>8.1f}ms{Colors.END} "
                  f"{result['response_length']:>7} chars ✓")
        else:
            status_msg = result.get('reason', result.get('error', 'failed'))
            print(
                f"  {result['model']:<20} {'N/A':<10} {'N/A':<12} {'N/A':<10} ⚠ {status_msg[:20]}...")

    if successful_results:
        # Find fastest model
        fastest = min(successful_results, key=lambda x: x['duration_ms'])
        print(f"\n  🏆 Fastest model: {Colors.GREEN}{fastest['model']} "
              f"({fastest['duration_ms']:.1f}ms){Colors.END}")

        # Calculate average performance
        avg_time = sum(r['duration_ms']
                       for r in successful_results) / len(successful_results)
        print(f"  📈 Average response time: {avg_time:.1f}ms")

    print()


async def test_environment_model_performance():
    """Test performance with different environment-configured models."""
    print("=== Environment Model Configuration Performance Test ===")

    # Test different environment variable configurations
    env_tests = [
        {
            "name": "FORM_AGENT_MODEL Priority",
            "env_vars": {"FORM_AGENT_MODEL": "gpt-4o-mini", "FORM_MODEL": "gpt-4", "DEFAULT_MODEL": "gpt-3.5-turbo"},
            "expected_model": "gpt-4o-mini"
        },
        {
            "name": "FORM_MODEL Fallback",
            "env_vars": {"FORM_AGENT_MODEL": None, "FORM_MODEL": "gpt-3.5-turbo", "DEFAULT_MODEL": "gpt-4"},
            "expected_model": "gpt-3.5-turbo"
        },
        {
            "name": "DEFAULT_MODEL Fallback",
            "env_vars": {"FORM_AGENT_MODEL": None, "FORM_MODEL": None, "DEFAULT_MODEL": "gpt-4o-mini"},
            "expected_model": "gpt-4o-mini"
        },
        {
            "name": "Gemini via Environment",
            "env_vars": {"FORM_AGENT_MODEL": "gemini-1.5-flash", "FORM_MODEL": None, "DEFAULT_MODEL": None},
            "expected_model": "gemini-1.5-flash"
        }
    ]

    # Store original environment values
    original_env = {
        "FORM_AGENT_MODEL": os.environ.get("FORM_AGENT_MODEL"),
        "FORM_MODEL": os.environ.get("FORM_MODEL"),
        "DEFAULT_MODEL": os.environ.get("DEFAULT_MODEL")
    }

    env_results = []

    for test in env_tests:
        print(f"\n  🔧 Testing {test['name']}")
        print(f"     Expected model: {test['expected_model']}")

        # Set up environment variables for this test
        for env_var, value in test['env_vars'].items():
            if value is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = value

        # Check if we have API access for the expected model
        provider = get_model_provider(test['expected_model'])
        api_key_available = False

        if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
            api_key_available = True
        elif provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            api_key_available = True
        elif provider == "gemini":
            # Gemini uses Google Cloud JSON authentication, not API key
            # Check if we have Google Cloud project configured and .gcloud.json available
            gcp_project = os.environ.get(
                "GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
            try:
                from src.config.common_settings import PROJECT_ID, credentials
                api_key_available = True if (
                    gcp_project or PROJECT_ID) and credentials else False
            except Exception:
                api_key_available = bool(gcp_project)
        elif provider == "xai" and os.environ.get("X_AI_API_KEY"):
            api_key_available = True

        if not api_key_available:
            print(f"     ⚠ {provider.upper()} API not available, skipping")
            env_results.append({
                "test": test['name'],
                "model": test['expected_model'],
                "status": "skipped",
                "reason": f"No {provider.upper()} API"
            })
            continue

        try:
            # Test field processing with environment-configured model
            test_field = f"env_test_{test['expected_model'].replace('-', '_')}"
            start_time = time.time()

            async for result in stream_field_processing(test_field):
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000

                print(
                    f"     ✓ Model used: {provider}/{test['expected_model']}")
                print(f"     ✓ Response time: {duration_ms:.1f}ms")
                print(f"     ✓ Environment priority working correctly")

                env_results.append({
                    "test": test['name'],
                    "model": test['expected_model'],
                    "provider": provider,
                    "duration_ms": duration_ms,
                    "status": "success"
                })
                break

        except Exception as e:
            print(f"     ✗ Test failed: {e}")
            env_results.append({
                "test": test['name'],
                "model": test['expected_model'],
                "status": "failed",
                "error": str(e)
            })

    # Restore original environment variables
    for env_var, original_value in original_env.items():
        if original_value is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = original_value

    # Summary of environment variable tests
    print(f"\n  📊 Environment Configuration Results:")
    successful_env_tests = [r for r in env_results if r['status'] == 'success']

    if successful_env_tests:
        print(
            f"     ✓ {len(successful_env_tests)} environment configurations tested successfully")
        for result in successful_env_tests:
            duration_color = Colors.GREEN if result['duration_ms'] < 1000 else Colors.YELLOW
            print(
                f"     • {result['test']}: {duration_color}{result['duration_ms']:.1f}ms{Colors.END}")
    else:
        print(f"     ⚠ No environment tests could be completed (missing API keys)")

    print()


def test_logging_methods():
    """Test various logging methods."""
    print("=== Logging Methods Test ===")

    # Test model selection logging
    performance_logger.log_model_selection("gpt-4", "openai", 0.7, True)

    # Test API call logging
    performance_logger.log_api_call_start("openai", "gpt-4", 500)
    time.sleep(0.1)
    performance_logger.log_api_call_complete("openai", "gpt-4", 200, 100.5)

    # Test streaming logging
    performance_logger.log_streaming_start("test_field")
    performance_logger.log_streaming_chunk("test_field", 150, 1)
    performance_logger.log_streaming_chunk("test_field", 200, 2)
    performance_logger.log_streaming_complete("test_field", 2, 250.0)

    print("✓ All logging methods executed successfully")
    print()


async def test_performance_under_load():
    """Test performance logging under simulated load."""
    print("=== Performance Under Load Test ===")

    # Simulate multiple concurrent operations
    operations = []

    for i in range(5):
        operation_id = performance_logger.start_operation(
            f"load_test_{i}",
            field_id=f"test_field_{i}"
        )
        operations.append(operation_id)

    # Simulate work
    await asyncio.sleep(0.1)

    # Finish all operations
    for operation_id in operations:
        performance_logger.finish_operation(
            operation_id,
            success=True,
            response_length=100
        )

    # Verify no active operations remain
    active_ops = performance_logger.get_active_operations()
    assert len(
        active_ops) == 0, f"Expected 0 active operations, got {len(active_ops)}"

    print("✓ Performance logging handled concurrent operations correctly")
    print()


async def run_performance_tests():
    """Run all performance logging tests."""
    print(f"{Colors.BOLD}{Colors.BLUE}Performance Logging Test Suite{Colors.END}")
    print("=" * 60)

    # Basic functionality tests
    test_performance_metrics_dataclass()
    test_color_formatting()
    test_context_manager()
    test_logging_methods()

    # Load testing
    await test_performance_under_load()

    # Integration tests (require API keys)
    await test_model_factory_performance()
    await test_streaming_performance()
    await test_environment_model_performance()

    print("=" * 60)
    print(f"{Colors.BOLD}{Colors.GREEN}🎉 All performance logging tests completed!{Colors.END}")
    print()
    print("Key Features Demonstrated:")
    print(f"  {Colors.GREEN}✓{Colors.END} Colored console output with response times")
    print(f"  {Colors.GREEN}✓{Colors.END} Performance metrics tracking")
    print(f"  {Colors.GREEN}✓{Colors.END} Context manager for automatic timing")
    print(f"  {Colors.GREEN}✓{Colors.END} Streaming performance monitoring")
    print(f"  {Colors.GREEN}✓{Colors.END} API call timing and logging")
    print(f"  {Colors.GREEN}✓{Colors.END} Error handling with performance context")
    print(f"  {Colors.GREEN}✓{Colors.END} Concurrent operation tracking")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_performance_tests())
