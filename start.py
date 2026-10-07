import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("railway_entrypoint")

if __name__ == "__main__":
    raw_port = os.environ.get("PORT", "8000")
    try:
        port = int(raw_port)
    except (ValueError, TypeError):
        logger.warning(f"Invalid PORT env '{raw_port}', falling back to port 8000")
        port = 8000

    host = os.environ.get("HOST", "0.0.0.0")
    logger.info(f"Initializing FastAPI server on host {host} and port {port}...")

    import uvicorn
    uvicorn.run("src.api.main:app", host=host, port=port, log_level="info")
