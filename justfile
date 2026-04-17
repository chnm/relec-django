# Religious Ecologies Project
# ==========================

# Show available commands
default:
    @just --list

# Development Commands
# ====================

# Start the Django development server
preview:
    uv run python manage.py runserver

# Check for any issues with the Django configuration
check:
    uv run python manage.py check

# Open Django shell for interactive debugging
shell:
    uv run python manage.py shell

# Database Management
# ===================

# Create new migration files based on model changes
mm:
    uv run python manage.py makemigrations

# Apply migrations to the database
migrate:
    uv run python manage.py migrate

# Show migration status
show-migrations:
    uv run python manage.py showmigrations

# Create database backup (SQL dump)
backup-db:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Creating database backup..."
    mkdir -p backups
    uv run python -c "
    from django.conf import settings
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django; django.setup()
    db = settings.DATABASES['default']
    print(f\"pg_dump -h {db['HOST']} -p {db['PORT']} -U {db['USER']} -d {db['NAME']}\")
    " | sh > "backups/backup_$(date +%Y%m%d_%H%M%S).sql"
    echo "Database backup created in backups/ directory"

# Restore database from backup file
restore-db backup_file:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -f "backups/{{ backup_file }}" ]; then
        echo "Error: Backup file backups/{{ backup_file }} not found!"
        ls -la backups/*.sql 2>/dev/null || echo "No backups found."
        exit 1
    fi
    echo "WARNING: This will replace all current database data with backup data!"
    read -p "Are you sure? Type 'yes' to continue: " confirm
    [ "$confirm" = "yes" ] || exit 1
    echo "Restoring database from backups/{{ backup_file }}..."
    uv run python -c "
    from django.conf import settings
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django; django.setup()
    db = settings.DATABASES['default']
    print(f\"psql -h {db['HOST']} -p {db['PORT']} -U {db['USER']} -d {db['NAME']} < backups/{{ backup_file }}\")
    " | sh
    echo "Database restored successfully from backups/{{ backup_file }}"

# List available database backups
list-backups:
    @ls -la backups/*.sql 2>/dev/null || echo "No backups found in backups/ directory"

# Database Reset & Cleanup
# ========================

# Clear all data from database (WARNING: DESTRUCTIVE)
[confirm("This will delete all database data. Continue?")]
clean-db:
    uv run python manage.py flush --noinput
    @echo "Database cleared. Run 'just setup-fresh-db' to recreate with migrations."

# Reset database and apply all migrations from scratch
[confirm("This will delete all database data and re-migrate. Continue?")]
reset-db: clean-db
    uv run python manage.py migrate
    @echo "Fresh database created with all migrations applied."

# Create a complete fresh database with all setup
setup-fresh-db: reset-db
    uv run python manage.py setup_transcription_groups
    @echo "Fresh database ready with user groups configured."

# Data Import Pipeline
# ====================
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
    uv run python manage.py import_locations static-data/popplaces_1926.csv --clear-existing

# Import denomination data from CSV
import-denoms:
    uv run python manage.py import_denominations static-data/denominations.csv --year 1926

# Import census schedule data from DataScribe CSV
import-omeka:
    uv run python manage.py import_datascribe_data --csv_file="static-data/schedules_with_datascribe.csv"

# Import image paths for census schedules
import-images:
    uv run python manage.py import_image_path --csv_file="static-data/schedules.csv"

# Fetch actual images from Omeka API
fetch-images:
    uv run python manage.py fetch_omeka_images

# Import denomination census report PDFs from Omeka
import-denom-pdfs:
    uv run python manage.py import_denomination_pdfs

# Setup user groups and permissions for transcription workflow
setup-groups:
    uv run python manage.py setup_transcription_groups

# Run the complete data import pipeline
import-all: import-locations import-denoms import-omeka import-images setup-groups
    @echo "Complete data import pipeline finished. Now run 'just fetch-images' to pull images from Omeka."

# Fresh Start (Complete Reset)
# ============================

# Complete fresh start: reset database and import all data
fresh-start: setup-fresh-db import-all
    @echo "Fresh installation complete with all data imported."

# Frontend Assets
# ===============

# Build Tailwind CSS for production (one-time build)
build-css:
    cd theme/static_src && npm run build

# Watch Tailwind CSS for development (auto-rebuild on changes)
watch-css:
    cd theme/static_src && npm run dev

# Utility Commands
# ================

# Create a superuser account
superuser:
    uv run python manage.py createsuperuser

# Collect static files (for production)
collectstatic:
    uv run python manage.py collectstatic --noinput

# Run tests
test *args:
    uv run pytest {{ args }}

# Format code with black
fmt:
    uv run black .

# Format HTML templates with djhtml
fmt-html:
    uv run djhtml templates/
