#! /usr/bin/env python3
## File: /utils/decorators.py

"""
Utility decorators for bot functionality
Rate limiting, authentication, and other cross-cutting concerns.
"""

import asyncio
import functools
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Callable, Any

from telegram import Update, ChatMember
from telegram.ext import ContextTypes
from telegram.constants import ChatType
from telegram.error import TelegramError

from app.config import CONFIG
from app.utils.log_settings import setup_logging

logger = setup_logging('decorators.log')

class RateLimitError(Exception):
    pass
class AuthenticationError(Exception):
    pass
class RateLimiter:
    """
    Rate limiter implementation with per-user tracking
    """
    def __init__(self):
        self._user_calls: Dict[Tuple[int, int], datetime] = {}
        self._max_size = 1000
        self._cleanup_interval = 300 # 5mins
        self._last_cleanup = datetime.now()
    
    def is_rate_limited(self, chat_id: int, user_id: int, per_seconds: int) -> Tuple[bool, float]:
        """check if user is rate limited"""
        key = (chat_id, user_id)
        now = datetime.now()

        if (now - self._last_cleanup).total_seconds() > self._cleanup_interval:
            self._cleanup_old_entries(now)
        
        if len(self._user_calls) >= self._max_size:
            logger.warning("Rate limiter reached max size, triggering cleanup")
            self._cleanup_old_entries(now)

        if key in self._user_calls:
            elapsed = (now - self._user_calls[key]).total_seconds()
            if elapsed < per_seconds:
                wait_time = per_seconds - elapsed
                return True, wait_time
        
        self._user_calls[key] = now
        return False, 0.0
    
    def _cleanup_old_entries(self, now: datetime) -> None:
        cutoff = now - timedelta(hours=1)
        keys_to_remove = [
            key for key, timestamp in self._user_calls.items()
            if timestamp < cutoff
        ]

        for key in keys_to_remove:
            del self._user_calls[key]
        
        while len(self._user_calls) > self._max_size * 0.8:
            oldest_key = min(self._user_calls, key=lambda k: self._user_calls[k])
            del self._user_calls[oldest_key]
            keys_to_remove.append(oldest_key)
        
        self._last_cleanup = now
        logger.debug(f"Cleaned up {len(keys_to_remove)} rate limit entries")

# Global rate limiter instance
_rate_limiter = RateLimiter()

def rate_limit(per_seconds: int = 5):
    """Decorator to rate limit commands execution per user"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id

            is_limited, wait_time = _rate_limiter.is_rate_limited(chat_id, user_id, per_seconds)

            if is_limited:
                await update.message.reply_text(
                    f"⏳ Please wait {wait_time:.1f} seconds before using this command again."
                )
                logger.info(f"Rate limited user {user_id} in chat {chat_id} for {wait_time:.1f}s")
                return 
            return await func(self, update, context, *args, **kwargs)
        
        return wrapper
    return decorator

def admin_required(func: Callable) -> Callable:
    """Decorator to require admin permissions in groups"""
    @functools.wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat
        user = update.effective_user

        if chat.type == ChatType.PRIVATE:
            return await func(self, update, context, *args, **kwargs)
        if self.bot._is_superadmin(user.id):
            return await func(self, update, context, *args, **kwargs)
        
        # check if user is group admin
        try:
            is_admin = await self.bot._is_user_admin(chat.id, user.id)
            if not is_admin:
                await update.message.reply_text("❌ Only group administrators can use this command.")
                return
        except TelegramError as e:
            logger.error(f"Telegram error checking admin status for user {user.id} in chat {chat.id}: {e}")
            await update.message.reply_text("❌ Failed to verify admin permissions due to Telegram error.")
            return
        
        return await func(self, update, context, *args, **kwargs)
    
    return wrapper

def superadmin_required(func: Callable) -> Callable:
    """Decorator to require superadmin permissions"""
    @functools.wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user

        if not self.bot._is_superadmin(user.id):
            await update.message.reply_text("❌ This command is only available to superadmins.")
            return
        
        return await func(self, update, context, *args, **kwargs)
    
    return wrapper

def subscribed_group_required(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat

        if chat.type == ChatType.PRIVATE:
            if self.bot._is_superadmin(update.effective_user.id):
                return await func(self, update, context, *args, **kwargs)
            else:
                await update.message.reply_text("❌ This command is only available in subscribed groups.")
                return 
        
        # Check if group is subscribed
        if not self.bot.group_manager.is_subscribed(str(chat.id)):
            await update.message.reply_text(
               "❌ This group is not subscribed. Use /subscribe to enable notifications." 
            )
            return
        
        return await func(self, update, context, *args, **kwargs)
    
    return wrapper

def error_handler(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except RateLimitError as e:
            logger.warning(f"Rate limit error in {func.__name__}: {e}")
            raise
        except AuthenticationError as e:
            logger.warning(f"Authentication error in {func.__name__}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise
    
    return wrapper

def log_command_usage(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        command_name = func.__name__.replace('_command', '')
        user = update.effective_user
        chat = update.effective_user

        return await func(self, update, context, *args, **kwargs)
        
    return wrapper

def async_retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator for retrying async functions with exponential backoff"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                            f"Retrying in {current_delay:.1f}s"
                        )
                        
                        
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"All {max_attempts} attempts failed for {func.__name__}: {e}")
            
            raise last_exception
        
        return wrapper
    return decorator

def validate_input(validation_func: Callable[[Any], bool], error_message: str):
    """Decorator to validate input parameters"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if hasattr(context, 'args') and context.args:
                user_input = ''.join(context.args)

                if not validation_func(user_input):
                    await update.message.reply_text(f"❌ {error_message}")
                    return
            return await func(self, update, context, *args, **kwargs)
        
        return wrapper
    return decorator

def validate_date_format(date_str: str) -> bool:
    """Validate date format (DD-MM-YYYY)"""
    try:
        datetime.strptime(date_str, '%d-%m-%Y')
        return True
    except ValueError:
        return False














        
