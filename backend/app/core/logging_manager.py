import logging
import os

class LoggingManager:
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        self.current_handler = None

    def setup_run_logging(self, run_id: str):
        self.cleanup_run_logging()
        log_file = os.path.join(self.log_dir, f"run_{run_id}.log")
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        self.current_handler = handler
        return log_file

    def cleanup_run_logging(self):
        if self.current_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self.current_handler)
            self.current_handler.close()
            self.current_handler = None

logging_manager = LoggingManager()
