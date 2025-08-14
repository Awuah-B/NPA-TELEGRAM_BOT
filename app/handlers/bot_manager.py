#! /usr/bin/env python3
## File: bot_manager.py

"""
Group chat management for Telegram bot
Handles group subscriptions, admin management, and persistence.
"""
import json
import os
import re
from typing import Set, Dict, Optional
from pathlib import Path
from datetime import datetime

from exceptions import ValidationError
from app.utils.log_settings import setup_logging

logger = setup_logging('group_manager.log')

class GroupChatManager:
    """Enhanced group chat manager with validation and persistence"""
    def __init__(self, storage_file: str = "group_subscriptions.json"):
        self.storage_file = Path(storage_file)
        self.subscribed_groups: Set[str] = set()
        self.group_admins: Dict[str, Set[str]] = {}
        self.group_metadata: Dict[str, Dict] = {}

        # Ensure storage directory exists
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_subscriptions()

    def _load_subscriptions(self) -> None:
            """Load subscriptions from file with robust error handling"""
            try:
                if self.storage_file.exists():
                    with open(self.storage_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                        # Load subscribed groups
                        self.subscribed_groups = set(data.get('groups', []))

                        # Load group admins
                        admins_data = data.get('admins', {})
                        self.group_admins = {k: set(v) for k, v in admins_data.items()}

                        # Load group metadata
                        self.group_metadata = data.get('metadata', {})
                    
                    logger.info(f"Loaded {len(self.subscribed_groups)} subscribed groups from storage")
                else:
                    logger.info("No subscriptions file found, starting with empty subscriptions")
                
            except json.JSONDecodeError as e:
                logger.error(f"Corrupted subscriptions file: {e}. Backing up and starting fresh")
                self._backup_corrupted_file()
                self._initialize_empty_state()
            
            except Exception as e:
                logger.error(f"Failed to load subscriptions: {e}")
                self._initialize_empty_state()
    
    def _initialize_empty_state(self) -> None:
        """Initialize empty state"""
        self.subscribed_groups = set()
        self.group_admins = {}
        self.group_metadata = {}

    
    def _backup_corrupted_file(self) -> None:
        """Backup corrupted subscription file"""
        try:
            if self.storage_file.exists():
                backup_file = self.storage_file.with_suffix('.json.backup')
                self.storage_file.rename(backup_file)
                logger.info(f"Corrupted file backed up to {backup_file}")
        except Exception as e:
            logger.error(f"Failed to backup corrupted file: {e}")
    
    def _save_subscriptions(self) -> None:
        """Save subscriptions to file with atomic write"""
        try:
            # Prepare data
            data = {
                'groups': list(self.subscribed_groups),
                'admins': {k: list(v) for k, v in self.group_admins.items()},
                'metadata': self.group_metadata,
                'last_updated': str(datetime.now())
            }

            # Atomic write using temporary file
            temp_file = self.storage_file.with_suffix('.tmp')

            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Replace original file
            temp_file.replace(self.storage_file)

            logger.debug(f"Saved {len(self.subscribed_groups)} to subscriptions to storage")

        except Exception as e:
            logger.error(f"Failed to save subscriptions: {e}")
            # Clean up temp file if it exists
            temp_file = self.storage_file.with_suffix('.tmp')
            if temp_file.exists():
                temp_file.unlink()

    def subscribe_group(self, group_id: str, group_title: Optional[str] = None, 
                       subscribed_by: Optional[str] = None) -> bool:
        """
        ubscribe a group to notifications
        
        Args:
            group_id: Telegram group ID
            group_title: Optional group title
            subscribed_by: Optional user ID who subscribed the group
            
        Returns:
            True if successfully subscribed
        """
        if not self._validate_group_id(group_id):
            logger.warning(f"Invalid group ID format: {group_id}")
            return False
        
        # Add to subscribed groups
        self.subscribed_groups.add(group_id)

        # Update metadata
        if group_id not in self.group_metadata:
            self.group_metadata[group_id] = {}
        
        metadata = self.group_metadata[group_id]
        metadata['subscribed_at'] = str(datetime.now())

        if group_title:
            metadata['title'] = group_title
        if subscribed_by:
            metadata['subscribed_by'] = subscribed_by
        
        self._save_subscriptions()
        
        logger.info(f"Group {group_id} ({group_title}) subscribed successfully")
        return True
    
    def unsubscribe_group(self, group_id: str) -> bool:
        """
        Unsubscribe a group from notifications
        
        Args:
            group_id: Telegram group ID
            
        Returns:
            True if successfully unsubscribed
        """

        # Remove from subscribed groups
        self.subscribed_groups.discard(group_id)

        # Remove admin associations
        if group_id in self.group_admins:
            del self.group_admins[group_id]

        # Update metadata
        if group_id in self.group_metadata:
            self.group_metadata[group_id]['unsubscribed_at'] = str(datetime.now())
        
        self._save_subscriptions()

        logger.info(f"Group {group_id} unsubscribed successfully")
        return True
    
    def is_subscribed(self, group_id: str) -> bool:
        """
        Check if group is subscribed
        
        Args:
            group_id: Telegram group ID
            
        Returns:
            True if subscribed
        """
        return group_id in self.subscribed_groups
    
    def get_subscribed_groups(self) -> Set[str]:
        """Get copy of all subscribed groups"""
        return self.subscribed_groups.copy()
    
    def add_admin(self, group_id: str, user_id: str) -> None:
        """
        Add admin for a group
        
        Args:
            group_id: Telegram group ID
            user_id: Telegram user ID
        """
        if not self._validate_group_id(group_id):
            logger.warning(f"Invalid group ID format: {group_id}")
            return
        
        if not self._validate_user_id(user_id):
            logger.warning(f"Invalid user ID format: {user_id}")
            return
        
        if group_id not in self.group_admins:
            self.group_admins[group_id] = set()
        
        self.group_admins[group_id].add(user_id)
        self._save_subscriptions()

        logger.debug(f"Added admin {user_id} for group {group_id}")

    def remove_admin(self, group_id: str, user_id: str) -> bool:
        """
        Remove admin for a group
        
        Args:
            group_id: Telegram group ID
            user_id: Telegram user ID
            
        Returns:
            True if admin was removed
        """
        if group_id in self.group_admins and user_id in self.group_admins[group_id]:
            self.group_admins[group_id].discard(user_id)
            
            # Remove empty admin sets
            if not self.group_admins[group_id]:
                del self.group_admins[group_id]
            
            self._save_subscriptions()
            logger.debug(f"Removed admin {user_id} from group {group_id}")
            return True
        
        return False
    
    def is_admin(self, group_id: str, user_id: str) -> bool:
        """
        Check if user is admin for a group
        
        Args:
            group_id: Telegram group ID
            user_id: Telegram user ID
            
        Returns:
            True if user is admin for the group
        """
        return user_id in self.group_admins.get(group_id, set())
    
    def get_group_admins(self, group_id: str) -> Set[str]:
        """
        Get all admins for a group
        
        Args:
            group_id: Telegram group ID
            
        Returns:
            Set of admin user IDs
        """
        return self.group_admins.get(group_id, set()).copy()
    
    def get_group_metadata(self, group_id: str) -> Dict:
        """
        Get metadata for a group
        
        Args:
            group_id: Telegram group ID
            
        Returns:
            Group metadata dictionary
        """
        return self.group_metadata.get(group_id, {}).copy()
    
    def update_group_metadata(self, group_id: str, **metadata) -> None:
        """
        Update group metadata
        
        Args:
            group_id: Telegram group ID
            **metadata: Metadata key-value pairs to update
        """
        if group_id not in self.group_metadata:
            self.group_metadata[group_id] = {}
        
        self.group_metadata[group_id].update(metadata)
        self.group_metadata[group_id]['last_updated'] = str(datetime.now())
        
        self._save_subscriptions()
        logger.debug(f"Updated metadata for group {group_id}")
    
    def get_subscription_stats(self) -> Dict:
        """
        Get subscription statistics
        
        Returns:
            Dictionary with subscription statistics
        """
        total_admins = sum(len(admins) for admins in self.group_admins.values())
        
        return {
            'total_subscribed_groups': len(self.subscribed_groups),
            'total_group_admins': total_admins,
            'groups_with_metadata': len(self.group_metadata),
            'storage_file': str(self.storage_file),
            'storage_exists': self.storage_file.exists()
        }
    
    def cleanup_inactive_groups(self, active_group_ids: Set[str]) -> int:
        """
        Remove groups that are no longer active
        
        Args:
            active_group_ids: Set of currently active group IDs
            
        Returns:
            Number of groups cleaned up
        """
        inactive_groups = self.subscribed_groups - active_group_ids
        
        for group_id in inactive_groups:
            self.unsubscribe_group(group_id)
        
        if inactive_groups:
            logger.info(f"Cleaned up {len(inactive_groups)} inactive groups")
        
        return len(inactive_groups)
    
    def export_subscriptions(self, export_file: str) -> bool:
        """
        Export subscriptions to a file
        
        Args:
            export_file: Path to export file
            
        Returns:
            True if export successful
        """
        try:
            export_data = {
                'subscribed_groups': list(self.subscribed_groups),
                'group_admins': {k: list(v) for k, v in self.group_admins.items()},
                'group_metadata': self.group_metadata,
                'export_timestamp': str(datetime.now()),
                'stats': self.get_subscription_stats()
            }
            
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported subscriptions to {export_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export subscriptions: {e}")
            return False
    
    def _validate_group_id(self, group_id: str) -> bool:
        """Validate Telegram group ID format"""
        if not group_id or not isinstance(group_id, str):
            return False
        
        # Telegram group IDs are negative integers
        try:
            gid = int(group_id)
            return gid < 0
        except ValueError:
            return False
    
    def _validate_user_id(self, user_id: str) -> bool:
        """Validate Telegram user ID format"""
        if not user_id or not isinstance(user_id, str):
            return False
        
        # Telegram user IDs are positive integers
        try:
            uid = int(user_id)
            return uid > 0
        except ValueError:
            return False
    

    

    


    


        



    


    



        







        



        



               






