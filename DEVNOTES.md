
## Development Workflow

### Essential Commands
View all available commands:
```bash
make help
```

### Development Server
```bash
make preview      # Start Django development server
make check        # Check Django configuration
make shell        # Open Django shell
```

### Database Management

#### Creating Backups
Always create a database backup before major operations:
```bash
make backup-db
```
This creates a timestamped SQL dump in the `backups/` directory using your PostgreSQL settings.

#### Migrations
```bash
make mm           # Create new migration files (makemigrations)
make migrate      # Apply migrations to database
make show-migrations  # Show current migration status
```

#### Database Reset (⚠️ DESTRUCTIVE)
```bash
make clean-db        # Delete all database data (with confirmation prompt)
make reset-db        # Reset database and apply migrations
make setup-fresh-db  # Fresh database with user groups configured
```

## Streamlined Data Import Pipeline

The Makefile provides simplified commands for the complete data import process:

### Quick Import Commands
```bash
make import-omeka       # Import census schedules from DataScribe CSV
make import-images      # Import image path data
make fetch-images       # Download images from Omeka API
make import-locations   # Import location data from CSV
make import-denoms      # Import denomination data from CSV
make setup-groups       # Setup user groups and permissions
make import-all         # Run complete import pipeline
```

### Complete Fresh Installation
```bash
make fresh-start     # Complete reset + full data import
```
**Warning**: This completely wipes the database and reimports everything.

### Data Import Order
The import pipeline **must** proceed in this exact order:
1. `make import-locations` - Import location data from CSV
2. `make import-denoms` - Import denomination data from CSV
3. `make import-omeka` - Import census schedule data
4. `make import-images` - Import image path data
5. `make fetch-images` - Download actual images
6. `make setup-groups` - Setup user permissions

## Manual Data Import Commands

For advanced usage or troubleshooting, you can run the import commands directly:

1. Import locations from CSV:
   ```bash
   poetry run python manage.py import_locations static-data/popplaces_1926.csv --clear-existing
   ```
2. Import denominations from CSV:
   ```bash
   poetry run python manage.py import_denominations static-data/denominations.csv --clear-existing
   ```
3. Import Datascribe export:
   ```bash
   poetry run python manage.py import_datascribe_data --reset --csv_files=static-data/schedules_with_datascribe.csv
   ```
4. Import image path data:
   ```bash
   poetry run python manage.py import_image_path --csv_file=static-data/schedules.csv
   ```

**Note**: Use the Makefile commands (`make import-all`) for routine imports.

### Utility Commands
```bash
make superuser       # Create Django superuser account
make collectstatic   # Collect static files (for production)
```

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

## User Permissions and Project Management

The Religious Ecologies admin interface implements a role-based permission system designed for collaborative transcription work with undergraduate and graduate students.

### User Groups and Roles

#### Transcribers Group
- **Purpose**: Student transcribers who work on assigned census schedules
- **Permissions**: Can add and edit census records, but cannot delete records
- **Access Level**: Restricted to only their assigned records (see Record Visibility below)

#### Reviewers Group
- **Purpose**: PIs, postdocs, and staff who review transcribed work
- **Permissions**: Full access to all records including add, edit, and delete
- **Access Level**: Can see all records across the entire project

### Record Visibility Rules

The admin interface uses intelligent filtering to show appropriate records based on user roles:

**Student Transcribers** (non-superuser, only in "Transcribers" group):
- See only census schedules assigned to them via the `assigned_transcriber` field
- This focused view helps students concentrate on their work without distractions
- Cannot see other students' assignments or unassigned records

**Everyone Else** (superusers, reviewers, or users in multiple groups):
- See all census schedules in the project
- Includes PIs, staff, and administrative users
- Can manage assignments and oversee the entire transcription workflow

**Examples**:
- `student_worker` (non-superuser, Transcribers only) → Sees 15 assigned records
- `pi_user` (Reviewers group) → Sees all 6,205 records
- `admin_user` (superuser, both groups) → Sees all 6,205 records

### Transcription Workflow

#### Status Progression
Records follow this workflow through transcription:
1. `unassigned` → Available for assignment
2. `assigned` → Assigned to a transcriber
3. `in_progress` → Transcriber is actively working
4. `needs_review` → Ready for reviewer attention
5. `completed` → Transcription finished
6. `approved` → Final approval by reviewer

#### Assignment System
- **assigned_transcriber**: Links record to student doing transcription work
- **assigned_reviewer**: Links record to PI/staff doing review work
- **Auto-transitions**: Status automatically updates when assignments change

#### Admin Interface Features

**Enhanced Filtering**: Multiple filter panels for efficient record management
- **Transcription Workflow**: Unassigned, Assigned to Me, Needs Review, In Progress, Completed, Approved
- **Assignment Status**: Has/No Transcriber, Has/No Reviewer, Fully Assigned, Completely Unassigned
- **Location Status**: Has County, Missing County, Missing Location

**Bulk Operations**: Efficient management of multiple records
- **Bulk Assignment**: Assign transcriber, reviewer, and status to multiple records
- **Status Changes**: Mark multiple records as assigned, in progress, completed, etc.
- **User Assignment**: Quick "Assign to Me" action for taking ownership

**Data Quality Tools**: Built-in analysis for project oversight
- **Schedule ID Gap Analysis**: Identifies missing census schedules by denomination
- **Missing County Analysis**: Shows location data completeness by state

### Setup Commands

#### Initial User Group Setup
```bash
# Create transcription groups with proper permissions
poetry run python manage.py setup_transcription_groups
```

#### Adding Users to Groups
Users must be manually added to appropriate groups via Django admin:
1. Navigate to Users in System Administration
2. Edit user and select appropriate groups:
   - Add students to "Transcribers" group only
   - Add PIs/staff to "Reviewers" group (or both groups for flexibility)
3. Superuser status provides full access regardless of group membership

### Access Control Implementation

The permission system is implemented in `census/admin.py`:

- **Record Filtering**: `CensusScheduleAdmin.get_queryset()` method
- **Delete Restrictions**: `has_delete_permission()` prevents student deletions
- **Auto-save Logic**: `save_model()` transitions status when students complete work
- **User Groups**: Managed via Django's built-in Group system with custom permissions
