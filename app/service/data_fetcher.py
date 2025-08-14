#! /usr/bin/env python3
## File: /data_fetcher.py

"""
Data fetch component for NPA API.
"""
import asyncio 
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any, Callable
from io import BytesIO
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass
import random

import aiohttp
from aiohttp import ClientTimeout, ClientResponse
import pandas as pd


from app.config import CONFIG
from app.utils.log_settings import setup_logging # custom logging

logger = setup_logging('fetcher.log')
 
@dataclass
class FetchResult:
    """Result of a fetch operation"""
    data: Optional[pd.DataFrame] = None
    error: Optional[str] = None
    

class DataFetcherError(Exception):
    """Custom exception for DataFetcher operations"""
    pass


class DataFetcher:
    """Handles data fetching from NPA API"""

    def __init__(self, config=None, logger=None):
        """Initialize DataFetcher with dependency injection"""
        self.config = config or CONFIG
        if self.config is None:
            raise DataFetcherError("Configuration is required")
        
        # Use the module-level logger if none is provided
        self.logger = logger or globals().get('logger')
        if self.logger is None:
        # Fallback: create a new logger if somehow the module-level one doesn't exist
            self.logger = setup_logging('fetcher.log')
            
        self.today = datetime.now()
        self.yesterday = self.today - timedelta(days=1)
        self.date_format = "%d-%m-%Y"
        self.timeout = ClientTimeout(total=self.config.monitoring.buffer_timeout_seconds)
        self.max_retries = self.config.monitoring.max_retries
        # Initialize stats
        self.stats = {
            'successful_requests': 0,
            'failed_requests': 0,
            'total_requests': 0
        }


    async def fetch_data(self, progress_callback: Optional[Callable] = None) -> FetchResult:
        """
        Fetch data from NPA 
        Args:
            progress_callback: Optional callback function for progress updates
        Returns:
            FetchResult with data or error information
        """
        for attempt in range(self.max_retries):
            try:
                if progress_callback:
                    progress_callback(f"Attempting to fetch data ({attempt + 1}/{self.max_retries})")
                
                result =  await self._fetch_data_single()

                if result.data is not None:
                    self.stats['successful_requests'] += 1
                    self.stats['total_requests'] += 1
                    return result
                else:
                    self.logger.warning(f"Failed attempt {attempt + 1}: {result.error}")
                    # If this is the last attempt, return the error
                    if attempt == self.max_retries - 1:
                        self.stats['failed_requests'] += 1
                        self.stats['total_requests'] += 1
                        return result
                    # Otherwise, continue to next attempt
                    await self._exponential_backoff(attempt)
            
            except asyncio.TimeoutError:
                error_msg = f"API request time out (attempt {attempt + 1})"
                self.logger.warning(error_msg)
                if attempt == self.max_retries -1:
                    self.stats['failed_requests'] += 1
                    self.stats['total_requests'] += 1
                    return FetchResult(error=error_msg)
                await self._exponential_backoff(attempt)
            
            except aiohttp.ClientError as e:
                error_msg = f"HTTP client error: {str(e)} (attempt {attempt + 1})"
                self.logger.error(error_msg)
                if attempt == self.max_retries - 1:
                    self.stats['failed_requests'] += 1
                    self.stats['total_requests'] += 1
                    return FetchResult(error=error_msg)
                await self._exponential_backoff(attempt)

            except Exception as e:
                error_msg = f"Unexpected error: {str(e)} (attempt {attempt + 1})"
                self.logger.error(error_msg)
                self.logger.debug(traceback.format_exc())
                if attempt == self.max_retries - 1:
                    self.stats['failed_requests'] += 1
                    self.stats['total_requests'] += 1
                    return FetchResult(error=error_msg)
                await self._exponential_backoff(attempt)
        
        # Fallback return if loop completes without returning
        self.stats['failed_requests'] += 1
        self.stats['total_requests'] += 1
        return FetchResult(error="All retry attempts failed")
    
    def get_stats(self) -> Dict[str, int]:
        """Get current statistics"""
        return self.stats.copy()
                
    async def _fetch_data_single(self) -> FetchResult:
        """Single fetch attempt"""
        params = self._build_api_params()
        headers = self._build_headers()
        url = str(self.config.api.url)

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                async with session.get(
                    url=url,
                    headers=headers,
                    params=params
                ) as response:
                    if response.status != 200:
                        return FetchResult(
                            error=f"HTTP {response.status}: {response.reason}"
                        )
                    
                    # Validate content type
                    content_type = response.headers.get('content-type', '').lower()
                    if 'excel' not in content_type and 'spreadsheet' not in content_type:
                        self.logger.warning(f"Unexpected content type: {content_type}")

                    content = await response.read()

                if not content:
                    return FetchResult(
                            error="Empty response from API"
                        )
                
                try:
                    df = pd.read_excel(BytesIO(content))
                except Exception as e:
                    return FetchResult(
                            error=f"Failed to parse Excel data: {str(e)}"
                        )
                
                # Validate DataFrame
                if df.empty:
                    self.logger.warning("Received empty DataFrame from API")
                    return FetchResult(
                            error="Empty data received"
                        )
                # Basic data validation
                validation_result = self._validate_dataframe(df)
                if not validation_result['valid']:
                    return FetchResult(
                            error=f"Data validation failed: {validation_result['issues']}"
                        )
                return FetchResult(
                        data=df
                    )
            except aiohttp.ClientError as e:
                raise 
            except Exception as e:
                return FetchResult(error=f"Unexpected error during fetch: {str(e)}")

    def _build_api_params(self) -> dict:
        """Build API request parameters"""
        try:
            return{
                'lngCompanyId': self.config.api.company_id,
                'szITSfromPersol': self.config.api.its_from_persol,
                'strGroupBy': self.config.api.group_by,
                'strGroupBy1': self.config.api.group_by1,
                'strQuery1': self.config.api.query1,
                'strQuery2': self.yesterday.strftime(self.date_format),
                'strQuery3': self.today.strftime(self.date_format),
                'strQuery4': self.config.api.query4,
                'strPicHeight': self.config.api.pic_height,
                'strPicWeight': self.config.api.pic_weight,
                'intPeriodID': self.config.api.period_id,
                'iUserId': self.config.api.user_id,
                'iAppId': self.config.api.app_id
            }
        except AttributeError as e:
            raise DataFetcherError(f"Missing required configuration parameter: {str(e)}")

    def _build_headers(self) -> dict:
        """Build HTTP headers for API request"""
        return {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif, image/webp, image/apng, */*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
            'accept-encoding': 'gzip, deflate',
            'cache-control': 'no-cache'
        }
    
    def _validate_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate fetched DataFrame for basic quality checks"""
        issues = []
        warnings = []

        # Check for minimum columns
        if len(df.columns) < 5:
            issues.append("DataFrame has too few columns")
        
        # Check for completely empty columns
        empty_cols = df.columns[df.isnull().all()].tolist()
        if empty_cols:
            warnings.append(f"Empty columns found: {empty_cols}")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings
        }
    
    async def _exponential_backoff(self, attempt: int) -> None:
        """Implement exponential backoff with jitter"""
        base_delay = 2 ** attempt
        jitter = random.uniform(0.1, 0.3)
        delay = base_delay + jitter

        await asyncio.sleep(delay)


    async def process_data(self, fetch_result: FetchResult) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Process raw data from API 
        
        Args:
            fetch_result: Result from DataFetcher containing the DataFrame
            
        Returns:
            A tuple of  processed DataFrames and optional error message
            
        Raises:
            DataProcessorError: If processing fails
        """

        try:
            if fetch_result.error:
                raise DataFetcherError(f"Input data contains error: {fetch_result.error}")
                
            if fetch_result.data is None or fetch_result.data.empty:
                raise DataFetcherError("Empty DataFrame received for processing")

            # Clean and transform data
            cleaned_df = await self._clean_dataframe(fetch_result.data)
            if cleaned_df is None or cleaned_df.empty:
                raise DataFetcherError("No data remaining after cleaning")

            # Customize the dataframe structure
            customized_df = await self._customize_dataframe(cleaned_df)
            if customized_df is None or customized_df.empty:
                raise DataFetcherError("No data remaining after customization")
            
            return customized_df, None
            
        except Exception as e:
            logger.error(f"Error processing data: {str(e)}")
            logger.debug(traceback.format_exc())
            return None, f"Data processing failed: {str(e)}"

    async def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean raw DataFrame by removing headers, empty rows/columns, and filtering records
        
        Args:
            df: Raw DataFrame from API
            
        Returns:
            Cleaned DataFrame
        """
        try:
            # Remove header rows and convert to strings
            df = df.iloc[7:].copy()
            df = df.astype(str)
            df = df.replace('nan', '', regex=True)

            # Remove empty rows and columns
            df = df[~df.apply(lambda row: all(val.strip() == '' for val in row), axis=1)]
            df = df.loc[:, ~df.apply(lambda col: all(val.strip() == '' for val in col), axis=0)]

            # Remove total rows
            df = df[~df.apply(lambda row: any('#Total' in str(val) for val in row), axis=1)]

            # Filter for BOST-KUMASI records
            mask = df.apply(lambda row: any(
                "BOST-KUMASI" in val or "BOST - KUMASI" in val
                for val in row
            ), axis=1)
            
            # Include section headers
            section_head_mask = self._get_section_header_mask(df)
            mask = mask | section_head_mask
            
            if not mask.any():
                return None
                
            df = df[mask]
            return df
            
        except Exception as e:
            logger.error({str(e)})
            logger.debug(traceback.format_exc())
            raise

    async def _customize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Customize DataFrame structure by selecting and renaming columns
        
        Args:
            df: Cleaned DataFrame
            
        Returns:
            DataFrame with standardized column structure
        """
        try:
            # Drop unnecessary columns if they exist
            columns_to_drop = ['Unnamed: 6', 'Unnamed: 19', 'Unnamed: 20']
            df = df.drop(columns=[col for col in columns_to_drop if col in df.columns], errors='ignore')

            # Handle status duplication
            mask = self._get_section_header_mask(df)
            if mask.any():
                special_rows = df[mask].copy()
                # Keep only first occurrence of each value in the first column
                first_col = df.columns[0]
                special_rows = special_rows.drop_duplicates(subset=[first_col], keep='first')
                # Update the main DataFrame
                df = pd.concat([df[~mask], special_rows]).sort_index()

            # Select and rename columns
            column_mapping = {
                'Unnamed: 0': 'ORDER_DATE',
                'Unnamed: 2': 'ORDER_NUMBER',
                'Unnamed: 5': 'PRODUCTS',
                'Unnamed: 9': 'VOLUME',
                'Unnamed: 10': 'EX_REF_PRICE',
                'Unnamed: 12': 'BRV_NUMBER',
                'Unnamed: 15': 'BDC'
            }
            
            df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})
            self._convert_data_types(df)
            df = df.dropna(how='all')
            return df
            
        except Exception as e:
            logger.error({str(e)})
            logger.debug(traceback.format_exc())
            raise

    def _convert_data_types(self, df: pd.DataFrame) -> None:
        """Convert DataFrame columns to appropriate data types"""
        try:
            # Skip ORDER_DATE conversion as it contains mixed data types
            # Keeping it as string to preserve original format
            
            # Convert numeric columns
            numeric_columns = ['VOLUME', 'EX_REF_PRICE']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Convert string columns (strip whitespace)
            string_columns = ['ORDER_NUMBER', 'BRV_NUMBER', 'BDC', 'PRODUCTS']
            for col in string_columns:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()
                    
        except Exception as e:
            self.logger.warning(f"Error converting data types: {e}")

    def _get_section_header_mask(self, df: pd.DataFrame) -> pd.Series:
        """
        Identify section header rows in DataFrame
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Boolean mask indicating section header rows
        """
        first_col = df.columns[0]
        return df.apply(lambda row: (row != '').sum() == 1 and row[first_col] != '', axis=1)



                    










