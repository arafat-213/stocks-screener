import logging
import os
from contextvars import ContextVar

# Context variable to store the current run_id in the current execution context (thread/task)
run_id_context: ContextVar[str] = ContextVar("run_id", default="")

class RunIDFilter(logging.Filter):
    """
    Filters log records based on the run_id in the current context.
    Only allows records that match the run_id this handler was created for.
    """
    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def filter(self, record):
        return run_id_context.get() == self.run_id

class LoggingManager:
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def setup_run_logging(self, run_id: str):
        """
        Sets up logging for a specific run. 
        Uses a context-aware filter to ensure logs only go to the correct file.
        Returns the handler to be removed later.
        """
        # Set the context for the current thread/task
        run_id_context.set(run_id)
        
        log_file = os.path.join(self.log_dir, f"run_{run_id}.log")
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)
        
        # Add the filter to THIS handler so it only captures logs for THIS run_id
        handler.addFilter(RunIDFilter(run_id))
        
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        
        return handler

    def cleanup_run_logging(self, handler):
        """
        Removes the specific handler from the root logger.
        """
        if handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(handler)
            handler.close()
            # Clear context
            run_id_context.set("")

logging_manager = LoggingManager()
