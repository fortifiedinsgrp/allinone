import streamlit as st
import pygsheets
import pandas as pd
import tempfile
import json
import re
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="📊 Fortified Agency Metrics (FAM)", layout="wide")

# --------------------------------------------------
# Password protection
# --------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Fortified Agency Metrics (FAM)")
    password = st.text_input("Enter password:", type="password")
    if password == "SalesTeam2024":
        st.session_state.authenticated = True
        st.rerun()
    else:
        if password:
            st.error("❌ Incorrect password")
        st.stop()

# --------------------------------------------------
# Google Sheets setup
# --------------------------------------------------
@st.cache_data(ttl=3600)
def connect_to_google_sheets():
    creds = st.secrets["gcp_service_account"]
    tmp = tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False)
    json.dump(creds, tmp)
    tmp.flush()
    return pygsheets.authorize(service_account_file=tmp.name)

@st.cache_data(ttl=3600)
def load_agency_totals():
    gc = connect_to_google_sheets()
    sheet = gc.open('Combined Call Sales & Agency Analysis Reports')
    wks = sheet.worksheet_by_title('Daily AgencY Totals')
    df = wks.get_as_df()
    df = df.loc[:, ~df.columns.duplicated(keep='first')]
    df = df.loc[:, df.columns.notna()]
    df = df.loc[:, df.columns != '']
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    return df

@st.cache_data(ttl=3600)
def load_campaign_data():
    gc = connect_to_google_sheets()
    sheet = gc.open('Combined Call Sales & Agency Analysis Reports')
    wks = sheet.worksheet_by_title('Daily Lead Vendor Totals')
    df = wks.get_as_df()
    df = df.loc[:, ~df.columns.duplicated(keep='first')]
    df = df.loc[:, df.columns.notna()]
    df = df.loc[:, df.columns != '']
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    return df

@st.cache_data(ttl=3600)
def load_agent_data():
    gc = connect_to_google_sheets()
    sheet = gc.open('Combined Call Sales & Agency Analysis Reports')
    wks = sheet.worksheet_by_title('Daily AgenT Totals')
    df = wks.get_as_df()
    df = df.loc[:, ~df.columns.duplicated(keep='first')]
    df = df.loc[:, df.columns.notna()]
    df = df.loc[:, df.columns != '']
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    return df


def clean_numeric(df, columns):
    for col in columns:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(r"[^\d.]", "", regex=True)
                .replace("", "0")
            )
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df

def calculate_campaign_metrics(df, agency=None):
    if agency and agency != "All":
        df = df[df["Agency"] == agency]

    grouped = df.groupby("Campaign").agg({
        "Revenue": ["sum", "mean"],
        "Lead Cost": ["sum", "mean"],
        "Total Calls": "sum",
        "Paid Calls": "sum",
        "# Unique Sales": "sum",
        "Date": "count"
    })

    grouped.columns = [
        "Total_Revenue", "Avg_Daily_Revenue",
        "Total_Cost", "Avg_Daily_Cost",
        "Total_Calls", "Total_Paid_Calls",
        "Total_Sales", "Days_Active"
    ]

    grouped["ROAS"] = grouped["Total_Revenue"] / grouped["Total_Cost"].replace(0, 1)
    grouped["Cost_Per_Call"] = grouped["Total_Cost"] / grouped["Total_Paid_Calls"].replace(0, 1)
    grouped["Revenue_Per_Call"] = grouped["Total_Revenue"] / grouped["Total_Calls"].replace(0, 1)
    grouped["Conversion_Rate"] = grouped["Total_Sales"] / grouped["Total_Calls"].replace(0, 1) * 100
    grouped["Profit_Per_Call"] = grouped["Revenue_Per_Call"] - grouped["Cost_Per_Call"]

    return grouped

