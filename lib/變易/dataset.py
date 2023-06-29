import collections
import datetime
from typing import Optional

import pandas
from dateutil.relativedelta import relativedelta
from 變易 import fin_stmt, pera, price, revenue, security, util

securities: pandas.DataFrame
prices: pandas.DataFrame
peras: pandas.DataFrame
revenues: pandas.DataFrame
income_sheets: pandas.DataFrame
cumulate_income_sheets: pandas.DataFrame
balance_sheets: pandas.DataFrame
cash_flows: pandas.DataFrame

datatime_range: dict[str, Optional[datetime.datetime]] = {
    "max_price": None,
    "max_pera": None,
    "max_revenue": None,
    "max_fin_stmt": None,
    "min_price": None,
    "min_pera": None,
    "min_revenue": None,
    "min_fin_stmt": None,
}

_FIN_DATA_START_DT = datetime.datetime.today() - relativedelta(years=5)


def refresh_securities(connection):
    global securities
    securities = security.read_sql(conn=connection)


def refresh_prices(
    connection,
    dt: datetime.datetime = datetime.datetime.today() - relativedelta(days=10),
):
    global prices
    prices = price.read_sql(conn=connection, start_time=dt)
    datatime_range["max_price"] = max(ts for ts, code in prices.index)
    datatime_range["min_price"] = min(ts for ts, code in prices.index)


def refresh_peras(
    connection,
    dt: datetime.datetime = datetime.datetime.today() - relativedelta(days=10),
):
    global peras
    peras = pera.read_sql(conn=connection, start_time=dt)
    datatime_range["max_pera"] = max(ts for ts, code in peras.index)
    datatime_range["min_pera"] = min(ts for ts, code in peras.index)


def refresh_revenues(
    connection, dt: datetime.datetime = _FIN_DATA_START_DT - relativedelta(months=5)
):
    global revenues
    revenues = revenue.read_sql(conn=connection, start_time=dt)
    datatime_range["max_revenue"] = max(ts for ts, code in revenues.index)
    datatime_range["min_revenue"] = min(ts for ts, code in revenues.index)


def refresh_fin_stmt(connection, dt: datetime.datetime = _FIN_DATA_START_DT):
    global income_sheets, cumulate_income_sheets, balance_sheets, cash_flows
    income_sheets = fin_stmt.income_sheet.read_sql(conn=connection, start_time=dt)
    cumulate_income_sheets = fin_stmt.cumulate_income_sheet.read_sql(
        conn=connection, start_time=dt
    )
    balance_sheets = fin_stmt.balance_sheet.read_sql(conn=connection, start_time=dt)
    cash_flows = fin_stmt.cash_flow.read_sql(conn=connection, start_time=dt)
    datatime_range["max_fin_stmt"] = max(ts for ts, code in balance_sheets.index)
    datatime_range["min_fin_stmt"] = min(ts for ts, code in balance_sheets.index)


# New DB session
_connection = util.get_db_proxy().connection
# Load data from DB
refresh_securities(_connection)
refresh_prices(_connection)
refresh_peras(_connection)
refresh_revenues(_connection)
refresh_fin_stmt(_connection)
# Close DB session
_connection.close()


STOCK_COLs = ["name", "group"]
PERA_COLs = [
    "殖利率(%)",
    "股利年度",
    "本益比",
    "股價淨值比",
]  # "每股股利(註)"]
PRICE_COLs = ["收盤價", "漲跌幅(%)"]
FIN_PROFIT_COLs = [
    "淨利率（%）",
    "毛利率（%）",
    "資產報酬率（%）",
    "股東報酬率（%）",
    "負債比(%)",
]
CUST_PROFIT_COLs = ["(C)營收合計", "(C)平均月營收", "(C)合計月數"]  # from revenues
REVENUE_COLs = ["當月營收", "YoY(%)", "MoM(%)", "IsM3"]
FIN_STMT_COLs = ["本期淨利（淨損）", "YoY(%)", "MoM(%)", "IsQ3"]
EPSA_COLs = (
    [
        "(C)PER",
        "(C)EPS",
        "E(Sum)",
        "E(Avg)",
        "E(Std)",
        "E(0)",
        "E(1)",
        "E(2)",
        "E(3)",
        "外%(0)",
        "外%(1)",
        "外%(2)",
        "外%(3)",
    ]
    + FIN_PROFIT_COLs
    + [
        "毛利率(%)增加",
        "淨利率(%）增加",
        "資產報酬率(%)增加",
        "股東報酬率(%)增加",
        "負債比(%)增加",
        "普通股股本增加",
        "資產總計增加",
        "權益總額增加",
    ]
)
INCOME_SHEET_COLs = [
    "基本每股盈餘合計",
    "營業外收入及支出合計",
    "營業毛利（毛損）",
    "營業毛利（毛損）淨額",
    "本期淨利（淨損）",
    "營業收入合計",
    "繼續營業單位稅前淨利（淨損）",
    "繼續營業單位本期淨利（淨損）",
    "母公司業主（淨利／損）",
    "繼續營業單位淨利（淨損）",
    "停業單位淨利（淨損）",
]

