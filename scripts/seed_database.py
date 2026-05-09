"""
Database Seeder - Populates the database with test accounts.

Test Accounts:
  seeker@example.com  / password123  - Seeker role
  jane@example.com    / password123  - Provider (Software Architect, MWK 50 fee)
  john@example.com    / password123  - Provider (Legal Consultant, MWK 75 fee)
  dual@example.com    / password123  - Both Seeker AND Provider (Dual-role demo)
"""

import sys
import os

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.modules.auth.service import register_user
from app.modules.providers.service import create_provider_profile


def seed():
    app = create_app()
    with app.app_context():
        print("Seeding database...")

        # Provider 1: Software Architect — offers several benefits
        try:
            provider_user1 = register_user("jane@example.com", "password123", "Jane", "Doe", "provider")
            create_provider_profile(
                provider_user1["id"],
                "Expert Software Architect",
                "I have 15 years of experience in building scalable systems.",
                "Node.js, React, AWS, System Design",
                "+1234567890",
                "Technology",
                150,
                50,
                offered_benefits={
                    "video_call_link": True,
                    "digital_product": True,
                    "exclusive_content": True,
                    "micro_consultation": True,
                    "personalized_resources": True,
                },
            )
        except ValueError as e:
            print(f"  Skipping jane@example.com (provider): {e}")

        # Provider 2: Legal Consultant — offers appointment and network pass
        try:
            provider_user2 = register_user("john@example.com", "password123", "John", "Smith", "provider")
            create_provider_profile(
                provider_user2["id"],
                "Legal Consultant",
                "Specializing in corporate law and intellectual property.",
                "Corporate Law, IP, Contracts",
                "+1987654321",
                "Legal",
                200,
                75,
                offered_benefits={
                    "whatsapp_link": True,
                    "appointment_details": True,
                    "network_fast_pass": True,
                    "booked_chat": True,
                    "darkweb_access": True,
                    "forex_exchange": True,
                },
            )
        except ValueError as e:
            print(f"  Skipping john@example.com (provider): {e}")

        # Seeker
        try:
            register_user("seeker@example.com", "password123", "Bob", "Seeker", "seeker")
        except ValueError as e:
            print(f"  Skipping seeker@example.com (seeker): {e}")

        # Dual-role user: same email for both seeker AND provider
        try:
            register_user("dual@example.com", "password123", "Favour", "Chipanda", "seeker")
        except ValueError as e:
            print(f"  Skipping dual@example.com (seeker): {e}")

        try:
            dual_provider = register_user("dual@example.com", "password123", "Favour", "Chipanda", "provider")
            create_provider_profile(
                dual_provider["id"],
                "Business Consultant",
                "Experienced consultant with expertise in strategy and operations.",
                "Business Strategy, Operations, Marketing",
                "+265999123456",
                "Business",
                100,
                30,
                offered_benefits={
                    "video_call_link": True,
                    "whatsapp_link": True,
                    "shadowing_session": True,
                    "personalized_resources": True,
                },
            )
        except ValueError as e:
            print(f"  Skipping dual@example.com (provider): {e}")

        print("Seeding completed successfully!")
        print("\nTest Accounts:")
        print("  seeker@example.com  / password123  - Seeker only")
        print("  jane@example.com    / password123  - Provider only (Software Architect)")
        print("  john@example.com    / password123  - Provider only (Legal Consultant)")
        print("  dual@example.com    / password123  - Both Seeker AND Provider (Dual-role)")


if __name__ == "__main__":
    seed()
