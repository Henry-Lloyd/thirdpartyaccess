"""
ThirdParty Access - Python/Flask Application Entry Point

Usage:
    python run.py          # Start the development server
    python run.py --seed   # Seed the database with test data then start

Test Accounts (after seeding):
    seeker@example.com  / password123  - Seeker only
    jane@example.com    / password123  - Provider (Software Architect, MWK 50 fee)
    john@example.com    / password123  - Provider (Legal Consultant, MWK 75 fee)
    dual@example.com    / password123  - Both Seeker AND Provider (Dual-role demo)
"""

import sys
import os

# Ensure project root is on path for imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from config import Config

app = create_app()

if __name__ == "__main__":
    # Optional: seed database if --seed flag is passed
    if "--seed" in sys.argv:
        print("Seeding database...")
        from scripts.seed_database import seed
        seed()
        print("Database seeded. Starting server...")

    print(f"Starting ThirdParty Access on http://{Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
