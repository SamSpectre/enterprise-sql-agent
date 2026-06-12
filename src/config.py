"""
Configuration management for the SQL Agent.
Loads settings from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# Database settings
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "taxi_data")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"


# OpenAI settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-4o-mini"  # Cheap and good for SQL generation


# Agent settings
MAX_QUERY_ROWS = 100  # Limit results to avoid overwhelming responses


def validate_config():
    """Check that required config is present."""
    issues = []
    
    if not POSTGRES_PASSWORD:
        issues.append("POSTGRES_PASSWORD not set")
    
    if not OPENAI_API_KEY:
        issues.append("OPENAI_API_KEY not set")
    
    if issues:
        print("Configuration issues:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    
    return True


if __name__ == "__main__":
    if validate_config():
        print("Configuration valid.")
        print(f"Database: {POSTGRES_DB} on {POSTGRES_HOST}:{POSTGRES_PORT}")
        print(f"Model: {OPENAI_MODEL}")