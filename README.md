# NPA Monitor Bot

A Telegram bot for monitoring the Ghana National Petroleum Authority (NPA) data pipeline and providing real-time notifications for petroleum distribution activities in Kumasi.

## Features

- **Real-time Monitoring**: Monitors multiple data tables for new records using Supabase realtime subscriptions
- **Telegram Bot Interface**: Interactive commands for data access and monitoring
- **AI-Powered Processing**: Natural language and speech message processing using Google Gemini AI
- **Multimodal Input**: Supports text, voice, and audio messages for command execution
- **PDF Generation**: Creates detailed reports with data visualizations
- **Group Management**: Supports multiple Telegram groups with admin controls
- **Caching System**: Intelligent caching for improved performance
- **Health Monitoring**: Built-in health checks and automatic reconnection
- **Cloud Deployment**: Ready for Google Cloud Run deployment

## Architecture

The bot is built with a modular architecture:

- **Bot Core** (`app/bot.py`): Main bot orchestration and lifecycle management
- **Database Layer** (`app/database/`): Supabase integration with caching and realtime subscriptions
- **Handlers** (`app/handlers/`): Command and event handlers for Telegram interactions
- **Services** (`app/service/`): Business logic for notifications, PDF generation, data fetching, and AI processing
- **Utils** (`app/utils/`): Logging, decorators, and helper functions

## Prerequisites

- Python 3.12+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Google Gemini API Key (from [Google AI Studio](https://makersuite.google.com/app/apikey))
- Supabase Project with appropriate tables
- Google Cloud account (for deployment)

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd npa-monitor-bot
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual configuration values
   ```

5. **Configure group subscriptions**:
   ```bash
   cp group_subscriptions.json.example group_subscriptions.json
   # Edit with your Telegram group IDs and admin user IDs
   ```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | Yes |
| `TELEGRAM_SUPERADMIN_IDS` | Comma-separated list of admin user IDs | Yes |
| `GEMINI_API_KEY` | Google Gemini API key for AI processing | Yes |
| `SUPABASE_URL` | Your Supabase project URL | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | Yes |
| `SUPABASE_ANON_KEY` | Supabase anonymous key | Yes |
| `MONITORING_TABLES` | Comma-separated list of tables to monitor | Yes |
| `TELEGRAM_WEBHOOK_URL` | Webhook URL (for production deployment) | No |
| `NPA_COMPANY_ID` | Your NPA company identifier | Yes |
| `NPA_GROUP_BY1` | Company name for filtering | Yes |

### Database Tables

The bot monitors these Supabase tables:
- `depot_manager_new_records` - New depot manager records
- `approved_new_records` - New approved records
- Other tables as configured in `MONITORING_TABLES`

Required table structure includes:
- `id` (primary key)
- `record_hash` (for deduplication)
- Timestamp fields for filtering
- Data fields specific to petroleum operations

## Usage

### Local Development

```bash
python main.py
```

### Available Commands

- `/start` - Initialize the bot and get welcome message
- `/help` - Display help information
- `/status` - Show bot status and statistics
- `/subscribe` - Subscribe group to notifications (admin only)
- `/unsubscribe` - Unsubscribe group from notifications (admin only)
- `/check` - Check for new records manually
- `/recent` - Show recent records
- `/stats` - Display detailed statistics
- `/volume` - Show volume analysis
- `/download_pdf` - Generate and download PDF report
- `/groups` - List subscribed groups (superadmin only)
- `/cache_status` - Show cache statistics
- `/clear_cache` - Clear cache (admin only)

### AI-Powered Features

The bot now supports natural language and speech processing:

**Text Messages:**
- Send natural language messages like "show me the help" or "check status"
- The bot uses Google Gemini AI to understand your intent and execute commands

**Voice/Audio Messages:**
- Send voice messages or audio files with spoken commands
- The bot transcribes your speech and executes the appropriate command
- Supports various audio formats (OGG, MP3, WAV)

**Examples:**
- Voice: *"Show me recent records"* → Executes `/recent`
- Text: *"What's the current status?"* → Executes `/status`
- Audio: *"Generate a PDF report"* → Executes `/download_pdf`

### Group Management

1. Add the bot to your Telegram group
2. Make the bot an administrator
3. Use `/subscribe` command to start receiving notifications
4. Configure group admins in `group_subscriptions.json`

## Deployment

### Google Cloud Run

1. **Configure deployment files**:
   ```bash
   cp env.yaml.example env.yaml
   # Edit env.yaml with your configuration
   ```

2. **Build and deploy**:
   ```bash
   gcloud builds submit --config cloudbuild.yaml
   ```

3. **Set up webhook** (optional):
   The bot will automatically configure webhooks when `TELEGRAM_WEBHOOK_URL` is set.

### Docker

```bash
docker build -t npa-monitor-bot .
docker run --env-file .env -p 8080:8080 npa-monitor-bot
```

## Monitoring and Logging

The bot includes comprehensive logging and monitoring:

- **Health Checks**: Automatic database and API health monitoring
- **Reconnection Logic**: Automatic reconnection for realtime subscriptions
- **Cache Management**: Intelligent cache cleanup and statistics
- **Error Handling**: Robust error handling with admin notifications

Logs are organized by component:
- `logs/bot.log` - Main bot operations
- `logs/database.log` - Database operations
- `logs/realtime.log` - Realtime subscription events
- Additional component-specific logs

## API Integration

### Google Gemini AI
The bot integrates with Google Gemini AI for natural language and speech processing:
- **Text Processing**: Understands natural language commands and intents
- **Speech Recognition**: Transcribes audio messages and extracts commands
- **Multimodal Support**: Handles both text and audio inputs seamlessly
- **Fallback Models**: Automatic fallback to available Gemini models

### NPA API
The bot integrates with the NPA Enterprise API for fetching petroleum data:
- Daily order reports
- Volume analysis
- Company-specific filtering

### Supabase Realtime
Uses Supabase realtime subscriptions for instant notifications:
- WebSocket connections for low-latency updates
- Automatic reconnection and health monitoring
- Support for multiple table monitoring

## Performance

- **Caching**: Intelligent caching reduces API calls and improves response times
- **Connection Pooling**: Efficient database connection management
- **Background Tasks**: Non-blocking background processing
- **Resource Management**: Proper cleanup and resource management

## Security

- **Token Management**: Secure handling of API tokens and keys
- **Admin Controls**: Role-based access for sensitive operations
- **Input Validation**: Comprehensive input validation and sanitization
- **Error Handling**: Secure error handling without information leakage

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue in the GitHub repository
- Contact the development team

## Changelog

### Version 1.1.0 (Latest)
- **AI Integration**: Added Google Gemini AI for natural language processing
- **Speech Recognition**: Support for voice and audio message processing
- **Multimodal Input**: Bot now accepts text, voice, and audio commands
- **Enhanced User Experience**: Natural language command understanding
- **Improved Error Handling**: Better fallback mechanisms for AI processing
- **Model Fallback**: Automatic fallback to available Gemini models

### Version 1.0.0
- Initial release with core monitoring functionality
- Telegram bot interface with comprehensive commands
- Real-time monitoring with Supabase integration
- PDF report generation
- Google Cloud Run deployment support
- Comprehensive logging and health monitoring