def optimize_budget(campaign_stats, daily_budget, min_calls=1, min_roas=1.0):
    profitable = campaign_stats[campaign_stats["ROAS"] >= min_roas].copy()
    if profitable.empty:
        return None, daily_budget

    profitable = profitable.sort_values("Profit_Per_Call", ascending=False)
    allocation = {}
    remaining_budget = daily_budget

    for campaign in profitable.index:
        cost = profitable.loc[campaign, "Cost_Per_Call"]
        if remaining_budget >= cost * min_calls:
            allocation[campaign] = min_calls
            remaining_budget -= cost * min_calls

    while remaining_budget > 0:
        allocated = False
        for campaign in profitable.index:
            cost = profitable.loc[campaign, "Cost_Per_Call"]
            avg_daily = profitable.loc[campaign, "Total_Calls"] / profitable.loc[campaign, "Days_Active"]
            max_calls = avg_daily * 1.5
            if allocation.get(campaign, 0) < max_calls:
                if remaining_budget >= cost:
                    allocation[campaign] = allocation.get(campaign, 0) + 1
                    remaining_budget -= cost
                    allocated = True
                    break
        if not allocated:
            break

    return allocation, remaining_budget

# --------------------------------------------------
# UI Header & View Toggle
# --------------------------------------------------
st.markdown("# 📊 Welcome to Fortified Agency Metrics (FAM)")
st.markdown("### What would you like to research today?")
view_mode = st.radio(
    label="",
    options=["🏠 Home", "💰 Budget Optimizer", "🧑‍💼 Agent Performance", "📊 Campaign Performance"],
    horizontal=True
)

