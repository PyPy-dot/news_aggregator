"""
Services package for News Aggregator.

Экспортирует утилиты и конфигурацию логирования.
"""

from services.logging_config import (
    setup_logging,
    get_logger,
    get_error_logger,
    LoggingContext,
)

from services.util import (
    load_prompt,
    truncate_text,
    format_number,
    log_error,
    log_execution_time,
    ExecutionTimer,
)

__all__ = [
    # Logging
    'setup_logging',
    'get_logger',
    'get_error_logger',
    'LoggingContext',
    # Utils
    'load_prompt',
    'truncate_text',
    'format_number',
    'log_error',
    'log_execution_time',
    'ExecutionTimer',
]
