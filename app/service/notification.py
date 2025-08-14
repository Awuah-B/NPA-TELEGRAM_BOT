#! /usr/bin/env python3
## File: notification.py

"""
Notification service for sending messages to subscribed groups
Handles formatting and sending of new record notifications.
"""
import asyncio
from typing import Dict
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from app.config import CONFIG
from app.handlers.bot_manager import GroupChatManager
from app.utils.log_settings import setup_logging
from app.utils.helper import format_notification_summary, split_message

logger = setup_logging('notification.log')

class NotificationService:
    """Service for sending notifications to subscribed groups"""

    def __init__(self, bot: Bot, group_manager: GroupChatManager):
        self.bot = bot
        self.group_manager = group_manager
    
    async def notify_new_records(self, table_name: str, record: Dict) -> None:
        """Notify subscribed groups about a new record"""
        try:
            # Format notification message with the actual record data
            message = format_notification_summary(table_name, record_data=record)
            messages = split_message(message, max_length=4000)

            # Get subscribed groups
            subscribed_groups = self.group_manager.get_subscribed_groups()

            # Send notification to each group
            for group_id in subscribed_groups:
                try:
                    for msg in messages:
                        await self.bot.send_message(
                            chat_id=int(group_id),
                            text=msg,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    logger.info(f"Sent notification to group {group_id} for new records in {table_name}")
                    await asyncio.sleep(2)  # Rate limiting between groups

                except TelegramError as e:
                    logger.warning(f"Failed to send notification to group {group_id}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error sending notification to group {group_id}: {e}")

            # Notify superadmin if no groups are subscribed
            if not subscribed_groups:
                logger.info(f"No subscribed groups found, notifying superadmins for {table_name}")
                await self._notify_superadmins_with_messages(messages, table_name)

        except Exception as e:
            logger.error(f"Error processing notification for {table_name}: {e}")
            # Try to notify superadmins about the error
            try:
                await self._notify_superadmins(f"🚨 Notification error for {table_name}: {str(e)}")
            except Exception as notify_error:
                logger.error(f"Failed to notify superadmins about notification error: {notify_error}")

    async def _notify_superadmins_with_messages(self, messages: list, table_name: str) -> None:
        """Send multiple messages to superadmins"""
        for admin_id in CONFIG.telegram.superadmin_ids:
            try:
                for msg in messages:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=msg,
                        parse_mode=ParseMode.MARKDOWN
                    )
                logger.info(f"Sent notification to superadmin {admin_id} for new record in {table_name}")
                await asyncio.sleep(1)  # Rate limiting between admins
            except TelegramError as e:
                logger.warning(f"Failed to notify superadmin {admin_id}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error notifying superadmin {admin_id}: {e}")
    
    async def _notify_superadmins(self, message: str) -> None:
        """Notify superadmins with error message and retry logic"""
        try:
            for admin_id in CONFIG.telegram.superadmin_ids:
                max_retries = 3
                retry_delay = 2
                
                for attempt in range(max_retries):
                    try:
                        await self.bot.send_message(
                            chat_id=admin_id,
                            text=message,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        logger.info(f"Successfully notified superadmin {admin_id}")
                        break  # Success, exit retry loop
                        
                    except TelegramError as e:
                        if attempt < max_retries - 1:
                            logger.warning(f"Attempt {attempt + 1} failed for superadmin {admin_id}: {e}, retrying in {retry_delay}s")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            logger.error(f"All attempts failed for superadmin {admin_id}: {e}")
                    except Exception as e:
                        logger.error(f"Unexpected error notifying superadmin {admin_id}: {e}")
                        break  # Don't retry on unexpected errors
                        
                await asyncio.sleep(0.5)  # Small delay between admins
                
        except Exception as e:
            logger.error(f"Failed to notify superadmins: {e}")