#! /usr/bin/env python3
## File: /database/connection.py

"""
Supabase connection management with pooling and retry logic
Handles database connections, connection pooling, and error recovery.
"""
import asyncio
from datetime import datetime
import aiohttp
import ssl
import certifi
from typing import Dict, Optional, AsyncGenerator, List
import contextlib

import pandas as pd

from app.config import CONFIG   
from app.utils.log_settings import setup_logging
from exceptions import DatabaseError, ConfigurationError

logger = setup_logging('database.log')


class SupabaseConnectionManager:
    """Manages Supabase connections with pooling and retry logic"""

    def __init__(self):
        self._connection_pool = []
        self._max_pool_size = 5
        self._connection_timeout = 60  
        self._retry_attempts = 5  
        self._retry_delay = 2  
        self._health_check_interval = 300  # 5mins
        self._background_tasks = set()
        self._start_background_tasks()

    def _start_background_tasks(self) -> None:
        """Start background monitoring tasks"""
        task = asyncio.create_task(self._connection_monitor())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
    
    async def _connection_monitor(self) -> None:
        """Background task to monitor connection health"""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self._health_check()
            except Exception as e:
                logger.error(f"Connection monitor error: {e}")
    
    async def _health_check(self) -> None:
        """Perform health check on database connection"""
        try:
            async with self.get_connection() as conn:
                # Create SSL context with proper certificate verification
                ssl_context = ssl.create_default_context(cafile=certifi.where())
                connector = aiohttp.TCPConnector(ssl=ssl_context)
                
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(
                        f"{conn['url']}/rest/v1/",
                        headers=conn['headers'],
                        timeout=aiohttp.ClientTimeout(total=self._connection_timeout)
                    ) as response:
                        if response.status == 404:
                            logger.warning(f"Health check failed with status {response.status} - Invalid URL")
                        elif response.status == 401:
                            logger.warning(f"Health check failed with status {response.status} - Authentication issue")
                        elif response.status != 200:
                            logger.warning(f"Health check failed with status {response.status}")
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
    
    @contextlib.asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[Dict, None]:
        """Acquire a connection with retry logic"""
        conn = None
        for attempt in range(self._retry_attempts):
            try:
                # Try to get from pool first
                if self._connection_pool:
                    conn = self._connection_pool.pop()
                    if self._is_connection_valid(conn):
                        yield conn
                        self._release_connection(conn)
                        return

                # Create new connection
                conn = await self._create_connection()
                yield conn
                self._release_connection(conn)
                return
            
            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < self._retry_attempts - 1:
                    await asyncio.sleep(self._retry_delay * (attempt + 1))
        
        raise DatabaseError(f"Failed to establish connection after {self._retry_attempts} attempts")
    
    async def _create_connection(self) -> Dict:
        """Create a new Supabase connection"""
        url = CONFIG.supabase.url
        key = CONFIG.supabase.service_role_key or CONFIG.supabase.anon_key

        if not url or not key:
            raise ConfigurationError("Missing Supabase credentials")
        
        headers = {
            'apikey': key,
            'Authorization': f"Bearer {key}",
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal'
        }
        
        # Test connection
        # Create SSL context with proper certificate verification
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(
                f"{url}/rest/v1/",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._connection_timeout)
            ) as response:
                # Supabase returns 401 without auth, 200 with auth, or 404 for invalid URLs
                if response.status == 404:
                    raise DatabaseError(f"Connection test failed with status {response.status} - Invalid URL")
                elif response.status == 401:
                    # 401 is expected without proper headers, but we have headers so this might indicate auth issue
                    logger.warning(f"Connection test returned 401 - checking if this is expected")
                elif response.status != 200:
                    raise DatabaseError(f"Connection test failed with status {response.status}")
                else:
                    logger.info("Connection test successful - SSL verification working correctly")
        
        return {
            'url': url,
            'headers': headers,
            'created_at': datetime.now(),
            'last_used': datetime.now()
        }
    
    def _is_connection_valid(self, conn: Dict) -> bool:
        """Check if connection is still valid"""
        # Check age (connections expire after 1 hour)
        age = datetime.now() - conn.get('created_at', datetime.now())
        return age.total_seconds() < 3600
    
    def _release_connection(self, conn: Dict) -> None:
        """Return connection to pool if space available"""
        if len(self._connection_pool) < self._max_pool_size and self._is_connection_valid(conn):
            conn['last_used'] = datetime.now()
            self._connection_pool.append(conn)

    async def close_all(self) -> None:
        """Cleanup all connections and background tasks"""
        for task in self._background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        # Clear connection pool
        self._connection_pool.clear()
        logger.info('All connections closed')

class LocalDatabaseConnection:
    pass

