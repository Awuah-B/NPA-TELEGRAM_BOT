#! /usr/bin/env python3
## File: /handlers/commands.py

"""
Telegram bot command handlers
Handles all bot commands with proper validation and error handling.
"""

import asyncio
from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

import pandas as pd
from telegram import Update, ChatMember
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ParseMode

from app.config import CONFIG
from app.service.data_fetcher import DataFetcher
from app.service.pdf_generator import PDFGenerator
from app.service.gemini_processor import GeminiProcessor
from app.database.connection import SupabaseHandler
from app.utils.decorators import rate_limit, admin_required, subscribed_group_required
from app.utils.helper import split_message, validate_brv_format
from app.utils.log_settings import setup_logging

logger = setup_logging('bot_commands.log')

class PDFCache:
    """Cache for PDF generation with TTL support"""
    
    def __init__(self, ttl_minutes: int = 30):
        self._cache: Dict[str, Tuple[bytes, str, datetime]] = {}  # key -> (pdf_data, filename, timestamp)
        self._ttl = timedelta(minutes=ttl_minutes)
        self._max_size = 10  # Maximum number of cached PDFs
    
    def _cleanup_expired(self) -> None:
        """Remove expired entries from cache"""
        now = datetime.now()
        expired_keys = [
            key for key, (_, _, timestamp) in self._cache.items()
            if now - timestamp > self._ttl
        ]
        
        for key in expired_keys:
            del self._cache[key]
            logger.debug(f"Removed expired PDF cache entry: {key}")
    
    def _enforce_size_limit(self) -> None:
        """Enforce maximum cache size by removing oldest entries"""
        while len(self._cache) > self._max_size:
            # Remove the oldest entry
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][2])
            del self._cache[oldest_key]
            logger.debug(f"Removed oldest PDF cache entry: {oldest_key}")
    
    def get(self, cache_key: str) -> Optional[Tuple[bytes, str]]:
        """Get cached PDF data if still valid"""
        self._cleanup_expired()
        
        if cache_key in self._cache:
            pdf_data, filename, timestamp = self._cache[cache_key]
            logger.debug(f"PDF cache hit for key: {cache_key}")
            return pdf_data, filename
        
        logger.debug(f"PDF cache miss for key: {cache_key}")
        return None
    
    def set(self, cache_key: str, pdf_data: bytes, filename: str) -> None:
        """Cache PDF data with current timestamp"""
        self._cleanup_expired()
        
        # Add the new entry
        self._cache[cache_key] = (pdf_data, filename, datetime.now())
        
        # Enforce size limit after adding (may remove the oldest entry if needed)
        self._enforce_size_limit()
        
        logger.debug(f"Cached PDF with key: {cache_key}, size: {len(pdf_data)} bytes")
    
    def clear(self) -> None:
        """Clear all cached PDFs"""
        self._cache.clear()
        logger.info("Cleared PDF cache")
    
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        self._cleanup_expired()
        return {
            'total_entries': len(self._cache),
            'max_size': self._max_size,
            'ttl_minutes': int(self._ttl.total_seconds() / 60)
        }

