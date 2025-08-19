# Deployment Guide - Realtime Payload Fixes

## ✅ Code Changes Summary

The following critical fixes have been implemented to address the "UnableToBroadcastChanges: :payload_missing" error:

### 🔧 Files Modified:
- `app/database/realtime.py` - Enhanced payload validation and error handling
- `app/bot.py` - Improved record processing and error recovery  
- `app/service/notification.py` - Better notification error handling

### 🛡️ Key Improvements:
1. **Comprehensive Payload Validation** - Prevents processing of malformed realtime payloads
2. **Enhanced Error Recovery** - Graceful handling of realtime connection issues
3. **Improved Monitoring** - Better health checks and reconnection logic
4. **Detailed Logging** - Enhanced debugging capabilities

## 🚀 Deployment Steps

### 1. Environment Configuration Required

Before deployment, you need to configure the `env.yaml` file with your actual values:

```yaml
TELEGRAM_WEBHOOK_URL: "https://your-service-url.run.app"
ENVIRONMENT: production
LOG_LEVEL: INFO
TELEGRAM_BOT_TOKEN: "your_bot_token"
TELEGRAM_SUPERADMIN_IDS: "your_user_id"
SUPABASE_URL: "https://your-project.supabase.co"
SUPABASE_SERVICE_ROLE_KEY: "your_service_role_key"
SUPABASE_ANON_KEY: "your_anon_key"
MONITORING_TABLES: "depot_manager_new_records,approved_new_records"
# ... other required variables
```

### 2. Deploy to Google Cloud Run

Once `env.yaml` is configured:

```bash
# Deploy using Cloud Build
gcloud builds submit --config cloudbuild.yaml

# Or build and deploy manually
docker build -t gcr.io/databaseinject/npa-monitor-bot:latest .
docker push gcr.io/databaseinject/npa-monitor-bot:latest

gcloud run deploy npa-monitor-bot \
  --image gcr.io/databaseinject/npa-monitor-bot:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --env-vars-file env.yaml \
  --memory 1Gi \
  --cpu 1 \
  --max-instances 10
```

### 3. Update Webhook (if using webhook mode)

After deployment, update your Telegram webhook:

```bash
# Get the service URL
SERVICE_URL=$(gcloud run services describe npa-monitor-bot --region=us-central1 --format="value(status.url)")

# Set webhook (replace YOUR_BOT_TOKEN)
curl -X POST "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"'$SERVICE_URL'/webhook"}'
```

## ✅ Verification Steps

### 1. Check Service Health
```bash
# Check if service is running
gcloud run services describe npa-monitor-bot --region=us-central1

# View logs
gcloud logs tail npa-monitor-bot --follow
```

### 2. Test Bot Commands
- Send `/status` to your bot
- Check for realtime connection status
- Verify error handling is working

### 3. Monitor for Payload Errors
- Check logs for improved error handling
- Verify no more "payload_missing" errors
- Confirm graceful degradation when realtime fails

## 🔍 What's Fixed

### Before (Issues):
❌ "UnableToBroadcastChanges: :payload_missing" errors  
❌ Bot crashes on malformed realtime payloads  
❌ Poor error recovery and reporting  
❌ Limited debugging information  

### After (Fixed):
✅ Comprehensive payload validation  
✅ Graceful error handling and recovery  
✅ Automatic reconnection with exponential backoff  
✅ Detailed error logging and superadmin notifications  
✅ Fallback polling when realtime fails  
✅ Enhanced connection monitoring  

## 📊 Monitoring

The improved system now provides:
- Real-time connection health monitoring
- Automatic error recovery and reconnection
- Detailed payload validation logging
- Superadmin notifications for critical issues
- Graceful degradation to polling mode

## 🚨 Important Notes

1. **Environment Configuration**: The `env.yaml` file must be properly configured before deployment
2. **Credentials**: Ensure all Supabase and Telegram credentials are valid
3. **Monitoring**: Check logs regularly during initial deployment
4. **Testing**: Use the test script `python3 test_realtime_payload.py` to validate improvements

The system is now much more resilient to realtime payload issues and will continue operating even when encountering the previous "payload_missing" errors.
