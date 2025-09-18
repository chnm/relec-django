
## Importing Data

Running data imports has to happen in the following procedure in order:

1. Import denominations from Apiary
2. Import locations from Apiary
3. Import Datascribe export: `poetry run python manage.py import_datascribe_data --reset --csv_files=static-data/schedules_with_datascribe.csv`
4. Import image path data: `poetry run python manage.py import_image_path --csv_file=static-data/schedules.csv`

## Fetching Omeka Images

The `fetch_omeka_images` management command downloads original images from the Omeka API and associates them with CensusSchedule records.

### How it works:
1. Uses the `datascribe_omeka_item_id` field from CensusSchedule records
2. Fetches Omeka item data from `https://omeka.religiousecologies.org/api/items/{item_id}`
3. Extracts media IDs from the item's `o:media` array
4. Fetches media data from `https://omeka.religiousecologies.org/api/media/{media_id}`
5. Downloads the `o:original_url` image and saves it with a unique filename
6. Updates the `datascribe_original_image_path` field with the saved image path

### Usage Examples:
```bash
# Test with 10 records (recommended first run)
poetry run python manage.py fetch_omeka_images --test

# Dry run to preview what would be processed
poetry run python manage.py fetch_omeka_images --dry-run --limit 20

# Process specific number of records
poetry run python manage.py fetch_omeka_images --limit 50

# Force re-download existing images
poetry run python manage.py fetch_omeka_images --limit 10 --force

# For large datasets - slower but safer
poetry run python manage.py fetch_omeka_images --delay 1.0 --batch-size 50

# Resume from specific record ID (if interrupted)
poetry run python manage.py fetch_omeka_images --start-from 1500

# Full processing (use with caution)
poetry run python manage.py fetch_omeka_images
```

### Command Options:
- `--test`: Process only 10 records for testing
- `--dry-run`: Show what would be processed without downloading
- `--limit N`: Process only N records
- `--force`: Re-download images even if they already exist
- `--start-from ID`: Resume processing from specific record ID
- `--delay N`: Delay in seconds between API requests (default: 0.5)
- `--batch-size N`: Process records in batches (default: 100)

### Safety Features:
- Skips records that already have images (unless `--force` used)
- Creates timestamped logs in `/logs/` directory
- Uses Django transactions for data integrity
- **Retry logic**: 3 attempts with exponential backoff for API failures
- **Rate limiting**: Configurable delay between requests (default 0.5s)
- **Batch processing**: Handles thousands of records in manageable chunks
- **Resume capability**: Can restart from specific record ID if interrupted
- **Graceful interruption**: Ctrl+C shows last processed ID for resuming
- Shows progress every 10 records with batch information

### Output:
- Images saved to `census_images/originals/` directory via Django ImageField
- Automatic thumbnail generation in multiple sizes (large: 800x600, medium: 400x300, small: 200x150, admin: 100x75)
- Admin interface displays thumbnails in list view and image preview in detail view
- Log files created as `logs/fetch_omeka_images_YYYYMMDD_HHMMSS.log`

### Image Management:
- **Original images**: Stored in `census_images/originals/` via `CensusSchedule.original_image`
- **Thumbnails**: Auto-generated using django-imagekit when accessed
- **Admin integration**: List view thumbnails, detail view preview with full-size link
- **File naming**: `schedule_{id}_{original_filename}_{media_id}.jpg`