class CommandHandlers:
    """Collection of bot command handlers"""
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.data_fetcher = DataFetcher()
        self.pdf_generator = PDFGenerator()
        self.db_handler = SupabaseHandler()  # Single instance for all operations
        self.pdf_cache = PDFCache(ttl_minutes=30)  # 30-minute cache for PDFs
        
        # Initialize Gemini processor with error handling
        try:
            self.gemini_processor = GeminiProcessor()
            self.available_commands = self._get_available_commands()
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini processor: {e}")
            self.gemini_processor = None
            self.available_commands = []
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        chat_type = update.effective_chat.type
        user_id = update.effective_user.id

        if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            welcome_message = self._get_group_welcome_message()
        else:
            welcome_message = self._get_private_welcome_message()
        
        await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        chat_type = update.effective_chat.type

        if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            help_message = self._get_group_help_message()
        else:
            help_message = self._get_private_help_message()
        
        await update.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            db_status = await self._test_database_connection()
            monitoring_status = "Active" if self.bot.monitoring_active else "Inactive"
            status_message = self._format_status_message(
                monitoring_status, db_status, update.effective_chat.id
            )
            await update.message.reply_text(status_message, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text("❌ Failed to get status information")

    @rate_limit(5)
    @admin_required
    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        user = update.effective_user

        if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await update.message.reply_text("❌ Subscription is only available in group chats.")
            return
        
        if self.bot.group_manager.is_subscribed(str(chat.id)):
            await update.message.reply_text("ℹ️ This group is already subscribed!")
            return

        try:
            if not await self._test_database_connection():
                await update.message.reply_text("❌ Cannot subscribe: Database connection failed.")
                return
            
            self.bot.group_manager.subscribe_group(str(chat.id))
            self.bot.group_manager.add_admin(str(chat.id), str(user.id))

            success_message = (
                f"✅ **Group Subscribed Successfully!**\n\n"
                f"🏷️ **Group:** {chat.title}\n"
                f"👤 **Subscribed by:** {user.first_name}\n"
                f"✨ **Database:** Connected"
            )
            await update.message.reply_text(success_message, parse_mode=ParseMode.MARKDOWN)
            logger.info(f"Group {chat.title} ({chat.id}) subscribed by user {user.id}")

        except Exception as e:
            logger.error(f"Subscribe command failed: {e}")
            await update.message.reply_text("❌ Subscription failed. Please try again later.")

    @rate_limit(5)
    @admin_required
    async def unsubscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /unsubscribe command"""
        chat = update.effective_chat
        user = update.effective_user
        
        if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await update.message.reply_text("❌ Unsubscription is only available in group chats.")
            return
        
        if not self.bot.group_manager.is_subscribed(str(chat.id)):
            await update.message.reply_text("ℹ️ This group is not subscribed.")
            return
        
        try:
            self.bot.group_manager.unsubscribe_group(str(chat.id))
            
            success_message = (
                f"✅ **Group Unsubscribed Successfully!**\n\n"
                f"🏷️ **Group:** {chat.title}\n"
                f"👤 **Unsubscribed by:** {user.first_name}"
            )
            
            await update.message.reply_text(success_message, parse_mode=ParseMode.MARKDOWN)
            logger.info(f"Group {chat.title} ({chat.id}) unsubscribed by user {user.id}")
        
        except Exception as e:
            logger.error(f"Unsubscribe command failed: {e}")
            await update.message.reply_text("❌ Unsubscription failed. Please try again later.")
    
    @rate_limit(10)
    async def check_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /check command to search for BRV number"""
        if not context.args:
            await update.message.reply_text("❌ Please provide a BRV number (e.g., /check AS496820)")
            return
        
        brv_number = context.args[0].strip()
        if not validate_brv_format(brv_number):
            await update.message.reply_text("❌ Please provide a valid BRV number (e.g., /check AS496820)")
            return
        await update.message.reply_text(f"🔍 Searching for BRV number: `{brv_number}`...")

        try:
            found_records = await self.db_handler.search_brv_number(brv_number)
            if not found_records:
                await update.message.reply_text(f"❌ No records found for BRV number: {brv_number}")
                return
            message = f"✅ **Found {len(found_records)} record(s) for BRV number: {brv_number}**\n\n"
            for idx, record in enumerate(found_records, start=1):
                row = record['data']
                table_name = record['table'].replace('_', ' ').title()
                order_date = row.get('order_date', 'N/A')
                if order_date != 'N/A':
                    try:
                        order_date = pd.to_datetime(order_date).strftime('%d-%m-%Y')
                    except (ValueError, TypeError, AttributeError) as e:
                        logger.warning(f"Failed to parse date '{order_date}': {e}")
                        order_date = str(order_date)  # Keep original value as string
                message += (
                    f"**Record {idx} (Status: {table_name})**\n"
                    f"📅 Date: {order_date}\n"
                    f"🔢 Order: {row.get('order_number', 'N/A')}\n"
                    f"🛢️ Product: {row.get('products', 'N/A')}\n"
                    f"📊 Volume: {row.get('volume', 'N/A')}\n"
                    f"💰 Price: {row.get('ex_ref_price', 'N/A')}\n"
                    f"📋 BRV: {row.get('brv_number', 'N/A')}\n"
                    f"🏢 BDC: {row.get('bdc', 'N/A')}\n"
                )
            messages = split_message(message)

            for msg in messages:
                await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Manual check failed: {e}")
            await update.message.reply_text(f"❌ Check failed: {str(e)}")

    @rate_limit(15)
    async def recent_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /recent command"""
        try:
            recent_df = await self.db_handler.get_new_records('depot_manager')
            if recent_df.empty:
                await update.message.reply_text("📭 No recent records found.")
                return
            recent_df = recent_df.head(10)
            message = "📋 **Recent Depot Manager Records (Last 10):**\n\n"
            for idx, (_, row) in enumerate(recent_df.iterrows(), 1):
                order_date = row.get('order_date', 'N/A')
                if order_date != 'N/A':
                    try:
                        order_date = pd.to_datetime(order_date).strftime('%d-%m-%Y')
                    except (ValueError, TypeError, AttributeError) as e:
                        logger.warning(f"Failed to parse date '{order_date}': {e}")
                        order_date = str(order_date)  # Keep original value as string
                message += (
                    f"**Record {idx}:**\n"
                    f"📅 Date: {order_date}\n"
                    f"🔢 Order: {row.get('order_number', 'N/A')}\n"
                    f"🛢️ Product: {row.get('products', 'N/A')}\n"
                    f"📊 Volume: {row.get('volume', 'N/A')}\n"
                    f"💰 Price: {row.get('ex_ref_price', 'N/A')}\n"
                    f"📋 BRV: {row.get('brv_number', 'N/A')}\n"
                    f"🏢 BDC: {row.get('bdc', 'N/A')}\n"
                    f"🕒 Detected: {pd.to_datetime(row.get('created_at', 'N/A')).strftime('%d-%m-%Y %H:%M:%S') if row.get('created_at') != 'N/A' else 'N/A'}\n"
                    "─────────────────\n"
                )
            messages = split_message(message)
            for msg in messages:
                await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Failed to get recent records: {e}")
            await update.message.reply_text(f"❌ Failed to retrieve recent records: {str(e)}")

    @rate_limit(20)
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        try:
            stats = await self.db_handler.get_table_stats()
            message = "📊 **Table Statistics**\n\n"
            for table_name, count in stats.items():
                display_name = table_name.replace('_', ' ').title()
                message += f"• **{display_name}**: {count} records\n"
            
            message += f"\n👥 **Subscribed Groups**: {len(self.bot.group_manager.get_subscribed_groups())}"
            
            messages = split_message(message)
            for msg in messages:
                await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Stats command failed: {e}")
            await update.message.reply_text(f"❌ Failed to retrieve statistics: {str(e)}")
        
    @rate_limit(10)
    async def cache_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cache_status command for superadmins"""
        user = update.effective_user

        if not self.bot._is_superadmin(user.id):
            await update.message.reply_text("❌ This command is only available to superadmins.")
            return
        
        try:
            # Get PDF cache statistics
            cache_stats = self.pdf_cache.get_stats()
            
            # Get database cache statistics if available
            db_cache_stats = {}
            if hasattr(self.bot.db_handler, 'cache') and hasattr(self.bot.db_handler.cache, 'get_stats'):
                db_cache_stats = self.bot.db_handler.cache.get_stats()
            
            cache_message = "🗄️ **Cache Status Report**\n\n"
            
            # PDF Cache Stats
            cache_message += "📄 **PDF Cache:**\n"
            cache_message += f"• Entries: {cache_stats['total_entries']}/{cache_stats['max_size']}\n"
            cache_message += f"• TTL: {cache_stats['ttl_minutes']} minutes\n"
            cache_message += f"• Status: {'🟢 Active' if cache_stats['total_entries'] > 0 else '🔴 Empty'}\n\n"
            
            # Database Cache Stats (if available)
            if db_cache_stats:
                cache_message += "🗃️ **Database Cache:**\n"
                cache_message += f"• Hit Rate: {db_cache_stats.get('hit_rate', 'N/A')}%\n"
                cache_message += f"• Total Requests: {db_cache_stats.get('total_requests', 'N/A')}\n"
                cache_message += f"• Cache Size: {db_cache_stats.get('cache_size', 'N/A')}\n"
            else:
                cache_message += "🗃️ **Database Cache:** Not available\n"
            
            cache_message += f"\n🕒 **Generated:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
            
            await update.message.reply_text(cache_message, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Cache status command failed: {e}")
            await update.message.reply_text(f"❌ Failed to get cache status: {str(e)}")
    
    @rate_limit(10)
    async def clear_cache_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clear_cache command for superadmins"""
        user = update.effective_user

        if not self.bot._is_superadmin(user.id):
            await update.message.reply_text("❌ This command is only available to superadmins.")
            return
        
        try:
            # Clear PDF cache
            old_stats = self.pdf_cache.get_stats()
            self.pdf_cache.clear()
            
            # Clear database cache if available
            db_cache_cleared = False
            if hasattr(self.bot.db_handler, 'cache') and hasattr(self.bot.db_handler.cache, 'clear'):
                self.bot.db_handler.cache.clear()
                db_cache_cleared = True
            
            clear_message = "🧹 **Cache Cleared Successfully**\n\n"
            clear_message += f"📄 **PDF Cache:** Cleared {old_stats['total_entries']} entries\n"
            
            if db_cache_cleared:
                clear_message += "🗃️ **Database Cache:** Cleared\n"
            else:
                clear_message += "🗃️ **Database Cache:** Not available\n"
            
            clear_message += f"\n🕒 **Cleared at:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
            
            await update.message.reply_text(clear_message, parse_mode=ParseMode.MARKDOWN)
            logger.info(f"Cache cleared by superadmin {user.id}")
            
        except Exception as e:
            logger.error(f"Clear cache command failed: {e}")
            await update.message.reply_text(f"❌ Failed to clear cache: {str(e)}")

    @rate_limit(10)
    @subscribed_group_required
    async def volume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /volume command - get total volume loaded"""
        try:
            await update.message.reply_text("📊 Calculating total volume loaded...")
            
            total_volume = await self.db_handler.get_total_volume_loaded()
            
            volume_message = (
                f"📊 **Total Volume Report**\n\n"
                f"🛢️ **Total Volume Loaded:** {total_volume:,.2f} liters\n"
                f"📅 **As of:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"*Volume calculated from: marked, brv_checked, loaded, order_released tables*"
            )
            
            await update.message.reply_text(volume_message, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Volume command failed: {e}")
            await update.message.reply_text(f"❌ Failed to calculate volume: {str(e)}")

    @rate_limit(60)  # Increased from 30 to 60 seconds
    @subscribed_group_required
    async def download_pdf_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /download_pdf command with caching"""
        chat = update.effective_chat

        if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await update.message.reply_text("❌ This command is only available in group chats.")
            return

        try:
            async with asyncio.timeout(30):
                current_time = datetime.now()
                cache_key = f"pdf_{current_time.strftime('%Y%m%d_%H')}"

                cached_result = self.pdf_cache.get(cache_key)
                if cached_result:
                    pdf_data, filename = cached_result
                    logger.info(f"Serving cached PDF: {filename}")
                    await update.message.reply_text("📄 Generating report from cache...")
                    with BytesIO(pdf_data) as pdf_file:
                        pdf_file.name = filename
                        await update.message.reply_document(
                            document=pdf_file,
                            filename=filename,
                            caption=f"📄 Latest Report (📋 Cached - Generated at {filename.split('_')[1][:8]})"
                        )
                    return

                await update.message.reply_text("📄 Generating fresh PDF report...")

                # First, try to get data from the database
                processed_data_frames = await self.db_handler.get_all_records_for_pdf()

                # If database is empty, fall back to API
                if not processed_data_frames:
                    logger.info("Database is empty, falling back to API for PDF generation.")
                    await update.message.reply_text("ℹ️ Database is empty, falling back to API...")
                    fetch_result = await self.data_fetcher.fetch_data()
                    if fetch_result.error:
                        await update.message.reply_text(f"❌ Failed to fetch data from API: {fetch_result.error}")
                        return
                    single_df, error = await self.data_fetcher.process_data(fetch_result)
                    if error:
                        await update.message.reply_text(f"❌ Failed to process API data: {error}")
                        return
                    if single_df is not None and not single_df.empty:
                        processed_data_frames = {"API Data": single_df}
                    else:
                        processed_data_frames = {}

                if not processed_data_frames:
                    await update.message.reply_text("📭 No data found to generate PDF.")
                    return

                title = f"BOST-KUMASI Report - {current_time.strftime('%d-%m-%Y %H:%M:%S')}"
                footnote = (
                    "Data sourced from I.T.S (Persol System Limited). "
                    "Modified by Awuah. Data may be incorrect. "
                )

                pdf_data, error = await self.pdf_generator.generate(processed_data_frames, title, footnote)
                if error:
                    await update.message.reply_text(f"❌ Failed to generate PDF: {error}")
                    return

                filename = f"BOST-KUMASI_{current_time.strftime('%Y%m%d_%H%M%S')}.pdf"

                self.pdf_cache.set(cache_key, pdf_data, filename)
                logger.info(f"Cached new PDF: {filename}")

                with BytesIO(pdf_data) as pdf_file:
                    pdf_file.name = filename
                    await update.message.reply_document(
                        document=pdf_file,
                        filename=filename,
                        caption=f"📄 Latest Report ({sum(len(df) for df in processed_data_frames.values())} records) ✨ Fresh"
                    )

        except asyncio.TimeoutError:
            logger.error("PDF generation timed out")
            await update.message.reply_text("❌ PDF generation timed out. Please try again later.")
        except Exception as e:
            logger.error(f"PDF download command failed: {e}")
            await update.message.reply_text(f"❌ Failed to generate PDF: {str(e)}")
    
    async def groups_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /groups command for superadmins"""
        user = update.effective_user

        if not self.bot._is_superadmin(user.id):
            await update.message.reply_text("❌ This command is only available to superadmins.")
            return
        
        try:
            subscribed_groups = self.bot.group_manager.get_subscribed_groups()

            if not subscribed_groups:
                await update.message.reply_text("ℹ️ No groups are currently subscribed.")
                return
            
            message = f"👥 **Subscribed Groups ({len(subscribed_groups)}):**\n\n"
            
            for group_id in subscribed_groups:
                try:
                    chat = await self.bot.bot.get_chat(int(group_id))
                    message += f"• {chat.title} (ID: {group_id})\n"
                except Exception as e:
                    logger.warning(f"Failed to get chat info for group {group_id}: {e}")
                    message += f"• Unknown Group (ID: {group_id})\n"
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        
        except Exception as e:
            logger.error(f"Groups command failed: {e}")
            await update.message.reply_text("❌ Failed to retrieve group information.")
    
    def _get_available_commands(self) -> List[str]:
        """Returns a list of available command strings."""
        commands = [
            "/start", "/help", "/status", "/subscribe", "/unsubscribe",
            "/check", "/recent", "/stats", "/cache_status", "/clear_cache",
            "/volume", "/download_pdf", "/groups", "/search_bdc"
        ]
        return commands

    async def handle_general_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles general text and audio messages using Gemini to determine intent."""
        message = update.message
        
        # Handle text messages
        if message.text and not message.text.startswith('/'):
            user_message = message.text
            
            # Check if Gemini processor is available
            if not self.gemini_processor:
                await update.message.reply_text("🤖 AI processing is currently unavailable. Please use direct commands like /help.", parse_mode=ParseMode.MARKDOWN)
                return

            command_to_execute = self.gemini_processor.get_command_from_text(user_message, self.available_commands)

            if command_to_execute != 'NO_COMMAND':
                command_handler_name = command_to_execute.strip('/').split(' ')[0] + "_command"
                handler = getattr(self, command_handler_name, None)
                if handler and callable(handler):
                    # Extract potential arguments from the user message
                    context.args = user_message.split()[1:] if len(user_message.split()) > 1 else []
                    await handler(update, context)
            else:
                await update.message.reply_text("I'm not sure how to respond to that. Try /help for a list of commands.", parse_mode=ParseMode.MARKDOWN)
        
        # Handle audio/voice messages
        elif message.voice or message.audio:
            await update.message.reply_text("🎵 Processing your audio message...")
            
            # Check if Gemini processor is available
            if not self.gemini_processor:
                await update.message.reply_text("🤖 AI processing is currently unavailable. Please use direct commands like /help.", parse_mode=ParseMode.MARKDOWN)
                return
            
            try:
                # Download the audio file
                if message.voice:
                    file = await message.voice.get_file()
                else:
                    file = await message.audio.get_file()
                
                # Create a temporary file path
                import tempfile
                import os
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_file:
                    temp_path = temp_file.name
                    await file.download_to_drive(temp_path)
                
                try:
                    # Process the audio with Gemini
                    command_to_execute = self.gemini_processor.process_audio_message(temp_path, self.available_commands)
                    
                    if command_to_execute != 'NO_COMMAND':
                        command_handler_name = command_to_execute.strip('/').split(' ')[0] + "_command"
                        handler = getattr(self, command_handler_name, None)
                        if handler and callable(handler):
                            # For audio commands, we don't have text args, so pass empty
                            context.args = []
                            await handler(update, context)
                        else:
                            await update.message.reply_text(f"🎵 I heard you want to execute: {command_to_execute}")
                    else:
                        await update.message.reply_text("🎵 I processed your audio but couldn't determine a specific command. Try speaking clearly or use text commands.", parse_mode=ParseMode.MARKDOWN)
                
                finally:
                    # Clean up temporary file
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                        
            except Exception as e:
                logger.error(f"Error processing audio message: {e}")
                await update.message.reply_text("❌ Sorry, I couldn't process your audio message. Please try again or use text commands.", parse_mode=ParseMode.MARKDOWN)
        
        # Ignore other message types or commands
        return
    
    async def _test_database_connection(self) -> bool:
        """Test database connection"""
        try:
            result, error = await self.db_handler.make_request('GET', 'depot_manager', params={'limit': '1'})
            return error is None
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def _format_status_message(self, monitoring_status: str, db_status: bool, chat_id: int) -> str:
        """Format status message with current bot information"""
        db_status_text = "✅ Connected" if db_status else "❌ Failed"
        is_subscribed = self.bot.group_manager.is_subscribed(str(chat_id))
        
        return f"""
📊 **Bot Status**

🔄 **Monitoring:** {monitoring_status}
🕒 **Last Check:** {self.bot.last_check_time.strftime("%Y-%m-%d %H:%M:%S") if self.bot.last_check_time else "Never"}
⏱️ **Check Interval:** {self.bot.monitoring_interval // 60} minutes
👥 **Subscribed Groups:** {len(self.bot.group_manager.get_subscribed_groups())}
🔢 **Total Checks:** {self.bot.total_checks}
📬 **Last Notification:** {self.bot.last_notification_count} records
🗄️ **Database:** {db_status_text}
💾 **Current Chat:** {'✅ Subscribed' if is_subscribed else '❌ Not Subscribed'}
        """
    
    @rate_limit(10)
    async def search_bdc_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search_bdc <bdc_name> - search records by BDC name (case-insensitive substring)

        Queries all configured tables using SupabaseHandler.search_bdc and returns a summary
        of the first matching records.
        """
        if not context.args:
            await update.message.reply_text("❌ Please provide a BDC name to search. Usage: /search_bdc <BDC name>")
            return

        query = " ".join(context.args).strip()
        if not query:
            await update.message.reply_text("❌ Please provide a non-empty BDC name to search.")
            return

        await update.message.reply_text(f"🔎 Searching for records matching BDC: `{query}`...", parse_mode=ParseMode.MARKDOWN)

        try:
            results = await self.db_handler.search_bdc(query)

            if not results:
                await update.message.reply_text(f"📭 No records found matching BDC: `{query}`", parse_mode=ParseMode.MARKDOWN)
                return

            total = len(results)
            max_show = 20
            show_count = min(total, max_show)

            message = f"✅ Found {total} record(s) matching BDC: `{query}`\nShowing first {show_count}:\n\n"

            for idx, item in enumerate(results[:show_count], start=1):
                row = item.get('data', {})
                table_name = item.get('table', 'unknown').replace('_', ' ').title()

                created_at = row.get('created_at', 'N/A')
                if created_at and created_at != 'N/A':
                    try:
                        created_at = pd.to_datetime(created_at).strftime('%d-%m-%Y %H:%M:%S')
                    except Exception:
                        created_at = str(created_at)

                message += (
                    f"**{idx}. Table:** {table_name}\n"
                    f"• ID: {row.get('id', 'N/A')}\n"
                    f"• Order: {row.get('order_number', 'N/A')}\n"
                    f"• BDC: {row.get('bdc', 'N/A')}\n"
                    f"• BRV: {row.get('brv_number', 'N/A')}\n"
                    f"• Volume: {row.get('volume', 'N/A')}\n"
                    f"• Detected: {created_at}\n"
                    "─────────────────\n"
                )

            if total > max_show:
                message += f"\nℹ️ {total - max_show} more results not shown. Run the command in a private chat or request an export to retrieve full results."

            messages = split_message(message)
            for msg in messages:
                await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error(f"search_bdc command failed for '{query}': {e}")
            await update.message.reply_text(f"❌ Search failed: {str(e)}")