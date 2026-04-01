#!/usr/bin/env python3
"""
Autonomous Revenue Agent
========================
Goal: Generate $250/month to pay for the Claude subscription.

Usage:
    python run.py                    # Run one session now
    python run.py --schedule 09:00   # Run daily at 9 AM
    python run.py --status           # Print current status
    python run.py --help             # Show all options

First time setup:
    1. Copy .env.example to .env
    2. Add your ANTHROPIC_API_KEY
    3. Run: python run.py
"""

import sys
from pathlib import Path

# Make sure 'agent' package is importable
sys.path.insert(0, str(Path(__file__).parent))

from agent.main import main

if __name__ == "__main__":
    main()
