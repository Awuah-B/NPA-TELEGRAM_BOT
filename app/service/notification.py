#! /usr/bin/env python3
## File: notification.py

"""
Notification service for sending messages to subscribed groups
Handles formatting and sending of new record notifications.
"""
import asyncio
from datetime import datetime
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
            # Validate input parameters
            if not table_name or not isinstance(table_name, str):
                logger.error(f"Invalid table_name for notification: {table_name}")
                return
            
            if not record or not isinstance(record, dict):
                logger.error(f"Invalid record data for notification in {table_name}: {record}")
                return
            
            # Validate record has some basic identifiable information
            record_id = record.get('id', 'N/A')
            if record_id == 'N/A':
                logger.warning(f"Record missing ID field for {table_name}")
            
            # Format notification message with the actual record data
            try:
                message = format_notification_summary(table_name, record_data=record)
                if not message or not message.strip():
                    logger.error(f"Empty message generated for {table_name} record {record_id}")
                    return
                    
                messages = split_message(message, max_length=4000)
                if not messages:
                    logger.error(f"No messages generated after splitting for {table_name} record {record_id}")
                    return
                    
            except Exception as format_error:
                logger.error(f"Error formatting notification for {table_name} record {record_id}: {format_error}")
                # Create a fallback simple message
                messages = [f"🚨 New record detected in {table_name.replace('_', ' ').title()}\n"
                           f"Record ID: {record_id}\n"
                           f"Time: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n"
                           f"Use /recent command for details."]

            # Get subscribed groups
            subscribed_groups = self.group_manager.get_subscribed_groups()

            # Send notification to each group
            successful_notifications = 0
            for group_id in subscribed_groups:
                try:
                    for msg in messages:
                        await self.bot.send_message(
                            chat_id=int(group_id),
                            text=msg,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    logger.info(f"Sent notification to group {group_id} for new record {record_id} in {table_name}")
                    successful_notifications += 1
                    await asyncio.sleep(2)  # Rate limiting between groups

                except TelegramError as e:
                    logger.warning(f"Failed to send notification to group {group_id}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error sending notification to group {group_id}: {e}")

            # Notify superadmin if no groups are subscribed or all notifications failed
            if not subscribed_groups:
                logger.info(f"No subscribed groups found, notifying superadmins for {table_name} record {record_id}")
                await self._notify_superadmins_with_messages(messages, table_name)
            elif successful_notifications == 0:
                logger.warning(f"All group notifications failed for {table_name} record {record_id}, notifying superadmins")
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