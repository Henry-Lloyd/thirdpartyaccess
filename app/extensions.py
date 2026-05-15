"""Flask extension instances."""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# SQLAlchemy is used for migration orchestration (Flask-Migrate/Alembic).
# Runtime query logic remains in app.database for compatibility with existing services.
db = SQLAlchemy()
migrate = Migrate()
