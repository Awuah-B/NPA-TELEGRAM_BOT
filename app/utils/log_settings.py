#! /usr/bin/env python3
## File: logging.py
"""
Logging configuration and utilities
Centralized logging setup with proper formatting and rotation.
"""
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

# Import config after logging to avoid circular imports
# or use late import inside functions


def setup_logging(
    log_file: str,
    log_level: str = 'INFO',  # Default fallback
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Setup logging with file rotation and console output
    
    Args:
        log_file: Log file name
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        max_bytes: Maximum size per log file
        backup_count: Number of backup files to keep
        
    Returns:
        Configured logger instance
    """
    # Late import to avoid circular dependency
    try:
        from config import CONFIG
        log_level = getattr(CONFIG, 'log_level', log_level)
        environment = CONFIG.environment.value 
    except ImportError:
        environment = "development"  # Default fallback
    
    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Get logger
    logger_name = 'telegram_bot'  # Unified logger name
    
    logger = logging.getLogger(logger_name)

    # Clear existing handlers to avoid duplicates
    if logger.handlers:
        logger.handlers.clear()

    # Set log level from config
    log_level_value = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(log_level_value)

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S' 
    )

    
    log_path = log_dir / log_file
    try:
        file_handler = logging.handlers.RotatingFileHandler(
           filename=log_path,
           maxBytes=max_bytes,
           backupCount=backup_count,
           encoding='utf-8' 
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level_value)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Failed to setup file logging to {log_path}: {e}", file=sys.stderr)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Set console level based on environment
    if environment == "development":
        console_handler.setLevel(logging.DEBUG)
    else:
        console_handler.setLevel(logging.INFO)
    
    logger.addHandler(console_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(f"npa_bot.{name}")

def set_log_level(logger: logging.Logger, level: str) -> None:
    """
    Set log level for a logger and its handlers
    
    Args:
        logger: Logger instance
        level: Log level string
    """
    log_level_value = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level_value)
    
    for handler in logger.handlers:
        handler.setLevel(log_level_value)

def configure_third_party_loggers() -> None:
    """Configure logging for third-party libraries"""
    # Reduce noise from third-party libraries
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('pandas').setLevel(logging.WARNING)
    logging.getLogger('fpdf').setLevel(logging.WARNING)
    
    
    # Set urllib3 to WARNING to reduce connection pool messages
    logging.getLogger('urllib3').setLevel(logging.WARNING)

# Configure third-party loggers on import
configure_third_party_loggers()