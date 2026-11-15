import pandas as pd


def test_sales_kpis():
    df = pd.DataFrame({
        "Sales": [100, 200, 50],
        "Profit": [20, 30, 5],
        "Order ID": ["A", "A", "B"],
        "Quantity": [1, 2, 1],
    })
    total_sales = df["Sales"].sum()
    total_profit = df["Profit"].sum()
    total_orders = df["Order ID"].nunique()
    total_qty = df["Quantity"].sum()
    margin = total_profit / total_sales * 100
    assert total_sales == 350
    assert total_profit == 55
    assert total_orders == 2
    assert total_qty == 4
    assert round(margin, 2) == 15.71


def test_profit_margin_zero_sales():
    total_sales, total_profit = 0, 0
    margin = total_profit / total_sales * 100 if total_sales else 0
    assert margin == 0
