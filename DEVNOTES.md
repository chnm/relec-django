
## Importing Data

Running data imports has to happen in the following procedure in order:

1. Import denominations from Apiary
2. Import locations from Apiary
3. Import Datascribe export: `poetry run python manage.py import_datascribe_data --reset --csv_files=static-data/schedules_with_datascribe.csv`
4. Import image path data: `poetry run python manage.py import_image_path --csv_file=static-data/schedules.csv`
