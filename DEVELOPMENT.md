# Development Guide

## Quick Start

1. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd npa-monitor-bot
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   cp group_subscriptions.json.example group_subscriptions.json
   # Edit these files with your actual values
   ```

3. **Run locally**:
   ```bash
   python main.py
   ```

## Project Structure

```
npa-monitor-bot/
├── app/
│   ├── bot.py              # Main bot class
│   ├── config.py           # Configuration management
│   ├── database/           # Database layer
│   │   ├── connection.py   # Supabase connection
│   │   ├── cache.py        # Caching system
│   │   └── realtime.py     # Realtime subscriptions
│   ├── handlers/           # Bot handlers
│   │   ├── commands.py     # Command handlers
│   │   ├── events.py       # Event handlers
│   │   └── bot_manager.py  # Group management
│   ├── service/            # Business logic
│   │   ├── notification.py # Notification service
│   │   ├── pdf_generator.py# PDF generation
│   │   └── data_fetcher.py # Data fetching
│   └── utils/              # Utilities
│       ├── decorators.py   # Custom decorators
│       ├── helper.py       # Helper functions
│       └── log_settings.py # Logging setup
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── Dockerfile             # Docker configuration
├── cloudbuild.yaml        # Google Cloud Build config
├── .env.example           # Environment template
└── README.md              # Documentation
```

## Development Workflow

### Code Style

- Follow PEP 8 guidelines
- Use type hints where appropriate
- Add docstrings for classes and functions
- Keep functions focused and modular

### Testing

```bash
# Test bot locally
python main.py

# Test specific commands in Telegram
/start
/status
/help
```

### Adding New Features

1. **New Commands**:
   - Add handler in `app/handlers/commands.py`
   - Register in `app/bot.py`
   - Update help text

2. **New Services**:
   - Create service class in `app/service/`
   - Follow existing patterns
   - Add proper error handling

3. **Database Changes**:
   - Update connection logic in `app/database/`
   - Test with Supabase
   - Update configuration if needed

### Environment Variables

Required for development:
- `TELEGRAM_BOT_TOKEN` - Bot token from @BotFather
- `TELEGRAM_SUPERADMIN_IDS` - Your Telegram user ID
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` - Service role key
- `SUPABASE_ANON_KEY` - Anonymous key

Optional:
- `LOG_LEVEL` - DEBUG for development
- `TELEGRAM_WEBHOOK_URL` - Leave empty for polling mode

### Common Tasks

#### Adding a New Command

1. Create handler function in `commands.py`:
   ```python
   async def new_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
       # Implementation here
       pass
   ```

2. Register in `bot.py`:
   ```python
   CommandHandler("new_command", self.command_handlers.new_command)
   ```

#### Adding Database Table Monitoring

1. Update `MONITORING_TABLES` in environment
2. Ensure table has required columns (`id`, `record_hash`)
3. Test realtime subscriptions

#### Debugging

1. Set `LOG_LEVEL=DEBUG` in `.env`
2. Check logs in console output
3. Use Telegram commands to test functionality
4. Monitor Supabase dashboard for database activity

### Performance Considerations

- Use caching appropriately
- Implement proper error handling
- Monitor memory usage
- Test with multiple concurrent users

### Deployment Testing

Before deploying:
1. Test all commands locally
2. Verify database connections
3. Check environment variable configuration
4. Test in a private Telegram group
