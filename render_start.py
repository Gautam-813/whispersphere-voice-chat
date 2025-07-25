#!/usr/bin/env python3
"""
Render.com startup script for WhisperSphere
"""
import os
import uvicorn
import logging
from main import app

if __name__ == "__main__":
    # Get port from environment variable (Render provides this)
    port = int(os.environ.get("PORT", 8000))

    # Disable all logging for maximum privacy on Render
    logging.getLogger("uvicorn").setLevel(logging.CRITICAL)
    logging.getLogger("uvicorn.access").setLevel(logging.CRITICAL)
    logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
    logging.getLogger("fastapi").setLevel(logging.CRITICAL)

    # Run the app with silent operation
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="critical",  # Only critical errors
        access_log=False       # Disable access logs for privacy
    )
