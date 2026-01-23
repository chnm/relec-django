# Religious Ecologies

A Django application for transcribing and managing historical religious census data with collaborative workflows for student researchers.

## Features

- **Project Management System**: Assign and track transcription work across student teams
- **Role-Based Access**: Students see only their assigned work; PIs oversee the entire project
- **Data Import Pipeline**: Automated import from DataScribe/Omeka with image fetching
- **Quality Control Tools**: Built-in data validation and gap analysis
- **Professional Admin Interface**: Custom dashboard with metrics and Religious Ecologies branding

## Quick Start

### Essential Commands
```bash
# View all available commands
make help

# Start development server
make preview

# Create database backup (always do this before major operations)
make backup-db

# Complete fresh installation (wipes existing data)
make fresh-start
```

### First-Time Setup
1. Set up database: `make setup-fresh-db`
2. Create admin user: `make superuser`
3. Import data: `make import-all` (after manual Apiary imports)
4. Add users to groups via Django admin

## Documentation

- **`DEVNOTES.md`**: Complete technical documentation and development workflow
- **`make help`**: All available commands with descriptions
- **Django Admin**: Built-in dashboard at `/admin/` with user management and data tools
