#! /usr/bin/env python3
## File: /database/realtime.py
"""
Real-time monitoring service for Supabase database
Handles realtime subscriptions for the depot_manager_new_records table only.
"""
import asyncio
import logging
import os
import ssl
import certifi
from typing import Optional, Dict, Any, Callable

from app.config import CONFIG
from app.utils.log_settings import setup_logging

try:
    # Explicitly import the async client required for realtime features
    from supabase._async.client import AsyncClient as Client, create_client
    ASYNC_CLIENT_AVAILABLE = True
except ImportError:
    from supabase import create_client, Client # fallback for type hinting
    ASYNC_CLIENT_AVAILABLE = False

logger = setup_logging('realtime.log')

class ConfigurationError(Exception):
    pass

class RealtimeListener:
    """
    Listens for real-time INSERT events in the depot_manager_new_records table only
    """

    def __init__(self, bot_instance):
        if not ASYNC_CLIENT_AVAILABLE:
            # Fail early if the required async dependency is not installed.
            logger.error("async client not installed")
            raise ImportError("async client not installed")
        
        self.bot = bot_instance
        self.supabase: Optional[Client] = None
        self.channels: Dict[str, Any] = {}
        # Monitor all new records tables for insertions
        self.tables = ['depot_manager_new_records', 'approved_new_records']
        self.is_connected_flag = False
        self._connection_lock = asyncio.Lock()
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self._background_tasks = set()  # Track background tasks
        self._configure_ssl_context()

    def _configure_ssl_context(self):
        """Configure SSL context for websockets connections"""
        try:
            # Set environment variables for websockets SSL context
            os.environ['SSL_CERT_FILE'] = certifi.where()
            os.environ['SSL_CERT_DIR'] = os.path.dirname(certifi.where())
            
            logger.info(f"SSL context configured with certificate file: {certifi.where()}")
            
            # Optional: Try to patch websockets SSL if available
            try:
                import websockets
                import websockets.asyncio.client
                
                # Create SSL context for websockets
                ssl_context = ssl.create_default_context(cafile=certifi.where())
                ssl_context.check_hostname = True
                ssl_context.verify_mode = ssl.CERT_REQUIRED
                
                # Store original connect function if not already patched
                if not hasattr(websockets.asyncio.client, '_original_connect'):
                    websockets.asyncio.client._original_connect = websockets.asyncio.client.connect
                    
                    def patched_connect(*args, **kwargs):
                        # Add SSL context if not provided
                        if 'ssl' not in kwargs:
                            kwargs['ssl'] = ssl_context
                        return websockets.asyncio.client._original_connect(*args, **kwargs)
                    
                    # Replace the connect function
                    websockets.asyncio.client.connect = patched_connect
                    logger.info("Websockets SSL context patched successfully")
                else:
                    logger.info("Websockets SSL context already patched")
                    
            except ImportError:
                logger.info("Websockets not available for SSL patching")
            except Exception as e:
                logger.warning(f"Failed to patch websockets SSL: {e}")
            
        except Exception as e:
            logger.warning(f"Failed to configure SSL context: {e}")
    
    async def initialize(self) -> None:
        """
        Initialize real-time listener with Supabase client and subscriptions
        """
        try:
            logger.info("Initializing Supabase realtime client")
            await self._connect()
            await self._subscribe_to_tables()
            logger.info("Realtime listener initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize real-time listener: {e}")
            self.is_connected_flag = False
            # Don't raise - allow the bot to start without realtime initially
            # Start a background task to retry connection with proper management
            task = asyncio.create_task(self._background_reconnect())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
    
    async def shutdown(self) -> None:
        """Shutdown the real-time listener"""
        try:
            logger.info("Shutting down realtime listener")
            self.is_connected_flag = False

            # Cancel background tasks
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to complete or be cancelled
            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()

            # Unsubscribe from all channels
            for table_name, channel in self.channels.items():
                try:
                    await channel.unsubscribe()
                except Exception as e:
                    logger.warning(f"Error unsubscribing from {table_name}: {e}")
            
            self.channels.clear()

            if self.supabase:
                # Note: The AsyncClient doesn't have an explicit close method
                # The connection will be cleaned up when the client is garbage collected
                self.supabase = None
            
            logger.info("Realtime listener shutdown completed")
        except Exception as e:
            logger.error(f"Error during realtime shutdown: {e}")

    async def _connect(self) -> None:
        """Establish connection to Supabase"""
        async with self._connection_lock:
            try:
                logger.info("Connecting to supabase realtime")
                if ASYNC_CLIENT_AVAILABLE:
                    logger.info("Using async Supabase client")
                    try:
                        # Use service_role_key if available, otherwise fall back to anon_key
                        auth_key = CONFIG.supabase.service_role_key or CONFIG.supabase.anon_key
                        
                        # Create client without complex options first to avoid configuration errors
                        self.supabase = await create_client(
                            str(CONFIG.supabase.url),
                            auth_key
                        )
                        
                        logger.info("Async Supabase client created successfully")
                    except Exception as e:
                        logger.error(f"Failed to create async Supabase client: {e}")
                        raise ConfigurationError(f"Failed to load configuration: {e}")
                    
                else:
                    logger.info("Using sync Supabase client (async not available)")
                    try:
                        # Use service_role_key if available, otherwise fall back to anon_key
                        auth_key = CONFIG.supabase.service_role_key or CONFIG.supabase.anon_key
                        
                        # Create client without complex options first to avoid configuration errors
                        self.supabase = create_client(
                            str(CONFIG.supabase.url), 
                            auth_key
                        )
                        
                        logger.info("Sync Supabase client created successfully")
                    except Exception as e:
                        logger.error(f"Failed to create sync Supabase client: {e}")
                        raise ConfigurationError(f"Failed to load configuration: {e}")
                
                self.is_connected_flag = True
                self.reconnect_attempts = 0
                logger.info("Successfully connected to Supabase realtime")
            except Exception as e:
                logger.error(f"Failed to connect to Supabase: {e}")
                self.reconnect_attempts += 1

                if self.reconnect_attempts < self.max_reconnect_attempts:
                    backoff_time = min(2 ** self.reconnect_attempts, 60)
                    logger.info(f"Retrying connection in {backoff_time} seconds (attempt {self.reconnect_attempts})")
                    await asyncio.sleep(backoff_time)
                    await self._connect()
                
                else:
                    logger.error("Max reconnection attempts reached")
                    self.is_connected_flag = False
                    raise
    
    async def _subscribe_to_tables(self) -> None:
        """Subscribe to depot_manager_new_records table for INSERT events only"""
        if not self.supabase:
            logger.error("Supabase client not initialized")
            return
        
        # Subscribe to the depot_manager_new_records table only
        for table in self.tables:
            table_name = table.strip()
            if not table_name:
                continue
                
            try:
                logger.info(f"Subscribing to table: {table_name}")

                # Create channel for the table
                channel = self.supabase.channel(f"realtime:{table_name}")

                # Create callback function for this specific table
                def create_callback(table_name: str) -> Callable:
                    def callback(payload: Dict[str, Any]) -> None:
                        try:
                            logger.info(f"Received realtime INSERT event for {table_name}: {payload.get('eventType', 'unknown')}")
                            if payload.get('eventType') == 'INSERT':
                                record = payload.get('new', {})
                                # Create task to handle the async callback with proper management
                                task = asyncio.create_task(self.bot._handle_new_record(table_name, record))
                                self._background_tasks.add(task)
                                task.add_done_callback(self._background_tasks.discard)
                        except Exception as e:
                            logger.error(f"Error processing callback for {table_name}: {e}")
                    return callback
                
                # Subscribe to Insert events only
                channel.on_postgres_changes(
                    event="INSERT",
                    schema="public",
                    table=table_name,
                    callback=create_callback(table_name)
                )

                # Subscribe to the channel
                response = await channel.subscribe()
                logger.info(f"Channel subscription response for {table_name}: {response}")
                
                # Store channel reference
                self.channels[table_name] = channel
                logger.info(f"Successfully subscribed to table: {table_name}")
            
            except Exception as e:
                logger.error(f"Failed to subscribe to table {table_name}: {e}", exc_info=True)

    def is_connected(self) -> bool:
        """Check if realtime client is connected"""
        return self.is_connected_flag and self.supabase is not None
    
    async def reconnect(self) -> None:
        """Reconnect to Supabase realtime"""
        try:
            logger.info("Attempting to reconnect realtime listener")
            await asyncio.sleep(2)  # Brief pause before reconnecting
            await self.initialize()
        except Exception as e:
            logger.error(f"Failed to reconnect realtime listener: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the realtime connection"""
        try:
            if not self.is_connected():
                logger.debug("Health check failed: not connected")
                return False
            
            if not self.supabase:
                logger.debug("Health check failed: no supabase client")
                return False
            
            # Check if we have active subscriptions
            if not self.channels:
                logger.debug("Health check failed: no active channels")
                return False
            
            # Test basic client functionality
            try:
                # Just check if the client object exists and has the expected methods
                has_required_methods = (
                    hasattr(self.supabase, 'table') and 
                    hasattr(self.supabase, 'channel')
                )
                if not has_required_methods:
                    logger.debug("Health check failed: client missing required methods")
                    return False
                
                logger.debug(f"Health check passed: {len(self.channels)} active channels")
                return True
                
            except Exception as e:
                logger.debug(f"Health check failed during client test: {e}")
                return False
            
        except Exception as e:
            logger.warning(f"Health check failed with exception: {e}")
            return False
            
    async def _background_reconnect(self) -> None:
        """Background task to periodically attempt reconnection if initial connection failed"""
        max_attempts = 20
        current_attempt = 0
        
        while current_attempt < max_attempts:
            try:
                # Wait with exponential backoff (max 5 minutes)
                wait_time = min(30 * (2 ** current_attempt), 300)
                logger.info(f"Will retry realtime connection in {wait_time} seconds (attempt {current_attempt + 1}/{max_attempts})")
                await asyncio.sleep(wait_time)
                
                # Attempt reconnection
                logger.info(f"Attempting background reconnection to Supabase realtime (attempt {current_attempt + 1}/{max_attempts})")
                await self._connect()
                await self._subscribe_to_tables()
                
                logger.info("Background reconnection successful!")
                return  # Exit the loop on successful reconnection
                
            except Exception as e:
                current_attempt += 1
                logger.warning(f"Background reconnection attempt {current_attempt}/{max_attempts} failed: {e}")
                
        logger.error(f"All {max_attempts} background reconnection attempts failed")
        # At this point, the bot will continue running without realtime