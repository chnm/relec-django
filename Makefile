# Development Commands
# ===================

# Default target - show help
.DEFAULT_GOAL := help

# Start the Django development server
preview:
	poetry run python manage.py runserver

# Check for any issues with the Django configuration
check:
	poetry run python manage.py check

# Open Django shell for interactive debugging
shell:
	poetry run python manage.py shell

# Database Management
# ==================

# Create new migration files based on model changes
mm:
	poetry run python manage.py makemigrations

# Apply migrations to the database
migrate:
	poetry run python manage.py migrate

# Show migration status
show-migrations:
	poetry run python manage.py showmigrations

# Create database backup (SQL dump)
backup-db:
	@echo "Creating database backup..."
	@mkdir -p backups
	@poetry run python -c "from django.conf import settings; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); import django; django.setup(); db = settings.DATABASES['default']; print(f\"pg_dump -h {db['HOST']} -p {db['PORT']} -U {db['USER']} -d {db['NAME']} > backups/backup_$$(date +%Y%m%d_%H%M%S).sql\")" | sh
	@echo "Database backup created in backups/ directory"

# Restore database from backup
restore-db:
	@echo "Available backups:"
	@ls -la backups/*.sql 2>/dev/null || echo "No backups found in backups/ directory"
	@echo ""
	@read -p "Enter backup filename (e.g., backup_20241201_143022.sql): " backup_file && \
	if [ ! -f "backups/$$backup_file" ]; then \
		echo "Error: Backup file backups/$$backup_file not found!"; \
		exit 1; \
	fi && \
	echo "WARNING: This will replace all current database data with backup data!" && \
	read -p "Are you sure? Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || exit 1 && \
	echo "Restoring database from backups/$$backup_file..." && \
	poetry run python -c "from django.conf import settings; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); import django; django.setup(); db = settings.DATABASES['default']; print(f\"psql -h {db['HOST']} -p {db['PORT']} -U {db['USER']} -d {db['NAME']} < backups/$$backup_file\")" | sh && \
	echo "Database restored successfully from backups/$$backup_file"

# Database Reset & Cleanup
# ========================

# WARNING: These commands will DESTROY all data in the database!
# Drop and recreate PostgreSQL database (for development only)
clean-db:
	@echo "WARNING: This will delete all database data!"
	@read -p "Are you sure? Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || exit 1
	poetry run python manage.py flush --noinput
	@echo "Database cleared. Run 'make setup-fresh-db' to recreate with migrations."

# Reset database and apply all migrations from scratch
reset-db: clean-db
	poetry run python manage.py migrate
	@echo "Fresh database created with all migrations applied."

# Create a complete fresh database with all setup
setup-fresh-db: reset-db
	poetry run python manage.py setup_transcription_groups
	@echo "Fresh database ready with user groups configured."

# Data Import Pipeline
# ===================
#
# IMPORTANT: Data importing must proceed in this exact order:
#   1. import-locations (location data from CSV)
#   2. import-denoms (denomination data from CSV)
#   3. import-omeka (Omeka/DataScribe census data)
#   4. import-images (Omeka/DataScribe image paths)
#   5. fetch-images (download actual images)
#   6. setup-groups (user permissions)

# Import location data from CSV
import-locations:
	poetry run python manage.py import_locations static-data/popplaces_1926.csv --clear-existing

# Import denomination data from CSV
import-denoms:
	poetry run python manage.py import_denominations static-data/denominations.csv --clear-existing

# Import census schedule data from DataScribe CSV
import-omeka:
	poetry run python manage.py import_datascribe_data --csv_file="static-data/schedules_with_datascribe.csv"

# Import image paths for census schedules
import-images:
	poetry run python manage.py import_image_path --csv_file="static-data/schedules.csv"

# Fetch actual images from Omeka API
fetch-images:
	poetry run python manage.py fetch_omeka_images

# Setup user groups and permissions for transcription workflow
setup-groups:
	poetry run python manage.py setup_transcription_groups

# Run the complete data import pipeline
import-all: import-locations import-denoms import-omeka import-images setup-groups
	@echo "Complete data import pipeline finished. Now run 'make fetch-images' to pull images from Omeka."

# Fresh Start (Complete Reset)
# ============================

# Complete fresh start: reset database and import all data
fresh-start: setup-fresh-db import-all
	@echo "Fresh installation complete with all data imported."

# Utility Commands
# ================

# Create a superuser account
superuser:
	poetry run python manage.py createsuperuser

# Collect static files (for production)
collectstatic:
	poetry run python manage.py collectstatic --noinput

# Help - show available commands
help:
	@echo "Religious Ecologies Project - Available Commands"
	@echo "==============================================="
	@echo ""
	@echo "Development:"
	@echo "  preview          - Start Django development server"
	@echo "  check           - Check Django configuration"
	@echo "  shell           - Open Django shell"
	@echo ""
	@echo "Database:"
	@echo "  mm              - Make migrations"
	@echo "  migrate         - Apply migrations"
	@echo "  show-migrations - Show migration status"
	@echo "  backup-db       - Create SQL backup in backups/ directory"
	@echo "  restore-db      - Restore database from backup file"
	@echo ""
	@echo "Database Reset (WARNING - DESTRUCTIVE):"
	@echo "  clean-db        - Delete database file"
	@echo "  reset-db        - Reset and recreate database"
	@echo "  setup-fresh-db  - Fresh database with groups"
	@echo ""
	@echo "Data Import:"
	@echo "  import-omeka    - Import census schedules"
	@echo "  import-images   - Import image paths"
	@echo "  fetch-images    - Download images from Omeka"
	@echo "  setup-groups    - Setup user groups"
	@echo "  import-all      - Run complete import pipeline"
	@echo ""
	@echo "Complete Reset:"
	@echo "  fresh-start     - Complete fresh installation"
	@echo ""
	@echo "Utilities:"
	@echo "  superuser       - Create superuser account"
	@echo "  collectstatic   - Collect static files"
	@echo "  help            - Show this help message"

.PHONY: preview check shell mm migrate show-migrations backup-db restore-db clean-db reset-db setup-fresh-db import-omeka import-images fetch-images setup-groups import-all fresh-start superuser collectstatic help
