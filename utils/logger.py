import logging
import os

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "voicebot.log")

# Create logger
logger = logging.getLogger("voicebot")
logger.setLevel(logging.INFO)

# Avoid adding duplicate handlers if they already exist
if not logger.handlers:
    # Console Handler
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.INFO)
    
    # File Handler
    f_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    f_handler.setLevel(logging.INFO)
    
    # Create formatters and add to handlers
    log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    c_handler.setFormatter(log_format)
    f_handler.setFormatter(log_format)
    
    # Add handlers to the logger
    logger.addHandler(c_handler)
    logger.addHandler(f_handler)

logger.info("Logging initialized. Writing to console and voicebot.log")