fin_profits: pandas.DataFrame
profit_df: pandas.DataFrame
price_df: pandas.DataFrame
pera_df: pandas.DataFrame
epsa_df: pandas.DataFrame


def calculate_stmt_profits(columns=None) -> pandas.DataFrame:
    global fin_profits
    columns = columns or FIN_PROFIT_COLs + CUST_PROFIT_COLs

    # 加入月營收，以季合計，作為與損益表["營業收入合計"] 做對照
    ifrs_dated_revenues = collections.defaultdict(list)
    for (ts, code), _revenue in revenues["當月營收"].items():
        dt = ts - relativedelta(months=1)  # '2023-06-10' represent '2023-05's revenue
        ifrs_date = util.IFRSDateIter.dt_in_ifrs_dt(dt)
        ifrs_dated_revenues[(ifrs_date, code)].append(_revenue)
    values = (
        (
            ts,
            code,
            sum(_revenues),
            sum(_revenues) / len(_revenues),
            len(_revenues),
        )
        for (ts, code), _revenues in ifrs_dated_revenues.items()
    )
    tmp = pandas.DataFrame(values, columns=util.TIMED_INDEX_COLs + CUST_PROFIT_COLs)
    tmp.set_index(util.TIMED_INDEX_COLs, inplace=True)

    # 加入損益表["營業毛利（毛損）", "本期淨利（淨損）", "營業收入合計"]
    tmp = income_sheets[INCOME_SHEET_COLs].merge(tmp, on=util.TIMED_INDEX_COLs)
    tmp["毛利率（%）"] = tmp["營業毛利（毛損）"] / tmp["營業收入合計"] * 100
    tmp["淨利率（%）"] = tmp["本期淨利（淨損）"] / tmp["營業收入合計"] * 100

    # 加入資產負債表["普通股股本", "資產總計", "權益總額"]
    tmp = tmp.merge(
        balance_sheets[["普通股股本", "資產總計", "權益總額"]], on=util.TIMED_INDEX_COLs
    )
    tmp["資產報酬率（%）"] = tmp["本期淨利（淨損）"] / tmp["資產總計"] * 100
    tmp["股東報酬率（%）"] = tmp["本期淨利（淨損）"] / tmp["權益總額"] * 100
    tmp["負債比(%)"] = (tmp["資產總計"] - tmp["權益總額"]) / tmp["資產總計"] * 100

    fin_profits = tmp
    return fin_profits[columns]


def analyze_price_df():
    global price_df

    price_df = prices.loc[datatime_range["max_price"]]
    return price_df


def analyze_pera_df():
    global pera_df

    pera_df = peras.loc[datatime_range["max_pera"]]
    return pera_df


def analyze_profit_df(columns=None) -> pandas.DataFrame:
    global profit_df
    columns = columns or (
        PERA_COLs
        + [
            "每股盈餘",
            "毛利率（%）",
            "淨利率（%）",
            "資產報酬率（%）",
            "股東報酬率（%）",
            "毛利率(%)增加",
            "淨利率(%）增加",
            "資產報酬率(%)增加",
            "股東報酬率(%)增加",
            "負債比(%)增加",
            "普通股股本增加",
            "資產總計增加",
            "權益總額增加",
        ]
    )
    tmp = epsa_df.copy()
    tmp["每股盈餘"] = tmp[["E(0)", "E(1)", "E(2)", "E(3)"]].sum(axis=1)
    tmp["淨利率（%）"] = tmp[
        ["淨利率（%）", "淨利率（%）_q1", "淨利率（%）_q2", "淨利率（%）_q3"]
    ].sum(axis=1)
    tmp["毛利率（%）"] = tmp[
        ["毛利率（%）", "毛利率（%）_q1", "毛利率（%）_q2", "毛利率（%）_q3"]
    ].sum(axis=1)
    tmp["資產報酬率（%）"] = tmp[
        [
            "資產報酬率（%）",
            "資產報酬率（%）_q1",
            "資產報酬率（%）_q2",
            "資產報酬率（%）_q3",
        ]
    ].sum(axis=1)
    tmp["股東報酬率（%）"] = tmp[
        [
            "股東報酬率（%）",
            "股東報酬率（%）_q1",
            "股東報酬率（%）_q2",
            "股東報酬率（%）_q3",
        ]
    ].sum(axis=1)

    profit_df = tmp
    return profit_df[columns]


