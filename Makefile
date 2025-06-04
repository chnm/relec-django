# Django helpers
# ---------------------------
preview :
	poetry run python manage.py runserver

mm :
	poetry run python manage.py makemigrations

migrate :
	poetry run python manage.py migrate

# ==========================================================================

# Data imports for locations and denominations come directly from Apiary
#
# Note: These must proceed in this order:
# 	1. sync_locations from Django Admin
# 	2. sync_denominations from Django Admin
# 	3. Run the import for the Omeka/DataScribe data
#
# ==========================================================================
omeka :
	poetry run python manage.py import_datascribe_data --csv_file="static-data/schedules_with_datascribe.csv"

.PHONY: omeka migrate mm preview
