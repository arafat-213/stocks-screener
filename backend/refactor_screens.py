import os
import glob
import re

SCREEN_DIR = "backend/app/screens"

def refactor_screens():
    for filepath in glob.glob(f"{SCREEN_DIR}/*.py"):
        if filepath.endswith("base.py") or filepath.endswith("cache.py") or filepath.endswith("materializer.py") or filepath.endswith("registry.py"):
            continue
            
        with open(filepath, "r") as f:
            content = f.read()
            
        # 1. Update function signatures
        content = re.sub(
            r"def (screen_\w+)\(db: Session, timeframe: str = 'D'\):",
            r"def \1(db: Session, timeframe: str = 'D', target_date=None):",
            content
        )
        
        # 2. Update date fetching
        content = re.sub(
            r"date = get_latest_signal_date\(db, timeframe\)",
            r"date = target_date if target_date else get_latest_signal_date(db, timeframe)",
            content
        )
        # Handle cases where timeframe is hardcoded e.g., 'D', 'W', 'M'
        content = re.sub(
            r"date_([a-z]) = get_latest_signal_date\(db, '([A-Z])'\)",
            r"date_\1 = target_date if target_date else get_latest_signal_date(db, '\2')",
            content
        )

        with open(filepath, "w") as f:
            f.write(content)
            
    print("Refactoring complete.")

if __name__ == "__main__":
    refactor_screens()
