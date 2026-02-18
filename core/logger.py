import json
import logging
import sys
import time
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """
    A custom logging formatter that outputs log records in JSON format.
    Includes timestamp, level, message, logger name, file, line number, process ID, and thread ID.
    Also captures any extra attributes passed to the log record.
    """
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.datefmt = "%Y-%m-%dT%H:%M:%S%z" if datefmt is None else datefmt
        self.standard_fields = (
            "name", "levelname", "levelno", "pathname", "lineno", 
            "asctime", "msecs", "relativeCreated", "created", 
            "thread", "threadName", "process", "processName", 
            "message", "exc_info", "exc_text", "stack_info"
        )

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        if datefmt is None:
            datefmt = self.datefmt
        if '%z' in datefmt and hasattr(ct, 'tm_zone') and ct.tm_zone:
            return time.strftime(datefmt, ct)
        return time.strftime(datefmt, ct)

    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "file": record.pathname.split('/')[-1] if record.pathname else None,
            "line": record.lineno,
            "process_id": record.process,
            "thread_id": record.thread,
        }

        for key, value in record.__dict__.items():
            if key not in self.standard_fields:
                try:
                    json.dumps(value)
                    log_record[key] = value
                except (TypeError, OverflowError):
                    log_record[key] = str(value)
        
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_record)

def setup_logger(name="btc_alerts"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = JSONFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger

logger = setup_logger()