class SupabaseHandler:
    """Supabase database handler"""

    def __init__(self):
        self.conn_manager = SupabaseConnectionManager()
        self.table_names = [
            'approved', 'bdc_cancel_order', 'bdc_decline', 'brv_checked',
            'depot_manager', 'good_standing', 'loaded', 'order_released',
            'ordered', 'ppmc_cancel_order', 'depot_manager_decline', 'marked',
            'depot_manager_new_records', 'approved_new_records'
        ]
    
    async def make_request(self, method: str, endpoint: str, 
                           data: Optional[Dict] = None,
                           params: Optional[Dict] = None,
                           headers: Optional[Dict] = None) -> tuple[Optional[Dict], Optional[str]]:
        """Make request to Supabase API"""
        try:
            async with self.conn_manager.get_connection() as conn:
                url = f"{conn['url']}/rest/v1/{endpoint}"
                
                # Combine connection headers with any custom headers
                request_headers = conn['headers'].copy()
                if headers:
                    request_headers.update(headers)

                ssl_context = ssl.create_default_context(cafile=certifi.where())
                connector = aiohttp.TCPConnector(ssl=ssl_context)
                
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.request(
                        method,
                        url,
                        headers=request_headers,
                        json=data,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        
                        if 200 <= response.status < 300:
                            if response.status == 201 or response.status == 204: # No content
                                return {}, None
                            
                            # Special handling for count
                            if request_headers.get("Prefer") == "count=exact":
                                content_range = response.headers.get('Content-Range')
                                if content_range and '/' in content_range:
                                    return {'count': int(content_range.split('/')[1])}, None
                                return {'count': 0}, None

                            return await response.json(), None
                        else:
                            error_text = await response.text()
                            error_msg = f"Request failed for {method} {endpoint}: {response.status} - {error_text}"
                            logger.error(error_msg)
                            return None, error_msg

        except aiohttp.ClientError as e:
            error_msg = f"Request failed for {method} {endpoint}: {e}"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error during {method} request: {e}"
            logger.error(error_msg)
            return None, error_msg

    async def get_records(self, table: str, **filters) -> tuple[Optional[list], Optional[str]]:
        """Get records from a table with optional filters"""
        return await self.make_request('GET', table, params=filters)
    
    async def search_brv_number(self, brv_number: str) -> List[Dict]:
        """Search for records by BRV number across all tables"""
        try:
            results = []
            for table_name in self.table_names:
                params = {'brv_number': f'eq.{brv_number}'}
                result, error = await self.make_request('GET', table_name, params=params)
                
                if result and not error:
                    for record in result:
                        results.append({'table': table_name, 'data': record})
                    logger.info(f"Found {len(result)} records in {table_name} for BRV {brv_number}")
            
            logger.info(f"Found {len(results)} total records for BRV number {brv_number}")
            return results
        except Exception as e:
            logger.error(f"Failed to search BRV number {brv_number}: {str(e)}")
            return []

    async def get_table_stats(self) -> Dict[str, int]:
        """Get record counts for all tables"""
        try:
            stats = {}
            for table_name in self.table_names:
                headers = {'Prefer': 'count=exact'}
                result, error = await self.make_request('GET', table_name, params={'limit': '0'}, headers=headers)
                
                if not error and result is not None:
                    stats[table_name] = result.get('count', 0)
                else:
                    stats[table_name] = 0
            
            logger.info(f"Retrieved table statistics: {stats}")
            return stats
        except Exception as e:
            logger.error(f"Failed to get table stats: {str(e)}")
            return {table: 0 for table in self.table_names}

    async def get_total_volume_loaded(self) -> float:
        """Get the total volume for specified tables"""
        try:
            total_volume = 0.0
            volume_tables = ['marked', 'brv_checked', 'loaded', 'order_released']
            
            for table_name in volume_tables:
                try:
                    # Get all records from the table with volume data
                    params = {'select': 'volume'}
                    result, error = await self.make_request('GET', table_name, params=params)
                    
                    if not error and result:
                        # Sum up the volume values
                        for record in result:
                            volume = record.get('volume', 0)
                            if volume is not None:
                                try:
                                    total_volume += float(volume)
                                except (ValueError, TypeError):
                                    logger.warning(f"Invalid volume value in {table_name}: {volume}")
                                    continue
                    
                    logger.debug(f"Volume from {table_name}: calculated successfully")
                    
                except Exception as table_error:
                    logger.warning(f"Failed to get volume from {table_name}: {table_error}")
                    continue
            
            logger.info(f"Total volume calculated: {total_volume}")
            return total_volume
            
        except Exception as e:
            logger.error(f"Failed to calculate total volume: {str(e)}")
            return 0.0

    async def get_new_records(self, table_name: str) -> pd.DataFrame:
        """Fetch recent records from a specified table"""
        try:
            params = {
                'order': 'created_at.desc',
                'limit': '100'
            }
            result, error = await self.make_request('GET', table_name, params=params)
            
            if error or not result:
                logger.error(f"Failed to fetch recent records from {table_name}: {error}")
                return pd.DataFrame()
            
            logger.info(f"Fetched {len(result)} recent records from {table_name}")
            return pd.DataFrame(result)
        except Exception as e:
            logger.error(f"Failed to fetch recent records from {table_name}: {str(e)}")
            return pd.DataFrame()

    async def insert_record(self, table: str, data: Dict) -> tuple[Optional[Dict], Optional[str]]:
        """Insert a record into a table"""
        return await self.make_request('POST', table, data=data)
    
    async def update_record(self, table: str, record_id: int, data: Dict) -> tuple[Optional[Dict], Optional[str]]:
        """Update a record in a table"""
        return await self.make_request('PATCH', f"{table}?id=eq.{record_id}", data=data)
    
    async def delete_record(self, table: str, filters: Dict) -> tuple[Optional[Dict], Optional[str]]:
        """Delete a record from a table"""
        return await self.make_request('DELETE', f"{table}", params=filters)
    
    async def close(self) -> None:
        """Close handler and cleanup connections"""
        await self.conn_manager.close_all()