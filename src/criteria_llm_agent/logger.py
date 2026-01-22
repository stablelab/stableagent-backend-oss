"""
Logging configuration for Criteria LLM Agent.

Provides structured logging with progress tracking for criteria evaluation.
"""
import logging
import sys
from datetime import datetime
from typing import Optional, Dict, Any

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
    END = '\033[0m'


class CriteriaEvaluationLogger:
    """Logger for criteria evaluation with progress tracking."""
    
    def __init__(self, logger_name: str = "criteria_llm_agent"):
        """
        Initialize the criteria evaluation logger.
        
        Args:
            logger_name: Name for the logger instance
        """
        self.logger = logging.getLogger(logger_name)
        
        # Ensure the logger has a console handler if none exists
        if not self.logger.handlers:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            self.logger.setLevel(logging.INFO)
    
    def log_evaluation_start(self, org: str, form_id: int, user_id: int):
        """Log the start of an evaluation."""
        self.logger.info(
            f"{Colors.BLUE}{'='*60}{Colors.END}"
        )
        self.logger.info(
            f"{Colors.BOLD}🎯 STARTING CRITERIA EVALUATION{Colors.END}"
        )
        self.logger.info(
            f"   Organization: {Colors.CYAN}{org}{Colors.END}"
        )
        self.logger.info(
            f"   Form ID: {Colors.CYAN}{form_id}{Colors.END}"
        )
        self.logger.info(
            f"   User ID: {Colors.CYAN}{user_id}{Colors.END}"
        )
        self.logger.info(
            f"{Colors.BLUE}{'='*60}{Colors.END}"
        )
    
    def log_batch_evaluation_start(self, org: str, form_id: int, user_count: int):
        """Log the start of a batch evaluation."""
        self.logger.info(
            f"{Colors.MAGENTA}{'='*60}{Colors.END}"
        )
        self.logger.info(
            f"{Colors.BOLD}🎯 STARTING BATCH CRITERIA EVALUATION{Colors.END}"
        )
        self.logger.info(
            f"   Organization: {Colors.CYAN}{org}{Colors.END}"
        )
        self.logger.info(
            f"   Form ID: {Colors.CYAN}{form_id}{Colors.END}"
        )
        self.logger.info(
            f"   Users: {Colors.CYAN}{user_count}{Colors.END}"
        )
        self.logger.info(
            f"{Colors.MAGENTA}{'='*60}{Colors.END}"
        )
    
    def log_data_fetch_start(self):
        """Log the start of data fetching."""
        self.logger.info(f"{Colors.YELLOW}📊 Fetching evaluation context from database...{Colors.END}")
    
    def log_data_fetch_complete(self, criteria_count: int, answers_count: int):
        """Log completion of data fetching."""
        self.logger.info(
            f"{Colors.GREEN}✅ Data fetch complete:{Colors.END} "
            f"{criteria_count} criteria, {answers_count} answers"
        )
    
    def log_criteria_evaluation_start(self, criterion_id: int, criterion_name: str, index: int, total: int):
        """Log the start of individual criterion evaluation."""
        progress = f"[{index}/{total}]"
        self.logger.info(
            f"{Colors.CYAN}🔍 {progress} Evaluating:{Colors.END} "
            f"{Colors.BOLD}{criterion_name}{Colors.END} (ID: {criterion_id})"
        )
    
    def log_criterion_score(
        self, 
        criterion_name: str, 
        raw_score: int, 
        weight: float, 
        weighted_score: float,
        duration_ms: float
    ):
        """Log the score for a single criterion."""
        score_color = Colors.GREEN if raw_score == 100 else Colors.YELLOW if raw_score == 50 else Colors.RED
        
        self.logger.info(
            f"   {score_color}Score: {raw_score}/100{Colors.END} "
            f"× weight {weight} = {Colors.BOLD}{weighted_score:.2f}{Colors.END} "
            f"({duration_ms:.0f}ms)"
        )
    
    def log_criterion_error(self, criterion_name: str, error: str):
        """Log an error during criterion evaluation."""
        self.logger.error(
            f"   {Colors.RED}❌ Error evaluating {criterion_name}: {error}{Colors.END}"
        )
    
    def log_aggregation_start(self, criteria_count: int):
        """Log the start of score aggregation."""
        self.logger.info(
            f"{Colors.YELLOW}📈 Aggregating scores from {criteria_count} criteria...{Colors.END}"
        )
    
    def log_evaluation_complete(
        self,
        total_weighted: float,
        max_possible: float,
        normalized: float,
        duration_seconds: float
    ):
        """Log the completion of evaluation with final scores."""
        score_color = (
            Colors.GREEN if normalized >= 80 else
            Colors.CYAN if normalized >= 60 else
            Colors.YELLOW if normalized >= 40 else
            Colors.RED
        )
        
        self.logger.info(
            f"{Colors.GREEN}{'='*60}{Colors.END}"
        )
        self.logger.info(
            f"{Colors.BOLD}✅ EVALUATION COMPLETE{Colors.END}"
        )
        self.logger.info(
            f"   Total Weighted Score: {Colors.BOLD}{total_weighted:.2f}{Colors.END} / {max_possible:.2f}"
        )
        self.logger.info(
            f"   Normalized Score: {score_color}{Colors.BOLD}{normalized:.2f}%{Colors.END}"
        )
        self.logger.info(
            f"   Duration: {Colors.CYAN}{duration_seconds:.2f}s{Colors.END}"
        )
        self.logger.info(
            f"{Colors.GREEN}{'='*60}{Colors.END}"
        )
    
    def log_batch_complete(self, user_count: int, duration_seconds: float):
        """Log completion of batch evaluation."""
        self.logger.info(
            f"{Colors.GREEN}{'='*60}{Colors.END}"
        )
        self.logger.info(
            f"{Colors.BOLD}✅ BATCH EVALUATION COMPLETE{Colors.END}"
        )
        self.logger.info(
            f"   Users Evaluated: {Colors.BOLD}{user_count}{Colors.END}"
        )
        self.logger.info(
            f"   Total Duration: {Colors.CYAN}{duration_seconds:.2f}s{Colors.END}"
        )
        self.logger.info(
            f"   Avg per User: {Colors.CYAN}{duration_seconds/user_count:.2f}s{Colors.END}"
        )
        self.logger.info(
            f"{Colors.GREEN}{'='*60}{Colors.END}"
        )
    
    def log_model_info(self, model_name: str, provider: str, temperature: float):
        """Log model configuration being used."""
        self.logger.info(
            f"{Colors.BOLD}🤖 Using Model:{Colors.END} "
            f"{Colors.CYAN}{provider}/{model_name}{Colors.END} "
            f"(temp: {temperature})"
        )
    
    def log_llm_call_start(self, criterion_name: str):
        """Log the start of an LLM API call."""
        self.logger.debug(f"   📡 Calling LLM for: {criterion_name}")
    
    def log_llm_call_complete(self, criterion_name: str, duration_ms: float):
        """Log the completion of an LLM API call."""
        duration_color = Colors.GREEN if duration_ms < 1000 else Colors.YELLOW if duration_ms < 3000 else Colors.RED
        self.logger.debug(
            f"   ✅ LLM response received: {criterion_name} "
            f"({duration_color}{duration_ms:.0f}ms{Colors.END})"
        )


# Global logger instance
evaluation_logger = CriteriaEvaluationLogger()


# Convenience functions
def get_logger() -> CriteriaEvaluationLogger:
    """Get the global evaluation logger instance."""
    return evaluation_logger


def log_evaluation_start(org: str, form_id: int, user_id: int):
    """Log the start of an evaluation."""
    evaluation_logger.log_evaluation_start(org, form_id, user_id)


def log_evaluation_complete(
    total_weighted: float,
    max_possible: float,
    normalized: float,
    duration_seconds: float
):
    """Log the completion of evaluation."""
    evaluation_logger.log_evaluation_complete(
        total_weighted, max_possible, normalized, duration_seconds
    )
