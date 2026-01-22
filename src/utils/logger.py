import logging

# Set up Python logging
logger = logging.getLogger("stablelab-logger")
logger.setLevel(logging.INFO)
logger.propagate = False  # Prevent duplicate logging from uvicorn's root handler

# Configure logging handler/format only if no handlers present
if not logger.handlers:
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s - [%(levelname)s] - %(name)s - %(funcName)s() - %(message)s"
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)