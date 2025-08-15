# Realtime Connection Troubleshooting Guide

## Issue: "UnableToBroadcastChanges: :payload_missing"

This error occurs when Supabase Realtime tries to broadcast changes but the payload data is missing or malformed.

## Root Causes and Solutions

### 1. **Missing or Invalid Payload Data**
**Symptoms:**
- `UnableToBroadcastChanges: :payload_missing` in Supabase logs
- Realtime callbacks not receiving data
- Empty or null payloads in callback functions

**Solutions Implemented:**
- Added comprehensive payload validation in `_validate_payload()` method
- Enhanced error handling in realtime callbacks
- Added fallback notification for malformed payloads

### 2. **Network Connectivity Issues**
**Symptoms:**
- Intermittent connection drops
- Websocket connection failures
- Timeout errors during subscription

**Solutions Implemented:**
- Enhanced SSL configuration for websockets
- Added timeout handling for subscription attempts
- Implemented exponential backoff for reconnection attempts
- Added connection health monitoring

### 3. **Race Conditions in Subscription Management**
**Symptoms:**
- Subscriptions failing randomly
- Channels not receiving events
- Multiple subscription attempts causing conflicts

**Solutions Implemented:**
- Added connection locks using `asyncio.Lock()`
- Improved subscription response validation
- Enhanced background task management

### 4. **Database Row-Level Security (RLS) Issues**
**Symptoms:**
- Realtime events not triggering for certain operations
- Payload data being filtered out
- Permission-related errors

**Solutions to Check:**
- Verify RLS policies allow realtime access
- Ensure service role key has proper permissions
- Check if anon key has sufficient privileges

## Code Changes Made

### 1. Enhanced Payload Validation
```python
def _validate_payload(self, payload: Dict[str, Any], table_name: str) -> bool:
    # Comprehensive validation of payload structure
    # Checks for required fields, data types, and content
```

### 2. Improved Error Handling
```python
def callback(payload: Dict[str, Any]) -> None:
    try:
        if not self._validate_payload(payload, table_name):
            return
        # Process valid payload
    except Exception as e:
        # Enhanced error reporting and recovery
```

### 3. Connection Health Monitoring
```python
async def _background_reconnect(self) -> None:
    # Automatic reconnection with proper error reporting
    # Notifies superadmins about connection status
```

### 4. Subscription Validation
```python
def _validate_subscription_response(self, response: Any, table_name: str) -> bool:
    # Validates subscription success before proceeding
```

## Testing and Verification

### Run the Payload Test Script
```bash
cd /Users/99ideas/deploy
python test_realtime_payload.py
```

This script will:
- Test various payload scenarios
- Validate the payload validation logic
- Identify potential issues with payload handling

### Monitor Logs
Key log files to monitor:
- `realtime.log` - Realtime connection and subscription logs
- `bot.log` - Main bot operations and error handling
- `notification.log` - Notification service operations

### Check Bot Status
Use the `/status` command to verify:
- Realtime connection status
- Background task health
- Subscription counts

## Prevention Strategies

### 1. **Regular Health Checks**
- Automated health monitoring every 30 seconds
- Connection validation before processing events
- Proactive reconnection on failures

### 2. **Graceful Degradation**
- Polling fallback when realtime is unavailable
- Continue bot operations even with realtime issues
- User notifications about system status

### 3. **Enhanced Logging**
- Detailed payload logging for debugging
- Error tracking with context
- Performance metrics monitoring

### 4. **Input Validation**
- Validate all incoming realtime data
- Sanitize record information before processing
- Handle edge cases gracefully

## Monitoring Commands

### Bot Management
- `/status` - Check overall bot health
- `/cache_status` - Monitor cache performance
- `/stats` - View operational statistics

### Troubleshooting
- Check Supabase dashboard for realtime logs
- Monitor websocket connection status
- Review database performance metrics

## When to Escalate

Contact system administrators if:
1. Realtime connection fails for > 10 minutes
2. Multiple consecutive subscription failures
3. Database connectivity issues persist
4. High error rates in payload processing

## Additional Notes

- The bot will continue operating with polling fallback even if realtime fails
- Superadmins are automatically notified of critical realtime issues
- All payload validation errors are logged for debugging
- Background reconnection attempts continue automatically

## Recent Improvements (Implemented)

1. ✅ Added comprehensive payload validation
2. ✅ Enhanced error handling and recovery
3. ✅ Improved connection monitoring
4. ✅ Added subscription response validation
5. ✅ Implemented graceful degradation
6. ✅ Enhanced notification error handling
7. ✅ Added test script for validation
8. ✅ Improved logging and debugging

The system should now be much more resilient to realtime payload issues and provide better error reporting and recovery.
