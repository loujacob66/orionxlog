# OrionX Podcast Analytics

A Streamlit-based web application for analyzing podcast download statistics. This application processes podcast download data from Excel files, stores it in a SQLite database, and provides interactive visualizations and analysis tools.

## Features

- **Data Import**: Import podcast download statistics from Excel files
- **Interactive Dashboard**: View download trends, top podcasts, and bandwidth usage
- **Admin Interface**: Manage data imports and database operations
- **Data Export**: Export filtered data to CSV format
- **Cloud Deployment**: Ready for deployment to Google Cloud Run
- **Backup System**: Automated backup to Google Cloud Storage

## Documentation

- [Data Ingestion and Database Schema](docs/DATA_INGESTION.md) - Details about data import process and database structure
- [Deployment Guide](docs/DEPLOY_TO_CLOUD_RUN.md) - Instructions for deploying to Google Cloud Run
- [Backup and Restore](docs/BACKUP_AND_RESTORE.md) - Guide for database backup and restore operations

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/orionxlog.git
   cd orionxlog
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up configuration:
   - Copy `config/config.yaml.sample` to `config/config.yaml`
   - Copy `.env.sample` to `.env`
   - Update the configuration files with your settings

5. Initialize the database:
   ```bash
   python scripts/init_db.py
   ```

## Development

### Local Development

1. Start the development server:
   ```bash
   streamlit run app.py
   ```

2. Access the application at `http://localhost:8501`

### Docker Development

1. Build and start the containers:
   ```bash
   docker-compose up --build
   ```

2. Access the application at `http://localhost:8501`

## Project Structure

```
orionxlog/
├── app.py                 # Main Streamlit application
├── config/               # Configuration files
│   ├── config.yaml      # Main configuration (not tracked)
│   └── config.yaml.sample # Sample configuration
├── data/                # Data directory
│   └── podcasts.db      # SQLite database
├── docs/                # Documentation
│   ├── DATA_INGESTION.md
│   ├── DEPLOY_TO_CLOUD_RUN.md
│   └── BACKUP_AND_RESTORE.md
├── scripts/             # Utility scripts
│   ├── import_data.py   # Data import script
│   └── init_db.py       # Database initialization
├── src/                 # Source code
│   ├── database.py      # Database operations
│   ├── importers.py     # Data importers
│   └── utils.py         # Utility functions
├── .env                 # Environment variables (not tracked)
├── .env.sample          # Sample environment variables
├── .gitignore          # Git ignore file
├── docker-compose.yml   # Docker Compose configuration
├── Dockerfile          # Docker configuration
└── requirements.txt     # Python dependencies
```

## Configuration

The application uses two types of configuration files:

1. **Environment Variables** (`.env`):
   - Database connection details
   - Cloud storage credentials
   - Application secrets

2. **YAML Configuration** (`config/config.yaml`):
   - Application settings
   - Feature flags
   - UI customization

See the sample files (`.env.sample` and `config/config.yaml.sample`) for configuration options.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 