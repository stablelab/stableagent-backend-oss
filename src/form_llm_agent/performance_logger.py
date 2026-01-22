"""
Performance logging utilities for Form LLM Agent.

Provides comprehensive response time logging with colored console output
and detailed performance metrics tracking.
"""

import time
import logging
from typing import Optional, Dict, Any, ContextManager
from contextlib import contextmanager
from dataclasses import dataclass, asdict
import json

# ANSI color codes for console output


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'  # Reset color


@dataclass
class PerformanceMetrics:
    """Data class for storing performance metrics."""
    operation: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    field_id: Optional[str] = None
    model_name: Optional[str] = None
    provider: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    response_length: Optional[int] = None

    def finish(self, success: bool = True, error_message: Optional[str] = None, response_length: Optional[int] = None):
        """Mark the operation as finished and calculate duration."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.success = success
        self.error_message = error_message
        self.response_length = response_length

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class FormLLMPerformanceLogger:
    """Performance logger for Form LLM Agent operations."""

    def __init__(self, logger_name: str = "form_llm_agent.performance"):
        """Initialize the performance logger."""
        self.logger = logging.getLogger(logger_name)

        # Ensure the logger has at least a console handler if none exists
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            # Simple format for colored output
            formatter = logging.Formatter('%(message)s')
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            self.logger.setLevel(logging.INFO)

        self._active_operations: Dict[str, PerformanceMetrics] = {}

    def _format_duration(self, duration_ms: float) -> str:
        """Format duration with appropriate color coding."""
        if duration_ms < 100:  # < 100ms - excellent
            color = Colors.GREEN
            status = "EXCELLENT"
        elif duration_ms < 500:  # < 500ms - good
            color = Colors.CYAN
            status = "GOOD"
        elif duration_ms < 1000:  # < 1s - okay
            color = Colors.YELLOW
            status = "OKAY"
        elif duration_ms < 3000:  # < 3s - slow
            color = Colors.MAGENTA
            status = "SLOW"
        else:  # > 3s - very slow
            color = Colors.RED
            status = "VERY SLOW"

        return f"{color}{duration_ms:.1f}ms ({status}){Colors.END}"

    def _format_success_status(self, success: bool) -> str:
        """Format success status with colors."""
        if success:
            return f"{Colors.GREEN}✓ SUCCESS{Colors.END}"
        else:
            return f"{Colors.RED}✗ FAILED{Colors.END}"

    def start_operation(
        self,
        operation: str,
        field_id: Optional[str] = None,
        model_name: Optional[str] = None,
        provider: Optional[str] = None
    ) -> str:
        """Start tracking an operation."""
        operation_id = f"{operation}_{int(time.time() * 1000000)}"  # Microsecond precision

        metrics = PerformanceMetrics(
            operation=operation,
            start_time=time.time(),
            field_id=field_id,
            model_name=model_name,
            provider=provider
        )

        self._active_operations[operation_id] = metrics

        # Log operation start with minimal color
        context_info = []
        if field_id:
            context_info.append(f"field_id={field_id}")
        if model_name:
            context_info.append(f"model={model_name}")
        if provider:
            context_info.append(f"provider={provider}")

        context_str = f" ({', '.join(context_info)})" if context_info else ""

        self.logger.info(f"🚀 Starting {operation}{context_str}")

        return operation_id

    def finish_operation(
        self,
        operation_id: str,
        success: bool = True,
        error_message: Optional[str] = None,
        response_length: Optional[int] = None
    ) -> Optional[PerformanceMetrics]:
        """Finish tracking an operation and log results."""
        if operation_id not in self._active_operations:
            self.logger.warning(
                f"Operation ID {operation_id} not found in active operations")
            return None

        metrics = self._active_operations.pop(operation_id)
        metrics.finish(success=success, error_message=error_message,
                       response_length=response_length)

        # Format the log message
        duration_str = self._format_duration(metrics.duration_ms)
        status_str = self._format_success_status(metrics.success)

        # Build context information
        context_parts = []
        if metrics.field_id:
            context_parts.append(f"field_id={metrics.field_id}")
        if metrics.model_name:
            context_parts.append(f"model={metrics.model_name}")
        if metrics.provider:
            context_parts.append(f"provider={metrics.provider}")
        if metrics.response_length:
            context_parts.append(f"response_length={metrics.response_length}")

        context_str = f" ({', '.join(context_parts)})" if context_parts else ""

        # Log the completion with minimal color usage (only times and model names)
        if success:
            # Only highlight the duration and keep everything else normal
            final_msg = (
                f"🎉 COMPLETED {metrics.operation} in {duration_str}"
                f"{context_str} {status_str}"
            )
        else:
            # Only highlight the duration for failed operations
            error_info = f" - {error_message}" if error_message else ""
            final_msg = (
                f"💥 FAILED {metrics.operation} after {duration_str}"
                f"{context_str} {status_str}{error_info}"
            )

        # Log to both console and file
        self.logger.info(final_msg)

        # Also log structured data for analysis
        self.logger.debug(
            f"Performance metrics: {json.dumps(metrics.to_dict(), indent=2)}")

        return metrics

    @contextmanager
    def track_operation(
        self,
        operation: str,
        field_id: Optional[str] = None,
        model_name: Optional[str] = None,
        provider: Optional[str] = None
    ) -> ContextManager[str]:
        """Context manager for tracking operations."""
        operation_id = self.start_operation(
            operation=operation,
            field_id=field_id,
            model_name=model_name,
            provider=provider
        )

        try:
            yield operation_id
        except Exception as e:
            self.finish_operation(
                operation_id=operation_id,
                success=False,
                error_message=str(e)
            )
            raise
        else:
            self.finish_operation(operation_id=operation_id, success=True)

    def log_model_selection(self, model_name: str, provider: str, temperature: float, json_mode: bool):
        """Log model selection with minimal color (only model name highlighted)."""
        self.logger.info(
            f"🤖 Model Selected: {Colors.BOLD}{provider}/{model_name}{Colors.END} "
            f"(temp: {temperature}, json_mode: {json_mode})"
        )

    def log_api_call_start(self, provider: str, model_name: str, prompt_length: int):
        """Log the start of an API call with minimal color."""
        self.logger.info(
            f"📡 API Call Start: {Colors.BOLD}{provider}/{model_name}{Colors.END} "
            f"(prompt: {prompt_length} chars)"
        )

    def log_api_call_complete(self, provider: str, model_name: str, response_length: int, duration_ms: float):
        """Log the completion of an API call with minimal color."""
        duration_str = self._format_duration(duration_ms)
        self.logger.info(
            f"📡 API Call Complete: {Colors.BOLD}{provider}/{model_name}{Colors.END} "
            f"(response: {response_length} chars) in {duration_str}"
        )

    def get_active_operations(self) -> Dict[str, PerformanceMetrics]:
        """Get currently active operations."""
        return self._active_operations.copy()

    def log_streaming_start(self, field_id: str):
        """Log the start of streaming response with minimal color."""
        self.logger.info(f"📺 Streaming Start: field_id={field_id}")

    def log_streaming_chunk(self, field_id: str, chunk_size: int, total_chunks: int):
        """Log streaming chunk information with minimal color."""
        self.logger.debug(
            f"📺 Streaming Chunk: field_id={field_id} "
            f"chunk={total_chunks} size={chunk_size} bytes"
        )

    def log_streaming_complete(self, field_id: str, total_chunks: int, total_duration_ms: float):
        """Log the completion of streaming with highlighted final time only."""
        duration_str = self._format_duration(total_duration_ms)
        self.logger.info(
            f"📺 STREAMING COMPLETE: field_id={field_id} "
            f"chunks={total_chunks} total_time={duration_str}"
        )


# Global performance logger instance
performance_logger = FormLLMPerformanceLogger()


# Convenience functions
def start_operation(operation: str, **kwargs) -> str:
    """Start tracking an operation."""
    return performance_logger.start_operation(operation, **kwargs)


def finish_operation(operation_id: str, **kwargs) -> Optional[PerformanceMetrics]:
    """Finish tracking an operation."""
    return performance_logger.finish_operation(operation_id, **kwargs)


def track_operation(operation: str, **kwargs):
    """Context manager for tracking operations."""
    return performance_logger.track_operation(operation, **kwargs)
