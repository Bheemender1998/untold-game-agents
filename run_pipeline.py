"""Convenience shim: `python3 run_pipeline.py ...` → `python3 -m engine.run_pipeline ...`.

The real entrypoint is engine/run_pipeline.py. This keeps the command from the
original setup guide working after the move into engine/.
"""
from engine.run_pipeline import main

if __name__ == "__main__":
    main()
