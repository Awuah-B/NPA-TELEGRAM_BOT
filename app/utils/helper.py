#! /usr/bin/env python3
## File: helper.py

"""
Helper functions and utilities
Common utility functions used throughout the application.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
import re

from app.utils.log_settings import setup_logging

logger = setup_logging('helpers.log')

def split_message(message: str, max_length: int = 4000) -> List[str]:
    """
    Split a long message into multiple parts while preserving markdown formatting
    
    Args:
        message: The message to split
        max_length: Maximum length per message part
        
    Returns:
        List of message parts
    """
    if len(message) <= max_length:
        return [message]
    
    messages = []
    current_message = ""
    lines = message.split("\n")

    for line in lines:
        # Check if adding this line would exceed the limit
        if len(current_message) + len(line) + 1 > max_length:
            if current_message.strip():
                # Fixed: message.append -> messages.append
                messages.append(current_message.strip())
            current_message = line + "\n"
        else:
            current_message += line + "\n"

    # Add the remaining message
    if current_message.strip():
        # Fixed: message.append -> messages.append
        messages.append(current_message.strip())
    
    return messages

def format_record_message(record: pd.Series, index: int, record_type: str = "Record") -> str:
    """
    Format a pandas Series record into a readable message
    
    Args:
        record: Pandas Series containing record data
        index: Record index for display
        record_type: Type of record (e.g., "New Record", "Search Result")
        
    Returns:
        Formatted message string
    """
    
    

def safe_get(record: pd.Series, key_upper: str, key_lower: str = None, default: str = 'N/A') -> str:
    """
    Safely get a value from a pandas Series with proper null handling
    Tries both uppercase and lowercase versions of keys
    
    Args:
        record: Pandas Series
        key_upper: Primary key to retrieve (usually uppercase)
        key_lower: Alternative lowercase key
        default: Default value if key is missing or null
        
    Returns:
        String value or default
    """
    try:
        # Try primary key first
        value = record.get(key_upper, None)
        
        # If not found and lowercase key provided, try that
        if (value is None or pd.isna(value)) and key_lower:
            value = record.get(key_lower, None)
            
        # If still not found, return default
        if value is None or pd.isna(value) or value == '' or value == 'nan':
            return default
            
        return str(value)
    except Exception:
        return default
    
def validate_brv_format(brv_number: str) -> bool:
    """
    Validate BRV number format
    
    Args:
        brv_number: BRV number to validate
        
    Returns:
        True if valid format, False otherwise
    """
    brv = brv_number.upper().strip()
    
    # Basic length validation - reasonable length
    if len(brv) < 2 or len(brv) > 15:
        return False
    
    # Check that first two characters are alphabets
    # This allows for more flexible formats while ensuring proper prefix
    pattern = re.match(r'^[A-Z]{2}', brv)

    return bool(pattern)

def extract_command_args(text: str) -> tuple[str, List[str]]:
    """
    Extract command and arguments from message text
    
    Args:
        text: Message text
        
    Returns:
        Tuple of (command, args_list)
    """
    if not text or not text.startswith('/'):
        return '', []
    
    parts = text.split()
    command = parts[0][1:]  # Remove the '/' prefix
    args = parts[1:] if len(parts) > 1 else []
    
    return command, args

def truncate_message(message: str, max_length: int = 4000) -> str:
    """
    Truncate message to maximum length with proper ending
    
    Args:
        message: Message to truncate
        max_length: Maximum allowed length
        
    Returns:
        Truncated message
    """
    if len(message) <= max_length:
        return message
    
    # Find a good place to cut (preferably at a line break)
    truncate_point = max_length - 50  # Leave room for truncation message
    
    # Look for a line break near the truncation point
    lines = message[:truncate_point].split('\n')
    if len(lines) > 1:
        truncated = '\n'.join(lines[:-1])
    else:
        truncated = message[:truncate_point]
    
    truncated += f"\n\n... (message truncated - {len(message) - len(truncated)} characters omitted)"
    
    return truncated



def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove extra underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    
    return sanitized

def generate_cache_key(*args) -> str:
    """
    Generate a consistent cache key from arguments
    
    Args:
        *args: Arguments to include in cache key
        
    Returns:
        Cache key string
    """
    # Convert all args to strings and join
    key_parts = [str(arg) for arg in args if arg is not None]
    return ':'.join(key_parts)

def clean_text(text: str, max_length: int = 50) -> str:
    """
    Clean and truncate text for display
    
    Args:
        text: Text to clean
        max_length: Maximum length
        
    Returns:
        Cleaned text
    """
    if not text or pd.isna(text):
        return 'N/A'
    
    # Convert to string and strip whitespace
    clean = str(text).strip()
    
    # Remove extra whitespace
    clean = re.sub(r'\s+', ' ', clean)
    
    # Truncate if too long
    if len(clean) > max_length:
        clean = clean[:max_length-3] + "..."
    
    return clean

    
def format_uptime(start_time: int) -> str:
    """
    Format uptime duration
    
    Args:
        start_time: When the bot started (as timestamp)
        
    Returns:
        Formatted uptime string
    """
    # Fixed: handle both datetime and timestamp
    if isinstance(start_time, int):
        start_time = datetime.fromtimestamp(start_time)
    
    uptime = datetime.now() - start_time
    
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m {seconds}s"
    
def mask_sensitive_data(data: str, mask_char: str = '*', visible_chars: int = 4) -> str:
    """
    Mask sensitive data for logging
    
    Args:
        data: Sensitive data to mask
        mask_char: Character to use for masking
        visible_chars: Number of characters to keep visible
        
    Returns:
        Masked string
    """
    if not data or len(data) <= visible_chars:
        return mask_char * len(data) if data else ''
    
    return data[:visible_chars] + mask_char * (len(data) - visible_chars)


def get_file_size_mb(file_size_bytes: int) -> str:
    """
    Convert file size to human readable format
    
    Args:
        file_size_bytes: File size in bytes
        
    Returns:
        Formatted file size string
    """
    mb = file_size_bytes / (1024 * 1024)
    
    if mb < 1:
        kb = file_size_bytes / 1024
        return f"{kb:.1f} KB"
    else:
        return f"{mb:.1f} MB"
    
    return bool(re.match(pattern, brv))

def is_valid_chat_id(chat_id: str) -> bool:
    """
    Validate Telegram chat ID format
    
    Args:
        chat_id: Chat ID to validate
        
    Returns:
        True if valid format
    """
    try:
        # Chat IDs are integers (can be negative for groups)
        int(chat_id)
        return True
    except ValueError:
        return False
    
def format_notification_summary(table_name: str, record_data=None, record_count: int = 1) -> str:
    """Format new records into a detailed, table-specific message"""
    table_display = table_name.replace('_', ' ').title()
    
    # If record_data is a DataFrame
    if hasattr(record_data, 'empty'):
        if record_data.empty:
            return f"📭 No new records to notify for {table_display}."
        count = len(record_data)
        records = record_data
    # If record_data is a dict (single record)
    elif isinstance(record_data, dict):
        count = 1
        import pandas as pd
        records = pd.DataFrame([record_data])
    # If record_data is a list
    elif isinstance(record_data, list):
        count = len(record_data)
        import pandas as pd
        records = pd.DataFrame(record_data)
    # If just count provided
    else:
        count = record_count
        records = None
    
    message = (
        f"🚨 **New {table_display} Records Detected!**\n\n"
        f"📊 **Total New Records:** {count}\n"
        f"🕒 **Detection Time:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
    )
    
    # Add detailed record information if available
    if records is not None and not records.empty:
        for idx, (_, row) in enumerate(records.head(5).iterrows(), 1):
            order_date = row.get('order_date', 'N/A')
            if order_date != 'N/A':
                try:
                    import pandas as pd
                    order_date = pd.to_datetime(order_date).strftime('%d-%m-%Y %H:%M')
                except (ValueError, TypeError, AttributeError) as e:
                    # Log the error but continue with original value
                    order_date = str(order_date) if order_date else 'N/A'
            message += (
                f"**Record {idx} ({table_display})**\n"
                f"📅 **Order Date:** {order_date}\n"
                f"🔢 **Order Number:** {row.get('order_number', 'N/A')}\n"
                f"🛢️ **Product:** {row.get('products', 'N/A')}\n"
                f"📊 **Volume:** {row.get('volume', 'N/A')}\n"
                f"💰 **Ex Ref Price:** {row.get('ex_ref_price', 'N/A')}\n"
                f"📋 **BRV Number:** {row.get('brv_number', 'N/A')}\n"
                f"🏢 **BDC:** {row.get('bdc', 'N/A')}\n"
                f"🕖 **Created At:** {pd.to_datetime(row.get('created_at', 'N/A')).strftime('%d-%m-%Y %H:%M:%S') if row.get('created_at') != 'N/A' else 'N/A'}\n"
                "─────────────────\n"
            )
        if count > 5:
            message += f"... and {count - 5} more records.\n\n"
        message += f"Use `/recent` to see recent {table_display} records.\nUse `/download_pdf` to get a detailed report."
    else:
        message += f"📝 **Details:** New record added to {table_display}\n"
        message += f"Use `/recent {table_name}` to see recent records.\nUse `/download_pdf` to get a detailed report."
    
    return message


