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
mkdir -p data logs
```

### 5. Run the App

```bash
streamlit run app/Home.py
```

---

## 📂 Folder Structure

```
orionxlog/
├── app/              # Streamlit UI components (Explore, Upload, etc.)
├── commands/         # CLI tools (import_from_excel.py)
├── data/             # Holds podcasts.db (created automatically)
├── logs/             # Deduplication logs, if needed
├── requirements.txt
├── README.md
```

---

## 🔄 Import Options

In the **Upload Data** tab, you can:

- ✅ Upload an Excel file
- ✅ Check `Dry run` to preview without modifying the DB
- ✅ Check `Override existing database` to reset before importing

---

## 📋 Dependencies

Generated via:

```bash
pip freeze > requirements.txt
```

Key packages:

```
streamlit
pandas
openpyxl
xlrd
```

---

## 🧼 .gitignore Tips

Add the following to avoid committing local junk:

```
.venv/
__pycache__/
*.pyc
data/podcasts.db
logs/
```

---

## 🛠 Notes

- This app reads/writes from `data/podcasts.db` using SQLite
- Data is parsed from Excel sheets like `2020`, `2021`, etc.
- `eq_full = full + 0.5 * partial`, floored to integer