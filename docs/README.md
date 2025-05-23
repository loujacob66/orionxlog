# OrionX Podcast Trends

This is a Streamlit-based analytics dashboard for exploring and importing podcast download data from Excel files.

---

## 📦 Features

- Upload `.xlsx` spreadsheets containing podcast metrics
- Parse metadata (title, code, feature, etc.) from filenames
- Deduplicate rows automatically
- Explore downloads with filters by feature and year
- View raw data directly from SQLite
- Supports `--dry-run` and `--override-db` import modes
- Secure authentication system
- Automated backup and restore functionality
- Cloud deployment support

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/orionxlog.git
cd orionxlog
```

### 2. Set Up a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Create Required Folders

```bash
mkdir -p data logs config
```

### 5. Configure the Application

1. Set up authentication:
   ```bash
   cp config/gcs_credentials.json.sample config/gcs_credentials.json
   cp config/config.yaml.sample config/config.yaml
   cp config/gcs_config.yaml.sample config/gcs_config.yaml
   ```

2. Edit the configuration files:
   - `config/gcs_credentials.json`: Add your Google Cloud service account credentials
   - `config/config.yaml`: Configure authentication settings and user accounts
   - `config/gcs_config.yaml`: Set your GCS bucket and project ID

3. Set environment variables:
   ```bash
   export GOOGLE_CLOUD_PROJECT=your-project-id
   export BACKUP_BUCKET_NAME=your-backup-bucket
   export GOOGLE_APPLICATION_CREDENTIALS=config/gcs_credentials.json
   ```

### 6. Run the App

```bash
streamlit run app/Home.py
```

---

## 📂 Folder Structure

```
orionxlog/
├── app/              # Streamlit UI components and core functionality
│   ├── pages/       # Additional Streamlit pages
│   ├── Home.py      # Main application entry point
│   └── utils.py     # Utility functions
├── config/          # Configuration files
│   ├── gcs_credentials.json.sample  # Template for GCS credentials
│   ├── gcs_credentials.json        # Your actual credentials (gitignored)
│   ├── config.yaml.sample          # Template for app configuration
│   ├── config.yaml                 # Your app configuration (gitignored)
│   ├── gcs_config.yaml.sample      # Template for GCS settings
│   └── gcs_config.yaml            # Your GCS settings (gitignored)
├── data/            # SQLite database and data files
├── docs/            # Documentation
├── logs/            # Application and backup logs
├── scripts/         # Utility scripts for backup/restore
├── requirements.txt # Python dependencies
└── README.md
```

---

## 🔄 Import Options

In the **Upload Data** tab, you can:

- ✅ Upload an Excel file
- ✅ Check `Dry run` to preview without modifying the DB
- ✅ Check `Override existing database` to reset before importing

---

## 📋 Dependencies

Key packages:

```
streamlit==1.44.1
pandas==2.2.3
openpyxl==3.1.5
streamlit-authenticator==0.3.1
plotly==6.0.1
altair==5.5.0
```

For a complete list, see `requirements.txt`.

---

## 🧼 .gitignore Tips

The following files and directories are ignored by git:

```
.venv/
__pycache__/
*.pyc
data/podcasts.db
logs/
config/gcs_credentials.json
config/*.key
config/*.pem
config/*.env
config/secrets/
config/config.yaml
config/gcs_config.yaml
config/*.bak
```

---

## 🛠 Notes

- This app reads/writes from `data/podcasts.db` using SQLite
- Data is parsed from Excel sheets like `2020`, `2021`, etc.
- `eq_full = full + 0.5 * partial`, floored to integer
- Backups are stored in Google Cloud Storage
- Authentication is required for sensitive operations
- Configuration is managed through YAML files in the config directory

For more details on deployment and backup/restore functionality, see:
- `docs/DEPLOY_TO_CLOUD_RUN.md`
- `docs/BACKUP_AND_RESTORE.md`