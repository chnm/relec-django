# Django helpers
# ---------------------------
preview :
	poetry run python manage.py runserver

mm :
	poetry run python manage.py makemigrations

migrate :
	poetry run python manage.py migrate

# Load data
# ---------------------------
# Data imports come from Apiary, and requires the export of the denominations table
# and the popplaces_1926 table.
#
# Must proceed in this order:
# 1. locations
# 2. denominations
# 3. Omeka data
locations :
	poetry run python manage.py import_data --locations="../data/popplaces_1926.csv"

denominations :
	poetry run python manage.py import_data --denominations="../data/denominations.csv"

omeka :
	echo "Not set up yet!"

location_fixture :
	poetry run python manage.py loaddata location

denomination_fixture :
	poetry run python manage.py loaddata denomination
