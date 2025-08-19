#!/bin/bash
# Quick Deployment Verification Script

echo "🔍 NPA Monitor Bot Deployment Verification"
echo "=========================================="

# Check Docker image
echo "📦 Docker Image Status:"
docker images npa-monitor-bot:test
echo ""

# Check if image was pushed to GCR
echo "☁️  Container Registry Status:"
gcloud container images list-tags gcr.io/smart-oasis-467912-a4/npa-monitor-bot --limit=1 --project=smart-oasis-467912-a4
echo ""

# Check Cloud Run services
echo "🚀 Cloud Run Services:"
gcloud run services list --project=smart-oasis-467912-a4 --region=us-central1
echo ""

# Check recent builds
echo "🔨 Recent Cloud Builds:"
gcloud builds list --limit=3 --project=smart-oasis-467912-a4
echo ""

echo "✅ Verification Complete!"
echo ""
echo "If the service is deployed, you can:"
echo "1. Get service URL: gcloud run services describe npa-monitor-bot --region=us-central1 --project=smart-oasis-467912-a4 --format='value(status.url)'"
echo "2. View logs: gcloud logs tail npa-monitor-bot --project=smart-oasis-467912-a4 --follow"
echo "3. Test bot: Send /status command to your Telegram bot"
