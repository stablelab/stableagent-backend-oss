"""
Parallelized performance tests for the fastest recent models.

Tests the 3 fastest recent Gemini models and latest Grok models with parallel execution
for comprehensive performance comparison.

Based on:
- Gemini API docs: https://ai.google.dev/gemini-api/docs/models
- xAI docs: https://docs.x.ai/docs/models
"""

from ..performance_logger import performance_logger, track_operation, Colors
from ..graph import stream_field_processing
from src.utils.model_factory import create_chat_model, get_model_provider
import os
import asyncio
import time
import sys
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set up test environment
os.environ['FORM_AGENT_TEMPERATURE'] = '0.3'
os.environ['FORM_AGENT_JSON_MODE'] = 'true'


class FastModelTester:
    """Tester for fast models with parallel execution and minimal logging."""

    def __init__(self):
        self.results = []
        self.completed_models = []
        self.total_models = 0

        # Define the fastest recent models based on documentation
        self.fast_models = [
            # 3 Fastest Recent Gemini Models (from https://ai.google.dev/gemini-api/docs/models)
            {
                "name": "Gemini 2.5 Flash-Lite",
                "model_id": "gemini-3-flash-preview-lite",
                "provider": "gemini",
                "description": "Most cost-efficient, optimized for low latency",
                "priority": 1
            },
            {
                "name": "Gemini 2.5 Flash",
                "model_id": "gemini-3-flash-preview",
                "provider": "gemini",
                "description": "Best price-performance with adaptive thinking",
                "priority": 2
            },
            {
                "name": "Gemini 2.0 Flash-Lite",
                "model_id": "gemini-2.0-flash-lite",
                "provider": "gemini",
                "description": "Cost efficiency and low latency",
                "priority": 3
            },

            # Latest Grok Models (from https://docs.x.ai/docs/models)
            {
                "name": "Grok 4 Fast Reasoning",
                "model_id": "grok-4-fast-reasoning",
                "provider": "xai",
                "description": "Latest fast reasoning model (2M context, $0.20/$0.50)",
                "priority": 1
            },
            {
                "name": "Grok 4 Fast Non-Reasoning",
                "model_id": "grok-4-fast-non-reasoning",
                "provider": "xai",
                "description": "Latest fast non-reasoning model (2M context, $0.20)",
                "priority": 1
            },
            {
                "name": "Grok Code Fast 1",
                "model_id": "grok-code-fast-1",
                "provider": "xai",
                "description": "Latest code-optimized model (256K context, $0.20/$1.50)",
                "priority": 2
            },

            # Fast OpenAI models for comparison
            {
                "name": "GPT-4o Mini",
                "model_id": "gpt-4o-mini",
                "provider": "openai",
                "description": "Fastest OpenAI model",
                "priority": 1
            },
            {
                "name": "GPT-3.5 Turbo",
                "model_id": "gpt-3.5-turbo",
                "provider": "openai",
                "description": "Fast and reliable OpenAI model",
                "priority": 2
            }
        ]

    def check_model_availability(self, model_config: Dict[str, Any]) -> bool:
        """Check if a model is available for testing."""
        provider = model_config["provider"]

        if provider == "openai":
            return bool(os.environ.get("OPENAI_API_KEY"))
        elif provider == "anthropic":
            return bool(os.environ.get("ANTHROPIC_API_KEY"))
        elif provider == "gemini":
            # Check for Google Cloud authentication
            gcp_project = os.environ.get(
                "GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
            try:
                from src.config.common_settings import PROJECT_ID, credentials
                return bool((gcp_project or PROJECT_ID) and credentials)
            except Exception:
                return bool(gcp_project)
        elif provider == "xai":
            return bool(os.environ.get("X_AI_API_KEY"))

        return False

    def _update_progress(self, completed: int, total: int, current_model: str = ""):
        """Update progress on a single line."""
        progress_bar = "█" * (completed * 20 // total) + \
            "░" * (20 - completed * 20 // total)
        percentage = (completed / total) * 100
        status_line = f"\r🚀 Testing [{progress_bar}] {completed}/{total} ({percentage:.0f}%) - {current_model}"
        print(status_line, end='', flush=True)

    async def test_single_model_performance(self, model_config: Dict[str, Any]) -> Dict[str, Any]:
        """Test performance of a single model with minimal logging."""
        model_id = model_config["model_id"]
        provider = model_config["provider"]

        # Set environment to use this specific model
        original_model = os.environ.get('FORM_AGENT_MODEL')
        os.environ['FORM_AGENT_MODEL'] = model_id

        try:
            test_field = f"parallel_test_{model_id.replace('-', '_')}"
            start_time = time.time()

            # Temporarily disable performance logging during parallel execution
            original_log_level = performance_logger.logger.level
            performance_logger.logger.setLevel(50)  # Critical only

            async for result in stream_field_processing(test_field):
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000

                # Restore logging level
                performance_logger.logger.setLevel(original_log_level)

                # Update progress
                self.completed_models.append(model_config["name"])
                self._update_progress(len(
                    self.completed_models), self.total_models, f"Completed {model_config['name']}")

                return {
                    "model_name": model_config["name"],
                    "model_id": model_id,
                    "provider": provider,
                    "description": model_config["description"],
                    "priority": model_config["priority"],
                    "duration_ms": duration_ms,
                    "response_length": len(result.response),
                    "response_text": result.response,
                    "result_type": result.type,
                    "success": not result.is_error,
                    "status": "success"
                }

        except Exception as e:
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            # Restore logging level
            performance_logger.logger.setLevel(original_log_level)

            # Update progress
            self.completed_models.append(f"{model_config['name']} (Failed)")
            self._update_progress(
                len(self.completed_models), self.total_models, f"Failed {model_config['name']}")

            return {
                "model_name": model_config["name"],
                "model_id": model_id,
                "provider": provider,
                "description": model_config["description"],
                "priority": model_config["priority"],
                "duration_ms": duration_ms,
                "success": False,
                "status": "failed",
                "error": str(e)[:100] + "..." if len(str(e)) > 100 else str(e)
            }

        finally:
            # Restore original environment
            if original_model is not None:
                os.environ['FORM_AGENT_MODEL'] = original_model
            elif 'FORM_AGENT_MODEL' in os.environ:
                del os.environ['FORM_AGENT_MODEL']

    async def run_parallel_model_tests(self) -> List[Dict[str, Any]]:
        """Run model performance tests in parallel."""
        print("=== Parallel Fast Model Performance Test ===")
        print("Testing the 3 fastest recent Gemini models + latest Grok models")
        print("Based on:")
        print("  • Gemini API: https://ai.google.dev/gemini-api/docs/models")
        print("  • xAI API: https://docs.x.ai/docs/models")
        print()

        # Filter available models
        available_models = [
            model for model in self.fast_models
            if self.check_model_availability(model)
        ]

        unavailable_models = [
            model for model in self.fast_models
            if not self.check_model_availability(model)
        ]

        print(f"📊 Model Availability:")
        print(f"  ✓ Available: {len(available_models)} models")
        print(
            f"  ⚠ Unavailable: {len(unavailable_models)} models (missing API keys/auth)")
        print()

        if not available_models:
            print("❌ No models available for testing. Please configure API keys.")
            return []

        # Set up progress tracking
        self.total_models = len(available_models)
        self.completed_models = []

        # Initialize progress display
        print(f"🚀 Running {len(available_models)} model tests in parallel...")
        self._update_progress(0, self.total_models, "Starting tests...")

        # Create tasks for parallel execution
        tasks = [
            self.test_single_model_performance(model_config)
            for model_config in available_models
        ]

        # Execute all tasks concurrently
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_duration = (time.time() - start_time) * 1000

        # Clear progress line and move to next line
        print(
            f"\r🎉 All {len(available_models)} models tested in {total_duration:.1f}ms" + " " * 20)

        # Process results
        successful_results = []
        failed_results = []

        for result in results:
            if isinstance(result, Exception):
                failed_results.append({
                    "status": "exception",
                    "error": str(result)
                })
            elif result.get("success", False):
                successful_results.append(result)
            else:
                failed_results.append(result)

        # Display example responses first
        self._display_example_responses(successful_results)

        # Then display performance results
        self._display_parallel_results(
            successful_results, failed_results, total_duration)

        return successful_results + failed_results

    def _display_example_responses(self, successful_results: List[Dict[str, Any]]):
        """Display example responses from each model."""
        if not successful_results:
            return

        print(f"\n📝 Example Responses from Each Model:")
        print("=" * 70)

        # Sort by speed for display
        sorted_results = sorted(
            successful_results, key=lambda x: x['duration_ms'])

        for i, result in enumerate(sorted_results, 1):
            model_name = result['model_name']
            provider = result['provider']
            duration = result['duration_ms']
            response = result.get('response_text', '')

            # Truncate response for display
            display_response = response[:200] + \
                "..." if len(response) > 200 else response

            duration_color = self._get_duration_color(duration)

            print(
                f"\n{i}. {Colors.BOLD}{provider.upper()}/{result['model_id']}{Colors.END}")
            print(f"   Name: {model_name}")
            print(f"   Time: {duration_color}{duration:.1f}ms{Colors.END}")
            print(f"   Response: {display_response}")

        print("\n" + "=" * 70)

    def _display_parallel_results(
        self,
        successful_results: List[Dict[str, Any]],
        failed_results: List[Dict[str, Any]],
        total_duration: float
    ):
        """Display parallel test results in a formatted table."""
        print(
            f"\n📊 Parallel Test Results (Total time: {Colors.BOLD}{total_duration:.1f}ms{Colors.END}):")
        print(f"{'Model':<25} {'Provider':<8} {'Priority':<8} {'Time (ms)':<12} {'Response':<10} {'Status'}")
        print(f"{'-'*25} {'-'*8} {'-'*8} {'-'*12} {'-'*10} {'-'*10}")

        # Sort successful results by duration (fastest first)
        successful_results.sort(key=lambda x: x['duration_ms'])

        # Display successful results
        for result in successful_results:
            duration_color = self._get_duration_color(result['duration_ms'])
            priority_indicator = "🏆" if result['priority'] == 1 else "🥈" if result['priority'] == 2 else "🥉"

            print(f"{result['model_name']:<25} {result['provider']:<8} {priority_indicator:<8} "
                  f"{duration_color}{result['duration_ms']:>8.1f}ms{Colors.END} "
                  f"{result.get('response_length', 0):>7} chars ✓")

        # Display failed results
        for result in failed_results:
            if result['status'] == 'exception':
                print(
                    f"{'Exception':<25} {'N/A':<8} {'N/A':<8} {'N/A':<12} {'N/A':<10} ❌ {result['error'][:30]}...")
            else:
                print(
                    f"{result['model_name']:<25} {result['provider']:<8} {'N/A':<8} {'N/A':<12} {'N/A':<10} ❌ {result.get('error', 'Failed')[:30]}...")

        # Performance analysis
        if successful_results:
            fastest = min(successful_results, key=lambda x: x['duration_ms'])
            slowest = max(successful_results, key=lambda x: x['duration_ms'])
            avg_time = sum(r['duration_ms']
                           for r in successful_results) / len(successful_results)

            print(f"\n🏁 Performance Analysis:")
            print(
                f"  🏆 Fastest: {Colors.GREEN}{fastest['model_name']} ({fastest['duration_ms']:.1f}ms){Colors.END}")
            print(f"  🐌 Slowest: {fastest['model_name'] if len(successful_results) == 1 else slowest['model_name']} "
                  f"({slowest['duration_ms']:.1f}ms)")
            print(f"  📈 Average: {avg_time:.1f}ms")
            print(f"  📊 Success Rate: {len(successful_results)}/{len(successful_results) + len(failed_results)} "
                  f"({len(successful_results)/(len(successful_results) + len(failed_results))*100:.1f}%)")

            # Provider breakdown
            provider_stats = {}
            for result in successful_results:
                provider = result['provider']
                if provider not in provider_stats:
                    provider_stats[provider] = {'count': 0, 'total_time': 0}
                provider_stats[provider]['count'] += 1
                provider_stats[provider]['total_time'] += result['duration_ms']

            print(f"\n🔍 Provider Performance:")
            for provider, stats in provider_stats.items():
                avg_provider_time = stats['total_time'] / stats['count']
                color = self._get_duration_color(avg_provider_time)
                print(
                    f"  {provider.upper()}: {color}{avg_provider_time:.1f}ms avg{Colors.END} ({stats['count']} models)")

    def _get_duration_color(self, duration_ms: float) -> str:
        """Get color for duration based on performance level."""
        if duration_ms < 500:
            return Colors.GREEN
        elif duration_ms < 1000:
            return Colors.CYAN
        elif duration_ms < 2000:
            return Colors.YELLOW
        elif duration_ms < 5000:
            return Colors.MAGENTA
        else:
            return Colors.RED


async def test_model_creation_parallel():
    """Test model creation in parallel for all fast models with minimal logging."""
    print("=== Parallel Model Creation Test ===")

    tester = FastModelTester()

    # Test model creation for all available models
    available_models = [
        model for model in tester.fast_models
        if tester.check_model_availability(model)
    ]

    if not available_models:
        print("❌ No models available for testing")
        return

    print(
        f"🏭 Testing model creation for {len(available_models)} models in parallel...")

    # Progress tracking for creation
    completed_count = 0
    total_count = len(available_models)

    async def create_model_test(model_config):
        """Test creating a single model with minimal logging."""
        nonlocal completed_count

        try:
            # Temporarily disable performance logging
            original_log_level = performance_logger.logger.level
            performance_logger.logger.setLevel(50)  # Critical only

            model = create_chat_model(
                model_name=model_config['model_id'],
                temperature=0.3,
                json_mode=model_config['provider'] in ['openai', 'xai']
            )

            # Restore logging level
            performance_logger.logger.setLevel(original_log_level)

            # Update progress
            completed_count += 1
            progress_bar = "█" * (completed_count * 20 // total_count) + \
                "░" * (20 - completed_count * 20 // total_count)
            percentage = (completed_count / total_count) * 100
            print(
                f"\r🔧 Creating [{progress_bar}] {completed_count}/{total_count} ({percentage:.0f}%) - {model_config['name']}", end='', flush=True)

            return {
                "model_name": model_config['name'],
                "model_id": model_config['model_id'],
                "provider": model_config['provider'],
                "success": True
            }

        except Exception as e:
            # Restore logging level
            performance_logger.logger.setLevel(original_log_level)

            completed_count += 1
            progress_bar = "█" * (completed_count * 20 // total_count) + \
                "░" * (20 - completed_count * 20 // total_count)
            percentage = (completed_count / total_count) * 100
            print(
                f"\r❌ Creating [{progress_bar}] {completed_count}/{total_count} ({percentage:.0f}%) - Failed {model_config['name']}", end='', flush=True)

            return {
                "model_name": model_config['name'],
                "model_id": model_config['model_id'],
                "provider": model_config['provider'],
                "success": False,
                "error": str(e)
            }

    # Run model creation tests in parallel
    tasks = [create_model_test(model) for model in available_models]
    creation_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Clear progress line
    print(f"\r✅ Model creation completed for {total_count} models" + " " * 30)

    # Display results
    successful_creations = [
        r for r in creation_results if isinstance(r, dict) and r.get('success')]
    failed_creations = [r for r in creation_results if isinstance(
        r, dict) and not r.get('success')]

    print(f"\n📊 Model Creation Results:")
    print(f"  ✓ Successful: {len(successful_creations)}")
    print(f"  ✗ Failed: {len(failed_creations)}")

    if successful_creations:
        print(
            f"  🚀 Ready models: {', '.join([r['model_name'] for r in successful_creations[:3]])}{'...' if len(successful_creations) > 3 else ''}")

    if failed_creations:
        for result in failed_creations:
            print(
                f"    ✗ {result['model_name']} ({result['provider']}): {result.get('error', 'Unknown error')[:50]}...")

    print()

    return successful_creations


async def test_streaming_performance_parallel():
    """Test streaming performance in parallel for fast models."""
    print("=== Parallel Streaming Performance Test ===")

    tester = FastModelTester()
    results = await tester.run_parallel_model_tests()

    return results


def test_fast_model_detection():
    """Test detection of the latest fast models."""
    print("=== Fast Model Detection Test ===")

    # Test the latest models
    latest_models = [
        # Latest Gemini models
        "gemini-3-flash-preview-lite",
        "gemini-3-flash-preview",
        "gemini-2.0-flash-lite",
        "gemini-3-pro-preview",

        # Latest Grok models (correct identifiers from xAI docs)
        "grok-4-fast-reasoning",
        "grok-4-fast-non-reasoning",
        "grok-code-fast-1",

        # Fast OpenAI models
        "gpt-4o-mini",
        "gpt-3.5-turbo"
    ]

    print("Latest model detection results:")
    for model in latest_models:
        provider = get_model_provider(model)
        print(f"  {model:<25} -> {provider}")

    print()


async def run_comprehensive_fast_model_tests():
    """Run all fast model tests with parallel execution."""
    print(f"{Colors.BOLD}🚀 Fast Models Parallel Performance Test Suite{Colors.END}")
    print("=" * 70)
    print("Testing the fastest recent models from:")
    print("  • Gemini API: https://ai.google.dev/gemini-api/docs/models")
    print("  • xAI API: https://docs.x.ai/docs/models")
    print("=" * 70)

    # Test 1: Model Detection
    test_fast_model_detection()

    # Test 2: Parallel Model Creation
    creation_results = await test_model_creation_parallel()

    # Test 3: Parallel Streaming Performance (only if models were created successfully)
    if creation_results:
        streaming_results = await test_streaming_performance_parallel()
    else:
        print("⚠ Skipping streaming tests - no models available")
        streaming_results = []

    # Final summary
    print("=" * 70)
    print(f"{Colors.BOLD}{Colors.GREEN}🎉 Fast Models Parallel Testing Complete!{Colors.END}")
    print()
    print("Key Features Demonstrated:")
    print(
        f"  {Colors.GREEN}✓{Colors.END} Parallel model testing for maximum efficiency")
    print(
        f"  {Colors.GREEN}✓{Colors.END} Latest Gemini 2.5 Flash models (fastest recent)")
    print(f"  {Colors.GREEN}✓{Colors.END} Grok 4 integration (latest xAI model)")
    print(
        f"  {Colors.GREEN}✓{Colors.END} Google Cloud JSON authentication for Gemini")
    print(f"  {Colors.GREEN}✓{Colors.END} Performance comparison across providers")
    print(
        f"  {Colors.GREEN}✓{Colors.END} Minimal color logging (times and model names only)")

    return {
        "creation_results": creation_results,
        "streaming_results": streaming_results
    }


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_comprehensive_fast_model_tests())
