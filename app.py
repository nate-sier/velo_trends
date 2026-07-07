"""
FB Velo × CI — Streamlit deployment-ready dashboard.

For every selected date window, each matched pitcher gets:
  * The last ytd_fb_velo available inside that window
  * The mean raw concentric impulse from Jump Data inside that same window

Pitchers whose last in-window ytd_fb_velo is below 85 mph are excluded.
"""
from __future__ import annotations

import html
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import gspread
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
DEFAULT_SHEET_ID = "1CF2n3fAt8jALZK6HIC80Un20ITScfSMZd4kXM4ZPMSo"
DEFAULT_JUMP_TAB = "Jump Data"
DEFAULT_VELO_TAB = "FB Velo"
LOCAL_SERVICE_ACCOUNT_FILE = Path.home() / "Desktop" / "service_account.json"
MIN_LAST_YTD_FB_VELO = 85.0

# Only these affiliate / roster groups are available in the dashboard.
INCLUDED_TEAMS = [
    "DSL", "FCL", "Fredericksburg", "Wilmington",
    "Harrisburg", "Rochester", "Washington", "REHAB",
]
TEAM_ALIASES = {
    "DSL": "DSL",
    "FCL": "FCL",
    "FREDERICKSBURG": "Fredericksburg",
    "WILMINGTON": "Wilmington",
    "HARRISBURG": "Harrisburg",
    "ROCHESTER": "Rochester",
    "WASHINGTON": "Washington",
    "REHAB": "REHAB",
    "REHABILITATION": "REHAB",
}

# -----------------------------------------------------------------------------
# DESIGN SYSTEM
# -----------------------------------------------------------------------------
BG = "#F6F8FC"
CARD_BG = "#FFFFFF"
NAVY = "#0A1F44"
NAVY_MID = "#183B6D"
ACCENT_RED = "#C8102E"
BLUE = "#1E5AA8"
GREEN = "#14805E"
TEAL = "#0D7E8A"
TEXT = "#162033"
SUBTEXT = "#667085"
BORDER = "#DDE4EE"
GRID = "#E8EDF3"

