# Data Utilities

This directory contains utility scripts for checking and analyzing project data.

## Available Scripts

### check_county_data.py

Check data availability for a specific county - useful for investigating data gaps or verifying imports.

**Purpose**: Quickly verify whether a county has location records, religious body data, and census schedules. Helps distinguish between display issues and actual data gaps.

**Usage**:
```bash
# Check a specific county
poetry run python utils/check_county_data.py --state IL --county Hancock

# Check another county
poetry run python utils/check_county_data.py --state VA --county Fairfax

# Counties with spaces in name
poetry run python utils/check_county_data.py --state NY --county "New York"
```

**Output**:
- Location record count and sample cities
- Religious body count and sample records
- Census schedule count
- Verdict: Complete data, data gap, or county not found
- Comparison with nearby counties (if data gap detected)

**Use Cases**:
- Investigating why a county doesn't appear in analytics
- Verifying data import success
- Identifying transcription gaps
- Quality assurance checks
