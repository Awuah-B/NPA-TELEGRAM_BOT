# Deployment Guide

This guide covers deploying the NPA Monitor Bot to Google Cloud Run.

## Prerequisites

- Google Cloud SDK installed and configured
- Docker installed (if building locally)
- Supabase project set up with required tables
- Telegram bot token from @BotFather

## Setup Steps

### 1. Environment Configuration

1. Copy the environment template:
   ```bash
   cp .env.example .env
   cp env.yaml.example env.yaml
   cp group_subscriptions.json.example group_subscriptions.json
   ```

2. Edit `.env` for local development with your actual values:
   - Get `TELEGRAM_BOT_TOKEN` from [@BotFather](https://t.me/botfather)
   - Get Supabase credentials from your Supabase dashboard
   - Set your Telegram user ID as `TELEGRAM_SUPERADMIN_IDS`

3. Edit `env.yaml` for Cloud Run deployment with the same values

4. Configure `group_subscriptions.json` with your Telegram group IDs

### 2. Supabase Setup

Ensure your Supabase project has these tables:
- `depot_manager_new_records`
- `approved_new_records`
- Other tables as needed (configured in `MONITORING_TABLES`)

Required columns:
- `id` (primary key)
- `record_hash` (text, for deduplication)
- Timestamp columns for filtering
- Data columns specific to your use case

### 3. Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py
```

Test the bot in Telegram to ensure everything works.

### 4. Google Cloud Deployment

1. **Enable required APIs**:
   ```bash
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable run.googleapis.com
   ```

2. **Set your project**:
   ```bash
   gcloud config set project YOUR_PROJECT_ID
   ```

3. **Deploy using Cloud Build**:
   ```bash
   gcloud builds submit --config cloudbuild.yaml
   ```

4. **Configure webhook** (optional):
   If using webhooks, update `TELEGRAM_WEBHOOK_URL` in `env.yaml` with your Cloud Run service URL.

### 5. Verification

1. Check that the Cloud Run service is running
2. Test bot commands in Telegram
3. Monitor logs: `gcloud logs tail cloud-run-service-name`

## Configuration Options

### Webhook vs Polling

- **Webhook Mode**: Set `TELEGRAM_WEBHOOK_URL` for production deployment
- **Polling Mode**: Leave `TELEGRAM_WEBHOOK_URL` empty for local development

### Monitoring Tables

Configure which tables to monitor in the `MONITORING_TABLES` environment variable:
```
MONITORING_TABLES=depot_manager,approved,bdc_cancel_order,bdc_decline,brv_checked,good_standing,loaded,order_released,ordered,ppmc_cancel_order,depot_manager_decline,marked
```

### Performance Tuning

Adjust these values in your configuration:
- `LOG_LEVEL`: INFO for production, DEBUG for development
- Cache TTL settings
- Monitoring intervals

## Troubleshooting

### Common Issues

1. **Bot not responding**:
   - Check Cloud Run logs
   - Verify environment variables
   - Ensure bot token is correct

2. **Database connection errors**:
   - Verify Supabase credentials
   - Check network connectivity
   - Ensure tables exist

3. **Webhook issues**:
   - Verify webhook URL is accessible
   - Check Cloud Run service health
   - Monitor Cloud Run logs

### Debugging

1. **Enable debug logging**:
   Set `LOG_LEVEL=DEBUG` in environment variables

2. **Check service health**:
   ```bash
   gcloud run services describe npa-monitor-bot --region=us-central1
   ```

3. **View logs**:
   ```bash
   gcloud logs tail cloud-run-service-name --follow
   ```

## Security Notes

- Never commit `.env`, `env.yaml`, or `group_subscriptions.json` files
- Rotate API keys regularly
- Use least-privilege access for service accounts
- Monitor access logs for suspicious activity

## Monitoring

The bot includes built-in health monitoring:
- Database connectivity checks
- Telegram API health checks
- Realtime subscription monitoring
- Automatic reconnection logic

Monitor the `/status` command output and Cloud Run logs for operational health.