st.set_page_config(
    page_title="YTD FB Velo × CI",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
<style>
    :root {{
      --fb-bg: {BG}; --fb-card: {CARD_BG}; --fb-navy: {NAVY};
      --fb-red: {ACCENT_RED}; --fb-blue: {BLUE}; --fb-text: {TEXT};
      --fb-sub: {SUBTEXT}; --fb-border: {BORDER};
    }}
    .stApp {{ background: var(--fb-bg); color: var(--fb-text); }}
    .block-container {{ max-width: 1540px; padding-top: 2.15rem; padding-bottom: 3rem; }}
    h1, h2, h3 {{ letter-spacing: -0.025em; }}

    [data-testid="stSidebar"] {{
      background: linear-gradient(180deg, #081B3A 0%, #0A1F44 100%);
      border-right: 1px solid rgba(255,255,255,.08);
    }}
    [data-testid="stSidebar"] > div:first-child {{ padding-top: 1.5rem; }}
    [data-testid="stSidebar"] * {{ color: #FFFFFF; }}
    [data-testid="stSidebar"] [data-baseweb="select"] * {{ color: var(--fb-text); }}
    [data-testid="stSidebar"] .stDateInput input,
    [data-testid="stSidebar"] .stNumberInput input {{ color: var(--fb-text) !important; }}
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{
      color: #DCE7F5 !important; font-weight: 700; font-size: .84rem;
    }}
    [data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.13); }}
    [data-testid="stSidebar"] .stButton button {{
      background: {ACCENT_RED}; color: #FFFFFF; border: none; border-radius: 10px;
      font-weight: 800; letter-spacing: .01em; min-height: 2.5rem;
    }}
    [data-testid="stSidebar"] .stButton button:hover {{ background: #A80D26; }}

    .metric-card {{
      position: relative; overflow: hidden; background: var(--fb-card);
      border: 1px solid var(--fb-border); border-radius: 16px; padding: 18px 20px;
      min-height: 120px; box-shadow: 0 8px 26px rgba(15,35,64,.06);
    }}
    .metric-card:after {{
      content: ""; position: absolute; right: -28px; bottom: -28px; width: 90px; height: 90px;
      border-radius: 50%; background: rgba(30,90,168,.045);
    }}
    .metric-accent {{ width: 36px; height: 4px; border-radius: 999px; margin-bottom: 15px; }}
    .metric-label {{ color: var(--fb-sub); font-size: 10px; letter-spacing: .1em;
                     font-weight: 800; text-transform: uppercase; margin-bottom: 7px; }}
    .metric-value {{ color: var(--fb-navy); font-size: 29px; line-height: 1.05;
                     font-weight: 800; margin: 0; letter-spacing: -0.03em; }}
    .lookup-value {{ font-size: 32px; font-weight: 800; letter-spacing: -0.035em; margin-top: 6px; }}

    [data-testid="stVerticalBlockBorderWrapper"] {{
      background: #FFFFFF; border: 1px solid var(--fb-border) !important;
      border-radius: 16px !important; box-shadow: 0 8px 26px rgba(15,35,64,.055);
      padding: 7px 8px 10px 8px;
    }}
    [data-testid="stDataFrame"] {{ border: 1px solid var(--fb-border); border-radius: 12px; overflow: hidden; }}
    .stPlotlyChart {{ border-radius: 12px; overflow: hidden; }}
    .stAlert {{ border-radius: 12px; }}
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
def first_existing(columns: list[str], candidates: list[str]) -> str | None:
    """Return the first matching column name, case-insensitively."""
    lookup = {str(col).strip().lower(): col for col in columns}
    for candidate in candidates:
        found = lookup.get(candidate.strip().lower())
        if found is not None:
            return found
    return None


def parse_sheet_dates(series: pd.Series) -> pd.Series:
    """Parse normal dates and Google/Excel serial-date values safely."""
    raw = series.copy()
    parsed = pd.to_datetime(raw, errors="coerce")
    missing = parsed.isna()
    if missing.any():
        numeric = pd.to_numeric(raw[missing], errors="coerce")
        serial_mask = numeric.between(30000, 60000)
        if serial_mask.any():
            parsed.loc[numeric[serial_mask].index] = (
                pd.Timestamp("1899-12-30") + pd.to_timedelta(numeric[serial_mask], unit="D")
            )
    return parsed.dt.normalize()


def normalize_team(value) -> str | None:
    """Return the approved display name for a team, otherwise None."""
    if pd.isna(value):
        return None
    key = re.sub(r"[^A-Z0-9]", "", str(value).upper().strip())
    return TEAM_ALIASES.get(key)


def canonical_name(value) -> str:
    """Create a stable name key across the two Google Sheet tabs."""
    if pd.isna(value):
        return ""

    name = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    name = name.lower().strip()
    if "," in name:
        pieces = [piece.strip() for piece in name.split(",") if piece.strip()]
        if len(pieces) >= 2:
            name = " ".join(pieces[1:] + [pieces[0]])

    tokens = re.findall(r"[a-z0-9]+", name)
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    tokens = [token for token in tokens if token not in suffixes]
    return " ".join(sorted(tokens))


def fmt(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):,.{digits}f}"


def fmt_date(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    value = pd.Timestamp(value)
    return f"{value.strftime('%b')} {value.day}, {value.year}"


def add_time_bucket_columns(df: pd.DataFrame, date_col: str, bucket_mode: str) -> pd.DataFrame:
    """Add bucket_start, bucket_end, and bucket_label for week or half-month buckets."""
    out = df.copy()
    dates = pd.to_datetime(out[date_col]).dt.normalize()

    if bucket_mode == "Half-Month":
        half_start_day = np.where(dates.dt.day <= 15, 1, 16)
        bucket_start = pd.to_datetime({
            "year": dates.dt.year,
            "month": dates.dt.month,
            "day": half_start_day,
        })
        month_end = dates.dt.to_period("M").dt.end_time.dt.normalize()
        bucket_end = np.where(
            dates.dt.day <= 15,
            pd.to_datetime({"year": dates.dt.year, "month": dates.dt.month, "day": 15}),
            month_end,
        )
        bucket_end = pd.to_datetime(bucket_end)
        out["bucket_label"] = [
            f"{s.strftime('%b')} {s.day}–{e.day}"
            for s, e in zip(bucket_start, bucket_end)
        ]
    else:
        bucket_start = dates - pd.to_timedelta(dates.dt.weekday, unit="D")
        bucket_end = bucket_start + pd.Timedelta(days=6)
        out["bucket_label"] = [
            f"{s.strftime('%b')} {s.day}–{e.strftime('%b')} {e.day}"
            for s, e in zip(bucket_start, bucket_end)
        ]

    out["bucket_start"] = pd.to_datetime(bucket_start)
    out["bucket_end"] = pd.to_datetime(bucket_end)
    return out


def secret_or_default(key: str, default: str) -> str:
    try:
        return str(st.secrets.get(key, default))
    except Exception:
        return default


def get_credentials() -> Credentials:
    """Use Streamlit secrets when deployed; fall back to local JSON for local runs."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    try:
        service_account_info = st.secrets.get("gcp_service_account")
    except Exception:
        service_account_info = None

    if service_account_info:
        return Credentials.from_service_account_info(dict(service_account_info), scopes=scopes)

    local_file = Path(os.environ.get("SERVICE_ACCOUNT_FILE", str(LOCAL_SERVICE_ACCOUNT_FILE))).expanduser()
    if local_file.exists():
        return Credentials.from_service_account_file(str(local_file), scopes=scopes)

    raise FileNotFoundError(
        "No Google credentials were found. For local use, put service_account.json on your Desktop. "
        "For Streamlit deployment, add [gcp_service_account] to the app's Secrets settings."
    )


def read_tab(client: gspread.Client, sheet_id: str, tab_name: str) -> pd.DataFrame:
    worksheet = client.open_by_key(sheet_id).worksheet(tab_name)
    return pd.DataFrame(worksheet.get_all_records())


@st.cache_data(ttl=300, show_spinner="Loading Google Sheet data…")
def load_source_data() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Load and normalize Jump Data + FB Velo from the configured Google Sheet."""
    sheet_id = secret_or_default("SHEET_ID", DEFAULT_SHEET_ID)
    jump_tab = secret_or_default("JUMP_TAB", DEFAULT_JUMP_TAB)
    velo_tab = secret_or_default("VELO_TAB", DEFAULT_VELO_TAB)

    creds = get_credentials()
    client = gspread.authorize(creds)
    jump_raw = read_tab(client, sheet_id, jump_tab)
    velo_raw = read_tab(client, sheet_id, velo_tab)

    if jump_raw.empty:
        raise ValueError(f"The '{jump_tab}' tab did not return any rows.")
    if velo_raw.empty:
        raise ValueError(f"The '{velo_tab}' tab did not return any rows.")

    # Jump Data
    jump_raw.columns = jump_raw.columns.astype(str).str.strip()
    jump_name_col = first_existing(jump_raw.columns.tolist(), ["Athlete", "athlete", "Player", "player", "Name", "name"])
    jump_date_col = first_existing(jump_raw.columns.tolist(), ["Date", "date", "Test Date", "test_date"])
    jump_ci_col = first_existing(jump_raw.columns.tolist(), ["Concentric Impulse [N s]", "Concentric Impulse", "CI"])
    jump_team_col = first_existing(jump_raw.columns.tolist(), ["Team", "team", "Level", "level"])

    missing_jump = [
        label for label, col in {
            "athlete name": jump_name_col,
            "date": jump_date_col,
            "concentric impulse": jump_ci_col,
        }.items() if col is None
    ]
    if missing_jump:
        raise ValueError(f"Jump Data is missing required column(s): {', '.join(missing_jump)}.")

    jump = pd.DataFrame({
        "athlete": jump_raw[jump_name_col].astype(str).str.strip(),
        "date": parse_sheet_dates(jump_raw[jump_date_col]),
        "ci": pd.to_numeric(jump_raw[jump_ci_col], errors="coerce"),
        "team_raw": jump_raw[jump_team_col].astype(str).str.strip() if jump_team_col else "",
    })
    jump["team"] = jump["team_raw"].map(normalize_team)
    jump["name_key"] = jump["athlete"].map(canonical_name)
    jump = jump[
        (jump["athlete"] != "") &
        (jump["name_key"] != "") &
        (jump["team"].notna())
    ].dropna(subset=["date", "ci"])
    jump = jump.drop(columns=["team_raw"]).sort_values(["athlete", "date"]).reset_index(drop=True)

    # FB Velo
    velo_raw.columns = velo_raw.columns.astype(str).str.strip()
    velo_name_col = first_existing(velo_raw.columns.tolist(), ["pitcher", "Pitcher", "athlete", "Athlete", "player", "Player", "Name", "name"])
    velo_date_col = first_existing(velo_raw.columns.tolist(), ["game_date", "Game_Date", "Game Date", "date", "Date"])
    velo_ytd_col = first_existing(velo_raw.columns.tolist(), [
        "ytd_fb_velo", "YTD_FB_Velo", "YTD FB Velo", "YTD Fastball Velo",
        "ytd fastball velo", "ytd_fastball_velo",
    ])

    missing_velo = [
        label for label, col in {
            "pitcher name": velo_name_col,
            "game date": velo_date_col,
            "ytd_fb_velo": velo_ytd_col,
        }.items() if col is None
    ]
    if missing_velo:
        raise ValueError(
            f"FB Velo is missing required column(s): {', '.join(missing_velo)}. "
            "This app requires ytd_fb_velo."
        )

    velo = pd.DataFrame({
        "pitcher": velo_raw[velo_name_col].astype(str).str.strip(),
        "date": parse_sheet_dates(velo_raw[velo_date_col]),
        "ytd_fb_velo": pd.to_numeric(velo_raw[velo_ytd_col], errors="coerce"),
    })
    velo["name_key"] = velo["pitcher"].map(canonical_name)
    velo = velo[(velo["pitcher"] != "") & (velo["name_key"] != "")].dropna(subset=["date", "ytd_fb_velo"])
    velo = velo.sort_values(["pitcher", "date"], kind="stable").reset_index(drop=True)

    status = (
        f"Loaded {len(jump):,} Jump Data rows and {len(velo):,} FB Velo rows · "
        f"{datetime.now().strftime('%I:%M %p').lstrip('0')}"
    )
    return jump, velo, status


def build_summary(
    jump: pd.DataFrame,
    velo: pd.DataFrame,
    start_date,
    end_date,
    team_filter: str,
    min_velo_records: int,
    min_ci_jumps: int,
) -> pd.DataFrame:
    """Create one matched pitcher-level row inside a shared selected date window."""
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()

    jump_window = jump[(jump["date"] >= start) & (jump["date"] <= end)].copy()
    velo_window = velo[(velo["date"] >= start) & (velo["date"] <= end)].copy()

    # Team is the pitcher's most recent team in Jump Data, independent of window.
    team_lookup = (
        jump.sort_values("date")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
    )

    jump_summary = (
        jump_window.groupby("name_key", as_index=False)
        .agg(
            athlete=("athlete", "first"),
            avg_ci=("ci", "mean"),
            ci_jumps=("ci", "count"),
            ci_test_dates=("date", "nunique"),
            first_ci_date=("date", "min"),
            last_ci_date=("date", "max"),
        )
    )

    # Keep count of eligible FB rows, while charting only the last YTD velo in-window.
    velo_window = velo_window.sort_values(["name_key", "date"], kind="stable")
    velo_counts = (
        velo_window.groupby("name_key", as_index=False)
        .agg(
            fb_records=("ytd_fb_velo", "count"),
            first_fb_date=("date", "min"),
            last_fb_date=("date", "max"),
        )
    )
    latest_ytd = (
        velo_window.groupby("name_key", as_index=False)
        .tail(1)[["name_key", "ytd_fb_velo", "date"]]
        .rename(columns={"ytd_fb_velo": "avg_fb_velo", "date": "ytd_as_of_date"})
    )
    velo_summary = velo_counts.merge(latest_ytd, on="name_key", how="inner")

    summary = velo_summary.merge(jump_summary, on="name_key", how="inner")
    summary = summary.merge(team_lookup, on="name_key", how="left")
    summary["team"] = summary["team"].fillna("Unassigned")

    # Automatically exclude pitchers below the requested velocity floor.
    summary = summary[summary["avg_fb_velo"] >= MIN_LAST_YTD_FB_VELO].copy()
    summary = summary[
        (summary["fb_records"] >= max(1, int(min_velo_records))) &
        (summary["ci_jumps"] >= max(1, int(min_ci_jumps)))
    ].copy()

    if team_filter != "All Teams":
        summary = summary[summary["team"] == team_filter].copy()

    return summary.sort_values("avg_fb_velo", ascending=False).reset_index(drop=True)


def correlation_stats(summary: pd.DataFrame) -> tuple[float, float, float, float] | None:
    if len(summary) < 2:
        return None
    x = summary["avg_ci"].to_numpy(dtype=float)
    y = summary["avg_fb_velo"].to_numpy(dtype=float)
    if np.isclose(np.std(x), 0) or np.isclose(np.std(y), 0):
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return r, r * r, float(slope), float(intercept)


def ci_band_summary(summary: pd.DataFrame, band_width: int) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame(columns=["CI band", "Last YTD FB Velo", "Pitchers", "Average CI"])

    width = max(1, int(band_width))
    work = summary[["avg_ci", "avg_fb_velo"]].dropna().copy()
    work["band_start"] = np.floor(work["avg_ci"] / width) * width
    grouped = (
        work.groupby("band_start", as_index=False)
        .agg(
            **{
                "Last YTD FB Velo": ("avg_fb_velo", "mean"),
                "Pitchers": ("avg_fb_velo", "count"),
                "Average CI": ("avg_ci", "mean"),
            }
        )
        .sort_values("band_start")
    )
    grouped["CI band"] = grouped["band_start"].map(lambda lower: f"{lower:.0f}–{lower + width:.0f} N·s")
    grouped["Last YTD FB Velo"] = grouped["Last YTD FB Velo"].round(2)
    grouped["Average CI"] = grouped["Average CI"].round(2)
    grouped["Pitchers"] = grouped["Pitchers"].astype(int)
    return grouped[["CI band", "Last YTD FB Velo", "Pitchers", "Average CI"]]


def base_figure_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        font={"family": "Inter, Avenir Next, Arial, sans-serif", "color": TEXT},
        hoverlabel={"bgcolor": "#FFFFFF", "bordercolor": BORDER, "font": {"color": TEXT, "size": 13}, "align": "left"},
        margin={"l": 66, "r": 30, "t": 20, "b": 58},
        height=height,
        bargap=0.28,
        showlegend=False,
    )
    return fig


def build_scatter(summary: pd.DataFrame, show_labels: bool, ci_lookup: float | None) -> go.Figure:
    fig = go.Figure()
    if summary.empty:
        fig.add_annotation(
            text="No matched pitchers meet the selected window and minimum-data rules.",
            showarrow=False, font={"size": 15, "color": SUBTEXT}, x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 560)

    customdata = np.column_stack([
        summary["athlete"], summary["team"], summary["fb_records"], summary["ci_jumps"],
        summary["ci_test_dates"], summary["last_fb_date"].map(fmt_date),
        summary["first_ci_date"].map(fmt_date), summary["last_ci_date"].map(fmt_date),
    ])
    fig.add_trace(go.Scatter(
        x=summary["avg_ci"], y=summary["avg_fb_velo"],
        mode="markers+text" if show_labels else "markers",
        text=summary["athlete"] if show_labels else None,
        textposition="top center", textfont={"size": 10, "color": NAVY},
        marker={"size": 13, "color": ACCENT_RED, "opacity": 0.88, "line": {"color": "#FFFFFF", "width": 2}},
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Team: %{customdata[1]}<br>"
            "Last YTD FB velo: %{y:.2f} mph<br>"
            "Average CI: %{x:.2f} N·s<br><br>"
            "FB records: %{customdata[2]} · YTD as of %{customdata[5]}<br>"
            "CI jumps: %{customdata[3]} across %{customdata[4]} test dates · %{customdata[6]}–%{customdata[7]}"
            "<extra></extra>"
        ),
    ))

    stats = correlation_stats(summary)
    if stats is not None:
        r, r2, slope, intercept = stats
        x_range = np.linspace(summary["avg_ci"].min(), summary["avg_ci"].max(), 100)
        fig.add_trace(go.Scatter(
            x=x_range, y=slope * x_range + intercept, mode="lines",
            line={"color": NAVY_MID, "width": 2.5, "dash": "dash"}, hoverinfo="skip",
        ))
        fig.add_annotation(
            text=f"r = {r:+.2f} · R² = {r2:.2f}",
            x=0.02, y=0.98, xref="paper", yref="paper", xanchor="left", yanchor="top",
            showarrow=False, font={"color": NAVY, "size": 13}, bgcolor="#FFFFFF",
            bordercolor=BORDER, borderwidth=1, borderpad=7,
        )
        if ci_lookup is not None and np.isfinite(ci_lookup):
            predicted = slope * float(ci_lookup) + intercept
            fig.add_vline(x=float(ci_lookup), line_color=TEAL, line_width=1.5, line_dash="dot")
            fig.add_hline(y=predicted, line_color=TEAL, line_width=1.5, line_dash="dot")
            fig.add_trace(go.Scatter(
                x=[float(ci_lookup)], y=[predicted], mode="markers",
                marker={"size": 15, "color": TEAL, "symbol": "diamond", "line": {"color": "#FFFFFF", "width": 2}},
                hovertemplate=(
                    "<b>CI lookup</b><br>Average CI: %{x:.1f} N·s<br>"
                    "Estimated last YTD FB velo: %{y:.2f} mph<extra></extra>"
                ),
            ))

    fig.update_xaxes(
        title="Average concentric impulse (N·s)", showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER, tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Last YTD FB velocity (mph)", showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER, tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 560)


def build_band_chart(summary: pd.DataFrame, band_width: int) -> go.Figure:
    bands = ci_band_summary(summary, band_width)
    fig = go.Figure()
    if bands.empty:
        fig.add_annotation(
            text="No matched pitchers are available for CI bands.", showarrow=False,
            font={"size": 14, "color": SUBTEXT}, x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 380)

    fig.add_trace(go.Bar(
        x=bands["CI band"], y=bands["Last YTD FB Velo"],
        marker={"color": BLUE, "line": {"color": NAVY_MID, "width": 0.8}},
        text=[f"{velo:.1f}" for velo in bands["Last YTD FB Velo"]], textposition="outside", cliponaxis=False,
        customdata=np.column_stack([bands["Pitchers"], bands["Average CI"]]),
        hovertemplate=(
            "<b>%{x}</b><br>Mean last YTD FB velo: %{y:.2f} mph<br>"
            "Pitchers: %{customdata[0]}<br>Mean CI within band: %{customdata[1]:.2f} N·s<extra></extra>"
        ),
    ))
    y_min = max(0, float(bands["Last YTD FB Velo"].min()) - 1.5)
    y_max = float(bands["Last YTD FB Velo"].max()) + 1.25
    fig.update_xaxes(
        title="Pitcher average CI band", showgrid=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Mean last YTD FB velo (mph)", range=[y_min, y_max], showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER, tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 380)


def metric_card(title: str, value: str, accent: str) -> str:
    return f"""
    <div class="metric-card">
      <div class="metric-accent" style="background:{accent};"></div>
      <div class="metric-label">{html.escape(title)}</div>
      <div class="metric-value">{html.escape(value)}</div>
    </div>
    """




def build_within_individual_pairs(
    jump: pd.DataFrame,
    velo: pd.DataFrame,
    start_date,
    end_date,
    team_filter: str,
    bucket_mode: str,
) -> pd.DataFrame:
    """Build within-individual CI and YTD FB velo pairs in week or half-month buckets."""
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()

    # Current team assignment follows the same latest-Jump-Data rule as the overview.
    team_lookup = (
        jump.sort_values("date")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
    )

    jump_window = jump[(jump["date"] >= start) & (jump["date"] <= end)].copy()
    jump_window = add_time_bucket_columns(jump_window, "date", bucket_mode)
    ci_bucketed = (
        jump_window.groupby(["name_key", "bucket_start", "bucket_end", "bucket_label"], as_index=False)
        .agg(
            athlete=("athlete", "first"),
            avg_ci=("ci", "mean"),
            ci_jumps=("ci", "count"),
            last_ci_date=("date", "max"),
        )
        .merge(team_lookup, on="name_key", how="left")
    )
    ci_bucketed["team"] = ci_bucketed["team"].fillna("Unassigned")
    if team_filter != "All Teams":
        ci_bucketed = ci_bucketed[ci_bucketed["team"] == team_filter].copy()

    velo_window = velo[(velo["date"] >= start) & (velo["date"] <= end)].copy()
    velo_window = add_time_bucket_columns(velo_window, "date", bucket_mode)
    velo_bucketed = (
        velo_window.sort_values(["name_key", "date"], kind="stable")
        .groupby(["name_key", "bucket_start", "bucket_end", "bucket_label"], as_index=False)
        .tail(1)[["name_key", "bucket_start", "bucket_end", "bucket_label", "date", "ytd_fb_velo"]]
        .rename(columns={"date": "velo_date"})
    )

    if ci_bucketed.empty or velo_bucketed.empty:
        return pd.DataFrame(columns=[
            "name_key", "athlete", "team", "date", "bucket_end", "bucket_label",
            "avg_ci", "ci_jumps", "last_ci_date", "velo_date", "ytd_fb_velo",
            "delta_ci", "delta_fb_velo",
        ])

    pairs = ci_bucketed.merge(
        velo_bucketed,
        on=["name_key", "bucket_start", "bucket_end", "bucket_label"],
        how="inner",
    ).rename(columns={"bucket_start": "date"})

    pairs = pairs.dropna(subset=["velo_date", "ytd_fb_velo"]).copy()
    pairs = pairs[pairs["ytd_fb_velo"] >= MIN_LAST_YTD_FB_VELO].copy()
    pairs = pairs.sort_values(["name_key", "date"], kind="stable").reset_index(drop=True)
    if pairs.empty:
        return pairs

    first_ci = pairs.groupby("name_key")["avg_ci"].transform("first")
    first_velo = pairs.groupby("name_key")["ytd_fb_velo"].transform("first")
    pairs["delta_ci"] = pairs["avg_ci"] - first_ci
    pairs["delta_fb_velo"] = pairs["ytd_fb_velo"] - first_velo
    return pairs


def build_within_individual_summary(pairs: pd.DataFrame, min_paired_dates: int) -> pd.DataFrame:
    """One row per pitcher with a within-pitcher correlation of paired changes."""
    rows = []
    required = max(3, int(min_paired_dates))
    if pairs.empty:
        return pd.DataFrame(columns=[
            "name_key", "athlete", "team", "paired_dates", "r", "r2", "slope",
            "first_date", "last_date", "delta_ci", "delta_fb_velo",
        ])

    for name_key, grp in pairs.groupby("name_key", sort=False):
        grp = grp.sort_values("date")
        n = len(grp)
        if n < required:
            continue
        x = grp["delta_ci"].to_numpy(dtype=float)
        y = grp["delta_fb_velo"].to_numpy(dtype=float)
        if np.isclose(np.std(x), 0) or np.isclose(np.std(y), 0):
            r = np.nan
            r2 = np.nan
            slope = np.nan
        else:
            slope, _ = np.polyfit(x, y, 1)
            r = float(np.corrcoef(x, y)[0, 1])
            r2 = r * r

        rows.append({
            "name_key": name_key,
            "athlete": grp["athlete"].iloc[0],
            "team": grp["team"].iloc[0],
            "paired_dates": n,
            "r": r,
            "r2": r2,
            "slope": slope,
            "first_date": grp["date"].iloc[0],
            "last_date": grp["date"].iloc[-1],
            "delta_ci": grp["delta_ci"].iloc[-1],
            "delta_fb_velo": grp["delta_fb_velo"].iloc[-1],
        })

    if not rows:
        return pd.DataFrame(columns=[
            "name_key", "athlete", "team", "paired_dates", "r", "r2", "slope",
            "first_date", "last_date", "delta_ci", "delta_fb_velo",
        ])
    return pd.DataFrame(rows).sort_values(["r", "paired_dates"], ascending=[False, False], na_position="last").reset_index(drop=True)


def build_within_scatter(player_pairs: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if player_pairs.empty:
        fig.add_annotation(
            text="No paired CI and YTD FB velo dates for this pitcher.", showarrow=False,
            font={"size": 14, "color": SUBTEXT}, x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 470)

    customdata = np.column_stack([
        player_pairs["bucket_label"],
        player_pairs["avg_ci"],
        player_pairs["ytd_fb_velo"],
        player_pairs["velo_date"].map(fmt_date),
        player_pairs["ci_jumps"],
        player_pairs["last_ci_date"].map(fmt_date),
    ])
    fig.add_trace(go.Scatter(
        x=player_pairs["delta_ci"],
        y=player_pairs["delta_fb_velo"],
        mode="markers+text",
        text=player_pairs["bucket_label"],
        textposition="top center",
        textfont={"size": 10, "color": NAVY},
        marker={"size": 13, "color": ACCENT_RED, "opacity": 0.9, "line": {"color": "#FFFFFF", "width": 2}},
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Δ CI: %{x:+.2f} N·s<br>"
            "Δ YTD FB velo: %{y:+.2f} mph<br><br>"
            "CI: %{customdata[1]:.2f} N·s · %{customdata[4]} jumps<br>"
            "Last CI in bucket: %{customdata[5]}<br>"
            "YTD FB velo: %{customdata[2]:.2f} mph<br>"
            "YTD as of %{customdata[3]}"
            "<extra></extra>"
        ),
    ))
    fig.add_vline(x=0, line_color="#AAB5C5", line_width=1)
    fig.add_hline(y=0, line_color="#AAB5C5", line_width=1)

    if len(player_pairs) >= 3 and not np.isclose(player_pairs["delta_ci"].std(), 0) and not np.isclose(player_pairs["delta_fb_velo"].std(), 0):
        x = player_pairs["delta_ci"].to_numpy(dtype=float)
        y = player_pairs["delta_fb_velo"].to_numpy(dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        r = float(np.corrcoef(x, y)[0, 1])
        x_range = np.linspace(x.min(), x.max(), 100)
        fig.add_trace(go.Scatter(
            x=x_range, y=slope * x_range + intercept, mode="lines",
            line={"color": NAVY_MID, "width": 2.5, "dash": "dash"}, hoverinfo="skip",
        ))
        fig.add_annotation(
            text=f"r = {r:+.2f} · {len(player_pairs)} paired buckets",
            x=0.02, y=0.98, xref="paper", yref="paper", xanchor="left", yanchor="top",
            showarrow=False, font={"color": NAVY, "size": 13}, bgcolor="#FFFFFF",
            bordercolor=BORDER, borderwidth=1, borderpad=7,
        )

    fig.update_xaxes(
        title="Change in average CI from first bucket (N·s)", showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER, tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Change in YTD FB velo from first bucket (mph)", showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER, tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 470)


def build_within_timeline(player_pairs: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if player_pairs.empty:
        fig.add_annotation(
            text="No paired buckets.", showarrow=False, font={"size": 14, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 360)

    fig.add_trace(go.Scatter(
        x=player_pairs["date"], y=player_pairs["avg_ci"], mode="lines+markers",
        name="Average CI", line={"color": BLUE, "width": 2.5}, marker={"size": 8},
        customdata=player_pairs[["bucket_label"]],
        hovertemplate="<b>%{customdata[0]}</b><br>Average CI: %{y:.2f} N·s<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=player_pairs["date"], y=player_pairs["ytd_fb_velo"], mode="lines+markers",
        name="YTD FB velo", yaxis="y2", line={"color": ACCENT_RED, "width": 2.5}, marker={"size": 8},
        customdata=player_pairs[["bucket_label"]],
        hovertemplate="<b>%{customdata[0]}</b><br>YTD FB velo: %{y:.2f} mph<extra></extra>",
    ))
    fig.update_layout(
        yaxis={"title": "Average CI (N·s)", "showgrid": True, "gridcolor": GRID, "zeroline": False, "linecolor": BORDER, "tickfont": {"color": SUBTEXT}, "title_font": {"color": SUBTEXT}},
        yaxis2={"title": "YTD FB velo (mph)", "overlaying": "y", "side": "right", "showgrid": False, "zeroline": False, "linecolor": BORDER, "tickfont": {"color": SUBTEXT}, "title_font": {"color": SUBTEXT}},
        legend={"orientation": "h", "x": 0, "y": 1.15, "font": {"color": SUBTEXT}},
        showlegend=True,
    )
    fig.update_xaxes(showgrid=False, linecolor=BORDER, tickfont={"color": SUBTEXT})
    return base_figure_layout(fig, 360)


# -----------------------------------------------------------------------------
# APP
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("<div style='height:4px;width:42px;border-radius:999px;background:#C8102E;margin:2px 0 16px;'></div>", unsafe_allow_html=True)
    st.markdown("<h2 style='color:#FFFFFF;margin:0 0 18px;font-size:27px;letter-spacing:-.03em;'>YTD FB Velo × CI</h2>", unsafe_allow_html=True)
    refresh = st.button("↻ Refresh", use_container_width=True, type="primary")

if refresh:
    load_source_data.clear()

try:
    jump, velo, status = load_source_data()
except Exception as exc:
    st.error(f"Could not load data. {exc}")
    st.stop()

all_dates = pd.concat([jump["date"], velo["date"]], ignore_index=True).dropna()
min_date = all_dates.min().date()
max_date = all_dates.max().date()
default_start = max(pd.Timestamp(year=max_date.year, month=1, day=1).date(), min_date)

with st.sidebar:
    selected_dates = st.date_input(
        "Date range",
        value=(default_start, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        start_date = end_date = selected_dates

    available_teams = set(jump["team"].dropna().unique().tolist())
    teams = ["All Teams"] + [team for team in INCLUDED_TEAMS if team in available_teams]
    team_filter = st.selectbox("Team", teams)

    st.markdown("---")
    ci_lookup = st.number_input("CI lookup", min_value=0.0, step=1.0, value=280.0, format="%.1f")
    ci_band_width = st.selectbox("CI band", [5, 10, 15, 20], index=1, format_func=lambda x: f"{x} N·s")

    st.markdown("---")
    min_velo_records = st.number_input("Min FB records", min_value=1, step=1, value=1)
    min_ci_jumps = st.number_input("Min CI jumps", min_value=1, step=1, value=1)
    show_labels = st.checkbox("Show names")

    st.markdown("---")
    bucket_mode = st.selectbox("Within bucket", ["Week", "Half-Month"])
    min_paired_dates = st.number_input("Min paired buckets", min_value=3, max_value=30, step=1, value=3)

summary = build_summary(
    jump=jump,
    velo=velo,
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    min_velo_records=int(min_velo_records),
    min_ci_jumps=int(min_ci_jumps),
)
within_pairs = build_within_individual_pairs(
    jump=jump,
    velo=velo,
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    bucket_mode=bucket_mode,
)
within_summary = build_within_individual_summary(within_pairs, int(min_paired_dates))

period_text = f"{fmt_date(start_date)} – {fmt_date(end_date)}"
title_col, filter_col = st.columns([4, 1])
with title_col:
    st.markdown("<h1 style='margin:0;color:#0A1F44;font-size:37px;font-weight:800;'>YTD FB Velo × CI</h1>", unsafe_allow_html=True)
with filter_col:
    st.markdown(
        f"<div style='text-align:right;color:#667085;font-weight:700;font-size:13px;padding-top:13px;'>{html.escape(team_filter)}</div>",
        unsafe_allow_html=True,
    )
st.markdown(f"<div style='color:#667085;font-size:13px;margin:3px 0 20px;'>{html.escape(period_text)}</div>", unsafe_allow_html=True)

overview_tab, within_tab = st.tabs(["Overview", "Within Individual"])

with overview_tab:
    stats = correlation_stats(summary)
    n_pitchers = len(summary)
    mean_velo = summary["avg_fb_velo"].mean() if n_pitchers else np.nan
    mean_ci = summary["avg_ci"].mean() if n_pitchers else np.nan
    r_text = f"{stats[0]:+.2f}" if stats is not None else "—"

    cols = st.columns(4)
    metric_values = [
        ("Pitchers", str(n_pitchers), BLUE),
        ("Correlation", r_text, ACCENT_RED),
        ("Last YTD FB Velo", f"{fmt(mean_velo)} mph", TEAL),
        ("Average CI", f"{fmt(mean_ci)} N·s", GREEN),
    ]
    for column, values in zip(cols, metric_values):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    estimated_velo = np.nan
    if stats is not None:
        estimated_velo = stats[2] * float(ci_lookup) + stats[3]

    with st.container(border=True):
        st.subheader("CI Lookup", anchor=False)
        lookup_left, lookup_right = st.columns(2)
        with lookup_left:
            st.markdown("<div class='metric-label'>Average CI</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='lookup-value' style='color:#0A1F44;'>{fmt(ci_lookup, 1)} N·s</div>", unsafe_allow_html=True)
        with lookup_right:
            st.markdown("<div class='metric-label'>Estimated FB Velo</div>", unsafe_allow_html=True)
            lookup_value = f"{fmt(estimated_velo)} mph" if pd.notna(estimated_velo) else "—"
            st.markdown(f"<div class='lookup-value' style='color:#0D7E8A;'>{lookup_value}</div>", unsafe_allow_html=True)

    with st.container(border=True):
        st.subheader("FB Velo by CI Band", anchor=False)
        st.plotly_chart(build_band_chart(summary, int(ci_band_width)), use_container_width=True, config={"displayModeBar": False})

    with st.container(border=True):
        st.subheader("CI vs YTD FB Velo", anchor=False)
        st.plotly_chart(build_scatter(summary, show_labels, float(ci_lookup)), use_container_width=True, config={"displayModeBar": False})

    with st.container(border=True):
        st.subheader("Pitcher Results", anchor=False)
        if summary.empty:
            st.info("No matching pitchers.")
        else:
            display = summary[[
                "athlete", "team", "avg_fb_velo", "ytd_as_of_date", "avg_ci", "fb_records", "ci_jumps", "ci_test_dates", "first_ci_date", "last_ci_date",
            ]].copy()
            display.columns = [
                "Pitcher", "Team", "Last YTD FB Velo", "YTD FB As Of", "Average CI", "FB Records", "CI Jumps", "CI Test Dates", "First CI", "Last CI",
            ]
            for date_col in ["YTD FB As Of", "First CI", "Last CI"]:
                display[date_col] = display[date_col].map(fmt_date)
            display["Last YTD FB Velo"] = display["Last YTD FB Velo"].round(2)
            display["Average CI"] = display["Average CI"].round(2)
            st.dataframe(
                display,
                hide_index=True,
                use_container_width=True,
                height=min(620, 44 + 36 * (len(display) + 1)),
                column_config={
                    "Last YTD FB Velo": st.column_config.NumberColumn(format="%.2f mph"),
                    "Average CI": st.column_config.NumberColumn(format="%.2f N·s"),
                },
            )

with within_tab:
    eligible_count = len(within_summary)
    valid_r = within_summary["r"].dropna() if not within_summary.empty else pd.Series(dtype=float)
    mean_within_r = valid_r.mean() if not valid_r.empty else np.nan
    total_pairs = len(within_pairs)

    cols = st.columns(4)
    metric_values = [
        ("Pitchers", str(eligible_count), BLUE),
        ("Mean Within r", f"{mean_within_r:+.2f}" if pd.notna(mean_within_r) else "—", ACCENT_RED),
        ("Paired Buckets", str(total_pairs), TEAL),
        ("Bucket", bucket_mode, GREEN),
    ]
    for column, values in zip(cols, metric_values):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    if within_summary.empty:
        st.info("No pitchers meet the paired-bucket rule.")
    else:
        athlete_options = within_summary["name_key"].tolist()
        name_map = dict(zip(within_summary["name_key"], within_summary["athlete"]))

        # Give this selector a stable key and force one clean redraw after a
        # pitcher change. This avoids stale chart content inside st.tabs on
        # some Streamlit/browser combinations.
        selector_key = "within_individual_pitcher"
        rendered_key = "within_individual_pitcher_rendered"
        if st.session_state.get(selector_key) not in athlete_options:
            st.session_state[selector_key] = athlete_options[0]

        selected_key = st.selectbox(
            "Pitcher",
            athlete_options,
            format_func=lambda key: name_map.get(key, key),
            key=selector_key,
        )

        if st.session_state.get(rendered_key) != selected_key:
            st.session_state[rendered_key] = selected_key
            st.rerun()

        player_pairs = within_pairs[within_pairs["name_key"] == selected_key].sort_values("date").copy()
        player_row = within_summary[within_summary["name_key"] == selected_key].iloc[0]

        player_cols = st.columns(4)
        player_metrics = [
            ("Paired Buckets", str(int(player_row["paired_dates"])), BLUE),
            ("Within r", f"{player_row['r']:+.2f}" if pd.notna(player_row["r"]) else "—", ACCENT_RED),
            ("Δ CI", f"{player_row['delta_ci']:+.1f} N·s", TEAL),
            ("Δ FB Velo", f"{player_row['delta_fb_velo']:+.2f} mph", GREEN),
        ]
        for column, values in zip(player_cols, player_metrics):
            with column:
                st.markdown(metric_card(*values), unsafe_allow_html=True)

        left, right = st.columns([1.25, 1])
        with left:
            with st.container(border=True):
                st.subheader("Δ CI vs Δ YTD FB Velo", anchor=False)
                st.plotly_chart(build_within_scatter(player_pairs), use_container_width=True, config={"displayModeBar": False})
        with right:
            with st.container(border=True):
                st.subheader("CI + YTD FB Velo", anchor=False)
                st.plotly_chart(build_within_timeline(player_pairs), use_container_width=True, config={"displayModeBar": False})

        with st.container(border=True):
            st.subheader("Within-Individual Results", anchor=False)
            individual_display = within_summary[[
                "athlete", "team", "paired_dates", "r", "r2", "delta_ci", "delta_fb_velo", "first_date", "last_date",
            ]].copy()
            individual_display.columns = [
                "Pitcher", "Team", "Paired Buckets", "Within r", "R²", "Δ CI", "Δ FB Velo", "First Bucket", "Last Bucket",
            ]
            for date_col in ["First Bucket", "Last Bucket"]:
                individual_display[date_col] = individual_display[date_col].map(fmt_date)
            individual_display["Within r"] = individual_display["Within r"].round(2)
            individual_display["R²"] = individual_display["R²"].round(2)
            individual_display["Δ CI"] = individual_display["Δ CI"].round(1)
            individual_display["Δ FB Velo"] = individual_display["Δ FB Velo"].round(2)
            st.dataframe(
                individual_display,
                hide_index=True,
                use_container_width=True,
                height=min(620, 44 + 36 * (len(individual_display) + 1)),
                column_config={
                    "Within r": st.column_config.NumberColumn(format="%+.2f"),
                    "R²": st.column_config.NumberColumn(format="%.2f"),
                    "Δ CI": st.column_config.NumberColumn(format="%+.1f N·s"),
                    "Δ FB Velo": st.column_config.NumberColumn(format="%+.2f mph"),
                },
            )

        with st.container(border=True):
            st.subheader("Bucket Data", anchor=False)
            paired_display = player_pairs[["bucket_label", "avg_ci", "ytd_fb_velo", "velo_date", "ci_jumps", "last_ci_date", "delta_ci", "delta_fb_velo"]].copy()
            paired_display.columns = ["Bucket", "Average CI", "YTD FB Velo", "YTD FB As Of", "CI Jumps", "Last CI", "Δ CI", "Δ FB Velo"]
            for date_col in ["YTD FB As Of", "Last CI"]:
                paired_display[date_col] = paired_display[date_col].map(fmt_date)
            for col in ["Average CI", "YTD FB Velo", "Δ CI", "Δ FB Velo"]:
                paired_display[col] = paired_display[col].round(2)
            st.dataframe(
                paired_display,
                hide_index=True,
                use_container_width=True,
                height=min(460, 44 + 36 * (len(paired_display) + 1)),
                column_config={
                    "Average CI": st.column_config.NumberColumn(format="%.2f N·s"),
                    "YTD FB Velo": st.column_config.NumberColumn(format="%.2f mph"),
                    "Δ CI": st.column_config.NumberColumn(format="%+.2f N·s"),
                    "Δ FB Velo": st.column_config.NumberColumn(format="%+.2f mph"),
                },
            )
