"""
Configuration management for NPA Monitor Bot
Centralized configuration with validation and environment handling.
"""
import os
from enum import Enum
from typing import List, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv

from exceptions import ConfigurationError

load_dotenv()

class Environment(Enum):
    """Application environment types"""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"

@dataclass
class TelegramConfig:
    """Telegram bot configuration"""
    bot_token: str
    superadmin_ids: List[int] = field(default_factory=list)
    webhook_url: Optional[str] = None
    webhook_port: int = 8080

@dataclass
class SupabaseConfig:
    """Supabase database configuration"""
    url: str
    anon_key: str
    service_role_key: Optional[str] = None
    project_ref: Optional[str] = None



@dataclass
class APIConfig:
    """External API configuration"""
    url: str
    company_id: str
    its_from_persol: str
    group_by: str
    group_by1: str
    query1: str
    query4: str
    pic_height: str
    pic_weight: str
    period_id: str
    user_id: str
    app_id: str

@dataclass(frozen=True)
class MonitoringConfig:
    interval_seconds: int = int(os.getenv('MONITORING_INTERVAL_SECONDS', '120'))  # Match data pipeline
    cache_max_size: int = int(os.getenv('CACHE_MAX_SIZE', '1000'))
    cache_ttl_seconds: int = int(os.getenv('CACHE_TTL_SECONDS', '600'))
    buffer_timeout_seconds: float = float(os.getenv('BUFFER_TIMEOUT', '5'))
    max_notification_records: int = int(os.getenv('MAX_NOTIFICATION_RECORDS', '5'))
    max_retries: int = int(os.getenv('MAX_RETRIES', '3'))
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')
    # Only monitor tables that actually have new_records detection in the data pipeline
    tables: List[str] = field(default_factory=lambda: ['depot_manager_new_records', 'approved_new_records'])
    # Data pipeline cleanup time - bot should expect data clearing
    pipeline_cleanup_time: str = os.getenv('PIPELINE_TABLE_CLEANUP_TIME', '23:00')
    # Pipeline run interval - should match data pipeline interval
    pipeline_interval: int = int(os.getenv('PIPELINE_INTERVAL', '120'))

class Config:
    """Main configuration class"""
    
    def __init__(self):
        self.env = Environment(os.getenv('ENVIRONMENT', 'production'))
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from environment variables"""
        try:
            self.telegram = TelegramConfig(
                bot_token=self._get_required_env('TELEGRAM_BOT_TOKEN'),
                superadmin_ids=self._parse_int_list(
                    self._get_required_env('TELEGRAM_SUPERADMIN_IDS')
                ),
                webhook_url=os.getenv('TELEGRAM_WEBHOOK_URL'),
                webhook_port=int(os.getenv('TELEGRAM_WEBHOOK_PORT', '8080'))
            )
            
            self.supabase = SupabaseConfig(
                url=self._get_required_env("SUPABASE_URL"),
                anon_key=self._get_required_env("SUPABASE_ANON_KEY"),
                service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
                project_ref=os.getenv("SUPABASE_PROJECT_REF", "icwrgmmallhfkkhegmqw")
            )
            
            self.api = APIConfig(
                url=self._get_required_env('NPA_URL'),
                company_id=self._get_required_env('NPA_COMPANY_ID'),
                its_from_persol=self._get_required_env('NPA_ITS_FROM_PERSOL'),
                group_by=os.getenv('NPA_GROUP_BY', ''),
                group_by1=os.getenv('NPA_GROUP_BY1', ''),
                query1=os.getenv('NPA_QUERY1', ''),
                query4=os.getenv('NPA_QUERY4', ''),
                pic_height=os.getenv('NPA_PIC_HEIGHT', '0'),
                pic_weight=os.getenv('NPA_PIC_WIDTH', '0'),
                period_id=os.getenv('NPA_PERIOD_ID', '1'),
                user_id=self._get_required_env('NPA_USER_ID'),
                app_id=self._get_required_env('NPA_APP_ID')
            )
            
            self.monitoring = MonitoringConfig(
                interval_seconds=int(os.getenv('MONITORING_INTERVAL_SECONDS', '120')),
                cache_max_size=int(os.getenv('CACHE_MAX_SIZE', '1000')),
                cache_ttl_seconds=int(os.getenv('CACHE_TTL_SECONDS', '600')),
                buffer_timeout_seconds=float(os.getenv('BUFFER_TIMEOUT', '5')),
                max_notification_records=int(os.getenv('MAX_NOTIFICATION_RECORDS', '5')),
                max_retries=int(os.getenv('MAX_RETRIES', '3')),
                log_level=os.getenv('LOG_LEVEL', 'INFO'),
                tables=os.getenv('MONITORING_TABLES', 'approved,brv_checked,good_standing,loaded,order_released,ordered,ppmc_cancel_order,marked,depot_manager,depot_manager_new_records,approved_new_records').split(',')
            )
            
            self._validate_config()
            self._validate_monitoring_config(self.monitoring)
            
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}")
    
    def _get_required_env(self, key: str) -> str:
        """Get required environment variable"""
        value = os.getenv(key)
        if not value:
            raise ConfigurationError(f"Required environment variable {key} is not set")
        return value
    
    def _parse_int_list(self, value: str) -> List[int]:
        """Parse comma-separated integer list"""
        try:
            return [int(x.strip()) for x in value.split(',') if x.strip()]
        except ValueError:
            raise ConfigurationError(f"Invalid integer list format: {value}")
    
    def _validate_config(self) -> None:
        """Validate configuration"""
        if not self.telegram.bot_token:
            raise ConfigurationError("Telegram bot token is required")
        
        if not self.telegram.superadmin_ids:
            raise ConfigurationError("At least one superadmin ID is required")
        
        if self.telegram.webhook_port <= 0:
            raise ConfigurationError("Webhook port must be a positive integer")
        
        if not self.supabase.url.startswith(('http://', 'https://')):
            raise ConfigurationError("Invalid Supabase URL format")
        
        if not self.supabase.anon_key:
            raise ConfigurationError("Supabase anonymous key is required")
        
        if self.supabase.project_ref and not self.supabase.project_ref.isalnum():
            raise ConfigurationError("Invalid Supabase project reference")
        
        if self.env == Environment.PRODUCTION and self.telegram.webhook_url:
            if not self.telegram.webhook_url.startswith('https://'):
                raise ConfigurationError("Webhook URL must use HTTPS in production")
    
    def _validate_monitoring_config(self, config: MonitoringConfig) -> None:
        """Validate monitoring configuration"""
        if config.interval_seconds <= 0:
            raise ConfigurationError("Monitoring interval must be positive")
        if config.cache_max_size <= 0:
            raise ConfigurationError("Cache max size must be positive")
        if config.cache_ttl_seconds <= 0:
            raise ConfigurationError("Cache TTL must be positive")
        if config.buffer_timeout_seconds <= 0:
            raise ConfigurationError("Buffer timeout must be positive")
        if config.max_notification_records <= 0:
            raise ConfigurationError("Max notification records must be positive")
        if config.log_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            raise ConfigurationError(f"Invalid log level: {config.log_level}")
        if not config.tables or any(not table.strip() for table in config.tables):
            raise ConfigurationError("At least one valid monitoring table is required")
        
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.env == Environment.PRODUCTION
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.env == Environment.DEVELOPMENT

# Global configuration instance
CONFIG = Config()