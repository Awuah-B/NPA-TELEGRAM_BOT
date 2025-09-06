#! /usr/bin/env python3
## File: /handlers/bot.py

"""
Main Telegram bot class
Orchestrates all bot functionality with proper lifecycle management.
"""
import asyncio
from datetime import datetime
from typing import Optional, Dict, List
from tenacity import retry, stop_after_attempt, wait_exponential, wait_fixed
from telegram import Bot, Update, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ChatMemberHandler, ContextTypes
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError, TimedOut
from telegram.request import HTTPXRequest
import re
import pandas as pd

from app.config import CONFIG
from app.database.connection import SupabaseHandler
from app.database.cache import CachedSupabaseHandler
from app.database.realtime import RealtimeListener
from app.handlers.commands import CommandHandlers
from app.handlers.events import EventHandlers
from app.handlers.bot_manager import GroupChatManager
from app.service.notification import NotificationService
from app.utils.log_settings import setup_logging
from app.utils.helper import format_uptime

logger = setup_logging('bot.log')

class NPAMonitorBot:
    """Main Telegram bot class with comprehensive functionality"""

    def __init__(self):
        # Clean the bot token to remove any newlines or whitespace
        raw_token = CONFIG.telegram.bot_token
        self.bot_token = raw_token.strip().replace('\n', '').replace('\r', '') if raw_token else None
        
        if not self.bot_token:
            raise ValueError("Bot token is empty or invalid after cleaning")
            
        self.superadmin_ids = {str(id) for id in CONFIG.telegram.superadmin_ids}
        # Monitor both new records tables supported by the data pipeline
        self.monitoring_tables = ['depot_manager_new_records', 'approved_new_records']
        self.application: Optional[Application] = None
        self.bot: Optional[Bot] = None
        self.db_handler: Optional[CachedSupabaseHandler] = None
        self.realtime_listener: Optional[RealtimeListener] = None
        self.group_manager = GroupChatManager()
        self.notification_service: Optional[NotificationService] = None
        self.command_handlers: Optional[CommandHandlers] = None
        self.event_handlers: Optional[EventHandlers] = None
        self.monitoring_active = False
        self.last_notification_count = 0
        self.monitoring_interval = CONFIG.monitoring.interval_seconds
        self.start_time = int(datetime.now().timestamp())
        self._background_tasks: set = set()
        self.total_checks = 0
        self.last_check_time = None
        self._initialized = False
        self.last_polled_timestamp: Dict[str, datetime] = {}
    
    async def initialise(self) -> None:
        """Initialize all bot components with proper error handling"""
        try:
            logger.info("Initializing Monitoring Bot")
            
            # Create custom request with longer timeout
            request = HTTPXRequest(
                connection_pool_size=10,
                connect_timeout=30.0,
                read_timeout=30.0,
                write_timeout=30.0,
                pool_timeout=30.0
            )
            
            # Initialize application with custom request
            self.application = Application.builder().token(self.bot_token).request(request).build()
            
            # Retry initialization with exponential backoff
            await self._initialize_with_retry()
            
            # Initialize bot instance
            self.bot = self.application.bot
            
            # Initialize database components
            supabase_handler = SupabaseHandler()
            self.db_handler = CachedSupabaseHandler(supabase_handler)
            
            # Initialize realtime listener
            self.realtime_listener = RealtimeListener(self) 
            await self.realtime_listener.initialize()
            
            # Initialize services
            self.notification_service = NotificationService(
                bot=self.bot,
                group_manager=self.group_manager
            )
            
            # Initialize handlers
            self.command_handlers = CommandHandlers(self)
            self.event_handlers = EventHandlers(self)
            
            # Setup Telegram handlers
            self._setup_telegram_handlers()
            
            # Load and verify subscribed groups
            await self._load_and_verify_groups()
            
            # Start background tasks
            await self._start_background_tasks()
            
            # Verify initialization
            await self._verify_initialization()
            
            self._initialized = True
            logger.info("Bot initialization completed successfully")
            
        except Exception as e:
            self._initialized = False
            logger.error(f"Failed to initialize bot: {e}")
            # Always try to notify superadmins safely
            await self._notify_superadmins_safe(f"🚨 Bot initialization failed: {str(e)}")
            raise
    
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=60))
    async def _initialize_with_retry(self) -> None:
        """Initialize application with retry logic"""
        try:
            await self.application.initialize()
            logger.info("Application initialized successfully")
        except (TimedOut, TelegramError) as e:
            logger.warning(f"Initialization timeout/error, retrying: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during initialization: {e}")
            raise
    
    def _setup_telegram_handlers(self) -> None:
        handlers = [
            CommandHandler("start", self.command_handlers.start_command),
            CommandHandler("help", self.command_handlers.help_command),
            CommandHandler("status", self.command_handlers.status_command),
            CommandHandler("subscribe", self.command_handlers.subscribe_command),
            CommandHandler("unsubscribe", self.command_handlers.unsubscribe_command),
            CommandHandler("check", self.command_handlers.check_command),
            CommandHandler("search_bdc", self.command_handlers.search_bdc_command),
            CommandHandler("recent", self.command_handlers.recent_command),
            CommandHandler("stats", self.command_handlers.stats_command),
            CommandHandler("volume", self.command_handlers.volume_command),
            CommandHandler("download_pdf", self.command_handlers.download_pdf_command),
            CommandHandler("groups", self.command_handlers.groups_command),
            CommandHandler("cache_status", self.command_handlers.cache_status_command),
            CommandHandler("clear_cache", self.command_handlers.clear_cache_command),
            CommandHandler("search_bdc", self.command_handlers.search_bdc_command)
        ]
        for handler in handlers:
            self.application.add_handler(handler)
        self.application.add_handler(
            ChatMemberHandler(self.event_handlers.track_chat_members, ChatMemberHandler.MY_CHAT_MEMBER)
        )
        # Add message handler for general text and audio messages
        self.application.add_handler(MessageHandler(
            (filters.TEXT & ~filters.COMMAND) | filters.VOICE | filters.AUDIO, 
            self.command_handlers.handle_general_message
        ))
        logger.info(f"🔧 Registered {len(handlers) + 1} handlers to application")
        logger.info(f"🔧 Application handlers count: {len(self.application.handlers.get(0, []))}")
    
    async def _load_and_verify_groups(self) -> None:
        """Load and verify subscribed groups during initialization"""
        try:
            # Force refresh subscriptions to ensure they're current
            self.group_manager.refresh_subscriptions()
            
            # Get current subscription stats
            stats = self.group_manager.get_subscription_stats()
            subscribed_groups = self.group_manager.get_subscribed_groups()
            
            logger.info(f"📋 Loaded subscription data:")
            logger.info(f"  - Total subscribed groups: {stats['total_subscribed_groups']}")
            logger.info(f"  - Total group admins: {stats['total_group_admins']}")
            logger.info(f"  - Storage file exists: {stats['storage_exists']}")
            logger.info(f"  - Storage file path: {stats['storage_file']}")
            
            if subscribed_groups:
                logger.info(f"📢 Active subscribed groups:")
                accessible_groups = []
                inaccessible_groups = []
                
                for group_id in subscribed_groups:
                    admins = self.group_manager.get_group_admins(group_id)
                    logger.info(f"  - Group {group_id}: {len(admins)} admin(s)")
                    
                    # Try to verify bot has access to the group
                    try:
                        if self.bot:
                            chat = await self.bot.get_chat(group_id)
                            accessible_groups.append(group_id)
                            logger.info(f"  ✅ Bot has access to group {group_id} ({chat.title if hasattr(chat, 'title') else 'Unknown'})")
                    except Exception as e:
                        inaccessible_groups.append(group_id)
                        logger.warning(f"  ❌ Bot cannot access group {group_id}: {e}")
                
                # Prepare notification message
                accessible_list = "\n".join([f"✅ {group_id}" for group_id in accessible_groups])
                inaccessible_list = "\n".join([f"❌ {group_id}" for group_id in inaccessible_groups])
                
                message_parts = [f"🔄 Bot initialized with {len(subscribed_groups)} subscribed group(s):"]
                if accessible_list:
                    message_parts.append(f"\nAccessible groups:\n{accessible_list}")
                if inaccessible_list:
                    message_parts.append(f"\nInaccessible groups:\n{inaccessible_list}")
                
                #await self._notify_superadmins_safe("\n".join(message_parts))
                    
            else:
                logger.info("📢 No subscribed groups found")
                await self._notify_superadmins_safe("🔄 Bot initialized with no subscribed groups")
                
        except Exception as e:
            logger.error(f"Failed to load and verify groups: {e}")
            await self._notify_superadmins_safe(f"⚠️ Failed to load subscribed groups: {str(e)}")
    
    async def _start_background_tasks(self) -> None:
        try:
            await self._start_monitoring()
            health_task = asyncio.create_task(self._health_check_loop())
            self._background_tasks.add(health_task)
            health_task.add_done_callback(self._background_tasks.discard)
            cache_task = asyncio.create_task(self._cache_cleanup_loop())
            self._background_tasks.add(cache_task)
            cache_task.add_done_callback(self._background_tasks.discard)
            # Add polling fallback task
            polling_task = asyncio.create_task(self._polling_fallback_loop())
            self._background_tasks.add(polling_task)
            polling_task.add_done_callback(self._background_tasks.discard)
        except Exception as e:
            logger.error(f"Failed to start background tasks: {e}")
            await self._notify_superadmins(f"🚨 Background tasks failed: {str(e)}")
            raise
    
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=30))
    async def _start_monitoring(self) -> None:
        try:
            self.monitoring_active = True
            logger.info(f"Real-time monitoring started for tables: {self.monitoring_tables}")
        except Exception as e:
            self.monitoring_active = False
            logger.error(f"Failed to start monitoring: {e}")
            await self._notify_superadmins(f"🚨 Real-time monitoring failed: {str(e)}")
            raise
    
    async def _handle_new_record(self, table_name: str, record: dict) -> None:
        try:
            # Validate input parameters
            if not table_name or not isinstance(table_name, str):
                logger.error(f"Invalid table_name: {table_name}")
                await self._notify_superadmins_safe("🚨 Invalid table name in realtime record")
                return
            
            if not record or not isinstance(record, dict):
                logger.error(f"Invalid record data for {table_name}: {record}")
                await self._notify_superadmins_safe(f"🚨 Invalid record data for {table_name}")
                return
            
            # Log with enhanced information
            record_id = record.get('id', 'unknown')
            logger.info(f"Processing new record {record_id} from {table_name}")
            
            self.total_checks += 1
            self.last_check_time = datetime.now()
            
            # Validate record has required fields for notifications
            required_fields = ['id', 'created_at']
            missing_fields = [field for field in required_fields if field not in record]
            
            if missing_fields:
                logger.warning(f"Record missing required fields {missing_fields} for {table_name}: {record_id}")
                # Still process the record but log the issue
            
            # Notify about new record with enhanced error handling
            try:
                await self.notification_service.notify_new_records(table_name, record)
                self.last_notification_count = 1
                logger.info(f"Successfully processed and notified new record {record_id} from {table_name}")
            except Exception as notify_error:
                logger.error(f"Failed to notify about new record {record_id} from {table_name}: {notify_error}")
                # Try to notify superadmins about the notification failure
                await self._notify_superadmins_safe(
                    f"🚨 Notification failed for record {record_id} in {table_name}: {str(notify_error)}"
                )
                    
        except Exception as e:
            logger.error(f"Error handling new record from {table_name}: {e}")
            # Always try to notify superadmins about critical errors
            await self._notify_superadmins_safe(f"🚨 Critical error processing record from {table_name}: {str(e)}")
    
    async def _health_check_loop(self) -> None:
        attempt = 0
        max_attempts = 5
        health_check_failures = 0
        max_health_failures = 3  # Only notify after multiple consecutive failures
        
        while True:
            try:
                await asyncio.sleep(CONFIG.monitoring.buffer_timeout_seconds)
                result, error = await self.db_handler.make_request('GET', '', params={'limit': '1'})
                if error:
                    logger.warning("Health check detected database issue")
                    await self._notify_superadmins("⚠️ Database health check failed")
                
                # Check realtime connection health
                if not self.realtime_listener.is_connected():
                    logger.warning("Real-time monitoring is not connected")
                    attempt += 1
                    if attempt > max_attempts:
                        logger.error("Max reconnection attempts reached")
                        await self._notify_superadmins("🚨 Real-time monitoring permanently disconnected")
                        break
                    # Try to reconnect
                    try:
                        await self.realtime_listener.reconnect()
                        logger.info("Successfully reconnected realtime listener")
                        attempt = 0  # Reset on success
                        health_check_failures = 0  # Reset health check failures
                    except Exception as reconnect_error:
                        logger.error(f"Failed to reconnect realtime listener: {reconnect_error}")
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    attempt = 0 
                    # Only check health if connected, and be less aggressive about failures
                    try:
                        health_ok = await self.realtime_listener.health_check()
                        if not health_ok:
                            health_check_failures += 1
                            logger.debug(f"Realtime listener health check failed ({health_check_failures}/{max_health_failures})")
                            
                            # Only notify after multiple consecutive failures
                            if health_check_failures >= max_health_failures:
                                logger.warning(f"Realtime listener failed {health_check_failures} consecutive health checks")
                                await self._notify_superadmins(f"⚠️ Realtime listener health check failed {health_check_failures} times")
                                health_check_failures = 0  # Reset after notification
                        else:
                            health_check_failures = 0  # Reset on successful health check
                    except Exception as health_error:
                        logger.debug(f"Health check exception: {health_error}")
                        health_check_failures += 1
            
            except asyncio.CancelledError:
                logger.info("Health check loop cancelled")
                raise
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(30)
    
    async def _cache_cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(CONFIG.monitoring.cache_ttl_seconds)
                if not hasattr(self.db_handler, 'cache'):
                    logger.warning("Cache not initialized for db_handler")
                    continue
                cleaned = self.db_handler.cache.cleanup_expired()
                if cleaned > 0:
                    logger.debug(f"Cleaned up {cleaned} expired cache entries")
            except asyncio.CancelledError:
                logger.info("Cache cleanup loop cancelled")
                raise
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
    
    async def _polling_fallback_loop(self) -> None:
        """Poll for new records when realtime is disconnected or polling is enabled"""
        polling_interval = CONFIG.monitoring.polling_interval_seconds
        
        while True:
            try:
                await asyncio.sleep(polling_interval)
                
                # Only poll if polling is enabled or realtime is disconnected
                if not CONFIG.monitoring.polling_enabled and \
                   (self.realtime_listener and self.realtime_listener.is_connected()):
                    continue
                    
                if CONFIG.monitoring.polling_enabled:
                    logger.info("Polling enabled, checking for new records")
                else:
                    logger.info("Realtime disconnected, checking for new records via polling")
                
                for table_name in self.monitoring_tables:
                    last_checked = self.last_polled_timestamp.get(table_name, datetime.min)
                    new_records_df = await self.db_handler.get_new_records_since(table_name, last_checked)
                    
                    if not new_records_df.empty:
                        logger.info(f"Polling detected {len(new_records_df)} new records in {table_name}")
                        for _, record in new_records_df.iterrows():
                            await self._handle_new_record(table_name, record.to_dict())
                        # Update last_polled_timestamp for this table to the latest record's created_at
                        latest_created_at = new_records_df['created_at'].max()
                        if pd.notna(latest_created_at):
                            # Ensure it's a datetime object
                            if isinstance(latest_created_at, pd.Timestamp):
                                self.last_polled_timestamp[table_name] = latest_created_at.to_pydatetime()
                            else:
                                self.last_polled_timestamp[table_name] = datetime.fromisoformat(latest_created_at)
                    else:
                        logger.debug(f"No new records in {table_name} since {last_checked}")
                
            except asyncio.CancelledError:
                logger.info("Polling fallback loop cancelled")
                raise
            except Exception as e:
                logger.error(f"Polling fallback error: {e}")
                await asyncio.sleep(60)  # Wait longer on error

    async def run(self) -> None:
        """Run the bot indefinitely"""
        try:
            logger.info("Starting NPA Monitor Bot")
            if CONFIG.telegram.webhook_url:
                logger.info("Webhook mode enabled, handled by serverless endpoint")
                # For webhook mode, we need to start the application but not run polling
                logger.info("Starting application for webhook processing...")
                await self.application.start()
                logger.info("✅ Application started for webhook mode")
            else:
                await self._run_polling()
        except Exception as e:
            logger.error(f"Error running bot: {e}")
            await self._notify_superadmins(f"🚨 Bot error: {str(e)}")
            raise
    
    async def _run_webhook(self) -> None:
        try:
            await self.bot.set_webhook(
                url=f"{CONFIG.telegram.webhook_url}/webhook",
                allowed_updates=Update.ALL_TYPES
            )
            await self.application.start()
            await self.application.updater.start_webhook(
                listen="0.0.0.0",
                port=CONFIG.telegram.webhook_port,
                url_path="/webhook",
                webhook_url=f"{CONFIG.telegram.webhook_url}/webhook"
            )

            logger.info(f"Bot running with webhook on port {CONFIG.telegram.webhook_port}")
        except Exception as e:
            logger.error(f"Failed to start webhook: {e}")
            raise
    
    async def _run_polling(self) -> None:
        try:
            logger.info("Starting bot in polling mode")
            await self.application.start()
            await self.application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            logger.info("Bot polling started successfully")
        except Exception as e:
            logger.error(f"Failed to start polling: {e}")
            raise

    async def shutdown(self) -> None:
        try:
            logger.info("Starting bot shutdown")
            self.monitoring_active = False
            for task in self._background_tasks:
                task.cancel()
            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)
            if self.realtime_listener:
                await self.realtime_listener.shutdown()
            if self.db_handler:
                await self.db_handler.close()
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            logger.info("Bot shutdown completed")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def _is_user_admin(self, chat_id: int, user_id: int) -> bool:
        try:
            chat_member = await self.bot.get_chat_member(chat_id, user_id)
            return chat_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
        except TelegramError as e:
            logger.warning(f"Telegram error checking admin status for user {user_id} in chat {chat_id}: {e}")
            raise
        except Exception as e:
            logger.warning(f"Unexpected error checking admin status for user {user_id} in chat {chat_id}: {e}")
            raise
    
    def _is_superadmin(self, user_id: int) -> bool:
        return str(user_id) in self.superadmin_ids

    async def _notify_superadmins(self, message: str) -> None:
        """Notify superadmins with proper error handling and retry logic"""
        if not self.bot:
            logger.error("Cannot notify superadmins: bot not initialized")
            return
            
        for admin_id in self.superadmin_ids:
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    await self.bot.send_message(
                        chat_id=int(admin_id),
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

    async def _notify_superadmins_safe(self, message: str) -> None:
        """Safe wrapper for notifying superadmins that won't raise exceptions"""
        try:
            await self._notify_superadmins(message)
        except Exception as e:
            logger.error(f"Critical error in superadmin notification: {e}")

    async def send_test_message(self, chat_id: int, message: str) -> bool:
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return True
        except TelegramError as e:
            logger.warning(f"Failed to send test message to {chat_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending test message to {chat_id}: {e}")
            return False
    
    def get_bot_stats(self) -> Dict:
        uptime = datetime.now().timestamp() - self.start_time
        stats = {
            'uptime_seconds': int(uptime),
            'uptime_formatted': format_uptime(self.start_time),
            'monitoring_active': self.monitoring_active,
            'total_checks': self.total_checks,
            'last_check_time': self.last_check_time.isoformat() if self.last_check_time else None,
            'last_notification_count': self.last_notification_count,
            'subscribed_groups': len(self.group_manager.get_subscribed_groups()),
            'background_tasks': len(self._background_tasks),
            'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
            'realtime_connected': self.realtime_listener.is_connected() if self.realtime_listener else False
        }
        if hasattr(self.db_handler, 'cache'):
            stats['cache'] = self.db_handler.get_cache_stats()
        else:
            stats['cache'] = {'error': 'Cache not initialized'}
        stats['group_manager'] = self.group_manager.get_subscription_stats()
        return stats
    
    async def perform_health_check(self) -> Dict[str, bool]:
        health = {}
        try:
            result, error = await self.db_handler.make_request('GET', '', params={'limit': '1'})
            health['database'] = error is None
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            health['database'] = False
        try:
            await self.bot.get_me()
            health['telegram_api'] = True
        except Exception as e:
            logger.warning(f"Telegram API health check failed: {e}")
            health['telegram_api'] = False
        health['monitoring'] = self.realtime_listener.is_connected() if self.realtime_listener else False
        health['background_tasks'] = len(self._background_tasks) > 0
        health['overall'] = all(health.values())
        return health
    
    def is_initialized(self) -> bool:
        """Check if bot is fully initialized and ready"""
        return self._initialized and self.bot is not None and self.db_handler is not None
    
    async def _verify_initialization(self) -> None:
        """Verify all components are working after initialization"""
        try:
            # Test Telegram API first (most critical - this is the only critical component)
            bot_info = await self.bot.get_me()
            logger.info(f"Connected to Telegram bot: @{bot_info.username}")
            
            # Test database connection (non-critical for startup)
            try:
                result, error = await self.db_handler.make_request('GET', '', params={'limit': '1'})
                if error:
                    logger.warning(f"Database connection issue during startup: {error}")
                    # Don't fail initialization, just log the warning
                else:
                    logger.info("Database connection verified successfully")
            except Exception as db_error:
                logger.warning(f"Database verification failed during startup: {db_error}")
                # Continue with initialization - database issues shouldn't block bot startup
            
            # Test realtime connection (non-critical for startup)
            try:
                if not self.realtime_listener.is_connected():
                    logger.warning("Realtime listener not connected during startup - will attempt reconnection in background")
                else:
                    logger.info("Realtime listener connected successfully")
            except Exception as rt_error:
                logger.warning(f"Realtime listener verification failed: {rt_error}")
                # Continue with initialization despite realtime issues
            
            # Test notification service (basic check)
            if not self.notification_service:
                logger.warning("Notification service not initialized - some features may be unavailable")
                # Don't raise exception, still allow bot to start
            else:
                logger.info("Notification service initialized successfully")
            
            # Mark as successfully initialized even with non-critical component issues
            logger.info("All critical components verified successfully")
        except Exception as e:
            logger.error(f"Critical initialization verification failed: {e}")
            raise
    
    # Public monitoring control methods
    async def start_monitoring(self) -> bool:
        """Start monitoring (public method)"""
        try:
            if not self.monitoring_active:
                await self._start_monitoring()
                return True
            else:
                logger.info("Monitoring is already active")
                return True
        except Exception as e:
            logger.error(f"Failed to start monitoring: {e}")
            return False
    
    async def stop_monitoring(self) -> bool:
        """Stop monitoring (public method)"""
        try:
            self.monitoring_active = False
            logger.info("Monitoring stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop monitoring: {e}")
            return False