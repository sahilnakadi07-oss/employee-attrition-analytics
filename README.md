# PeoplePulse — Employee Attrition Analytics & Prediction System

A complete Flask + SQLite + Pandas + scikit-learn student project based on the uploaded project specification. Includes employee CRUD, CSV upload, attendance/performance tables, workforce analytics, attrition prediction history, model comparison and CSV reporting.

## Features
- Login, registration and password hashing.
- SQLite normalized tables: `users`, `employees`, `attendance`, `performance`, `attrition_predictions`; employee child records use foreign keys. Existing databases receive a safe migration for record-source labels.
- Dashboard KPIs: headcount, recorded attrition cases/rate and average monthly salary.
- Employee create/read/update/delete with search and department filter.
- Attendance & performance opens with starter records for the demo employee dataset; each row is labelled **Demo data** or **Manual**. Demo values are illustrative and can be replaced by submitting the forms. Existing manual records are not overwritten.
- Attendance validates the selected month and prevents present + leave days from exceeding the actual number of calendar days in that month. Ratings and review dates are validated.
- CSV import with extension/size checks, sanitized filenames, required-column validation and duplicate-code upsert.
- Department attrition/salary/tenure analysis and tenure distribution charts.
- Train and compare Logistic Regression and Random Forest; test split, accuracy, precision, recall, F1 and confusion matrix. Best F1 model is persisted with joblib.
- Live prediction for a saved employee; probability/risk and timestamp are saved to prediction history.
- Downloadable CSV report.

## Requirements
- Python 3.10+ recommended
- Internet connection for Bootstrap, Chart.js and Google Fonts CDN (the application itself runs locally).

## Run on Windows (PowerShell)
```powershell
cd employee_attrition_analytics
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
```
Open `http://127.0.0.1:5000`.

## Demo credentials
- Username: `admin`
- Password: `Admin@123`

Change the development secret and demo credentials before any deployment. For example, set `SECRET_KEY` in your environment. This is a classroom/demo app, not hardened for production.

## Included dataset
- `data/hr_attrition_dataset.csv` and root-level `hr_attrition_dataset.csv` contain 500 synthetic sample employee rows.
- `Attrition` is the target (`Yes` / `No`).
- Fields are documented in `data/DATASET_README.md`.
- The sample CSV is included for optional testing, but it is **not imported automatically**. New installations start with an empty employee table; upload a CSV when you are ready to add data.

### Important dataset limitation
The sample data is artificially generated to make the app runnable without private HR records. It is not a real IBM HR dataset, and model metrics should only be used to demonstrate the ML workflow. Synthetic correlations can create misleading performance. Do not make employment decisions using this model.

## ML workflow
1. Open **Reports & model** and choose **Train models now**.
2. The training script encodes categorical values, imputes missing values, scales numeric values, creates a train/test split and compares Logistic Regression and Random Forest.
3. The highest-F1 model is stored at `models/best_model.joblib`.
4. Open **Attrition prediction** and choose an employee to save a probability and risk band to the database.

## CSV upload format
Required columns: `EmployeeNumber, Age, Department, JobRole, MonthlyIncome, JobSatisfaction, WorkLifeBalance, OverTime, YearsAtCompany, YearsSinceLastPromotion, TrainingTimesLastYear, PerformanceRating, AbsentDaysLastYear, Attrition`. Optional: `Gender`, `MaritalStatus`, and `AttritionDate` (YYYY-MM-DD). Add actual `AttritionDate` values for employees who left to populate the dashboard monthly and yearly attrition charts; the app does not fabricate exit dates. `EmployeeNumber` becomes the unique employee code.

## Database notes
The `attendance` and `performance` tables include a `record_source` label. Enter attendance and performance records explicitly; dashboard employee data is not preloaded.

## Troubleshooting
- If packages fail to install, use Python 3.10 or 3.11 and retry `pip install -r requirements.txt`.
- If the port is busy: `python -c "from run import app; app.run(port=5001, debug=True)"`
- Delete `instance/hr_analytics.db` only if you want to reset the local database; the app recreates an empty employee table.
- Use CSV upload to import or update employee records.


## Security and deployment notes

- The seeded demo account is `admin` / `Admin@123`. Change/remove it before using real employee data.
- Set a long random `SECRET_KEY` environment variable before deployment. When omitted locally, a random process-specific key is generated, so login sessions may be cleared after restarting the app.
- Set `SESSION_COOKIE_SECURE=1` when serving over HTTPS. Do not expose Flask's development server directly to the internet.
- This demo stores employee and prediction data locally in SQLite. Back up the database securely and restrict access to the machine.
- The supplied dataset is synthetic/demo data. Model scores and risk bands are for demonstration and must not be used to make employment decisions.
- `pytz` is included in requirements because the dashboard uses the `Asia/Kolkata` timezone.


## Security and validation improvements
- All POST forms require a session-bound CSRF token.
- Login attempts are limited per client IP and username (5 failures trigger a 15-minute block).
- A seeded demo administrator is created on a fresh database (`admin` / `Admin@123`); subsequent registrations receive the HR role. Admin role is required for CSV imports, model training and employee deletion. Change the seeded demo password before real use.
- CSV imports validate the complete file before writing any rows. Errors include CSV row numbers, and an invalid file is rejected as a whole.
- Model reports include stratified cross-validation precision, recall, F1 and ROC-AUC, class imbalance counts, holdout metrics and calibrated probability Brier score.
- Analytics supports joining-date filters, department filtering, CSV export and PNG chart downloads. This dataset has no dedicated exit date, so date filters refer to joining dates rather than actual attrition timing.

## Production notes
Set a strong random `SECRET_KEY` environment variable and enable `SESSION_COOKIE_SECURE=1` when served only over HTTPS. Demo data in attendance/performance is explicitly marked as illustrative. Use a production WSGI server and review authorization policy before deployment.
