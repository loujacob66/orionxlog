# OrionX Podcast Trends Application Description

The OrionX Podcast Trends application is a Streamlit-based analytics dashboard designed for exploring and importing podcast download data from Excel files.

## How it Works

The application allows users to upload podcast metrics data via `.xlsx` spreadsheets. When a file is uploaded, the system parses metadata (such as title, code, and feature) directly from the filenames. This data is then processed, which includes an automatic deduplication step to ensure data integrity. Any transformations, like the `eq_full` calculation mentioned in the documentation (`eq_full = full + 0.5 * partial`, floored to an integer), are also applied during this stage.

The processed data is stored in an SQLite database (`data/podcasts.db`). Users interact with the data through a Streamlit web interface. This interface, served via `app/Home.py` and other pages in the `app/pages/` directory (like Admin, Analytics, and Explore), allows users to:
*   Explore download statistics with filters (e.g., by feature and year).
*   View the raw data directly from the SQLite database.

The application uses several key technologies:
*   **Streamlit:** For building the interactive web dashboard.
*   **Pandas:** For data manipulation and analysis, particularly for handling the Excel files and performing calculations.
*   **Openpyxl:** For reading data from Excel files.
*   **SQLite:** As the database backend for storing the podcast data.
*   **Streamlit-Authenticator:** For managing user access and securing sensitive operations.
*   **Google Cloud Storage:** Used for the automated backup and restore functionality.

The `lib/` directory contains core Python modules for database interactions (`db.py`), data sanitization (`sanitize.py`), deduplication logic (`dedupe.py`, `deduplication.py`), and other utilities. Scripts in the `scripts/` folder, such as `import_data.py` and `process_initial_logs.py`, handle data import and initial processing tasks. The application also supports Docker for containerization, facilitating deployment, including to environments like Google Cloud Run.

## Key Features

*   **Excel Data Upload:** Users can upload `.xlsx` spreadsheets containing podcast metrics.
*   **Metadata Parsing:** Automatically extracts metadata (title, code, feature, etc.) from filenames.
*   **Deduplication:** Automatically deduplicates rows to maintain data accuracy.
*   **Data Exploration:** Provides an interface to explore download statistics with filters by feature and year.
*   **Raw Data Viewing:** Allows users to view the raw data directly from the SQLite database.
*   **Flexible Import Options:** Supports different import modes, including `--dry-run` (to preview changes without modifying the database) and `--override-db` (to reset the database before importing).
*   **Authentication:** A secure authentication system protects sensitive operations and data.
*   **Backup and Restore:** Offers automated backup to and restore from Google Cloud Storage.
*   **Cloud Deployment:** Supports deployment to cloud environments like Google Cloud Run, with relevant documentation and scripts provided.
*   **Configuration Management:** Uses YAML files (`config/config.yaml`, `config/gcs_config.yaml`) for application and GCS settings.
