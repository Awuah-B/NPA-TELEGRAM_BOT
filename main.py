
import os
import json
import asyncio
import gc
import psutil
import platform
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from telegram import Update
from app.bot import NPAMonitorBot
from app.config import CONFIG
from app.utils.log_settings import setup_logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure garbage collection for better memory management
gc.set_threshold(700, 10, 5)  # More aggressive garbage collection
gc.enable()  # Ensure garbage collection is enabled

logger = setup_logging('webhook.log')

bot_instance = None

def log_memory_usage(context=""):
    """Log detailed memory usage information"""
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        
        # Calculate memory in different formats
        memory_mb = memory_info.rss / 1024 / 1024
        memory_percent = process.memory_percent()
        
        # Get Python GC statistics
        gc_counts = gc.get_count()
        gc_threshold = gc.get_threshold()
        
        # Log basic memory info
        logger.info(f"Memory usage {context}: {memory_mb:.1f} MB ({memory_percent:.1f}%)")
        
        # Log detailed memory info
        logger.info(f"Memory details: RSS={memory_info.rss/1024/1024:.1f}MB, "
                   f"VMS={memory_info.vms/1024/1024:.1f}MB, "
                   f"Shared={getattr(memory_info, 'shared', 0)/1024/1024:.1f}MB")
        
        # Log GC info
        logger.info(f"GC stats: counts={gc_counts}, thresholds={gc_threshold}")
        
        # Return memory usage in MB for use in health endpoints
        return memory_mb
    except Exception as e:
        logger.warning(f"Could not get memory info: {e}")
        return 0

async def initialize_bot():
    global bot_instance
    if bot_instance is None:
        try:
            log_memory_usage("before bot initialization")
            
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not token:
                logger.error("TELEGRAM_BOT_TOKEN is not set - bot cannot be initialized")
                return False
            
            # Clean the token to remove any newlines or whitespace
            token = token.strip().replace('\n', '').replace('\r', '')
            if not token:
                logger.error("TELEGRAM_BOT_TOKEN is empty after cleaning - bot cannot be initialized")
                return False
            
            logger.info(f"Initializing bot with token: {token[:10]}...")
            
            # Force garbage collection before initialization
            gc.collect()
            log_memory_usage("after garbage collection")
            
            logger.info("Creating NPAMonitorBot instance...")
            bot_instance = NPAMonitorBot()
            log_memory_usage("after bot instance creation")
            
            logger.info("Starting bot initialization process...")
            await bot_instance.initialise()
            log_memory_usage("after bot initialization")
            
            # Verify bot is properly initialized
            if bot_instance.is_initialized():
                logger.info("✅ Bot initialization successful!")
                
                # Force garbage collection after initialization
                gc.collect()
                log_memory_usage("after post-init garbage collection")
                
                # Always start the bot's run method to ensure application is started
                webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL")
                if not webhook_url:
                    # Create and track the bot task
                    bot_task = asyncio.create_task(bot_instance.run())
                    # Store the task reference to prevent it from being garbage collected
                    bot_instance._main_task = bot_task
                    logger.info("Bot task created successfully for polling mode")
                else:
                    # For webhook mode, just start the application without polling
                    bot_task = asyncio.create_task(bot_instance.run())
                    bot_instance._main_task = bot_task
                    logger.info("Bot task created successfully for webhook mode")
                
                return True
            else:
                logger.error("❌ Bot initialization failed - bot is not in initialized state")
                bot_instance = None
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize bot: {e}", exc_info=True)
            # Don't raise HTTPException during startup - let FastAPI start anyway
            bot_instance = None
            # Force cleanup on failure
            gc.collect()
            return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start bot initialization in background to avoid blocking startup
    log_memory_usage("at application startup")
    logger.info("🚀 FastAPI application starting - starting bot initialization in background")
    
    # Start bot initialization as a background task to avoid blocking startup
    initialization_task = asyncio.create_task(initialize_bot_background())
    
    yield
    
    # Cancel initialization task during shutdown if still running
    if not initialization_task.done():
        logger.info("🛑 Cancelling bot initialization task during shutdown")
        initialization_task.cancel()
        try:
            await initialization_task
        except asyncio.CancelledError:
            pass
    
    # Cleanup if needed
    if bot_instance:
        logger.info("🛑 Shutting down bot")
        try:
            # Cancel the main bot task if it exists
            if hasattr(bot_instance, '_main_task') and not bot_instance._main_task.done():
                logger.info("Cancelling bot main task...")
                bot_instance._main_task.cancel()
                try:
                    await bot_instance._main_task
                except asyncio.CancelledError:
                    logger.info("Bot main task cancelled successfully")
            
            # Shutdown the bot properly
            await bot_instance.shutdown()
            logger.info("✅ Bot shutdown completed")
        except Exception as e:
            logger.error(f"❌ Error during bot shutdown: {e}", exc_info=True)
    log_memory_usage("at application shutdown")

