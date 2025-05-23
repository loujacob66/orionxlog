# Data Ingestion and Database Schema

This document explains how podcast download data is ingested into the system and how the database schema is structured.

## File Types

The system supports two types of Excel files:

1. **Monthly Files**
   - Filename format: `YYYYMMDD_podcast_downloads.xlsx`
   - Contains data for a specific month
   - Single sheet with download statistics

2. **Report Files**
   - Filename format: `report*.xlsx`
   - Contains historical data
   - Multiple sheets, one per year
   - Sheet names are years (e.g., "2020", "2021")

## Data Extraction

### From Filenames

The system extracts metadata from podcast filenames using several patterns:

1. **Pattern 1**: `DDD@FEATURE_TITLE`
   - Example: `123@HPCpodcast_My_Podcast_Title`
   - Code: `123`
   - Feature: `HPCpodcast`
   - Title: `My_Podcast_Title`

2. **Pattern 2**: `ADDD-TITLE`
   - Example: `A123-My_Podcast_Title`
   - Code: `A123`
   - Title: `My_Podcast_Title`

3. **Pattern 3**: `FEATURE_CODE_TITLE`
   - Example: `HPC001_My_Podcast_Title`
   - Feature: `HPC`
   - Code: `001`
   - Title: `My_Podcast_Title`

4. **Pattern 4**: `FEATURE_TITLE` or `FEATURE_CODE_TITLE`
   - Example: `HPCpodcast_001_My_Podcast_Title`
   - Feature: `HPCpodcast`
   - Code: `001`
   - Title: `My_Podcast_Title`

### From Excel Files

The system reads the following columns from Excel files:

1. **Monthly Files**:
   - `Downloads`: URL/path to the podcast file
   - `Hits`: Number of full downloads
   - `206 Hits`: Number of partial downloads
   - `Bandwidth`: Total bandwidth used
   - `Average size`: Average file size

2. **Report Files**:
   - `URL`: URL/path to the podcast file
   - `Full`: Number of full downloads
   - `Partial`: Number of partial downloads
   - `Total BW`: Total bandwidth used
   - `Avg BW`: Average bandwidth per download

## Database Schema

The SQLite database (`data/podcasts.db`) has the following schema:

```sql
CREATE TABLE podcasts (
    url TEXT NOT NULL,              -- Canonical URL of the podcast
    title TEXT,                     -- Podcast title
    code TEXT,                      -- Podcast code (e.g., "001", "A123")
    feature TEXT,                   -- Feature category (e.g., "HPCpodcast")
    full INTEGER,                   -- Number of full downloads
    partial INTEGER,                -- Number of partial downloads
    avg_bw REAL,                    -- Average bandwidth per download
    total_bw REAL,                  -- Total bandwidth used
    eq_full INTEGER,                -- Calculated: full + 0.5 * partial (floored)
    created_at TEXT,                -- Podcast creation date
    consumed_at TEXT,               -- Date when downloads were recorded
    consumed_year INTEGER NOT NULL, -- Year of consumption
    consumed_month INTEGER NOT NULL,-- Month of consumption
    assumed_month INTEGER NOT NULL DEFAULT 0, -- Whether month was assumed
    imported_at TEXT,               -- When the record was imported
    source_file_path TEXT,          -- Source Excel file
    PRIMARY KEY (url, consumed_year, consumed_month)
)
```

## Data Processing

1. **Deduplication**:
   - Rows with the same code, feature, and title are merged
   - Downloads and bandwidth are summed
   - The longest title and URL are used as canonical versions

2. **Date Handling**:
   - Monthly files: Date extracted from filename (YYYYMMDD)
   - Report files: Year from sheet name, month assumed as December

3. **Calculated Fields**:
   - `eq_full`: `floor(full + 0.5 * partial)`
   - `avg_bw`: `total_bw / (full + partial)` if downloads exist

## Import Process

1. **File Detection**:
   - System automatically detects file type (monthly or report)
   - Handles various filename formats including timestamps

2. **Data Validation**:
   - Checks for required columns
   - Validates date formats
   - Ensures numeric values are valid

3. **Database Operations**:
   - Creates backup before import (unless skipped)
   - Can reset database if requested
   - Supports dry-run mode for testing

4. **Error Handling**:
   - Logs skipped sheets and rows
   - Reports reconciliation of merged records
   - Provides detailed import statistics

## Usage

### Command Line
```bash
python scripts/import_data.py path/to/file.xlsx [--override-db] [--dry-run] [--reset-db]
```

### Web Interface
1. Go to the Admin page
2. Upload Excel file(s)
3. Choose import options:
   - Dry run (preview only)
   - Override existing database
   - Reset database

## Notes

- All dates are stored in ISO format (YYYY-MM-DD)
- Bandwidth values are stored in MB
- The system automatically handles URL encoding/decoding
- Backup files are stored in the `data/` directory 