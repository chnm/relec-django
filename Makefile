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
# 	1. locations
# 	2. denominations
# 	3. Omeka/DataScribe data
#
# ==========================================================================
locations :
	poetry run python manage.py sync_locations

denominations :
	poetry run python manage.py sync_denominations

omeka :
	poetry run python manage.py import_datascribe_data --csv_file="../data/schedules_with_datascribe.csv"

paths :
	poetry run python manage.py import_image_path --csv_file="../data/schedules.csv"

data : locations denominations omeka

.PHONY: data omeka denominations locations migrate mm preview
