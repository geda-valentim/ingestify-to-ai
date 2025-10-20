#!/usr/bin/env python3
"""
Initialize database - create tables

Usage:
    python scripts/init_db.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.shared.database import init_db
from backend.shared.config import get_settings

def main():
    print("=" * 60)
    print("Doc2MD - Database Initialization")
    print("=" * 60)

    settings = get_settings()
    print(f"\nDatabase URL: {settings.database_url}")
    print("\nCreating tables...")

    try:
        init_db()
        print("\n✅ Database initialized successfully!")
        print("\nTables created:")
        print("  - users")
        print("  - api_keys")
        print("  - jobs")
        print("  - pages")
        print("\nYou can now start the API and register users.")

        # Check Elasticsearch connection
        print("\nChecking Elasticsearch connection...")
        try:
            from backend.shared.elasticsearch_client import get_es_client
            es_client = get_es_client()
            if es_client.health_check():
                print("✅ Elasticsearch connection OK")
                print("   Indices will be created automatically on first use")
            else:
                print("⚠️  Elasticsearch not available")
                print("   Search features will be limited")
        except Exception as e:
            print(f"⚠️  Elasticsearch connection failed: {e}")
            print("   Search features will be limited")

    except Exception as e:
        print(f"\n❌ Error initializing database: {e}")
        print("\nPlease check:")
        print("  1. MySQL is running")
        print("  2. Database 'doc2md' exists")
        print("  3. Credentials in DATABASE_URL are correct")
        print(f"     Current: {settings.database_url}")
        sys.exit(1)


if __name__ == "__main__":
    main()