# --------------------------------------------------
# HOME: WTD Profit Bar Chart
# --------------------------------------------------
if view_mode == "🏠 Home":
    df_agency = load_agency_totals()
    df_agency = clean_numeric(df_agency, ["Profit"])
    df_agency = df_agency.rename(columns={"Agency Name": "Agency"})
    df_agency = df_agency[df_agency["Agency"].str.strip().str.lower() != "try again"]

    today = datetime.now().date()
    sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    df_wtd = df_agency[df_agency["Date"].dt.date >= sunday]

    wtd_totals = (
        df_wtd.groupby("Agency")["Profit"]
        .sum()
        .reset_index()
        .sort_values("Profit", ascending=False)
    )

    fig = px.bar(
        wtd_totals,
        x="Agency",
        y="Profit",
        color="Agency",
        text=wtd_totals["Profit"].apply(lambda x: f"${x:,.0f}"),
        title=f"Week-to-Date Profit by Agency (Sunday to {today.strftime('%A')})",
        labels={"Profit": "Total Profit ($)", "Agency": "Agency"}
    )
    fig.update_traces(textposition="outside", width=0.4)
    fig.update_layout(bargap=0.35, plot_bgcolor='white', showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

# --------------------------------------------------
# BUDGET OPTIMIZER
elif view_mode == "💰 Budget Optimizer":
    st.markdown("### 💰 Budget Optimizer")

    df = load_campaign_data()
    numeric_cols = ['Revenue', 'Lead Cost', '# Unique Sales', 'Total Calls', 'Paid Calls']
    df = clean_numeric(df, numeric_cols)
    df = df[df["Agency"].str.strip().str.lower() != "try again"]

    with st.sidebar:
        st.header("⚙️ Optimizer Settings")
        date_options = [7, 14, 30, 90]
        selected_days = st.selectbox("Analysis Period", date_options, index=2, format_func=lambda x: f"Last {x} days")
        cutoff = datetime.now() - timedelta(days=selected_days)
        df = df[df["Date"] >= cutoff]

        agencies = ["All"] + sorted(df["Agency"].dropna().unique())
        selected_agency = st.selectbox("Select Agency", agencies)

        daily_budget = st.number_input("Daily Budget ($)", min_value=100, max_value=50000, value=5000, step=100)
        min_roas = st.slider("Minimum ROAS", min_value=0.5, max_value=5.0, value=1.0, step=0.1)

    with st.spinner("Optimizing budget allocation..."):
        stats = calculate_campaign_metrics(df, selected_agency)
        allocation, leftover = optimize_budget(stats, daily_budget, min_roas=min_roas)

        if allocation:
            result_rows = []
            total_revenue = 0
            total_cost = 0

            for campaign, calls in allocation.items():
                cost = stats.loc[campaign, "Cost_Per_Call"]
                revenue = stats.loc[campaign, "Revenue_Per_Call"]
                budget = calls * cost
                expected_revenue = calls * revenue
                roi = (expected_revenue / budget - 1) * 100 if budget else 0

                total_revenue += expected_revenue
                total_cost += budget

                result_rows.append({
                    "Campaign": campaign,
                    "Recommended Calls": calls,
                    "Budget": f"${budget:,.2f}",
                    "Expected Revenue": f"${expected_revenue:,.2f}",
                    "ROAS": f"{stats.loc[campaign, 'ROAS']:.2f}",
                    "ROI %": f"{roi:.1f}%"
                })

            st.success(f"✅ Expected ROAS: {total_revenue / total_cost:.2f}")

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Budget", f"${total_cost:,.2f}")
            col2.metric("Expected Revenue", f"${total_revenue:,.2f}")
            col3.metric("Expected Profit", f"${total_revenue - total_cost:,.2f}")

            results_df = pd.DataFrame(result_rows)
            st.dataframe(results_df, use_container_width=True)

            csv = results_df.to_csv(index=False)
            st.download_button("📥 Download Allocation CSV", csv, "budget_allocation.csv", "text/csv")
        else:
            st.warning("No campaigns meet the ROAS threshold.")

# --------------------------------------------------
# CAMPAIGN PERFORMANCE
elif view_mode == "📊 Campaign Performance":
    st.markdown("### 📊 Campaign Performance")

    df_campaign = load_campaign_data()
    numeric_cols = ['Revenue', 'Lead Cost', '# Unique Sales']
    df_campaign = clean_numeric(df_campaign, numeric_cols)
    df_campaign = df_campaign[df_campaign["Agency"].str.strip().str.lower() != "try again"]

    with st.sidebar:
        st.header("📊 Campaign Filters")
        date_options = [7, 14, 30, 90]
        selected_days = st.selectbox("Analysis Period", date_options, index=2, format_func=lambda x: f"Last {x} days")
        cutoff = datetime.now() - timedelta(days=selected_days)
        df_campaign = df_campaign[df_campaign["Date"] >= cutoff]

        agencies = ["All"] + sorted(df_campaign["Agency"].dropna().unique())
        selected_agency = st.selectbox("Select Agency", agencies)
        if selected_agency != "All":
            df_campaign = df_campaign[df_campaign["Agency"] == selected_agency]

        campaigns = ["All"] + sorted(df_campaign["Campaign"].dropna().unique())
        selected_campaign = st.selectbox("Select Campaign", campaigns)
        if selected_campaign != "All":
            df_campaign = df_campaign[df_campaign["Campaign"] == selected_campaign]

    total_revenue = df_campaign['Revenue'].sum()
    total_cost = df_campaign['Lead Cost'].sum()
    total_sales = df_campaign['# Unique Sales'].sum()
    roas = total_revenue / (total_cost if total_cost else 1)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Total Revenue", f"${total_revenue:,.2f}")
    col2.metric("💸 Total Cost", f"${total_cost:,.2f}")
    col3.metric("📈 ROAS", f"{roas:.2f}")
    col4.metric("🛒 Total Sales", f"{int(total_sales)}")

    if selected_campaign != "All":
        df_selected = df_campaign.sort_values("Date").copy()
        df_selected["ROAS"] = df_selected["Revenue"] / df_selected["Lead Cost"].replace(0, 1)

        fig_line = px.line(
            df_selected,
            x="Date",
            y="ROAS",
            title=f"ROAS Over Time – {selected_campaign}",
            labels={"ROAS": "Return on Ad Spend"}
        )
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("⬅️ Select a specific campaign to view daily ROAS trend.")

# --------------------------------------------------
# Agent Performance
elif view_mode == "🧑‍💼 Agent Performance":
    st.markdown("### 🧑‍💼 Agent Performance Dashboard")

    df_agents = load_agent_data()
    df_agents = df_agents[
        ~df_agents["Agency"].str.strip().str.lower().isin(["no agency found", "termed ee"])
    ]
    df_agents = clean_numeric(df_agents, [
        "Revenue", "Profit", "Lead Spend", "Closing Ratio", "Agent Profitability"
    ])

    with st.sidebar:
        st.header("🎯 Agent Filters")

        # Date range selection
        date_mode = st.radio("Date Range Mode", ["Last 7 Days", "Last 14 Days", "Last 30 Days", "Last 90 Days", "Custom"])
        if date_mode == "Custom":
            start_date = st.date_input("Start Date", value=datetime.now().date() - timedelta(days=7))
            end_date = st.date_input("End Date", value=datetime.now().date())
            df_agents = df_agents[(df_agents["Date"].dt.date >= start_date) & (df_agents["Date"].dt.date <= end_date)]
        else:
            days_back = int(date_mode.split()[1])
            cutoff = datetime.now() - timedelta(days=days_back)
            df_agents = df_agents[df_agents["Date"] >= cutoff]

        agencies = ["All"] + sorted(df_agents["Agency"].dropna().unique())
        selected_agency = st.selectbox("Select Agency", agencies)
        if selected_agency != "All":
            df_agents = df_agents[df_agents["Agency"] == selected_agency]

        agents = sorted(df_agents["Agent Name"].dropna().unique())
        selected_agents = st.multiselect("Select Agents", agents, default=agents)
        if selected_agents:
            df_agents = df_agents[df_agents["Agent Name"].isin(selected_agents)]

    # Group and aggregate
    grouped = df_agents.groupby(["Agent Name", "Agency"]).agg({
        "Revenue": "sum",
        "Profit": "sum",
        "Lead Spend": "sum",
        "Closing Ratio": "mean",
        "Agent Profitability": "sum"
    }).reset_index()

    # KPIs
    total_revenue = grouped["Revenue"].sum()
    total_profit = grouped["Profit"].sum()
    total_lead_spend = grouped["Lead Spend"].sum()
    avg_closing_ratio = grouped["Closing Ratio"].mean()
    total_agent_profitability = grouped["Agent Profitability"].sum()

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Revenue", f"${total_revenue:,.2f}")
    col2.metric("Total Lead Spend", f"${total_lead_spend:,.2f}")
    col3.metric("Total Profit", f"${total_profit:,.2f}")
    col4.metric("Avg. Closing Ratio", f"{avg_closing_ratio:.2f}%")
    col5.metric("Total Agent Profitability", f"${total_agent_profitability:,.2f}")

    # Sort controls
    st.markdown("### 📊 Top Agents by Selected Metric")
    metric_options = ["Closing Ratio", "Revenue", "Lead Spend", "Profit", "Agent Profitability"]
    selected_metric = st.selectbox("Sort by", metric_options, index=4)
    sort_order = st.radio("Sort Order", ["Descending", "Ascending"], horizontal=True)
    ascending = sort_order == "Ascending"

    # Bar Chart: Top 5 agents (numerically sorted)
    top5 = grouped.sort_values(by=selected_metric, ascending=ascending).head(5)
    fig = px.bar(
        top5,
        x=selected_metric,
        y="Agent Name",
        orientation="h",
        title=f"Top 5 Agents by {selected_metric}",
        labels={"Agent Name": "Agent"},
        color="Agency"
    )
    fig.update_layout(yaxis=dict(categoryorder='total ascending' if ascending else 'total descending'))
    st.plotly_chart(fig, use_container_width=True)

    # Sort then format table
    st.markdown("### 📄 Agent Performance Table")
    display_df = grouped.sort_values(by=selected_metric, ascending=ascending).copy()
    display_df["Revenue"] = display_df["Revenue"].map("${:,.2f}".format)
    display_df["Profit"] = display_df["Profit"].map("${:,.2f}".format)
    display_df["Lead Spend"] = display_df["Lead Spend"].map("${:,.2f}".format)
    display_df["Agent Profitability"] = display_df["Agent Profitability"].map("${:,.2f}".format)
    display_df["Closing Ratio"] = display_df["Closing Ratio"].map("{:.2f}%".format)

    st.dataframe(display_df, use_container_width=True)
