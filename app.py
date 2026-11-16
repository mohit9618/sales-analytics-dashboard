import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(
    page_title="Sales Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------- Data utilities -----------------------------
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trim column names and normalize whitespace without changing their meaning."""
    result = df.copy()
    result.columns = [str(col).strip().replace("\n", " ") for col in result.columns]
    return result


def read_uploaded_file(uploaded_file) -> pd.DataFrame:
    """Read CSV, Excel, or JSON uploads with useful validation errors."""
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        elif name.endswith(".xlsx"):
            df = pd.read_excel(uploaded_file, engine="openpyxl")
        elif name.endswith(".json"):
            payload = json.load(uploaded_file)
            if isinstance(payload, list):
                df = pd.json_normalize(payload)
            elif isinstance(payload, dict):
                # Accept either a list stored under a top-level key or a single record.
                list_values = [value for value in payload.values() if isinstance(value, list)]
                df = pd.json_normalize(list_values[0]) if list_values else pd.json_normalize(payload)
            else:
                raise ValueError("JSON must contain an object or a list of records.")
        else:
            raise ValueError("Unsupported file type. Upload CSV, XLSX, or JSON.")
    except Exception as exc:
        raise ValueError(f"Could not read the uploaded file: {exc}") from exc

    df = normalize_columns(df)
    if df.empty:
        raise ValueError("The uploaded file contains no data rows.")
    if len(df.columns) == 0:
        raise ValueError("The uploaded file does not contain any columns.")
    if df.columns.duplicated().any():
        duplicates = df.columns[df.columns.duplicated()].tolist()
        raise ValueError(f"Duplicate column names found: {duplicates}")
    return df


def find_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Find a column by case-insensitive exact candidate name."""
    lookup = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def clean_data(df: pd.DataFrame, missing_strategy: str, duplicate_strategy: str) -> tuple[pd.DataFrame, dict]:
    """Clean duplicates, whitespace, numeric fields, and date-like columns."""
    clean = df.copy()
    stats = {
        "duplicate_rows_found": int(clean.duplicated().sum()),
        "missing_cells_before": int(clean.isna().sum().sum()),
        "date_columns_converted": [],
        "numeric_columns_converted": [],
    }

    # Normalize text values and common representations of missing data.
    for col in clean.select_dtypes(include=["object", "string"]).columns:
        clean[col] = clean[col].astype("string").str.strip()
        clean[col] = clean[col].replace(
            {"": pd.NA, "NA": pd.NA, "N/A": pd.NA, "null": pd.NA, "None": pd.NA}
        )

    if duplicate_strategy == "Remove duplicates":
        clean = clean.drop_duplicates()

    # Convert likely date columns only when most non-null values parse successfully.
    for col in clean.columns:
        col_name = str(col).lower()
        if any(token in col_name for token in ["date", "time"]):
            parsed = pd.to_datetime(clean[col], errors="coerce", dayfirst=False)
            non_null = clean[col].notna().sum()
            if non_null and parsed.notna().sum() / non_null >= 0.7:
                clean[col] = parsed
                stats["date_columns_converted"].append(col)

    # Convert numeric-looking object columns when conversion is largely successful.
    for col in clean.select_dtypes(include=["object", "string"]).columns:
        converted = pd.to_numeric(
            clean[col].astype("string").str.replace(",", "", regex=False).str.replace("$", "", regex=False),
            errors="coerce",
        )
        non_null = clean[col].notna().sum()
        if non_null and converted.notna().sum() / non_null >= 0.85:
            clean[col] = converted
            stats["numeric_columns_converted"].append(col)

    if missing_strategy == "Drop rows with missing values":
        clean = clean.dropna()
    elif missing_strategy == "Fill numeric with median; text with mode":
        for col in clean.columns:
            if pd.api.types.is_numeric_dtype(clean[col]):
                median = clean[col].median()
                clean[col] = clean[col].fillna(median if pd.notna(median) else 0)
            else:
                mode = clean[col].mode(dropna=True)
                if not mode.empty:
                    clean[col] = clean[col].fillna(mode.iloc[0])

    stats["missing_cells_after"] = int(clean.isna().sum().sum())
    stats["rows_after_cleaning"] = int(len(clean))
    return clean, stats


def numeric_series(df: pd.DataFrame, col: Optional[str]) -> pd.Series:
    if not col or col not in df.columns:
        return pd.Series(dtype="float64", index=df.index)
    series = pd.to_numeric(df[col], errors="coerce")
    return series.replace([np.inf, -np.inf], np.nan).fillna(0)


@st.cache_data(ttl=3600, show_spinner=False)
def get_exchange_rate(target_currency: str) -> tuple[float, str]:
    """Get the latest reference rate for converting INR to the selected currency."""
    if target_currency == "INR":
        return 1.0, "INR base currency"

    url = f"https://api.frankfurter.dev/v2/rate/inr/{target_currency.lower()}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    payload = response.json()
    return float(payload["rate"]), str(payload.get("date", "Latest available rate"))


def calculate_kpis(df: pd.DataFrame, sales_col: Optional[str], profit_col: Optional[str],
                   order_col: Optional[str], quantity_col: Optional[str]) -> dict:
    """Reusable KPI calculation function."""
    total_sales = float(numeric_series(df, sales_col).sum()) if sales_col else None
    total_profit = float(numeric_series(df, profit_col).sum()) if profit_col else None
    total_quantity = float(numeric_series(df, quantity_col).sum()) if quantity_col else None
    total_orders = int(df[order_col].nunique(dropna=True)) if order_col and order_col in df else None
    margin = ((total_profit / total_sales * 100)
              if total_sales not in (None, 0) and total_profit is not None else None)
    return {
        "Total Sales": total_sales,
        "Total Profit": total_profit,
        "Total Orders": total_orders,
        "Total Quantity Sold": total_quantity,
        "Profit Margin (%)": margin,
    }


def format_money(value: float, currency_symbol: str) -> str:
    return f"{currency_symbol}{value:,.2f}"


# ----------------------------- Interface -----------------------------
st.title("Sales Analytics Dashboard")
st.caption("Upload retail data, validate and clean it, filter records, and explore interactive sales insights.")

with st.sidebar:
    st.header("1. Upload data")
    uploaded = st.file_uploader("Choose a CSV, Excel (.xlsx), or JSON file",
                                type=["csv", "xlsx", "json"])
    st.divider()
    st.header("2. Cleaning options")
    duplicate_strategy = st.selectbox("Duplicate records", ["Keep all records", "Remove duplicates"])
    missing_strategy = st.selectbox(
        "Missing-value handling",
        ["Keep missing values", "Fill numeric with median; text with mode", "Drop rows with missing values"],
    )
    currency_options = {
        "INR (₹) - Indian Rupee": ("INR", "₹"),
        "USD ($) - US Dollar": ("USD", "$"),
        "EUR (€) - Euro": ("EUR", "€"),
        "GBP (£) - British Pound": ("GBP", "£"),
    }
    selected_currency = st.selectbox("Display currency", list(currency_options.keys()))
    target_currency, currency_symbol = currency_options[selected_currency]

if uploaded is None:
    st.info("Upload a sales dataset to begin. The dashboard works best when the file contains fields such as Sales, Profit, Order ID, Quantity, Date, Region, and Category.")
    st.subheader("Supported formats")
    st.write("CSV (.csv) · Excel (.xlsx) · JSON (.json)")
    st.stop()

try:
    raw_df = read_uploaded_file(uploaded)
    df, cleaning_stats = clean_data(raw_df, missing_strategy, duplicate_strategy)
except Exception as exc:
    st.error(str(exc))
    st.stop()

if df.empty:
    st.error("No rows remain after cleaning. Change the cleaning options and try again.")
    st.stop()

# Resolve common sales schema variants; user can override each mapping.
st.header("Data validation")
info_cols = st.columns(4)
info_cols[0].metric("Rows", f"{len(raw_df):,}")
info_cols[1].metric("Columns", f"{raw_df.shape[1]:,}")
info_cols[2].metric("Duplicate rows", f"{cleaning_stats['duplicate_rows_found']:,}")
info_cols[3].metric("Missing cells", f"{cleaning_stats['missing_cells_before']:,}")

with st.expander("Column names, data types, and missing values", expanded=True):
    schema = pd.DataFrame({
        "Column": raw_df.columns,
        "Data type": raw_df.dtypes.astype(str).values,
        "Missing values": raw_df.isna().sum().values,
        "Missing (%)": (raw_df.isna().mean().values * 100).round(2),
    })
    st.dataframe(schema, use_container_width=True, hide_index=True)
    st.caption(f"Original dimensions: {raw_df.shape[0]} rows × {raw_df.shape[1]} columns. Cleaned dimensions: {df.shape[0]} rows × {df.shape[1]} columns.")
    st.dataframe(raw_df.head(10), use_container_width=True)

st.subheader("Preprocessing summary")
st.write({
    "Duplicate rows found": cleaning_stats["duplicate_rows_found"],
    "Missing cells before cleaning": cleaning_stats["missing_cells_before"],
    "Missing cells after cleaning": cleaning_stats["missing_cells_after"],
    "Date columns converted": cleaning_stats["date_columns_converted"],
    "Numeric columns converted": cleaning_stats["numeric_columns_converted"],
    "Rows after cleaning": cleaning_stats["rows_after_cleaning"],
})

# Column mapping makes the dashboard usable with varying column names.
st.header("Analysis configuration")
all_cols = ["(Not available)"] + list(df.columns)
def choose_col(label: str, candidates: list[str]):
    detected = find_column(df, candidates)
    options = all_cols
    default = options.index(detected) if detected in options else 0
    selected = st.selectbox(label, options, index=default)
    return None if selected == "(Not available)" else selected

map1, map2, map3 = st.columns(3)
with map1:
    sales_col = choose_col("Sales column", ["Sales", "Total Sales", "Revenue", "Amount"])
    profit_col = choose_col("Profit column", ["Profit", "Total Profit", "Net Profit"])
with map2:
    order_col = choose_col("Order ID column", ["Order ID", "Order_ID", "OrderID", "Invoice"])
    quantity_col = choose_col("Quantity column", ["Quantity", "Qty", "Units Sold"])
with map3:
    date_col = choose_col("Date column", ["Order Date", "Date", "Sales Date", "Datetime"])
    region_col = choose_col("Region / location filter", ["Region", "State", "City", "Country", "Market"])
    category_col = choose_col("Category filter", ["Category", "Product Category", "Sub-Category", "Product", "Family"])

# At least three interactive filters. Date, categorical and numeric filters are conditional on available fields.
st.header("Interactive filters")
filtered = df.copy()
filter_cols = st.columns(3)

with filter_cols[0]:
    if date_col and pd.api.types.is_datetime64_any_dtype(df[date_col]):
        valid_dates = df[date_col].dropna()
        if not valid_dates.empty:
            start_date, end_date = st.date_input(
                "Date range",
                value=(valid_dates.min().date(), valid_dates.max().date()),
                min_value=valid_dates.min().date(),
                max_value=valid_dates.max().date(),
            )
            filtered = filtered[
                filtered[date_col].notna()
                & (filtered[date_col].dt.date >= start_date)
                & (filtered[date_col].dt.date <= end_date)
            ]
        else:
            st.caption("Date column has no valid dates.")
    else:
        st.caption("Date filter: map a valid date column above.")

with filter_cols[1]:
    if region_col:
        vals = sorted(df[region_col].dropna().astype(str).unique().tolist())
        chosen = st.multiselect("Region / location", vals, default=vals)
        filtered = filtered[filtered[region_col].astype(str).isin(chosen)]
    else:
        st.caption("Region filter: map a region/location column above.")

with filter_cols[2]:
    if category_col:
        vals = sorted(df[category_col].dropna().astype(str).unique().tolist())
        chosen = st.multiselect("Category / product", vals, default=vals)
        filtered = filtered[filtered[category_col].astype(str).isin(chosen)]
    else:
        st.caption("Category filter: map a category/product column above.")

# Optional fourth filter if a numeric measure exists.
numeric_options = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
if numeric_options:
    selected_measure = st.selectbox("Optional numeric range filter", ["None"] + numeric_options)
    if selected_measure != "None":
        low = float(df[selected_measure].min())
        high = float(df[selected_measure].max())
        if low < high:
            selected_range = st.slider("Select numeric range", min_value=low, max_value=high,
                                       value=(low, high))
            filtered = filtered[filtered[selected_measure].between(*selected_range)]

# Convert only the analysis copy. The original cleaned data remains in INR.
try:
    exchange_rate, exchange_rate_date = get_exchange_rate(target_currency)
except (requests.RequestException, KeyError, ValueError) as exc:
    st.error(f"Could not fetch the {target_currency} exchange rate. Please try again later. Details: {exc}")
    st.stop()

analysis_df = filtered.copy()
for money_col in [sales_col, profit_col]:
    if money_col and money_col in analysis_df.columns:
        analysis_df[money_col] = numeric_series(analysis_df, money_col) * exchange_rate

st.caption(
    f"Currency conversion: 1 INR = {exchange_rate:.6g} {target_currency} "
    f"(reference rate dated {exchange_rate_date})."
)

st.header("Key performance indicators")
kpis = calculate_kpis(analysis_df, sales_col, profit_col, order_col, quantity_col)
kpi_cols = st.columns(5)
kpi_cols[0].metric("Total Sales", format_money(kpis["Total Sales"], currency_symbol) if kpis["Total Sales"] is not None else "N/A")
kpi_cols[1].metric("Total Profit", format_money(kpis["Total Profit"], currency_symbol) if kpis["Total Profit"] is not None else "N/A")
kpi_cols[2].metric("Total Orders", f"{kpis['Total Orders']:,}" if kpis["Total Orders"] is not None else "N/A")
kpi_cols[3].metric("Total Quantity Sold", f"{kpis['Total Quantity Sold']:,.0f}" if kpis["Total Quantity Sold"] is not None else "N/A")
kpi_cols[4].metric("Profit Margin", f"{kpis['Profit Margin (%)']:.2f}%" if kpis["Profit Margin (%)"] is not None else "N/A")

if not sales_col:
    st.warning("Map a Sales column to calculate meaningful sales KPIs and sales charts.")
if not profit_col:
    st.warning("Map a Profit column to calculate Total Profit and Profit Margin.")
if not order_col:
    st.warning("Map an Order ID column to calculate unique Total Orders.")
if not quantity_col:
    st.warning("Map a Quantity column to calculate Total Quantity Sold.")

st.header("Interactive visualizations")
if filtered.empty:
    st.warning("No records match the selected filters.")
elif not sales_col:
    st.info("Select a Sales column in Analysis configuration to enable the sales visualizations.")
else:
    tab1, tab2, tab3 = st.tabs(["Sales trend", "Sales breakdown", "Profit analysis"])

    with tab1:
        if date_col and pd.api.types.is_datetime64_any_dtype(filtered[date_col]):
            trend = analysis_df.dropna(subset=[date_col]).groupby(date_col, as_index=False)[sales_col].sum()
            fig = px.line(trend, x=date_col, y=sales_col, markers=True,
                          title="Sales over time", labels={sales_col: f"Sales ({currency_symbol})", date_col: "Date"})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Map a valid date column to display the sales trend.")
        if category_col:
            cat_sales = analysis_df.groupby(category_col, as_index=False)[sales_col].sum().sort_values(sales_col, ascending=False)
            fig = px.bar(cat_sales, x=category_col, y=sales_col, title="Sales by category",
                         labels={sales_col: f"Sales ({currency_symbol})"})
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        dimension = region_col or category_col
        if dimension:
            grouped = analysis_df.groupby(dimension, as_index=False)[sales_col].sum().sort_values(sales_col, ascending=False)
            fig = px.pie(grouped, names=dimension, values=sales_col, hole=0.35,
                         title=f"Sales share by {dimension} ({currency_symbol})")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Map a Region or Category column to show a sales breakdown.")
        if quantity_col:
            qty_by_dim = filtered.groupby(dimension, as_index=False)[quantity_col].sum() if dimension else pd.DataFrame()
            if not qty_by_dim.empty:
                fig = px.bar(qty_by_dim, x=dimension, y=quantity_col, title=f"Quantity sold by {dimension}")
                st.plotly_chart(fig, use_container_width=True)

    with tab3:
        if profit_col:
            if category_col:
                prof = analysis_df.groupby(category_col, as_index=False)[profit_col].sum()
                fig = px.bar(prof, x=category_col, y=profit_col, title="Profit by category",
                             labels={profit_col: f"Profit ({currency_symbol})"})
                st.plotly_chart(fig, use_container_width=True)
            if sales_col:
                scatter = analysis_df[[sales_col, profit_col]].copy()
                fig = px.scatter(scatter, x=sales_col, y=profit_col,
                                 title=f"Sales vs. Profit ({currency_symbol})", opacity=0.65)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Map a Profit column to display profit analysis.")

st.divider()
st.subheader("Download cleaned and filtered data")
csv_bytes = filtered.to_csv(index=False).encode("utf-8")
st.download_button("Download filtered data as CSV", data=csv_bytes,
                   file_name="cleaned_filtered_sales.csv", mime="text/csv")
st.caption("KPIs and monetary charts update with the selected display currency. Downloads remain in the original INR values.")
