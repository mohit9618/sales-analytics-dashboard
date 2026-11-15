# Sales Analytics Dashboard

An interactive Streamlit application for uploading, validating, cleaning, filtering, and analyzing sales data.

## Features
- Upload CSV, Excel (`.xlsx`), and JSON record files.
- Inspect dimensions, columns, data types, missing values, and duplicate rows.
- Choose duplicate and missing-value handling strategies.
- Convert likely date columns and numeric-looking text columns.
- Map dataset-specific fields to Sales, Profit, Order ID, Quantity, Date, Region, and Category.
- Interactive date, region, category, and optional numeric-range filters.
- Five dynamically updating KPIs: Total Sales, Total Profit, unique Total Orders, Total Quantity Sold, and Profit Margin.
- Interactive Plotly charts and CSV export.

## Run locally
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Community Cloud
1. Create a public GitHub repository (or a private repository accessible to Streamlit Community Cloud).
2. Upload `app.py`, `requirements.txt`, and this `README.md` to the repository root.
3. Open https://share.streamlit.io/ and sign in with GitHub.
4. Choose **Create app**, select the repository, branch, and `app.py` as the main file.
5. Deploy, then open the generated app URL and test a CSV, XLSX, and JSON file.
6. Verify filters, KPI updates, charts, error handling, and CSV download.

## Demo data
`demo_sales_data.csv` is a synthetic example containing all five KPI fields and the recommended filter dimensions. It is included for testing and is not real customer or business data.

## Expected column names
The app auto-detects common names, but any column can be manually mapped. For meaningful KPI values, map the relevant Sales, Profit, Order ID, and Quantity columns. Filters and charts are enabled when matching Date, Region, and Category columns are available.

## Notes
- JSON should contain a list of records, a single record object, or an object containing a list of records.
- Profit Margin is calculated as `Total Profit / Total Sales * 100`.
- The app does not assume that every uploaded dataset has all sales fields; unavailable KPIs display `N/A` instead of a misleading zero. For example, the earlier time-series sample file has Sales and Date but no Profit, Order ID, or Quantity fields, so those three KPIs cannot be calculated from it.
"# sales-analytics-dashboard" 