async def initialize_bot_background():
    """Initialize bot in background without blocking startup"""
    try:
        logger.info("🔄 Starting background bot initialization...")
        # Add a small delay to let the server start first
        await asyncio.sleep(2)
        
        success = await initialize_bot()
        if success:
            logger.info("✅ Background bot initialization completed successfully")
        else:
            logger.warning("⚠️ Background bot initialization failed - will retry on first request")
    except Exception as e:
        logger.error(f"💥 Background bot initialization error: {e}", exc_info=True)

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    """Simple root endpoint for basic connectivity test"""
    return {"message": "NPA Monitor Bot API", "status": "running"}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        # Check if bot is initialized
        if not bot_instance:
            logger.warning("⚠️ Bot not initialized, attempting emergency initialization...")
            log_memory_usage("before emergency bot initialization")
            success = await initialize_bot()
            if not success:
                logger.error("❌ Emergency bot initialization failed")
                return JSONResponse(
                    status_code=503,
                    content={"status": "error", "message": "Bot initialization failed"}
                )
            
        # Double-check bot is properly initialized
        if not bot_instance or not bot_instance.is_initialized():
            logger.error("❌ Bot initialization failed, rejecting webhook")
            return JSONResponse(
                status_code=503,
                content={"status": "error", "message": "Bot not ready"}
            )
        
        log_memory_usage("before processing webhook")
        data = await request.json()
        logger.info(f"📨 Received webhook update: {json.dumps(data, indent=2)}")
        update = Update.de_json(data, bot_instance.bot)
        if update:
            logger.info(f"🔄 Processing update ID: {update.update_id}")
            
            # Add detailed logging for debugging
            if update.message:
                logger.info(f"📝 Message received: text='{update.message.text}', chat_type='{update.message.chat.type}', user_id={update.message.from_user.id}")
                if update.message.text and update.message.text.startswith('/'):
                    logger.info(f"🎯 Command detected: '{update.message.text}'")
            
            await bot_instance.application.process_update(update)
            logger.info("✅ Update processed successfully")
            
            # Force garbage collection after processing
            gc.collect()
            log_memory_usage("after processing webhook")
            
            return {"status": "ok"}
        else:
            logger.warning("❌ Invalid update received")
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Invalid update"}
            )
    except Exception as e:
        logger.error(f"💥 Error processing webhook: {e}", exc_info=True)
        # Force garbage collection on error
        gc.collect()
        if "Unauthorized" in str(e):
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": str(e)}
            )
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.get("/health")
async def health_check():
    try:
        # Simple health check that doesn't depend on bot initialization
        memory_mb = log_memory_usage("during health check")
        health_status = {
            "status": "healthy",
            "memory_mb": memory_mb,
            "environment": os.getenv("ENVIRONMENT", "unknown"),
            "bot_running": bool(bot_instance),
            "bot_initialized": bot_instance.is_initialized() if bot_instance else False,
            "token_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "supabase_configured": bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        }
        if bot_instance:
            bot_health = await bot_instance.perform_health_check()
            health_status["bot_health"] = bot_health
            health_status["bot_stats"] = bot_instance.get_bot_stats()
        logger.info("Health check completed: healthy")
        return health_status
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "unhealthy", "error": str(e)}
        )

@app.get("/ready")
async def readiness_check():
    """Check if the bot is ready to handle requests"""
    try:
        if not bot_instance:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "message": "Bot instance not created"}
            )
        
        if not bot_instance.is_initialized():
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "message": "Bot not fully initialized"}
            )
        
        return {"status": "ready", "message": "Bot is ready to handle requests"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "error": str(e)}
        )

@app.post("/initialize")
async def manual_initialize():
    """Manually trigger bot initialization"""
    try:
        if bot_instance and bot_instance.is_initialized():
            return {"status": "already_initialized", "message": "Bot is already initialized"}
        
        logger.info("🔄 Manual bot initialization triggered")
        success = await initialize_bot()
        
        if success:
            return {"status": "success", "message": "Bot initialized successfully"}
        else:
            return JSONResponse(
                status_code=500,
                content={"status": "failed", "message": "Bot initialization failed"}
            )
            
    except Exception as e:
        logger.error(f"Manual initialization failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

    
    
    