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

## Local Testing

Install the development dependencies and Playwright's local Chromium binary once:

```bash
make test-setup
```

Run the complete suite, including browser tests against Django's isolated live test server:

```bash
make test
```

For a faster backend-only run, use `make test-fast`. To run only the Playwright tests, use `make test-e2e`. Browser tests are local and headless by default; no hosted testing service is required.

## Documentation

- **`DEVNOTES.md`**: Complete technical documentation and development workflow
- **`make help`**: All available commands with descriptions
- **Django Admin**: Built-in dashboard at `/admin/` with user management and data tools