def analyze_epsa_df(columns=None) -> pandas.DataFrame:
    global epsa_df
    columns = columns or (PRICE_COLs + PERA_COLs + EPSA_COLs)

    latest_ifrs_ts = datatime_range["max_fin_stmt"]
    year, quarter = util.IFRSDateIter.ifrs_dt2quarter(latest_ifrs_ts)

    ifrs_iter = util.IFRSDateIter(year, quarter)
    q0_ts = ifrs_iter.current_ifrs_dt()

    # Based on pera_df
    # merge income_sheets["本期淨利（淨損）", "基本每股盈餘合計", "營業外收入及支出合計"] from `fin_profits_df`
    fin_profits
    tmp = pera_df.merge(
        fin_profits.loc[q0_ts],
        on=[util.SECURITY_ID_NAME],
        how="left",
        suffixes=("", ""),
    )
    tmp = tmp.merge(
        fin_profits.loc[ifrs_iter.previous_ifrs_dt()],
        on=[util.SECURITY_ID_NAME],
        how="left",
        suffixes=("", "_q1"),
    )
    tmp = tmp.merge(
        fin_profits.loc[ifrs_iter.previous_ifrs_dt()],
        on=[util.SECURITY_ID_NAME],
        how="left",
        suffixes=("", "_q2"),
    )
    tmp = tmp.merge(
        fin_profits.loc[ifrs_iter.previous_ifrs_dt()],
        on=[util.SECURITY_ID_NAME],
        how="left",
        suffixes=("", "_q3"),
    )
    tmp = tmp.merge(
        fin_profits.loc[ifrs_iter.previous_ifrs_dt()],
        on=[util.SECURITY_ID_NAME],
        how="left",
        suffixes=("", "_q4"),
    )
    column_map = {
        "基本每股盈餘合計": "E(0)",
        "基本每股盈餘合計_q1": "E(1)",
        "基本每股盈餘合計_q2": "E(2)",
        "基本每股盈餘合計_q3": "E(3)",
        "基本每股盈餘合計_q4": "E(4)",
        "營業外收入及支出合計": "外(0)",
        "營業外收入及支出合計_q1": "外(1)",
        "營業外收入及支出合計_q2": "外(2)",
        "營業外收入及支出合計_q3": "外(3)",
        "營業外收入及支出合計_q4": "外(4)",
    }
    tmp.rename(columns=column_map, inplace=True)
    tmp["E(Avg)"] = tmp[["E(0)", "E(1)", "E(2)", "E(3)"]].mean(axis=1)
    tmp["E(Std)"] = tmp[["E(0)", "E(1)", "E(2)", "E(3)"]].std(axis=1)
    tmp["E(Sum)"] = tmp[["E(0)", "E(1)", "E(2)", "E(3)"]].sum(axis=1)

    # 業外收入
    tmp["外%(0)"] = tmp["外(0)"] / tmp["本期淨利（淨損）"] * 100
    tmp["外%(1)"] = tmp["外(1)"] / tmp["本期淨利（淨損）_q1"] * 100
    tmp["外%(2)"] = tmp["外(2)"] / tmp["本期淨利（淨損）_q2"] * 100
    tmp["外%(3)"] = tmp["外(3)"] / tmp["本期淨利（淨損）_q3"] * 100

    # (C)EPS
    tmp["(C)EPS"] = tmp["本期淨利（淨損）"] / tmp["普通股股本"] * 10
    # (C)PER
    tmp = append_price_info(tmp)
    tmp["(C)PER"] = tmp["收盤價"] / (tmp["(C)EPS"] * 4)

    tmp["毛利率(%)增加"] = tmp["毛利率（%）_q1"] - tmp["毛利率（%）_q1"]
    tmp["淨利率(%）增加"] = tmp["淨利率（%）_q1"] - tmp["淨利率（%）_q1"]
    tmp["資產報酬率(%)增加"] = tmp["資產報酬率（%）"] - tmp["資產報酬率（%）_q1"]
    tmp["股東報酬率(%)增加"] = tmp["股東報酬率（%）"] - tmp["股東報酬率（%）_q1"]
    tmp["負債比(%)增加"] = tmp["負債比(%)"] - tmp["負債比(%)_q1"]

    tmp["普通股股本增加"] = tmp["普通股股本"] - tmp["普通股股本_q1"]
    tmp["資產總計增加"] = tmp["資產總計"] - tmp["資產總計_q1"]
    tmp["權益總額增加"] = tmp["權益總額"] - tmp["權益總額_q1"]

    epsa_df = tmp
    return epsa_df[columns]


def append_stock_info(df: pandas.DataFrame) -> pandas.DataFrame:
    return securities[STOCK_COLs].merge(df, on=[util.SECURITY_ID_NAME], how="right")


def append_price_info(df: pandas.DataFrame) -> pandas.DataFrame:
    return price_df[PRICE_COLs].merge(
        df,
        on=[util.SECURITY_ID_NAME],
        how="right",
    )


def reverse_df_index(df: pandas.DataFrame) -> pandas.DataFrame:
    tmp = df.reset_index()
    tmp.set_index(list(df.index.names)[::-1], inplace=True)
    return tmp


calculate_stmt_profits()
analyze_price_df()
analyze_pera_df()
analyze_epsa_df()
analyze_profit_df()
