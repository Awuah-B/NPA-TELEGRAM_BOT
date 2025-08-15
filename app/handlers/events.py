#! /usr/bin/env python3 
## File: handlers/events.py

"""
Event handlers for Telegram bot
Handles chat member updates and other Telegram events.
"""
from telegram import Update, ChatMember
from telegram.ext import ContextTypes
from telegram.constants import ChatMemberStatus

from app.utils.log_settings import setup_logging

logger = setup_logging('events.log')
 
class EventHandlers:
    """
    Handles Telegram events such as chat member updates
    """

    def __init__(self, bot):
        self.bot = bot

    async def track_chat_members(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            chat_member = update.my_chat_member
            chat = chat_member.chat
            new_status = chat_member.new_chat_member.status
            old_status = chat_member.old_chat_member.status

            logger.debug(f"Chat member update in {chat.id}: {old_status} -> {new_status}")

            if new_status == ChatMemberStatus.MEMBER:
                self.bot.group_manager.add_group(str(chat.id), chat.title or "Unnamed Group")
                logger.info(f"Bot added to group {chat.id} ({chat.title or 'Unnamed Group'})")
                await self.bot._notify_superadmins(f"🤖 Bot added to group: {chat.title or 'Unnamed Group'} (ID: {chat.id})")
            
            # Handle both old (KICKED) and new (BANNED) status values for compatibility
            elif new_status in [ChatMemberStatus.LEFT, getattr(ChatMemberStatus, 'BANNED', None), getattr(ChatMemberStatus, 'KICKED', None)]:
                # Filter out None values in case the attribute doesn't exist
                if new_status is not None:
                    self.bot.group_manager.remove_group(str(chat.id))
                    logger.info(f"Bot removed from group {chat.id}")
                    await self.bot._notify_superadmins(f"🤖 Bot removed from group: {chat.title or 'Unnamed Group'} (ID: {chat.id})")
        
        except AttributeError as e:
            logger.error(f"AttributeError in chat member update (likely ChatMemberStatus compatibility issue): {e}")
            # Still try to notify but don't crash
            await self.bot._notify_superadmins(f"⚠️ Chat member update error (status compatibility): {str(e)}")
        except Exception as e:
            logger.error(f"Error handling chat member update: {e}")
            await self.bot._notify_superadmins(f"🚨 Error handling chat member update: {str(e)}")
