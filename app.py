"""
Performance × CI — Streamlit deployment-ready dashboard.


"""
from __future__ import annotations

# Selected defensive relationships build v7.
# Relative Peak Power × Sprint Speed now uses the baserunning-sheet Sprint Speed source.
# Selected baserunning/defensive tabs use current baserunning-sheet Sprint Speed where applicable.

# Defensive relationship integration build: 2026-08-13 v7

import html
import hmac
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
DEFAULT_BAT_TAB = "PP_Sprint"
DEFAULT_EXIT_TAB = "Nats Hitting"
DEFAULT_PINCH_TAB = "Pinch Grip"
DEFAULT_INFIELD_SHEET_NAME = "nats_players_infield_2026"
DEFAULT_BASERUNNING_SHEET_NAME = "nats_players_baserunning_2026"
LOCAL_SERVICE_ACCOUNT_FILE = Path.home() / "Desktop" / "service_account.json"
MIN_LAST_YTD_FB_VELO = 85.0
POTENTIAL_CI_INCREASE = 10.0
FB_VELO_OUTPUT_BUCKET_WIDTH = 2.0
FB_VELO_OUTPUT_BUCKET_TOP = 98.0
CI_BUCKET_TOP = 360.0
HITTING_CI_BUCKET_FLOOR = 240.0
SPRINT_SPEED_OUTPUT_BUCKET_WIDTH = 0.5
BAT_SPEED_OUTPUT_BUCKET_WIDTH = 2.0
BAT_SPEED_OUTPUT_BUCKET_FLOOR = 62.0
EXIT_VELO_OUTPUT_BUCKET_WIDTH = 2.0
EXIT_VELO_OUTPUT_BUCKET_FLOOR = 96.0
POTENTIAL_PINCH_INCREASE = 10.0
POTENTIAL_PEAK_POWER_REL_INCREASE = 5.0
POTENTIAL_PEAK_POWER_INCREASE = 500.0
MIN_SPRINT_MONTH_DATA_DATES = 14

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
    "WESTPALMBEACH": "FCL",
    "PALMBEACH": "FCL",
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
    page_title="Performance × CI",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="collapsed",
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
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {{ display: none !important; }}
    .block-container {{ max-width: 1540px; padding-top: 2.15rem; padding-bottom: 3rem; }}
    h1, h2, h3 {{ letter-spacing: -0.025em; }}

    [data-testid="stSidebar"] {{
      background: linear-gradient(180deg, #081B3A 0%, #0A1F44 100%);
      border-right: 1px solid rgba(255,255,255,.08);
    }}
    [data-testid="stSidebar"] > div:first-child {{ padding-top: 1.5rem; }}

    /* Keep sidebar labels/lightweight copy readable without overriding form controls. */
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown span {{
      color: #DCE7F5 !important;
    }}
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{
      font-weight: 700; font-size: .84rem;
    }}

    /* Selectboxes: selected values and menu text must always be dark on white. */
    [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-testid="stSelectbox"] div[role="combobox"],
    [data-testid="stSidebar"] [data-baseweb="select"] > div {{
      background: #FFFFFF !important;
      border: 1px solid #DDE4EE !important;
      border-radius: 14px !important;
      min-height: 3rem !important;
      box-shadow: none !important;
    }}
    [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] *,
    [data-testid="stSidebar"] [data-testid="stSelectbox"] div[role="combobox"] *,
    [data-testid="stSidebar"] [data-baseweb="select"] input,
    [data-testid="stSidebar"] [data-baseweb="select"] span,
    [data-testid="stSidebar"] [data-baseweb="select"] div {{
      color: #162033 !important;
      -webkit-text-fill-color: #162033 !important;
      opacity: 1 !important;
    }}
    [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] svg,
    [data-testid="stSidebar"] [data-baseweb="select"] svg {{
      fill: #162033 !important;
      color: #162033 !important;
      opacity: 1 !important;
    }}

    /* Native Streamlit input controls. */
    [data-testid="stSidebar"] .stDateInput > div > div,
    [data-testid="stSidebar"] .stNumberInput > div > div,
    [data-testid="stSidebar"] div[data-baseweb="input"] > div {{
      background: #FFFFFF !important;
      border: 1px solid #DDE4EE !important;
      border-radius: 14px !important;
      min-height: 3rem;
      box-shadow: none !important;
    }}
    [data-testid="stSidebar"] .stDateInput input,
    [data-testid="stSidebar"] .stNumberInput input,
    [data-testid="stSidebar"] div[data-baseweb="input"] input {{
      color: #162033 !important;
      -webkit-text-fill-color: #162033 !important;
      opacity: 1 !important;
    }}

    /* Dropdown menu can render in a portal outside the sidebar. */
    div[data-baseweb="popover"],
    div[role="listbox"] {{ background: #FFFFFF !important; }}
    div[data-baseweb="popover"] *,
    div[role="listbox"] *,
    div[role="option"],
    div[role="option"] * {{
      color: #162033 !important;
      -webkit-text-fill-color: #162033 !important;
      opacity: 1 !important;
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


def ci_bucket_start(values: pd.Series, width: float) -> pd.Series:
    """Return CI bucket starts, with every value >= 360 N·s grouped into 360+."""
    starts = np.floor(values / width) * width
    return np.minimum(starts, CI_BUCKET_TOP)


def ci_bucket_label(lower: float, width: float) -> str:
    """Format a CI bucket label with a final 360+ N·s bucket."""
    if lower >= CI_BUCKET_TOP:
        return f"{CI_BUCKET_TOP:.0f}+ N·s"
    return f"{lower:.0f}–{lower + width:.0f} N·s"


def hitting_ci_bucket_start(values: pd.Series, width: float) -> pd.Series:
    """Hitting CI buckets use <240 N·s as the floor and 360+ N·s as the ceiling."""
    starts = np.floor(values / width) * width
    starts = np.where(values < HITTING_CI_BUCKET_FLOOR, HITTING_CI_BUCKET_FLOOR - width, starts)
    return pd.Series(np.minimum(starts, CI_BUCKET_TOP), index=values.index)


def hitting_ci_bucket_label(lower: float, width: float) -> str:
    """Format hitting CI buckets with <240 and 360+ endpoint buckets."""
    if lower < HITTING_CI_BUCKET_FLOOR:
        return f"<{HITTING_CI_BUCKET_FLOOR:.0f} N·s"
    if lower >= CI_BUCKET_TOP:
        return f"{CI_BUCKET_TOP:.0f}+ N·s"
    return f"{lower:.0f}–{lower + width:.0f} N·s"


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


def read_external_sheet(
    client: gspread.Client,
    *,
    id_secret: str,
    name_secret: str,
    default_name: str,
    tab_secret: str,
) -> pd.DataFrame:
    """Read an external Google spreadsheet by optional ID or, by default, title."""
    sheet_id = secret_or_default(id_secret, "").strip()
    sheet_name = secret_or_default(name_secret, default_name).strip()
    tab_name = secret_or_default(tab_secret, "").strip()

    book = client.open_by_key(sheet_id) if sheet_id else client.open(sheet_name)
    worksheet = book.worksheet(tab_name) if tab_name else book.sheet1
    return pd.DataFrame(worksheet.get_all_records())


@st.cache_data(ttl=300, show_spinner="Loading Google Sheet data…")
def load_source_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Load core performance data plus selected infield and baserunning outcomes."""
    sheet_id = secret_or_default("SHEET_ID", DEFAULT_SHEET_ID)
    jump_tab = secret_or_default("JUMP_TAB", DEFAULT_JUMP_TAB)
    velo_tab = secret_or_default("VELO_TAB", DEFAULT_VELO_TAB)
    bat_tab = secret_or_default("BAT_TAB", DEFAULT_BAT_TAB)
    exit_tab = secret_or_default("EXIT_TAB", DEFAULT_EXIT_TAB)
    pinch_tab = secret_or_default("PINCH_TAB", DEFAULT_PINCH_TAB)

    creds = get_credentials()
    client = gspread.authorize(creds)
    jump_raw = read_tab(client, sheet_id, jump_tab)
    velo_raw = read_tab(client, sheet_id, velo_tab)
    bat_raw = read_tab(client, sheet_id, bat_tab)
    exit_raw = read_tab(client, sheet_id, exit_tab)
    pinch_raw = read_tab(client, sheet_id, pinch_tab)
    infield_raw = read_external_sheet(
        client,
        id_secret="INFIELD_SHEET_ID",
        name_secret="INFIELD_SHEET_NAME",
        default_name=DEFAULT_INFIELD_SHEET_NAME,
        tab_secret="INFIELD_TAB",
    )
    baserunning_raw = read_external_sheet(
        client,
        id_secret="BASERUNNING_SHEET_ID",
        name_secret="BASERUNNING_SHEET_NAME",
        default_name=DEFAULT_BASERUNNING_SHEET_NAME,
        tab_secret="BASERUNNING_TAB",
    )

    if jump_raw.empty:
        raise ValueError(f"The '{jump_tab}' tab did not return any rows.")
    if velo_raw.empty:
        raise ValueError(f"The '{velo_tab}' tab did not return any rows.")
    if bat_raw.empty:
        raise ValueError(f"The '{bat_tab}' tab did not return any rows.")
    if exit_raw.empty:
        raise ValueError(f"The '{exit_tab}' tab did not return any rows.")
    if pinch_raw.empty:
        raise ValueError(f"The '{pinch_tab}' tab did not return any rows.")
    if infield_raw.empty:
        raise ValueError("The infield defensive spreadsheet did not return any rows.")
    if baserunning_raw.empty:
        raise ValueError("The baserunning spreadsheet did not return any rows.")

    # Jump Data. CI and relative peak power are cleaned independently so
    # missing values in one metric do not remove valid observations for the other.
    jump_raw.columns = jump_raw.columns.astype(str).str.strip()
    jump_name_col = first_existing(jump_raw.columns.tolist(), ["Athlete", "athlete", "Player", "player", "Name", "name"])
    jump_date_col = first_existing(jump_raw.columns.tolist(), ["Date", "date", "Test Date", "test_date"])
    jump_ci_col = first_existing(jump_raw.columns.tolist(), ["Concentric Impulse [N s]", "Concentric Impulse", "CI"])
    jump_peak_power_rel_col = first_existing(
        jump_raw.columns.tolist(),
        [
            "Peak Power / BM [W/kg]", "Peak Power / BM",
            "Peak Power Rel", "Relative Peak Power",
            "peak_power_rel", "peak power / bm [w/kg]",
        ],
    )
    jump_peak_power_col = first_existing(
        jump_raw.columns.tolist(),
        [
            "Peak Power [W]", "Peak Power", "peak power [w]",
            "peak_power", "Peak Power W", "Peak Power (W)",
        ],
    )
    jump_team_col = first_existing(jump_raw.columns.tolist(), ["Team", "team", "Level", "level"])

    missing_jump = [
        label for label, col in {
            "athlete name": jump_name_col,
            "date": jump_date_col,
            "concentric impulse": jump_ci_col,
            "Peak Power / BM [W/kg]": jump_peak_power_rel_col,
            "Peak Power [W]": jump_peak_power_col,
        }.items() if col is None
    ]
    if missing_jump:
        raise ValueError(f"Jump Data is missing required column(s): {', '.join(missing_jump)}.")

    jump_base = pd.DataFrame({
        "athlete": jump_raw[jump_name_col].astype(str).str.strip(),
        "date": parse_sheet_dates(jump_raw[jump_date_col]),
        "ci": pd.to_numeric(jump_raw[jump_ci_col], errors="coerce"),
        "peak_power_rel": pd.to_numeric(
            jump_raw[jump_peak_power_rel_col], errors="coerce"
        ),
        "peak_power": pd.to_numeric(
            jump_raw[jump_peak_power_col], errors="coerce"
        ),
        "team_raw": jump_raw[jump_team_col].astype(str).str.strip() if jump_team_col else "",
    })
    jump_base["team"] = jump_base["team_raw"].map(normalize_team)
    jump_base["name_key"] = jump_base["athlete"].map(canonical_name)
    jump_base = jump_base[
        (jump_base["athlete"] != "")
        & (jump_base["name_key"] != "")
        & (jump_base["team"].notna())
    ].copy()

    jump = (
        jump_base.dropna(subset=["date", "ci"])[
            ["athlete", "date", "ci", "team", "name_key"]
        ]
        .sort_values(["athlete", "date"], kind="stable")
        .reset_index(drop=True)
    )
    jump_power = (
        jump_base.dropna(subset=["date"])[
            ["athlete", "date", "peak_power", "peak_power_rel", "team", "name_key"]
        ]
        .sort_values(["athlete", "date"], kind="stable")
        .reset_index(drop=True)
    )

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



    # Pinch Grip. This intentionally uses the dedicated Pinch Grip sheet,
    # not the DOM Pinch field from Shoulder Data.
    pinch_raw.columns = pinch_raw.columns.astype(str).str.strip()
    pinch_name_col = first_existing(
        pinch_raw.columns.tolist(),
        ["Name", "name", "Athlete", "athlete", "Player", "player"],
    )
    pinch_date_col = first_existing(
        pinch_raw.columns.tolist(),
        ["Date", "date", "Test Date", "test_date"],
    )
    pinch_team_col = first_existing(
        pinch_raw.columns.tolist(),
        ["Team", "team", "Level", "level"],
    )
    pinch_player_id_col = first_existing(
        pinch_raw.columns.tolist(),
        ["PlayerID", "Player ID", "player_id", "playerid"],
    )
    pinch_left_col = first_existing(
        pinch_raw.columns.tolist(),
        [
            "Pinch - L", "Pinch-L", "Pinch L", "pinch - l", "pinch_l",
            "Left Pinch", "left pinch", "Left_Pinch", "left_pinch",
        ],
    )
    pinch_right_col = first_existing(
        pinch_raw.columns.tolist(),
        [
            "Pinch - R", "Pinch-R", "Pinch R", "pinch - r", "pinch_r",
            "Right Pinch", "right pinch", "Right_Pinch", "right_pinch",
        ],
    )

    missing_pinch = [
        label for label, col in {
            "name": pinch_name_col,
            "date": pinch_date_col,
        }.items() if col is None
    ]
    if missing_pinch:
        raise ValueError(
            f"Pinch Grip is missing required column(s): {', '.join(missing_pinch)}."
        )
    if pinch_left_col is None and pinch_right_col is None:
        raise ValueError(
            "Pinch Grip must contain Pinch - R and/or Pinch - L."
        )

    pinch = pd.DataFrame({
        "athlete": pinch_raw[pinch_name_col].astype(str).str.strip(),
        "date": parse_sheet_dates(pinch_raw[pinch_date_col]),
        "player_id": (
            pinch_raw[pinch_player_id_col].astype(str).str.strip()
            if pinch_player_id_col else ""
        ),
        "team_raw": (
            pinch_raw[pinch_team_col].astype(str).str.strip()
            if pinch_team_col else ""
        ),
        "left_pinch": (
            pd.to_numeric(pinch_raw[pinch_left_col], errors="coerce")
            if pinch_left_col else np.nan
        ),
        "right_pinch": (
            pd.to_numeric(pinch_raw[pinch_right_col], errors="coerce")
            if pinch_right_col else np.nan
        ),
    })
    pinch["team"] = pinch["team_raw"].map(normalize_team)
    pinch["name_key"] = pinch["athlete"].map(canonical_name)

    # Each athlete with velocity data is tested on only one hand. Use the
    # populated hand directly rather than creating bilateral or best-side values.
    pinch["pinch_strength"] = pinch["right_pinch"].combine_first(
        pinch["left_pinch"]
    )
    pinch["pinch_hand"] = np.select(
        [
            pinch["right_pinch"].notna(),
            pinch["left_pinch"].notna(),
        ],
        ["Right", "Left"],
        default="Unknown",
    )
    pinch = pinch[
        (pinch["athlete"] != "")
        & (pinch["name_key"] != "")
    ].dropna(subset=["date", "pinch_strength"])
    pinch = (
        pinch.drop(columns=["team_raw"])
        .sort_values(["athlete", "date"], kind="stable")
        .reset_index(drop=True)
    )

    # Monthly bat speed. The source repeats monthly_avg_bat_speed on each
    # game row, so retain one final non-null value per hitter and month.
    bat_raw.columns = bat_raw.columns.astype(str).str.strip()
    bat_name_col = first_existing(
        bat_raw.columns.tolist(),
        [
            "batter", "Batter", "hitter", "Hitter", "athlete", "Athlete",
            "player", "Player", "Name", "name",
        ],
    )
    bat_date_col = first_existing(
        bat_raw.columns.tolist(),
        ["game_date", "Game Date", "date", "Date"],
    )
    bat_speed_col = first_existing(
        bat_raw.columns.tolist(),
        [
            "monthly_avg_bat_speed", "Monthly Avg Bat Speed",
            "monthly avg bat speed", "monthly_average_bat_speed",
            "Monthly Average Bat Speed",
        ],
    )
    sprint_speed_col = first_existing(
        bat_raw.columns.tolist(),
        [
            "monthly_max_sprint_speed", "Monthly Max Sprint Speed",
            "monthly max sprint speed", "monthly_max_speed",
            "Monthly Maximum Sprint Speed",
        ],
    )
    bat_team_col = first_existing(
        bat_raw.columns.tolist(),
        ["Team", "team", "Level", "level"],
    )

    missing_bat = [
        label for label, col in {
            "batter name": bat_name_col,
            "game date": bat_date_col,
            "monthly_avg_bat_speed": bat_speed_col,
        }.items() if col is None
    ]
    if missing_bat:
        raise ValueError(
            f"Bat-speed tab is missing required column(s): {', '.join(missing_bat)}. "
            "The default BAT_TAB is 'PP_Sprint'."
        )
    if sprint_speed_col is None:
        raise ValueError(
            "PP_Sprint is missing monthly_max_sprint_speed, which is required "
            "for the Sprint Speed Overview tab."
        )


    bat = pd.DataFrame({
        "hitter": bat_raw[bat_name_col].astype(str).str.strip(),
        "date": parse_sheet_dates(bat_raw[bat_date_col]),
        "monthly_avg_bat_speed": pd.to_numeric(
            bat_raw[bat_speed_col], errors="coerce"
        ),
        "team_raw": (
            bat_raw[bat_team_col].astype(str).str.strip()
            if bat_team_col else ""
        ),
    })
    bat["team"] = bat["team_raw"].map(normalize_team)
    bat["name_key"] = bat["hitter"].map(canonical_name)
    bat = bat[
        (bat["hitter"] != "") & (bat["name_key"] != "")
    ].dropna(subset=["date", "monthly_avg_bat_speed"])
    bat["month"] = bat["date"].dt.to_period("M").dt.to_timestamp()
    bat = bat.sort_values(["name_key", "month", "date"], kind="stable")
    bat = (
        bat.groupby(["name_key", "month"], as_index=False)
        .tail(1)[[
            "name_key", "hitter", "month", "date",
            "monthly_avg_bat_speed", "team",
        ]]
        .rename(columns={"date": "bat_speed_as_of"})
        .sort_values(["hitter", "month"], kind="stable")
        .reset_index(drop=True)
    )

    # P90 exit velocity from the dedicated Nats Hitting tab. The supplied
    # structure has one current row per hitter and no game date. Match by name;
    # current Jump Data team assignment remains the source of truth downstream.
    exit_raw.columns = exit_raw.columns.astype(str).str.strip()
    exit_name_col = first_existing(
        exit_raw.columns.tolist(),
        [
            "name", "Name", "hitter", "Hitter", "batter", "Batter",
            "athlete", "Athlete", "player", "Player",
        ],
    )
    exit_p90_col = first_existing(
        exit_raw.columns.tolist(),
        [
            "p90 EV", "P90 EV", "p90_ev", "P90 Exit Velo",
            "P90 Exit Velocity", "p90 exit velo", "p90 exit velocity",
        ],
    )
    exit_level_col = first_existing(
        exit_raw.columns.tolist(),
        [
            "levelofplay_lk", "LevelOfPlay_Lk", "Level of Play",
            "Level", "level", "Team", "team",
        ],
    )

    missing_exit = [
        label for label, col in {
            "hitter name": exit_name_col,
            "p90 EV": exit_p90_col,
        }.items() if col is None
    ]
    if missing_exit:
        raise ValueError(
            f"Nats Hitting is missing required column(s): {', '.join(missing_exit)}. "
            "Expected at least 'name' and 'p90 EV'."
        )

    level_to_team = {
        "MLB": "Washington",
        "AAA": "Rochester",
        "AA": "Harrisburg",
        "A+": "Wilmington",
        "A": "Fredericksburg",
        "FCL": "FCL",
        "DSL": "DSL",
        "REHAB": "REHAB",
    }
    exit_velo = pd.DataFrame({
        "hitter": exit_raw[exit_name_col].astype(str).str.strip(),
        "p90_exit_velo": pd.to_numeric(exit_raw[exit_p90_col], errors="coerce"),
        "team_raw": (
            exit_raw[exit_level_col].astype(str).str.strip()
            if exit_level_col else ""
        ),
    })
    exit_velo["team"] = exit_velo["team_raw"].map(
        lambda value: level_to_team.get(str(value).strip().upper())
    )
    exit_velo["name_key"] = exit_velo["hitter"].map(canonical_name)
    exit_velo = exit_velo[
        (exit_velo["hitter"] != "") & (exit_velo["name_key"] != "")
    ].dropna(subset=["p90_exit_velo"])
    exit_velo = (
        exit_velo.drop(columns=["team_raw"])
        .drop_duplicates("name_key", keep="last")
        .sort_values("hitter", kind="stable")
        .reset_index(drop=True)
    )

    # Monthly max sprint speed. Keep the valid PP_Sprint source rows here so
    # the selected dashboard date range can be applied before monthly coverage
    # is calculated. A qualifying month must contain at least 14 DISTINCT data
    # dates; merely having two sparse records 14 days apart is not sufficient.
    sprint = pd.DataFrame({
        "athlete": bat_raw[bat_name_col].astype(str).str.strip(),
        "date": parse_sheet_dates(bat_raw[bat_date_col]),
        "monthly_max_sprint_speed": pd.to_numeric(
            bat_raw[sprint_speed_col], errors="coerce"
        ),
        "team_raw": (
            bat_raw[bat_team_col].astype(str).str.strip()
            if bat_team_col else ""
        ),
    })
    sprint["team"] = sprint["team_raw"].map(normalize_team)
    sprint["name_key"] = sprint["athlete"].map(canonical_name)
    sprint = sprint[
        (sprint["athlete"] != "") & (sprint["name_key"] != "")
    ].dropna(subset=["date", "monthly_max_sprint_speed"])
    sprint["month"] = sprint["date"].dt.to_period("M").dt.to_timestamp()
    sprint = sprint.sort_values(
        ["name_key", "month", "date"], kind="stable"
    ).reset_index(drop=True)

    # Selected defensive/baserunning outcomes. These source sheets are current
    # season-to-date snapshots, so they are matched cross-sectionally to the
    # player's mean Peak Power / BM inside the dashboard's selected date window.
    infield_raw.columns = infield_raw.columns.astype(str).str.strip()
    infield_name_col = first_existing(
        infield_raw.columns.tolist(), ["name", "Name", "player", "Player", "Athlete", "athlete"]
    )
    infield_reaction_col = first_existing(
        infield_raw.columns.tolist(), ["IF_reaction_3ft", "IF Reaction 3ft", "IF reaction 3ft"]
    )
    if infield_name_col is None or infield_reaction_col is None:
        raise ValueError("Infield source must contain 'name' and 'IF_reaction_3ft'.")
    infield_defense = pd.DataFrame({
        "athlete": infield_raw[infield_name_col].astype(str).str.strip(),
        "if_reaction_3ft": pd.to_numeric(infield_raw[infield_reaction_col], errors="coerce"),
    })
    infield_defense["name_key"] = infield_defense["athlete"].map(canonical_name)
    infield_defense = (
        infield_defense[(infield_defense["athlete"] != "") & (infield_defense["name_key"] != "")]
        .dropna(subset=["if_reaction_3ft"])
        .groupby("name_key", as_index=False)
        .agg(athlete=("athlete", "first"), if_reaction_3ft=("if_reaction_3ft", "mean"))
    )

    baserunning_raw.columns = baserunning_raw.columns.astype(str).str.strip()
    baserunning_name_col = first_existing(
        baserunning_raw.columns.tolist(), ["name", "Name", "player", "Player", "Athlete", "athlete"]
    )
    nbsr_col = first_existing(baserunning_raw.columns.tolist(), ["nBSR", "NBSR", "nbsr"])
    adv_runs_col = first_existing(
        baserunning_raw.columns.tolist(), ["Adv Runs", "Adv runs", "adv runs", "Adv_Runs", "adv_runs"]
    )
    baserunning_sprint_col = first_existing(
        baserunning_raw.columns.tolist(),
        ["Sprint Speed", "Sprint speed", "sprint speed", "Sprint_Speed", "sprint_speed"],
    )
    if (
        baserunning_name_col is None
        or nbsr_col is None
        or adv_runs_col is None
        or baserunning_sprint_col is None
    ):
        raise ValueError(
            "Baserunning source must contain 'name', 'nBSR', 'Adv Runs', and 'Sprint Speed'."
        )
    baserunning_defense = pd.DataFrame({
        "athlete": baserunning_raw[baserunning_name_col].astype(str).str.strip(),
        "nbsr": pd.to_numeric(baserunning_raw[nbsr_col], errors="coerce"),
        "adv_runs": pd.to_numeric(baserunning_raw[adv_runs_col], errors="coerce"),
        "baserunning_sprint_speed": pd.to_numeric(
            baserunning_raw[baserunning_sprint_col], errors="coerce"
        ),
    })
    baserunning_defense["name_key"] = baserunning_defense["athlete"].map(canonical_name)
    baserunning_defense = (
        baserunning_defense[(baserunning_defense["athlete"] != "") & (baserunning_defense["name_key"] != "")]
        .dropna(subset=["nbsr", "adv_runs", "baserunning_sprint_speed"], how="all")
        .groupby("name_key", as_index=False)
        .agg(
            athlete=("athlete", "first"),
            nbsr=("nbsr", "mean"),
            adv_runs=("adv_runs", "mean"),
            baserunning_sprint_speed=("baserunning_sprint_speed", "mean"),
        )
    )

    status = (
        f"Loaded {len(jump):,} CI rows, {len(jump_power):,} relative-power rows, "
        f"{len(velo):,} FB Velo rows, {len(pinch):,} Pinch Grip rows, "
        f"{len(sprint):,} valid sprint-speed rows, {len(bat):,} hitter-month "
        f"bat-speed rows, {len(exit_velo):,} valid P90 exit-velocity rows, "
        f"{len(infield_defense):,} IF Reaction 3ft rows, and {len(baserunning_defense):,} baserunning rows · "
        f"{datetime.now().strftime('%I:%M %p').lstrip('0')}"
    )
    return (
        jump, jump_power, velo, bat, pinch, sprint, exit_velo,
        infield_defense, baserunning_defense, status,
    )


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


def ci_band_summary(summary: pd.DataFrame, band_width: int, velo_stat: str = "Mean") -> pd.DataFrame:
    """Summarize last YTD FB velo by pitcher-average CI bucket using mean or median."""
    stat = "Median" if str(velo_stat).strip().lower() == "median" else "Mean"
    velo_col = f"{stat} Last YTD FB Velo"

    if summary.empty:
        return pd.DataFrame(columns=["CI band", velo_col, "Pitchers", "Average CI"])

    width = max(1, int(band_width))
    work = summary[["avg_ci", "avg_fb_velo"]].dropna().copy()
    work["band_start"] = ci_bucket_start(work["avg_ci"], width)
    grouped = (
        work.groupby("band_start", as_index=False)
        .agg(
            **{
                velo_col: ("avg_fb_velo", "median" if stat == "Median" else "mean"),
                "Pitchers": ("avg_fb_velo", "count"),
                "Average CI": ("avg_ci", "mean"),
            }
        )
        .sort_values("band_start")
    )
    grouped["CI band"] = grouped["band_start"].map(lambda lower: ci_bucket_label(lower, width))
    grouped[velo_col] = grouped[velo_col].round(2)
    grouped["Average CI"] = grouped["Average CI"].round(2)
    grouped["Pitchers"] = grouped["Pitchers"].astype(int)
    return grouped[["CI band", velo_col, "Pitchers", "Average CI"]]


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


def build_band_chart(summary: pd.DataFrame, band_width: int, velo_stat: str = "Mean") -> go.Figure:
    stat = "Median" if str(velo_stat).strip().lower() == "median" else "Mean"
    velo_col = f"{stat} Last YTD FB Velo"
    bands = ci_band_summary(summary, band_width, stat)
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
        x=bands["CI band"], y=bands[velo_col],
        marker={"color": BLUE, "line": {"color": NAVY_MID, "width": 0.8}},
        text=[f"{velo:.1f}" for velo in bands[velo_col]], textposition="outside", cliponaxis=False,
        customdata=np.column_stack([bands["Pitchers"], bands["Average CI"]]),
        hovertemplate=(
            f"<b>%{{x}}</b><br>{stat} last YTD FB velo: %{{y:.2f}} mph<br>"
            "Pitchers: %{customdata[0]}<br>Mean CI within band: %{customdata[1]:.2f} N·s<extra></extra>"
        ),
    ))
    y_min = max(0, float(bands[velo_col].min()) - 1.5)
    y_max = float(bands[velo_col].max()) + 1.25
    fig.update_xaxes(
        title="Pitcher average CI band", showgrid=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title=f"{stat} last YTD FB velo (mph)", range=[y_min, y_max], showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER, tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 380)



def ci_band_members(
    summary: pd.DataFrame,
    band_width: int,
    ci_band: str,
    velo_stat: str = "Mean",
) -> tuple[pd.DataFrame, float, str]:
    """Return all pitchers in one CI band and flag them versus that band's mean/median velo."""
    stat = "Median" if str(velo_stat).strip().lower() == "median" else "Mean"
    width = max(1, int(band_width))

    cols = ["athlete", "team", "avg_ci", "avg_fb_velo"]
    if summary.empty or any(col not in summary.columns for col in cols):
        return pd.DataFrame(columns=cols + ["CI band", "Status", "Difference"]), np.nan, stat

    detail = summary[cols].dropna().copy()
    detail["band_start"] = ci_bucket_start(detail["avg_ci"], width)
    detail["CI band"] = detail["band_start"].map(
        lambda lower: ci_bucket_label(lower, width)
    )
    detail = detail[detail["CI band"] == ci_band].copy()
    if detail.empty:
        return detail, np.nan, stat

    reference = (
        float(detail["avg_fb_velo"].median())
        if stat == "Median"
        else float(detail["avg_fb_velo"].mean())
    )
    detail["Difference"] = detail["avg_fb_velo"] - reference
    detail["Status"] = np.where(
        np.isclose(detail["Difference"], 0, atol=1e-10),
        f"At {stat.lower()}",
        np.where(detail["Difference"] > 0, f"Above {stat.lower()}", f"Below {stat.lower()}"),
    )
    detail["Display"] = detail.apply(
        lambda row: f"{row['athlete']} · {row['avg_ci']:.1f} CI", axis=1
    )
    return detail.sort_values("avg_fb_velo", ascending=False).reset_index(drop=True), reference, stat


def build_ci_band_member_chart(
    summary: pd.DataFrame,
    band_width: int,
    ci_band: str,
    velo_stat: str = "Mean",
) -> go.Figure:
    """Horizontal detail chart for every pitcher in a selected CI band."""
    detail, reference, stat = ci_band_members(summary, band_width, ci_band, velo_stat)
    fig = go.Figure()

    if detail.empty:
        fig.add_annotation(
            text="No pitchers are available in this CI band.", showarrow=False,
            font={"size": 14, "color": SUBTEXT}, x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 340)

    status_style = [
        (f"Above {stat.lower()}", GREEN),
        (f"At {stat.lower()}", TEAL),
        (f"Below {stat.lower()}", ACCENT_RED),
    ]
    category_order = detail["Display"].tolist()

    for status, color in status_style:
        sub = detail[detail["Status"] == status].copy()
        if sub.empty:
            continue
        customdata = np.column_stack([
            sub["athlete"], sub["team"], sub["avg_ci"], sub["Difference"], sub["Status"],
        ])
        fig.add_trace(go.Bar(
            x=sub["avg_fb_velo"],
            y=sub["Display"],
            orientation="h",
            name=status.title(),
            marker={"color": color, "line": {"color": "#FFFFFF", "width": 1}},
            text=[f"{value:.2f}" for value in sub["avg_fb_velo"]],
            textposition="outside",
            cliponaxis=False,
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Team: %{customdata[1]}<br>"
                "Average CI: %{customdata[2]:.2f} N·s<br>"
                "Last YTD FB velo: %{x:.2f} mph<br>"
                f"{stat} difference: %{{customdata[3]:+.2f}} mph<br>"
                "Flag: %{customdata[4]}<extra></extra>"
            ),
        ))

    x_min = max(0, float(detail["avg_fb_velo"].min()) - 1.5)
    x_max = float(detail["avg_fb_velo"].max()) + 1.25
    fig.add_vline(
        x=reference, line_color=NAVY_MID, line_width=2, line_dash="dash",
        annotation_text=f"{stat} {reference:.2f}",
        annotation_font_color=NAVY_MID,
        annotation_position="top right",
    )
    fig.update_xaxes(
        title="Last YTD FB velo (mph)", range=[x_min, x_max], showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER, tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Pitcher · Average CI", categoryorder="array", categoryarray=category_order,
        autorange="reversed", showgrid=False, linecolor=BORDER, tickfont={"color": TEXT, "size": 12},
        title_font={"color": SUBTEXT}, automargin=True,
    )
    fig = base_figure_layout(fig, max(340, len(detail) * 42 + 125))
    fig.update_layout(
        showlegend=True,
        legend={"orientation": "h", "x": 0, "y": 1.14, "font": {"color": SUBTEXT}},
        margin={"l": 190, "r": 70, "t": 50, "b": 58},
    )
    return fig


def metric_card(title: str, value: str, accent: str) -> str:
    return f"""
    <div class="metric-card">
      <div class="metric-accent" style="background:{accent};"></div>
      <div class="metric-label">{html.escape(title)}</div>
      <div class="metric-value">{html.escape(value)}</div>
    </div>
    """


def output_bucket_summary(
    df: pd.DataFrame,
    output_col: str,
    testing_col: str,
    bucket_width: float,
    output_bucket_label: str,
    testing_metric_label: str,
    output_unit: str,
    testing_unit: str,
    testing_stat: str = "Mean",
) -> pd.DataFrame:
    """Summarize the mean or median testing metric within output-metric buckets."""
    stat = "Median" if str(testing_stat).strip().lower() == "median" else "Mean"
    value_col = f"{stat} {testing_metric_label}"
    output_avg_col = f"Average {output_bucket_label}"
    cols = [output_col, testing_col]
    empty_columns = [output_bucket_label, value_col, "Observations", output_avg_col]
    if df.empty or any(col not in df.columns for col in cols):
        return pd.DataFrame(columns=empty_columns)

    width = max(float(bucket_width), 1e-9)
    work = df[cols].dropna().copy()
    if work.empty:
        return pd.DataFrame(columns=empty_columns)

    work["band_start"] = np.floor(work[output_col] / width) * width
    if output_col == "monthly_avg_bat_speed":
        work.loc[work[output_col] < BAT_SPEED_OUTPUT_BUCKET_FLOOR, "band_start"] = (
            BAT_SPEED_OUTPUT_BUCKET_FLOOR - width
        )
    if output_col == "p90_exit_velo":
        work.loc[work[output_col] < EXIT_VELO_OUTPUT_BUCKET_FLOOR, "band_start"] = (
            EXIT_VELO_OUTPUT_BUCKET_FLOOR - width
        )
    if output_col == "avg_fb_velo":
        work["band_start"] = np.minimum(work["band_start"], FB_VELO_OUTPUT_BUCKET_TOP)

    agg_func = "median" if stat == "Median" else "mean"
    grouped = (
        work.groupby("band_start", as_index=False)
        .agg(
            **{
                value_col: (testing_col, agg_func),
                "Observations": (testing_col, "count"),
                output_avg_col: (output_col, "mean"),
            }
        )
        .sort_values("band_start")
        .reset_index(drop=True)
    )

    def _fmt_bucket(lower: float) -> str:
        if output_col == "monthly_avg_bat_speed" and lower < BAT_SPEED_OUTPUT_BUCKET_FLOOR:
            return f"<{BAT_SPEED_OUTPUT_BUCKET_FLOOR:.0f} {output_unit}"
        if output_col == "p90_exit_velo" and lower < EXIT_VELO_OUTPUT_BUCKET_FLOOR:
            return f"<{EXIT_VELO_OUTPUT_BUCKET_FLOOR:.0f} {output_unit}"
        if output_col == "avg_fb_velo" and lower >= FB_VELO_OUTPUT_BUCKET_TOP:
            return f"{FB_VELO_OUTPUT_BUCKET_TOP:.0f}+ {output_unit}"
        upper = lower + width
        if float(width).is_integer():
            return f"{lower:.0f}–{upper:.0f} {output_unit}"
        return f"{lower:.1f}–{upper:.1f} {output_unit}"

    grouped[output_bucket_label] = grouped["band_start"].map(_fmt_bucket)
    grouped[value_col] = grouped[value_col].round(2)
    grouped[output_avg_col] = grouped[output_avg_col].round(2)
    grouped["Observations"] = grouped["Observations"].astype(int)
    return grouped[[output_bucket_label, value_col, "Observations", output_avg_col]]


def build_output_bucket_chart(
    df: pd.DataFrame,
    output_col: str,
    testing_col: str,
    bucket_width: float,
    output_bucket_label: str,
    testing_metric_label: str,
    output_axis_title: str,
    testing_axis_title: str,
    output_unit: str,
    empty_text: str,
    color: str = BLUE,
    testing_stat: str = "Mean",
) -> go.Figure:
    stat = "Median" if str(testing_stat).strip().lower() == "median" else "Mean"
    bands = output_bucket_summary(
        df=df,
        output_col=output_col,
        testing_col=testing_col,
        bucket_width=bucket_width,
        output_bucket_label=output_bucket_label,
        testing_metric_label=testing_metric_label,
        output_unit=output_unit,
        testing_unit="",
        testing_stat=stat,
    )
    value_col = f"{stat} {testing_metric_label}"
    output_avg_col = f"Average {output_bucket_label}"

    fig = go.Figure()
    if bands.empty:
        fig.add_annotation(
            text=empty_text,
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 380)

    fig.add_trace(go.Bar(
        x=bands[output_bucket_label],
        y=bands[value_col],
        marker={"color": color, "line": {"color": NAVY_MID, "width": 0.8}},
        text=[f"{value:.1f}" for value in bands[value_col]],
        textposition="outside",
        cliponaxis=False,
        customdata=np.column_stack([bands["Observations"], bands[output_avg_col]]),
        hovertemplate=(
            f"<b>%{{x}}</b><br>{stat} {testing_metric_label}: %{{y:.2f}}<br>"
            "Observations: %{customdata[0]}<br>"
            f"Mean {output_axis_title.lower()}: %{{customdata[1]:.2f}} {output_unit}<extra></extra>"
        ),
    ))
    y_min = max(0, float(bands[value_col].min()) - 1.5)
    y_max = float(bands[value_col].max()) + 1.25
    fig.update_xaxes(
        title=output_axis_title, showgrid=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title=testing_axis_title, range=[y_min, y_max], showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 380)


def output_bucket_members(
    df: pd.DataFrame,
    output_col: str,
    testing_col: str,
    bucket_width: float,
    selected_bucket: str,
    output_bucket_label: str,
    output_unit: str,
    entity_col: str = "athlete",
    team_col: str = "team",
    testing_stat: str = "Mean",
) -> tuple[pd.DataFrame, float, str]:
    """Return athletes in one output bucket and compare testing values with mean/median."""
    stat = "Median" if str(testing_stat).strip().lower() == "median" else "Mean"
    required = [entity_col, output_col, testing_col]
    columns = required + [team_col, output_bucket_label, "Difference", "Status", "Display"]
    if df.empty or any(col not in df.columns for col in required):
        return pd.DataFrame(columns=columns), np.nan, stat

    width = max(float(bucket_width), 1e-9)
    work_cols = list(dict.fromkeys(required + ([team_col] if team_col in df.columns else [])))
    detail = df[work_cols].dropna(subset=required).copy()
    if detail.empty:
        return pd.DataFrame(columns=columns), np.nan, stat

    detail["band_start"] = np.floor(detail[output_col] / width) * width
    if output_col == "monthly_avg_bat_speed":
        detail.loc[detail[output_col] < BAT_SPEED_OUTPUT_BUCKET_FLOOR, "band_start"] = (
            BAT_SPEED_OUTPUT_BUCKET_FLOOR - width
        )
    if output_col == "p90_exit_velo":
        detail.loc[detail[output_col] < EXIT_VELO_OUTPUT_BUCKET_FLOOR, "band_start"] = (
            EXIT_VELO_OUTPUT_BUCKET_FLOOR - width
        )
    if output_col == "avg_fb_velo":
        detail["band_start"] = np.minimum(detail["band_start"], FB_VELO_OUTPUT_BUCKET_TOP)

    def _fmt_bucket(lower: float) -> str:
        if output_col == "monthly_avg_bat_speed" and lower < BAT_SPEED_OUTPUT_BUCKET_FLOOR:
            return f"<{BAT_SPEED_OUTPUT_BUCKET_FLOOR:.0f} {output_unit}"
        if output_col == "p90_exit_velo" and lower < EXIT_VELO_OUTPUT_BUCKET_FLOOR:
            return f"<{EXIT_VELO_OUTPUT_BUCKET_FLOOR:.0f} {output_unit}"
        if output_col == "avg_fb_velo" and lower >= FB_VELO_OUTPUT_BUCKET_TOP:
            return f"{FB_VELO_OUTPUT_BUCKET_TOP:.0f}+ {output_unit}"
        upper = lower + width
        if float(width).is_integer():
            return f"{lower:.0f}–{upper:.0f} {output_unit}"
        return f"{lower:.1f}–{upper:.1f} {output_unit}"

    detail[output_bucket_label] = detail["band_start"].map(_fmt_bucket)
    detail = detail[detail[output_bucket_label] == selected_bucket].copy()
    if detail.empty:
        return detail, np.nan, stat

    if team_col not in detail.columns:
        detail[team_col] = "Unassigned"
    detail[team_col] = detail[team_col].fillna("Unassigned")

    reference = (
        float(detail[testing_col].median())
        if stat == "Median"
        else float(detail[testing_col].mean())
    )
    detail["Difference"] = detail[testing_col] - reference
    detail["Status"] = np.where(
        np.isclose(detail["Difference"], 0, atol=1e-10),
        f"At {stat.lower()}",
        np.where(
            detail["Difference"] > 0,
            f"Above {stat.lower()}",
            f"Below {stat.lower()}",
        ),
    )
    detail["Display"] = detail.apply(
        lambda row: f"{row[entity_col]} · {row[output_col]:.1f} {output_unit}", axis=1,
    )
    return detail.sort_values(testing_col, ascending=False).reset_index(drop=True), reference, stat


def build_output_bucket_member_chart(
    df: pd.DataFrame,
    output_col: str,
    testing_col: str,
    bucket_width: float,
    selected_bucket: str,
    output_bucket_label: str,
    output_unit: str,
    testing_axis_title: str,
    testing_unit: str,
    entity_label: str,
    output_value_label: str,
    entity_col: str = "athlete",
    team_col: str = "team",
    testing_stat: str = "Mean",
) -> go.Figure:
    """Horizontal athlete chart for one output bucket, using mean/median reference."""
    detail, reference, stat = output_bucket_members(
        df=df, output_col=output_col, testing_col=testing_col, bucket_width=bucket_width,
        selected_bucket=selected_bucket, output_bucket_label=output_bucket_label,
        output_unit=output_unit, entity_col=entity_col, team_col=team_col, testing_stat=testing_stat,
    )
    fig = go.Figure()

    if detail.empty:
        fig.add_annotation(
            text="No athletes are available in this output bucket.", showarrow=False,
            font={"size": 14, "color": SUBTEXT}, x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 340)

    status_style = [
        (f"Above {stat.lower()}", GREEN),
        (f"At {stat.lower()}", TEAL),
        (f"Below {stat.lower()}", ACCENT_RED),
    ]
    category_order = detail["Display"].tolist()

    for status, color in status_style:
        sub = detail[detail["Status"] == status].copy()
        if sub.empty:
            continue
        customdata = np.column_stack([
            sub[entity_col], sub[team_col], sub[output_col], sub["Difference"], sub["Status"],
        ])
        fig.add_trace(go.Bar(
            x=sub[testing_col], y=sub["Display"], orientation="h", name=status.title(),
            marker={"color": color, "line": {"color": "#FFFFFF", "width": 1}},
            text=[f"{value:.2f}" for value in sub[testing_col]], textposition="outside",
            cliponaxis=False, customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Team: %{customdata[1]}<br>"
                f"{output_value_label}: %{{customdata[2]:.2f}} {output_unit}<br>"
                f"{testing_axis_title}: %{{x:.2f}} {testing_unit}<br>"
                f"Difference from bucket {stat.lower()}: %{{customdata[3]:+.2f}}<br>"
                "Flag: %{customdata[4]}<extra></extra>"
            ),
        ))

    values = detail[testing_col].to_numpy(dtype=float)
    data_min = float(np.min(values))
    data_max = float(np.max(values))
    span = max(data_max - data_min, abs(reference) * 0.05, 1.0)
    pad = max(span * 0.18, 0.5)
    x_min = max(0, data_min - pad)
    x_max = data_max + pad

    fig.add_vline(
        x=reference, line_color=NAVY_MID, line_width=2, line_dash="dash",
        annotation_text=f"{stat} {reference:.2f}", annotation_font_color=NAVY_MID,
        annotation_position="top right",
    )
    fig.update_xaxes(
        title=testing_axis_title, range=[x_min, x_max], showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title=f"{entity_label} · {output_value_label}", categoryorder="array",
        categoryarray=category_order, autorange="reversed", showgrid=False, linecolor=BORDER,
        tickfont={"color": TEXT, "size": 12}, title_font={"color": SUBTEXT}, automargin=True,
    )
    fig = base_figure_layout(fig, max(340, len(detail) * 42 + 125))
    fig.update_layout(
        showlegend=True,
        legend={"orientation": "h", "x": 0, "y": 1.14, "font": {"color": SUBTEXT}},
        margin={"l": 210, "r": 80, "t": 50, "b": 58},
    )
    return fig

def fisher_mean_correlation(values: pd.Series) -> float:
    """Average correlations on Fisher's z scale rather than raw r."""
    clean = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(clean) == 0:
        return np.nan
    clean = np.clip(clean, -0.999999, 0.999999)
    return float(np.tanh(np.mean(np.arctanh(clean))))




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
# MONTHLY BAT SPEED × CI
# -----------------------------------------------------------------------------
def build_bat_monthly_pairs(
    jump: pd.DataFrame,
    bat: pd.DataFrame,
    start_date,
    end_date,
    team_filter: str,
    min_ci_jumps: int,
) -> pd.DataFrame:
    """Create one hitter-level observation from the latest qualifying month.

    A qualifying month must contain a valid final monthly_avg_bat_speed value
    whose as-of date falls inside the selected dashboard date range and at
    least min_ci_jumps raw CI rows from Jump Data in that same month and
    selected date range. After those rules are applied, only each hitter's
    latest qualifying month is retained, so the regression receives exactly
    one row per hitter.
    """
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()

    # Apply the actual selected dates before assigning Jump Data to months.
    # This prevents tests outside a partial selected month from contributing.
    jump_window = jump[
        (jump["date"] >= start) & (jump["date"] <= end)
    ].copy()
    jump_window["month"] = (
        jump_window["date"].dt.to_period("M").dt.to_timestamp()
    )
    ci_monthly = (
        jump_window.groupby(["name_key", "month"], as_index=False)
        .agg(
            athlete=("athlete", "first"),
            avg_ci=("ci", "mean"),
            ci_jumps=("ci", "count"),
            ci_test_dates=("date", "nunique"),
            first_ci_date=("date", "min"),
            last_ci_date=("date", "max"),
        )
    )

    team_lookup = (
        jump.sort_values("date")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
        .rename(columns={"team": "current_team"})
    )

    # The bat table already contains one final non-null monthly value per
    # hitter-month. Require that final value's as-of date to fall inside the
    # selected dashboard window.
    bat_window = bat[
        (bat["bat_speed_as_of"] >= start)
        & (bat["bat_speed_as_of"] <= end)
    ].copy()

    eligible = ci_monthly.merge(
        bat_window, on=["name_key", "month"], how="inner"
    )
    eligible = eligible.merge(team_lookup, on="name_key", how="left")
    eligible["team"] = eligible["current_team"].combine_first(
        eligible["team"]
    )
    eligible = eligible.drop(columns=["current_team"])
    eligible["team"] = eligible["team"].fillna("Unassigned")
    eligible = eligible[
        eligible["ci_jumps"] >= max(1, int(min_ci_jumps))
    ].copy()

    if team_filter != "All Teams":
        eligible = eligible[eligible["team"] == team_filter].copy()

    if eligible.empty:
        eligible["month_label"] = pd.Series(dtype=str)
        eligible["observation"] = pd.Series(dtype=str)
        return eligible.reset_index(drop=True)

    # Select the latest qualifying month only after matching and minimum-data
    # rules, preserving one independent cross-sectional observation per hitter.
    summary = (
        eligible.sort_values(
            ["name_key", "month", "bat_speed_as_of"],
            kind="stable",
        )
        .groupby("name_key", as_index=False)
        .tail(1)
        .copy()
    )
    summary["month_label"] = summary["month"].dt.strftime("%b %Y")
    summary["observation"] = summary["athlete"]
    return summary.sort_values(
        ["athlete"], kind="stable"
    ).reset_index(drop=True)


def bat_correlation_stats(
    pairs: pd.DataFrame,
) -> tuple[float, float, float, float] | None:
    if len(pairs) < 2:
        return None
    x = pairs["avg_ci"].to_numpy(dtype=float)
    y = pairs["monthly_avg_bat_speed"].to_numpy(dtype=float)
    if np.isclose(np.std(x), 0) or np.isclose(np.std(y), 0):
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return r, r * r, float(slope), float(intercept)


def bat_ci_band_summary(
    pairs: pd.DataFrame,
    band_width: int,
    bat_stat: str = "Mean",
) -> pd.DataFrame:
    stat = "Median" if str(bat_stat).strip().lower() == "median" else "Mean"
    speed_col = f"{stat} Monthly Bat Speed"
    if pairs.empty:
        return pd.DataFrame(
            columns=["CI band", speed_col, "Hitters", "Average CI"]
        )

    width = max(1, int(band_width))
    work = pairs[
        ["name_key", "avg_ci", "monthly_avg_bat_speed"]
    ].dropna().copy()
    work["band_start"] = hitting_ci_bucket_start(work["avg_ci"], width)
    grouped = (
        work.groupby("band_start", as_index=False)
        .agg(
            **{
                speed_col: (
                    "monthly_avg_bat_speed",
                    "median" if stat == "Median" else "mean",
                ),
                "Hitters": ("name_key", "nunique"),
                "Average CI": ("avg_ci", "mean"),
            }
        )
        .sort_values("band_start")
    )
    grouped["CI band"] = grouped["band_start"].map(
        lambda lower: hitting_ci_bucket_label(lower, width)
    )
    grouped[speed_col] = grouped[speed_col].round(2)
    grouped["Average CI"] = grouped["Average CI"].round(2)
    return grouped[["CI band", speed_col, "Hitters", "Average CI"]]


def build_bat_scatter(
    pairs: pd.DataFrame,
    show_labels: bool,
    ci_lookup: float | None,
) -> go.Figure:
    fig = go.Figure()
    if pairs.empty:
        fig.add_annotation(
            text="No matched hitters meet the selected rules.",
            showarrow=False,
            font={"size": 15, "color": SUBTEXT},
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 560)

    customdata = np.column_stack([
        pairs["athlete"],
        pairs["team"],
        pairs["month_label"],
        pairs["ci_jumps"],
        pairs["ci_test_dates"],
        pairs["first_ci_date"].map(fmt_date),
        pairs["last_ci_date"].map(fmt_date),
        pairs["bat_speed_as_of"].map(fmt_date),
    ])
    fig.add_trace(go.Scatter(
        x=pairs["avg_ci"],
        y=pairs["monthly_avg_bat_speed"],
        mode="markers+text" if show_labels else "markers",
        text=pairs["observation"] if show_labels else None,
        textposition="top center",
        textfont={"size": 9, "color": NAVY},
        marker={
            "size": 13,
            "color": BLUE,
            "opacity": 0.86,
            "line": {"color": "#FFFFFF", "width": 2},
        },
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b> · %{customdata[2]}<br>"
            "Team: %{customdata[1]}<br>"
            "Monthly average bat speed: %{y:.2f} mph<br>"
            "Monthly average CI: %{x:.2f} N·s<br><br>"
            "CI jumps: %{customdata[3]} across %{customdata[4]} dates · "
            "%{customdata[5]}–%{customdata[6]}<br>"
            "Bat-speed value as of %{customdata[7]}<extra></extra>"
        ),
    ))

    stats = bat_correlation_stats(pairs)
    if stats is not None:
        r, r2, slope, intercept = stats
        x_range = np.linspace(
            pairs["avg_ci"].min(), pairs["avg_ci"].max(), 100
        )
        fig.add_trace(go.Scatter(
            x=x_range,
            y=slope * x_range + intercept,
            mode="lines",
            line={"color": NAVY_MID, "width": 2.5, "dash": "dash"},
            hoverinfo="skip",
        ))
        fig.add_annotation(
            text=f"r = {r:+.2f} · R² = {r2:.2f}",
            x=0.02,
            y=0.98,
            xref="paper",
            yref="paper",
            xanchor="left",
            yanchor="top",
            showarrow=False,
            font={"color": NAVY, "size": 13},
            bgcolor="#FFFFFF",
            bordercolor=BORDER,
            borderwidth=1,
            borderpad=7,
        )
        if ci_lookup is not None and np.isfinite(ci_lookup):
            predicted = slope * float(ci_lookup) + intercept
            fig.add_vline(
                x=float(ci_lookup),
                line_color=TEAL,
                line_width=1.5,
                line_dash="dot",
            )
            fig.add_hline(
                y=predicted,
                line_color=TEAL,
                line_width=1.5,
                line_dash="dot",
            )
            fig.add_trace(go.Scatter(
                x=[float(ci_lookup)],
                y=[predicted],
                mode="markers",
                marker={
                    "size": 15,
                    "color": TEAL,
                    "symbol": "diamond",
                    "line": {"color": "#FFFFFF", "width": 2},
                },
                hovertemplate=(
                    "<b>CI lookup</b><br>"
                    "Monthly average CI: %{x:.1f} N·s<br>"
                    "Estimated monthly average bat speed: %{y:.2f} mph"
                    "<extra></extra>"
                ),
            ))

    fig.update_xaxes(
        title="Monthly average concentric impulse (N·s)",
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Monthly average bat speed (mph)",
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 560)


def build_bat_band_chart(
    pairs: pd.DataFrame,
    band_width: int,
    bat_stat: str = "Mean",
) -> go.Figure:
    stat = "Median" if str(bat_stat).strip().lower() == "median" else "Mean"
    speed_col = f"{stat} Monthly Bat Speed"
    bands = bat_ci_band_summary(pairs, band_width, stat)
    fig = go.Figure()
    if bands.empty:
        fig.add_annotation(
            text="No matched hitters are available for CI bands.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 380)

    fig.add_trace(go.Bar(
        x=bands["CI band"],
        y=bands[speed_col],
        marker={"color": BLUE, "line": {"color": NAVY_MID, "width": 0.8}},
        text=[f"{speed:.1f}" for speed in bands[speed_col]],
        textposition="outside",
        cliponaxis=False,
        customdata=np.column_stack([
            bands["Hitters"],
            bands["Average CI"],
        ]),
        hovertemplate=(
            f"<b>%{{x}}</b><br>{stat} monthly bat speed: %{{y:.2f}} mph<br>"
            "Hitters: %{customdata[0]}<br>"
            "Mean CI within band: %{customdata[1]:.2f} N·s"
            "<extra></extra>"
        ),
    ))
    y_min = max(0, float(bands[speed_col].min()) - 2.0)
    y_max = float(bands[speed_col].max()) + 1.5
    fig.update_xaxes(
        title="Monthly average CI band",
        showgrid=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title=f"{stat} monthly average bat speed (mph)",
        range=[y_min, y_max],
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 380)




def bat_ci_band_members(
    pairs: pd.DataFrame,
    band_width: int,
    ci_band: str,
    bat_stat: str = "Mean",
) -> tuple[pd.DataFrame, float, str]:
    """Return all hitters in one CI band and flag them versus that band's mean/median bat speed."""
    stat = "Median" if str(bat_stat).strip().lower() == "median" else "Mean"
    width = max(1, int(band_width))

    cols = [
        "athlete", "team", "month_label", "avg_ci",
        "monthly_avg_bat_speed",
    ]
    if pairs.empty or any(col not in pairs.columns for col in cols):
        return (
            pd.DataFrame(columns=cols + ["CI band", "Status", "Difference"]),
            np.nan,
            stat,
        )

    detail = pairs[cols].dropna(
        subset=["avg_ci", "monthly_avg_bat_speed"]
    ).copy()
    detail["band_start"] = hitting_ci_bucket_start(detail["avg_ci"], width)
    detail["CI band"] = detail["band_start"].map(
        lambda lower: hitting_ci_bucket_label(lower, width)
    )
    detail = detail[detail["CI band"] == ci_band].copy()
    if detail.empty:
        return detail, np.nan, stat

    reference = (
        float(detail["monthly_avg_bat_speed"].median())
        if stat == "Median"
        else float(detail["monthly_avg_bat_speed"].mean())
    )
    detail["Difference"] = detail["monthly_avg_bat_speed"] - reference
    detail["Status"] = np.where(
        np.isclose(detail["Difference"], 0, atol=1e-10),
        f"At {stat.lower()}",
        np.where(
            detail["Difference"] > 0,
            f"Above {stat.lower()}",
            f"Below {stat.lower()}",
        ),
    )
    detail["Display"] = detail.apply(
        lambda row: f"{row['athlete']} · {row['avg_ci']:.1f} CI",
        axis=1,
    )
    return (
        detail.sort_values(
            "monthly_avg_bat_speed", ascending=False
        ).reset_index(drop=True),
        reference,
        stat,
    )


def build_bat_ci_band_member_chart(
    pairs: pd.DataFrame,
    band_width: int,
    ci_band: str,
    bat_stat: str = "Mean",
) -> go.Figure:
    """Horizontal detail chart for every hitter in a selected CI band."""
    detail, reference, stat = bat_ci_band_members(
        pairs, band_width, ci_band, bat_stat
    )
    fig = go.Figure()

    if detail.empty:
        fig.add_annotation(
            text="No hitters are available in this CI band.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 340)

    status_style = [
        (f"Above {stat.lower()}", GREEN),
        (f"At {stat.lower()}", TEAL),
        (f"Below {stat.lower()}", ACCENT_RED),
    ]
    category_order = detail["Display"].tolist()

    for status, color in status_style:
        sub = detail[detail["Status"] == status].copy()
        if sub.empty:
            continue
        customdata = np.column_stack([
            sub["athlete"],
            sub["team"],
            sub["month_label"],
            sub["avg_ci"],
            sub["Difference"],
            sub["Status"],
        ])
        fig.add_trace(go.Bar(
            x=sub["monthly_avg_bat_speed"],
            y=sub["Display"],
            orientation="h",
            name=status.title(),
            marker={
                "color": color,
                "line": {"color": "#FFFFFF", "width": 1},
            },
            text=[
                f"{value:.2f}"
                for value in sub["monthly_avg_bat_speed"]
            ],
            textposition="outside",
            cliponaxis=False,
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Team: %{customdata[1]}<br>"
                "Matched month: %{customdata[2]}<br>"
                "Monthly average CI: %{customdata[3]:.2f} N·s<br>"
                "Monthly average bat speed: %{x:.2f} mph<br>"
                f"{stat} difference: %{{customdata[4]:+.2f}} mph<br>"
                "Flag: %{customdata[5]}<extra></extra>"
            ),
        ))

    x_min = max(
        0,
        float(detail["monthly_avg_bat_speed"].min()) - 2.0,
    )
    x_max = float(detail["monthly_avg_bat_speed"].max()) + 1.5
    fig.add_vline(
        x=reference,
        line_color=NAVY_MID,
        line_width=2,
        line_dash="dash",
        annotation_text=f"{stat} {reference:.2f}",
        annotation_font_color=NAVY_MID,
        annotation_position="top right",
    )
    fig.update_xaxes(
        title="Monthly average bat speed (mph)",
        range=[x_min, x_max],
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Hitter · Monthly average CI",
        categoryorder="array",
        categoryarray=category_order,
        autorange="reversed",
        showgrid=False,
        linecolor=BORDER,
        tickfont={"color": TEXT, "size": 12},
        title_font={"color": SUBTEXT},
        automargin=True,
    )
    fig = base_figure_layout(
        fig, max(340, len(detail) * 42 + 125)
    )
    fig.update_layout(
        showlegend=True,
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.14,
            "font": {"color": SUBTEXT},
        },
        margin={"l": 210, "r": 70, "t": 50, "b": 58},
    )
    return fig



def build_bat_within_pairs(monthly_pairs: pd.DataFrame) -> pd.DataFrame:
    pairs = monthly_pairs.sort_values(
        ["name_key", "month"], kind="stable"
    ).copy()
    if pairs.empty:
        pairs["delta_ci"] = pd.Series(dtype=float)
        pairs["delta_bat_speed"] = pd.Series(dtype=float)
        return pairs

    first_ci = pairs.groupby("name_key")["avg_ci"].transform("first")
    first_bat = pairs.groupby("name_key")[
        "monthly_avg_bat_speed"
    ].transform("first")
    pairs["delta_ci"] = pairs["avg_ci"] - first_ci
    pairs["delta_bat_speed"] = (
        pairs["monthly_avg_bat_speed"] - first_bat
    )
    return pairs


def build_bat_within_summary(
    pairs: pd.DataFrame,
    min_paired_months: int,
) -> pd.DataFrame:
    rows = []
    required = max(3, int(min_paired_months))
    columns = [
        "name_key", "athlete", "team", "paired_months", "r", "r2",
        "slope", "first_month", "last_month", "delta_ci",
        "delta_bat_speed",
    ]
    if pairs.empty:
        return pd.DataFrame(columns=columns)

    for name_key, grp in pairs.groupby("name_key", sort=False):
        grp = grp.sort_values("month")
        n = len(grp)
        if n < required:
            continue

        x = grp["delta_ci"].to_numpy(dtype=float)
        y = grp["delta_bat_speed"].to_numpy(dtype=float)
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
            "paired_months": n,
            "r": r,
            "r2": r2,
            "slope": slope,
            "first_month": grp["month"].iloc[0],
            "last_month": grp["month"].iloc[-1],
            "delta_ci": grp["delta_ci"].iloc[-1],
            "delta_bat_speed": grp["delta_bat_speed"].iloc[-1],
        })

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).sort_values(
        ["r", "paired_months"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)


def build_bat_within_scatter(player_pairs: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if player_pairs.empty:
        fig.add_annotation(
            text="No monthly CI and bat-speed pairs for this hitter.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 470)

    customdata = np.column_stack([
        player_pairs["month_label"],
        player_pairs["avg_ci"],
        player_pairs["monthly_avg_bat_speed"],
        player_pairs["ci_jumps"],
        player_pairs["last_ci_date"].map(fmt_date),
    ])
    fig.add_trace(go.Scatter(
        x=player_pairs["delta_ci"],
        y=player_pairs["delta_bat_speed"],
        mode="markers+text",
        text=player_pairs["month_label"],
        textposition="top center",
        textfont={"size": 10, "color": NAVY},
        marker={
            "size": 13,
            "color": BLUE,
            "opacity": 0.9,
            "line": {"color": "#FFFFFF", "width": 2},
        },
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Δ CI: %{x:+.2f} N·s<br>"
            "Δ monthly bat speed: %{y:+.2f} mph<br><br>"
            "Monthly CI: %{customdata[1]:.2f} N·s · "
            "%{customdata[3]} jumps<br>"
            "Last CI test: %{customdata[4]}<br>"
            "Monthly average bat speed: %{customdata[2]:.2f} mph"
            "<extra></extra>"
        ),
    ))
    fig.add_vline(x=0, line_color="#AAB5C5", line_width=1)
    fig.add_hline(y=0, line_color="#AAB5C5", line_width=1)

    if (
        len(player_pairs) >= 3
        and not np.isclose(player_pairs["delta_ci"].std(), 0)
        and not np.isclose(player_pairs["delta_bat_speed"].std(), 0)
    ):
        x = player_pairs["delta_ci"].to_numpy(dtype=float)
        y = player_pairs["delta_bat_speed"].to_numpy(dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        r = float(np.corrcoef(x, y)[0, 1])
        x_range = np.linspace(x.min(), x.max(), 100)
        fig.add_trace(go.Scatter(
            x=x_range,
            y=slope * x_range + intercept,
            mode="lines",
            line={"color": NAVY_MID, "width": 2.5, "dash": "dash"},
            hoverinfo="skip",
        ))
        fig.add_annotation(
            text=f"r = {r:+.2f} · {len(player_pairs)} paired months",
            x=0.02,
            y=0.98,
            xref="paper",
            yref="paper",
            xanchor="left",
            yanchor="top",
            showarrow=False,
            font={"color": NAVY, "size": 13},
            bgcolor="#FFFFFF",
            bordercolor=BORDER,
            borderwidth=1,
            borderpad=7,
        )

    fig.update_xaxes(
        title="Change in monthly average CI from first month (N·s)",
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Change in monthly average bat speed from first month (mph)",
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 470)


def build_bat_within_timeline(player_pairs: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if player_pairs.empty:
        fig.add_annotation(
            text="No paired months.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 360)

    fig.add_trace(go.Scatter(
        x=player_pairs["month"],
        y=player_pairs["avg_ci"],
        mode="lines+markers",
        name="Monthly average CI",
        line={"color": BLUE, "width": 2.5},
        marker={"size": 8},
        customdata=player_pairs[["month_label"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Monthly average CI: %{y:.2f} N·s<extra></extra>"
        ),
    ))
    fig.add_trace(go.Scatter(
        x=player_pairs["month"],
        y=player_pairs["monthly_avg_bat_speed"],
        mode="lines+markers",
        name="Monthly average bat speed",
        yaxis="y2",
        line={"color": ACCENT_RED, "width": 2.5},
        marker={"size": 8},
        customdata=player_pairs[["month_label"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Monthly average bat speed: %{y:.2f} mph<extra></extra>"
        ),
    ))
    fig.update_layout(
        yaxis={
            "title": "Monthly average CI (N·s)",
            "showgrid": True,
            "gridcolor": GRID,
            "zeroline": False,
            "linecolor": BORDER,
            "tickfont": {"color": SUBTEXT},
            "title_font": {"color": SUBTEXT},
        },
        yaxis2={
            "title": "Monthly average bat speed (mph)",
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "zeroline": False,
            "linecolor": BORDER,
            "tickfont": {"color": SUBTEXT},
            "title_font": {"color": SUBTEXT},
        },
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.15,
            "font": {"color": SUBTEXT},
        },
        showlegend=True,
    )
    fig.update_xaxes(
        showgrid=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 360)




# -----------------------------------------------------------------------------
# P90 EXIT VELOCITY × YEAR-TO-DATE CI
# -----------------------------------------------------------------------------
def build_exit_velo_summary(
    jump: pd.DataFrame,
    exit_velo: pd.DataFrame,
    start_date,
    end_date,
    team_filter: str,
    min_ci_jumps: int,
) -> pd.DataFrame:
    """Create one P90 exit-velocity observation per hitter.

    Nats Hitting supplies one current ``p90 EV`` value per hitter and no
    observation date. To preserve the prior year-to-date CI comparison without
    inventing a P90 measurement date, CI is averaged from January 1 through
    the selected dashboard end date.
    """
    end = pd.Timestamp(end_date).normalize()
    year = int(end.year)

    columns = [
        "name_key", "athlete", "team", "year",
        "p90_exit_velo", "exit_velo_as_of", "exit_velo_records",
        "avg_ci", "ci_jumps", "ci_test_dates",
        "first_ci_date", "last_ci_date", "observation",
    ]
    if exit_velo.empty:
        return pd.DataFrame(columns=columns)

    current_exit = exit_velo[[
        "name_key", "hitter", "team", "p90_exit_velo",
    ]].dropna(subset=["p90_exit_velo"]).copy()
    current_exit = current_exit.drop_duplicates("name_key", keep="last")
    current_exit["year"] = year
    # Retain the existing downstream date field, but it now means CI through
    # this selected date; it is not a fabricated P90 measurement date.
    current_exit["exit_velo_as_of"] = end
    current_exit["exit_velo_records"] = 1

    team_lookup = (
        jump.sort_values("date")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
        .rename(columns={"team": "current_team"})
    )

    ci_candidates = jump[
        (jump["date"].dt.year == year) & (jump["date"] <= end)
    ].copy()
    ci_summary = (
        ci_candidates.groupby("name_key", as_index=False)
        .agg(
            athlete=("athlete", "first"),
            avg_ci=("ci", "mean"),
            ci_jumps=("ci", "count"),
            ci_test_dates=("date", "nunique"),
            first_ci_date=("date", "min"),
            last_ci_date=("date", "max"),
        )
    )

    summary = current_exit.merge(ci_summary, on="name_key", how="inner")
    summary = summary.merge(team_lookup, on="name_key", how="left")
    summary["team"] = summary["current_team"].combine_first(summary["team"])
    summary = summary.drop(columns=["current_team"])
    summary["team"] = summary["team"].fillna("Unassigned")
    summary = summary[
        summary["ci_jumps"] >= max(1, int(min_ci_jumps))
    ].copy()

    if team_filter != "All Teams":
        summary = summary[summary["team"] == team_filter].copy()

    summary["observation"] = (
        summary["athlete"] + " · " + summary["year"].astype(str)
    )
    return summary.sort_values(
        "p90_exit_velo", ascending=False
    ).reset_index(drop=True)


def exit_velo_correlation_stats(
    summary: pd.DataFrame,
) -> tuple[float, float, float, float] | None:
    if len(summary) < 2:
        return None
    x = summary["avg_ci"].to_numpy(dtype=float)
    y = summary["p90_exit_velo"].to_numpy(dtype=float)
    if np.isclose(np.std(x), 0) or np.isclose(np.std(y), 0):
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return r, r * r, float(slope), float(intercept)


def exit_velo_ci_band_summary(
    summary: pd.DataFrame,
    band_width: int,
    exit_stat: str = "Mean",
) -> pd.DataFrame:
    stat = "Median" if str(exit_stat).strip().lower() == "median" else "Mean"
    velo_col = f"{stat} P90 Exit Velo"
    if summary.empty:
        return pd.DataFrame(columns=[
            "CI band", velo_col, "Hitters", "Average CI",
        ])

    width = max(1, int(band_width))
    work = summary[[
        "name_key", "avg_ci", "p90_exit_velo",
    ]].dropna().copy()
    work["band_start"] = hitting_ci_bucket_start(work["avg_ci"], width)
    grouped = (
        work.groupby("band_start", as_index=False)
        .agg(**{
            velo_col: (
                "p90_exit_velo",
                "median" if stat == "Median" else "mean",
            ),
            "Hitters": ("name_key", "nunique"),
            "Average CI": ("avg_ci", "mean"),
        })
        .sort_values("band_start")
    )
    grouped["CI band"] = grouped["band_start"].map(
        lambda lower: hitting_ci_bucket_label(lower, width)
    )
    grouped[velo_col] = grouped[velo_col].round(2)
    grouped["Average CI"] = grouped["Average CI"].round(2)
    return grouped[["CI band", velo_col, "Hitters", "Average CI"]]


def build_exit_velo_scatter(
    summary: pd.DataFrame,
    show_labels: bool,
    ci_lookup: float | None,
) -> go.Figure:
    fig = go.Figure()
    if summary.empty:
        fig.add_annotation(
            text="No matched hitters meet the selected rules.",
            showarrow=False,
            font={"size": 15, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 560)

    customdata = np.column_stack([
        summary["athlete"],
        summary["team"],
        summary["year"],
        summary["exit_velo_records"],
        summary["exit_velo_as_of"].map(fmt_date),
        summary["ci_jumps"],
        summary["ci_test_dates"],
        summary["first_ci_date"].map(fmt_date),
        summary["last_ci_date"].map(fmt_date),
    ])
    fig.add_trace(go.Scatter(
        x=summary["avg_ci"],
        y=summary["p90_exit_velo"],
        mode="markers+text" if show_labels else "markers",
        text=summary["athlete"] if show_labels else None,
        textposition="top center",
        textfont={"size": 10, "color": NAVY},
        marker={
            "size": 13, "color": BLUE, "opacity": 0.88,
            "line": {"color": "#FFFFFF", "width": 2},
        },
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Team: %{customdata[1]}<br>"
            "Calendar year: %{customdata[2]}<br>"
            "P90 exit velo: %{y:.2f} mph<br>"
            "YTD average CI: %{x:.2f} N·s<br><br>"
            "P90 source rows: %{customdata[3]}<br>"
            "CI through %{customdata[4]}<br>"
            "CI jumps: %{customdata[5]} across %{customdata[6]} dates · "
            "%{customdata[7]}–%{customdata[8]}<extra></extra>"
        ),
    ))

    stats = exit_velo_correlation_stats(summary)
    if stats is not None:
        r, r2, slope, intercept = stats
        x_range = np.linspace(
            summary["avg_ci"].min(), summary["avg_ci"].max(), 100
        )
        fig.add_trace(go.Scatter(
            x=x_range,
            y=slope * x_range + intercept,
            mode="lines",
            line={"color": NAVY_MID, "width": 2.5, "dash": "dash"},
            hoverinfo="skip",
        ))
        fig.add_annotation(
            text=f"r = {r:+.2f} · R² = {r2:.2f}",
            x=0.02, y=0.98, xref="paper", yref="paper",
            xanchor="left", yanchor="top", showarrow=False,
            font={"color": NAVY, "size": 13}, bgcolor="#FFFFFF",
            bordercolor=BORDER, borderwidth=1, borderpad=7,
        )
        if ci_lookup is not None and np.isfinite(ci_lookup):
            predicted = slope * float(ci_lookup) + intercept
            fig.add_vline(
                x=float(ci_lookup), line_color=TEAL,
                line_width=1.5, line_dash="dot",
            )
            fig.add_hline(
                y=predicted, line_color=TEAL,
                line_width=1.5, line_dash="dot",
            )
            fig.add_trace(go.Scatter(
                x=[float(ci_lookup)], y=[predicted], mode="markers",
                marker={
                    "size": 15, "color": TEAL, "symbol": "diamond",
                    "line": {"color": "#FFFFFF", "width": 2},
                },
                hovertemplate=(
                    "<b>CI lookup</b><br>"
                    "YTD average CI: %{x:.1f} N·s<br>"
                    "Estimated P90 exit velo: %{y:.2f} mph"
                    "<extra></extra>"
                ),
            ))

    fig.update_xaxes(
        title="Year-to-date average concentric impulse (N·s)",
        showgrid=True, gridcolor=GRID, zeroline=False,
        linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="P90 exit velocity (mph)",
        showgrid=True, gridcolor=GRID, zeroline=False,
        linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 560)


def build_exit_velo_band_chart(
    summary: pd.DataFrame,
    band_width: int,
    exit_stat: str = "Mean",
) -> go.Figure:
    stat = "Median" if str(exit_stat).strip().lower() == "median" else "Mean"
    velo_col = f"{stat} P90 Exit Velo"
    bands = exit_velo_ci_band_summary(summary, band_width, stat)
    fig = go.Figure()
    if bands.empty:
        fig.add_annotation(
            text="No matched hitters are available for CI bands.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 380)

    fig.add_trace(go.Bar(
        x=bands["CI band"],
        y=bands[velo_col],
        marker={"color": BLUE, "line": {"color": NAVY_MID, "width": 0.8}},
        text=[f"{value:.1f}" for value in bands[velo_col]],
        textposition="outside", cliponaxis=False,
        customdata=np.column_stack([
            bands["Hitters"], bands["Average CI"],
        ]),
        hovertemplate=(
            f"<b>%{{x}}</b><br>{stat} P90 exit velo: "
            "%{y:.2f} mph<br>Hitters: %{customdata[0]}<br>"
            "Mean CI within band: %{customdata[1]:.2f} N·s"
            "<extra></extra>"
        ),
    ))
    y_min = max(0, float(bands[velo_col].min()) - 2.0)
    y_max = float(bands[velo_col].max()) + 1.5
    fig.update_xaxes(
        title="Year-to-date average CI band", showgrid=False,
        linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title=f"{stat} P90 exit velocity (mph)",
        range=[y_min, y_max], showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 380)


def exit_velo_ci_band_members(
    summary: pd.DataFrame,
    band_width: int,
    ci_band: str,
    exit_stat: str = "Mean",
) -> tuple[pd.DataFrame, float, str]:
    stat = "Median" if str(exit_stat).strip().lower() == "median" else "Mean"
    width = max(1, int(band_width))
    cols = [
        "athlete", "team", "year", "avg_ci", "p90_exit_velo",
        "exit_velo_as_of",
    ]
    if summary.empty or any(col not in summary.columns for col in cols):
        return (
            pd.DataFrame(columns=cols + ["CI band", "Status", "Difference"]),
            np.nan,
            stat,
        )

    detail = summary[cols].dropna(
        subset=["avg_ci", "p90_exit_velo"]
    ).copy()
    detail["band_start"] = hitting_ci_bucket_start(detail["avg_ci"], width)
    detail["CI band"] = detail["band_start"].map(
        lambda lower: hitting_ci_bucket_label(lower, width)
    )
    detail = detail[detail["CI band"] == ci_band].copy()
    if detail.empty:
        return detail, np.nan, stat

    reference = (
        float(detail["p90_exit_velo"].median())
        if stat == "Median"
        else float(detail["p90_exit_velo"].mean())
    )
    detail["Difference"] = detail["p90_exit_velo"] - reference
    detail["Status"] = np.where(
        np.isclose(detail["Difference"], 0, atol=1e-10),
        f"At {stat.lower()}",
        np.where(
            detail["Difference"] > 0,
            f"Above {stat.lower()}",
            f"Below {stat.lower()}",
        ),
    )
    detail["Display"] = detail.apply(
        lambda row: f"{row['athlete']} · {row['avg_ci']:.1f} CI",
        axis=1,
    )
    return (
        detail.sort_values(
            "p90_exit_velo", ascending=False
        ).reset_index(drop=True),
        reference,
        stat,
    )


def build_exit_velo_ci_band_member_chart(
    summary: pd.DataFrame,
    band_width: int,
    ci_band: str,
    exit_stat: str = "Mean",
) -> go.Figure:
    detail, reference, stat = exit_velo_ci_band_members(
        summary, band_width, ci_band, exit_stat
    )
    fig = go.Figure()
    if detail.empty:
        fig.add_annotation(
            text="No hitters are available in this CI band.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 340)

    status_style = [
        (f"Above {stat.lower()}", GREEN),
        (f"At {stat.lower()}", TEAL),
        (f"Below {stat.lower()}", ACCENT_RED),
    ]
    category_order = detail["Display"].tolist()
    for status, color in status_style:
        sub = detail[detail["Status"] == status].copy()
        if sub.empty:
            continue
        customdata = np.column_stack([
            sub["athlete"], sub["team"], sub["year"],
            sub["avg_ci"], sub["Difference"], sub["Status"],
            sub["exit_velo_as_of"].map(fmt_date),
        ])
        fig.add_trace(go.Bar(
            x=sub["p90_exit_velo"],
            y=sub["Display"],
            orientation="h",
            name=status.title(),
            marker={"color": color, "line": {"color": "#FFFFFF", "width": 1}},
            text=[f"{value:.2f}" for value in sub["p90_exit_velo"]],
            textposition="outside", cliponaxis=False,
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Team: %{customdata[1]}<br>"
                "Calendar year: %{customdata[2]}<br>"
                "YTD average CI: %{customdata[3]:.2f} N·s<br>"
                "P90 exit velo: %{x:.2f} mph<br>"
                "CI through %{customdata[6]}<br>"
                f"{stat} difference: %{{customdata[4]:+.2f}} mph<br>"
                "Flag: %{customdata[5]}<extra></extra>"
            ),
        ))

    x_min = max(0, float(detail["p90_exit_velo"].min()) - 2.0)
    x_max = float(detail["p90_exit_velo"].max()) + 1.5
    fig.add_vline(
        x=reference, line_color=NAVY_MID, line_width=2,
        line_dash="dash", annotation_text=f"{stat} {reference:.2f}",
        annotation_font_color=NAVY_MID,
        annotation_position="top right",
    )
    fig.update_xaxes(
        title="P90 exit velocity (mph)",
        range=[x_min, x_max], showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Hitter · Year-to-date average CI",
        categoryorder="array", categoryarray=category_order,
        autorange="reversed", showgrid=False, linecolor=BORDER,
        tickfont={"color": TEXT, "size": 12},
        title_font={"color": SUBTEXT}, automargin=True,
    )
    fig = base_figure_layout(fig, max(340, len(detail) * 42 + 125))
    fig.update_layout(
        showlegend=True,
        legend={
            "orientation": "h", "x": 0, "y": 1.14,
            "font": {"color": SUBTEXT},
        },
        margin={"l": 210, "r": 70, "t": 50, "b": 58},
    )
    return fig


# -----------------------------------------------------------------------------
# BASERUNNING SPRINT SPEED × RELATIVE PEAK POWER
# -----------------------------------------------------------------------------
def build_sprint_overview_summary(
    jump_power: pd.DataFrame,
    baserunning: pd.DataFrame,
    start_date,
    end_date,
    team_filter: str,
    min_power_jumps: int,
) -> pd.DataFrame:
    """Match current baserunning-sheet Sprint Speed to mean in-window Relative Peak Power.

    Sprint Speed is the current season-to-date snapshot from the same baserunning
    Google Sheet used by the nBSR and Adv Runs tabs. Relative Peak Power is the
    player's mean Peak Power / BM from Jump Data inside the selected dashboard
    date window. There is no PP_Sprint monthly-eligibility requirement here.
    """
    columns = [
        "name_key", "athlete", "team", "avg_peak_power_rel",
        "power_jumps", "power_test_dates", "first_power_date",
        "last_power_date", "monthly_max_sprint_speed", "month_label",
        "observation",
    ]
    required = {"name_key", "athlete", "baserunning_sprint_speed"}
    if jump_power.empty or baserunning.empty or not required.issubset(baserunning.columns):
        return pd.DataFrame(columns=columns)

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()

    team_lookup = (
        jump_power.sort_values("date")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
    )

    power_window = jump_power[
        (jump_power["date"] >= start)
        & (jump_power["date"] <= end)
        & jump_power["peak_power_rel"].notna()
    ].copy()
    if power_window.empty:
        return pd.DataFrame(columns=columns)

    power_summary = (
        power_window.groupby("name_key", as_index=False)
        .agg(
            athlete=("athlete", "first"),
            avg_peak_power_rel=("peak_power_rel", "mean"),
            power_jumps=("peak_power_rel", "count"),
            power_test_dates=("date", "nunique"),
            first_power_date=("date", "min"),
            last_power_date=("date", "max"),
        )
        .merge(team_lookup, on="name_key", how="left")
    )

    sprint_snapshot = (
        baserunning[["name_key", "baserunning_sprint_speed"]]
        .dropna(subset=["baserunning_sprint_speed"])
        .drop_duplicates("name_key")
        .rename(columns={"baserunning_sprint_speed": "monthly_max_sprint_speed"})
    )

    summary = power_summary.merge(sprint_snapshot, on="name_key", how="inner")
    summary = summary[
        summary["power_jumps"] >= max(1, int(min_power_jumps))
    ].copy()
    if team_filter != "All Teams":
        summary = summary[summary["team"] == team_filter].copy()

    summary["month_label"] = "Current baserunning snapshot"
    summary["observation"] = summary["athlete"]
    return summary.sort_values("athlete", kind="stable").reset_index(drop=True)


def sprint_correlation_stats(
    pairs: pd.DataFrame,
) -> tuple[float, float, float, float] | None:
    if len(pairs) < 2:
        return None
    x = pairs["avg_peak_power_rel"].to_numpy(dtype=float)
    y = pairs["monthly_max_sprint_speed"].to_numpy(dtype=float)
    if np.isclose(np.std(x), 0) or np.isclose(np.std(y), 0):
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return r, r * r, float(slope), float(intercept)


def build_sprint_residual_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    """Add predicted sprint speed and residuals from relative peak power."""
    columns = list(pairs.columns) + [
        "predicted_sprint_speed",
        "sprint_speed_residual",
        "abs_sprint_speed_residual",
    ]
    if pairs.empty:
        return pd.DataFrame(columns=columns)

    stats = sprint_correlation_stats(pairs)
    if stats is None:
        return pd.DataFrame(columns=columns)

    _, _, slope, intercept = stats
    work = pairs.dropna(
        subset=["avg_peak_power_rel", "monthly_max_sprint_speed"]
    ).copy()
    work["predicted_sprint_speed"] = (
        slope * work["avg_peak_power_rel"] + intercept
    )
    work["sprint_speed_residual"] = (
        work["monthly_max_sprint_speed"] - work["predicted_sprint_speed"]
    )
    work["abs_sprint_speed_residual"] = work[
        "sprint_speed_residual"
    ].abs()
    return work.sort_values(
        "sprint_speed_residual", ascending=True
    ).reset_index(drop=True)


def build_sprint_residual_chart(pairs: pd.DataFrame) -> go.Figure:
    residuals = build_sprint_residual_summary(pairs)
    fig = go.Figure()
    if residuals.empty:
        fig.add_annotation(
            text="Sprint-speed residuals could not be calculated.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 480)

    residuals = residuals.sort_values(
        "sprint_speed_residual", ascending=True
    ).copy()
    colors = [
        TEAL if value >= 0 else ACCENT_RED
        for value in residuals["sprint_speed_residual"]
    ]
    customdata = np.column_stack([
        residuals["team"],
        residuals["month_label"],
        residuals["avg_peak_power_rel"],
        residuals["monthly_max_sprint_speed"],
        residuals["predicted_sprint_speed"],
    ])
    fig.add_trace(go.Bar(
        x=residuals["sprint_speed_residual"],
        y=residuals["athlete"],
        orientation="h",
        marker={"color": colors},
        text=[f"{value:+.2f}" for value in residuals["sprint_speed_residual"]],
        textposition="outside",
        cliponaxis=False,
        customdata=customdata,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Team: %{customdata[0]}<br>"
            "Source: %{customdata[1]}<br>"
            "Relative peak power: %{customdata[2]:.2f} W/kg<br>"
            "Actual sprint speed: %{customdata[3]:.2f} ft/s<br>"
            "Predicted sprint speed: %{customdata[4]:.2f} ft/s<br>"
            "Residual: %{x:+.2f} ft/s<extra></extra>"
        ),
    ))
    fig.add_vline(
        x=0,
        line_color=NAVY_MID,
        line_width=1.5,
        line_dash="dash",
    )
    max_abs = float(residuals["sprint_speed_residual"].abs().max())
    pad = max(0.15, max_abs * 0.18)
    fig.update_xaxes(
        title="Sprint speed residual: actual − predicted (ft/s)",
        range=[-max_abs - pad, max_abs + pad],
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="",
        showgrid=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
    )
    height = max(460, min(1200, 160 + 28 * len(residuals)))
    return base_figure_layout(fig, height)


def sprint_power_band_summary(
    pairs: pd.DataFrame,
    band_width: float,
    sprint_stat: str = "Mean",
) -> pd.DataFrame:
    stat = "Median" if str(sprint_stat).strip().lower() == "median" else "Mean"
    speed_col = f"{stat} Sprint Speed"
    if pairs.empty:
        return pd.DataFrame(columns=[
            "Power band", speed_col, "Players", "Average Peak Power / BM",
        ])

    width = max(0.1, float(band_width))
    work = pairs[[
        "name_key", "avg_peak_power_rel", "monthly_max_sprint_speed"
    ]].dropna().copy()
    work["band_start"] = (
        np.floor(work["avg_peak_power_rel"] / width) * width
    )
    grouped = (
        work.groupby("band_start", as_index=False)
        .agg(**{
            speed_col: (
                "monthly_max_sprint_speed",
                "median" if stat == "Median" else "mean",
            ),
            "Players": ("name_key", "nunique"),
            "Average Peak Power / BM": ("avg_peak_power_rel", "mean"),
        })
        .sort_values("band_start")
    )
    grouped["Power band"] = grouped["band_start"].map(
        lambda lower: f"{lower:.1f}–{lower + width:.1f} W/kg"
    )
    grouped[speed_col] = grouped[speed_col].round(2)
    grouped["Average Peak Power / BM"] = grouped[
        "Average Peak Power / BM"
    ].round(2)
    return grouped[[
        "Power band", speed_col, "Players", "Average Peak Power / BM",
    ]]



def build_sprint_scatter(
    pairs: pd.DataFrame,
    show_labels: bool,
    power_lookup: float | None,
) -> go.Figure:
    fig = go.Figure()
    if pairs.empty:
        fig.add_annotation(
            text="No matched players meet the selected rules.",
            showarrow=False, font={"size": 15, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 560)

    customdata = np.column_stack([
        pairs["athlete"],
        pairs["team"],
        pairs["power_jumps"],
        pairs["power_test_dates"],
        pairs["first_power_date"].map(fmt_date),
        pairs["last_power_date"].map(fmt_date),
    ])
    fig.add_trace(go.Scatter(
        x=pairs["avg_peak_power_rel"],
        y=pairs["monthly_max_sprint_speed"],
        mode="markers+text" if show_labels else "markers",
        text=pairs["observation"] if show_labels else None,
        textposition="top center",
        textfont={"size": 9, "color": NAVY},
        marker={
            "size": 13,
            "color": TEAL,
            "opacity": 0.86,
            "line": {"color": "#FFFFFF", "width": 2},
        },
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Team: %{customdata[1]}<br>"
            "Baserunning Sprint Speed: %{y:.2f} ft/s<br>"
            "Mean Peak Power / BM: %{x:.2f} W/kg<br><br>"
            "Jump rows: %{customdata[2]} across %{customdata[3]} dates · "
            "%{customdata[4]}–%{customdata[5]}<extra></extra>"
        ),
    ))

    stats = sprint_correlation_stats(pairs)
    if stats is not None:
        r, r2, slope, intercept = stats
        x_range = np.linspace(
            pairs["avg_peak_power_rel"].min(),
            pairs["avg_peak_power_rel"].max(),
            100,
        )
        fig.add_trace(go.Scatter(
            x=x_range,
            y=slope * x_range + intercept,
            mode="lines",
            line={"color": NAVY_MID, "width": 2.5, "dash": "dash"},
            hoverinfo="skip",
        ))
        fig.add_annotation(
            text=f"r = {r:+.2f} · R² = {r2:.2f}",
            x=0.02, y=0.98, xref="paper", yref="paper",
            xanchor="left", yanchor="top", showarrow=False,
            font={"color": NAVY, "size": 13}, bgcolor="#FFFFFF",
            bordercolor=BORDER, borderwidth=1, borderpad=7,
        )
        if power_lookup is not None and np.isfinite(power_lookup):
            predicted = slope * float(power_lookup) + intercept
            fig.add_vline(
                x=float(power_lookup), line_color=TEAL,
                line_width=1.5, line_dash="dot",
            )
            fig.add_hline(
                y=predicted, line_color=TEAL,
                line_width=1.5, line_dash="dot",
            )
            fig.add_trace(go.Scatter(
                x=[float(power_lookup)], y=[predicted], mode="markers",
                marker={
                    "size": 15, "color": TEAL, "symbol": "diamond",
                    "line": {"color": "#FFFFFF", "width": 2},
                },
                hovertemplate=(
                    "<b>Power lookup</b><br>"
                    "Mean Peak Power / BM: %{x:.1f} W/kg<br>"
                    "Estimated Sprint Speed: %{y:.2f} ft/s"
                    "<extra></extra>"
                ),
            ))

    fig.update_xaxes(
        title="Mean Peak Power / BM in selected window (W/kg)",
        showgrid=True, gridcolor=GRID, zeroline=False,
        linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Baserunning Sprint Speed (ft/s)",
        showgrid=True, gridcolor=GRID, zeroline=False,
        linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 560)


def build_sprint_band_chart(
    pairs: pd.DataFrame,
    band_width: float,
    sprint_stat: str = "Mean",
) -> go.Figure:
    stat = "Median" if str(sprint_stat).strip().lower() == "median" else "Mean"
    speed_col = f"{stat} Sprint Speed"
    bands = sprint_power_band_summary(pairs, band_width, stat)
    fig = go.Figure()
    if bands.empty:
        fig.add_annotation(
            text="No matched players are available for power bands.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 380)

    fig.add_trace(go.Bar(
        x=bands["Power band"],
        y=bands[speed_col],
        marker={"color": TEAL, "line": {"color": NAVY_MID, "width": 0.8}},
        text=[f"{speed:.1f}" for speed in bands[speed_col]],
        textposition="outside",
        cliponaxis=False,
        customdata=np.column_stack([
            bands["Players"],
            bands["Average Peak Power / BM"],
        ]),
        hovertemplate=(
            f"<b>%{{x}}</b><br>{stat} sprint speed: "
            "%{y:.2f} ft/s<br>"
            "Players: %{customdata[0]}<br>"
            "Mean Peak Power / BM within band: %{customdata[1]:.2f} W/kg"
            "<extra></extra>"
        ),
    ))
    y_min = max(0, float(bands[speed_col].min()) - 1.5)
    y_max = float(bands[speed_col].max()) + 1.0
    fig.update_xaxes(
        title="Mean Peak Power / BM band",
        showgrid=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title=f"{stat} baserunning Sprint Speed (ft/s)",
        range=[y_min, y_max], showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 380)


# -----------------------------------------------------------------------------
# PINCH GRIP × FB VELO
# -----------------------------------------------------------------------------
def build_pinch_summary(
    pinch: pd.DataFrame,
    velo: pd.DataFrame,
    jump: pd.DataFrame,
    start_date,
    end_date,
    team_filter: str,
    min_velo_records: int,
    min_pinch_tests: int,
) -> pd.DataFrame:
    """Mirror the CI overview: mean in-window pinch versus last in-window YTD FB velo."""
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()

    pinch_window = pinch[
        (pinch["date"] >= start) & (pinch["date"] <= end)
    ].copy()
    velo_window = velo[
        (velo["date"] >= start) & (velo["date"] <= end)
    ].copy()

    pinch_summary = (
        pinch_window.groupby("name_key", as_index=False)
        .agg(
            athlete=("athlete", "first"),
            pinch_hand=("pinch_hand", "first"),
            avg_pinch_strength=("pinch_strength", "mean"),
            pinch_tests=("pinch_strength", "count"),
            pinch_test_dates=("date", "nunique"),
            first_pinch_date=("date", "min"),
            last_pinch_date=("date", "max"),
        )
    )

    velo_window = velo_window.sort_values(
        ["name_key", "date"], kind="stable"
    )
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
        .rename(
            columns={
                "ytd_fb_velo": "avg_fb_velo",
                "date": "ytd_as_of_date",
            }
        )
    )
    velo_summary = velo_counts.merge(latest_ytd, on="name_key", how="inner")

    jump_team_lookup = (
        jump.sort_values("date", kind="stable")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
        .rename(columns={"team": "jump_team"})
    )
    pinch_team_lookup = (
        pinch.dropna(subset=["team"])
        .sort_values("date", kind="stable")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
        .rename(columns={"team": "pinch_team"})
    )

    summary = velo_summary.merge(pinch_summary, on="name_key", how="inner")
    summary = summary.merge(jump_team_lookup, on="name_key", how="left")
    summary = summary.merge(pinch_team_lookup, on="name_key", how="left")
    summary["team"] = summary["jump_team"].combine_first(
        summary["pinch_team"]
    ).fillna("Unassigned")
    summary = summary.drop(columns=["jump_team", "pinch_team"])

    summary = summary[
        summary["avg_fb_velo"] >= MIN_LAST_YTD_FB_VELO
    ].copy()
    summary = summary[
        (summary["fb_records"] >= max(1, int(min_velo_records)))
        & (summary["pinch_tests"] >= max(1, int(min_pinch_tests)))
    ].copy()

    if team_filter != "All Teams":
        summary = summary[summary["team"] == team_filter].copy()

    return summary.sort_values(
        "avg_fb_velo", ascending=False
    ).reset_index(drop=True)


def pinch_correlation_stats(
    summary: pd.DataFrame,
) -> tuple[float, float, float, float] | None:
    work = summary[["avg_pinch_strength", "avg_fb_velo"]].dropna()
    if len(work) < 2:
        return None
    x = work["avg_pinch_strength"].to_numpy(dtype=float)
    y = work["avg_fb_velo"].to_numpy(dtype=float)
    if np.isclose(np.std(x), 0) or np.isclose(np.std(y), 0):
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return r, r * r, float(slope), float(intercept)


def pinch_band_summary(
    summary: pd.DataFrame,
    band_width: float,
    velo_stat: str = "Mean",
) -> pd.DataFrame:
    """Mirror CI bands using average single-hand pinch strength."""
    stat = "Median" if str(velo_stat).strip().lower() == "median" else "Mean"
    velo_col = f"{stat} Last YTD FB Velo"
    if summary.empty:
        return pd.DataFrame(
            columns=["Pinch band", velo_col, "Pitchers", "Average Pinch"]
        )

    width = max(0.1, float(band_width))
    work = summary[["avg_pinch_strength", "avg_fb_velo"]].dropna().copy()
    work["band_start"] = (
        np.floor(work["avg_pinch_strength"] / width) * width
    )
    grouped = (
        work.groupby("band_start", as_index=False)
        .agg(
            **{
                velo_col: (
                    "avg_fb_velo",
                    "median" if stat == "Median" else "mean",
                ),
                "Pitchers": ("avg_fb_velo", "count"),
                "Average Pinch": ("avg_pinch_strength", "mean"),
            }
        )
        .sort_values("band_start")
    )
    grouped["Pinch band"] = grouped["band_start"].map(
        lambda lower: f"{lower:g}–{lower + width:g}"
    )
    grouped[velo_col] = grouped[velo_col].round(2)
    grouped["Average Pinch"] = grouped["Average Pinch"].round(2)
    grouped["Pitchers"] = grouped["Pitchers"].astype(int)
    return grouped[["Pinch band", velo_col, "Pitchers", "Average Pinch"]]


def build_pinch_scatter(
    summary: pd.DataFrame,
    show_labels: bool,
    pinch_lookup: float | None,
) -> go.Figure:
    work = summary.dropna(
        subset=["avg_pinch_strength", "avg_fb_velo"]
    ).copy()
    fig = go.Figure()
    if work.empty:
        fig.add_annotation(
            text="No matched pitchers meet the selected pinch-grip rules.",
            showarrow=False,
            font={"size": 15, "color": SUBTEXT},
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 560)

    customdata = np.column_stack([
        work["athlete"],
        work["team"],
        work["pinch_hand"],
        work["pinch_tests"],
        work["pinch_test_dates"],
        work["first_pinch_date"].map(fmt_date),
        work["last_pinch_date"].map(fmt_date),
        work["ytd_as_of_date"].map(fmt_date),
    ])
    fig.add_trace(go.Scatter(
        x=work["avg_pinch_strength"],
        y=work["avg_fb_velo"],
        mode="markers+text" if show_labels else "markers",
        text=work["athlete"] if show_labels else None,
        textposition="top center",
        textfont={"size": 10, "color": NAVY},
        marker={
            "size": 13,
            "color": GREEN,
            "opacity": 0.88,
            "line": {"color": "#FFFFFF", "width": 2},
        },
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Team: %{customdata[1]}<br>"
            "Tested hand: %{customdata[2]}<br>"
            "Average pinch strength: %{x:.2f}<br>"
            "Last YTD FB velo: %{y:.2f} mph<br><br>"
            "Pinch tests: %{customdata[3]} across %{customdata[4]} dates · "
            "%{customdata[5]}–%{customdata[6]}<br>"
            "YTD FB velo as of %{customdata[7]}"
            "<extra></extra>"
        ),
    ))

    stats = pinch_correlation_stats(work)
    if stats is not None:
        r, r2, slope, intercept = stats
        x_range = np.linspace(
            work["avg_pinch_strength"].min(),
            work["avg_pinch_strength"].max(),
            100,
        )
        fig.add_trace(go.Scatter(
            x=x_range,
            y=slope * x_range + intercept,
            mode="lines",
            line={"color": NAVY_MID, "width": 2.5, "dash": "dash"},
            hoverinfo="skip",
        ))
        fig.add_annotation(
            text=f"r = {r:+.2f} · R² = {r2:.2f}",
            x=0.02,
            y=0.98,
            xref="paper",
            yref="paper",
            xanchor="left",
            yanchor="top",
            showarrow=False,
            font={"color": NAVY, "size": 13},
            bgcolor="#FFFFFF",
            bordercolor=BORDER,
            borderwidth=1,
            borderpad=7,
        )
        if pinch_lookup is not None and np.isfinite(pinch_lookup):
            predicted = slope * float(pinch_lookup) + intercept
            fig.add_vline(
                x=float(pinch_lookup),
                line_color=TEAL,
                line_width=1.5,
                line_dash="dot",
            )
            fig.add_hline(
                y=predicted,
                line_color=TEAL,
                line_width=1.5,
                line_dash="dot",
            )
            fig.add_trace(go.Scatter(
                x=[float(pinch_lookup)],
                y=[predicted],
                mode="markers",
                marker={
                    "size": 15,
                    "color": TEAL,
                    "symbol": "diamond",
                    "line": {"color": "#FFFFFF", "width": 2},
                },
                hovertemplate=(
                    "<b>Pinch lookup</b><br>"
                    "Average pinch strength: %{x:.1f}<br>"
                    "Estimated last YTD FB velo: %{y:.2f} mph"
                    "<extra></extra>"
                ),
            ))

    fig.update_xaxes(
        title="Average pinch strength",
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Last YTD FB velocity (mph)",
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 560)


def build_pinch_band_chart(
    summary: pd.DataFrame,
    band_width: float,
    velo_stat: str = "Mean",
) -> go.Figure:
    stat = "Median" if str(velo_stat).strip().lower() == "median" else "Mean"
    velo_col = f"{stat} Last YTD FB Velo"
    bands = pinch_band_summary(summary, band_width, stat)
    fig = go.Figure()
    if bands.empty:
        fig.add_annotation(
            text="No matched pitchers are available for pinch bands.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 380)

    fig.add_trace(go.Bar(
        x=bands["Pinch band"],
        y=bands[velo_col],
        marker={"color": GREEN, "line": {"color": NAVY_MID, "width": 0.8}},
        text=[f"{velo:.1f}" for velo in bands[velo_col]],
        textposition="outside",
        cliponaxis=False,
        customdata=np.column_stack([
            bands["Pitchers"],
            bands["Average Pinch"],
        ]),
        hovertemplate=(
            f"<b>%{{x}}</b><br>{stat} last YTD FB velo: %{{y:.2f}} mph<br>"
            "Pitchers: %{customdata[0]}<br>"
            "Mean pinch within band: %{customdata[1]:.2f}"
            "<extra></extra>"
        ),
    ))
    y_min = max(0, float(bands[velo_col].min()) - 1.5)
    y_max = float(bands[velo_col].max()) + 1.25
    fig.update_xaxes(
        title="Pitcher average pinch-strength band",
        showgrid=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title=f"{stat} last YTD FB velo (mph)",
        range=[y_min, y_max],
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 380)


def pinch_band_members(
    summary: pd.DataFrame,
    band_width: float,
    pinch_band: str,
    velo_stat: str = "Mean",
) -> tuple[pd.DataFrame, float, str]:
    stat = "Median" if str(velo_stat).strip().lower() == "median" else "Mean"
    width = max(0.1, float(band_width))
    columns = [
        "athlete", "team", "pinch_hand", "avg_pinch_strength", "avg_fb_velo"
    ]
    if summary.empty or any(col not in summary.columns for col in columns):
        return (
            pd.DataFrame(columns=columns + ["Pinch band", "Status", "Difference"]),
            np.nan,
            stat,
        )

    detail = summary[columns].dropna().copy()
    detail["band_start"] = (
        np.floor(detail["avg_pinch_strength"] / width) * width
    )
    detail["Pinch band"] = detail["band_start"].map(
        lambda lower: f"{lower:g}–{lower + width:g}"
    )
    detail = detail[detail["Pinch band"] == pinch_band].copy()
    if detail.empty:
        return detail, np.nan, stat

    reference = (
        float(detail["avg_fb_velo"].median())
        if stat == "Median"
        else float(detail["avg_fb_velo"].mean())
    )
    detail["Difference"] = detail["avg_fb_velo"] - reference
    detail["Status"] = np.where(
        np.isclose(detail["Difference"], 0, atol=1e-10),
        f"At {stat.lower()}",
        np.where(
            detail["Difference"] > 0,
            f"Above {stat.lower()}",
            f"Below {stat.lower()}",
        ),
    )
    detail["Display"] = detail.apply(
        lambda row: (
            f"{row['athlete']} · {row['avg_pinch_strength']:.1f} "
            f"({row['pinch_hand'][0]})"
        ),
        axis=1,
    )
    return (
        detail.sort_values("avg_fb_velo", ascending=False).reset_index(drop=True),
        reference,
        stat,
    )


def build_pinch_band_member_chart(
    summary: pd.DataFrame,
    band_width: float,
    pinch_band: str,
    velo_stat: str = "Mean",
) -> go.Figure:
    detail, reference, stat = pinch_band_members(
        summary, band_width, pinch_band, velo_stat
    )
    fig = go.Figure()
    if detail.empty:
        fig.add_annotation(
            text="No pitchers are available in this pinch band.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 340)

    status_style = [
        (f"Above {stat.lower()}", GREEN),
        (f"At {stat.lower()}", TEAL),
        (f"Below {stat.lower()}", ACCENT_RED),
    ]
    category_order = detail["Display"].tolist()
    for status, color in status_style:
        sub = detail[detail["Status"] == status].copy()
        if sub.empty:
            continue
        customdata = np.column_stack([
            sub["athlete"],
            sub["team"],
            sub["pinch_hand"],
            sub["avg_pinch_strength"],
            sub["Difference"],
            sub["Status"],
        ])
        fig.add_trace(go.Bar(
            x=sub["avg_fb_velo"],
            y=sub["Display"],
            orientation="h",
            name=status.title(),
            marker={"color": color, "line": {"color": "#FFFFFF", "width": 1}},
            text=[f"{value:.2f}" for value in sub["avg_fb_velo"]],
            textposition="outside",
            cliponaxis=False,
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Team: %{customdata[1]}<br>"
                "Tested hand: %{customdata[2]}<br>"
                "Average pinch strength: %{customdata[3]:.2f}<br>"
                "Last YTD FB velo: %{x:.2f} mph<br>"
                f"{stat} difference: %{{customdata[4]:+.2f}} mph<br>"
                "Flag: %{customdata[5]}<extra></extra>"
            ),
        ))

    x_min = max(0, float(detail["avg_fb_velo"].min()) - 1.5)
    x_max = float(detail["avg_fb_velo"].max()) + 1.25
    fig.add_vline(
        x=reference,
        line_color=NAVY_MID,
        line_width=2,
        line_dash="dash",
        annotation_text=f"{stat} {reference:.2f}",
        annotation_font_color=NAVY_MID,
        annotation_position="top right",
    )
    fig.update_xaxes(
        title="Last YTD FB velo (mph)",
        range=[x_min, x_max],
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Pitcher · Average pinch",
        categoryorder="array",
        categoryarray=category_order,
        autorange="reversed",
        showgrid=False,
        linecolor=BORDER,
        tickfont={"color": TEXT, "size": 12},
        title_font={"color": SUBTEXT},
        automargin=True,
    )
    fig = base_figure_layout(fig, max(340, len(detail) * 42 + 125))
    fig.update_layout(
        showlegend=True,
        legend={"orientation": "h", "x": 0, "y": 1.14, "font": {"color": SUBTEXT}},
        margin={"l": 205, "r": 70, "t": 50, "b": 58},
    )
    return fig


def build_pinch_within_pairs(
    pinch: pd.DataFrame,
    velo: pd.DataFrame,
    jump: pd.DataFrame,
    start_date,
    end_date,
    team_filter: str,
    bucket_mode: str,
) -> pd.DataFrame:
    """Mirror CI within-individual pairing using pinch tests in the same buckets."""
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()

    jump_team_lookup = (
        jump.sort_values("date", kind="stable")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
        .rename(columns={"team": "jump_team"})
    )
    pinch_team_lookup = (
        pinch.dropna(subset=["team"])
        .sort_values("date", kind="stable")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
        .rename(columns={"team": "pinch_team"})
    )
    team_lookup = jump_team_lookup.merge(
        pinch_team_lookup, on="name_key", how="outer"
    )
    team_lookup["team"] = team_lookup["jump_team"].combine_first(
        team_lookup["pinch_team"]
    ).fillna("Unassigned")
    team_lookup = team_lookup[["name_key", "team"]]

    pinch_window = pinch[
        (pinch["date"] >= start) & (pinch["date"] <= end)
    ].copy()
    pinch_window = add_time_bucket_columns(
        pinch_window, "date", bucket_mode
    )
    pinch_bucketed = (
        pinch_window.groupby(
            ["name_key", "bucket_start", "bucket_end", "bucket_label"],
            as_index=False,
        )
        .agg(
            athlete=("athlete", "first"),
            pinch_hand=("pinch_hand", "first"),
            avg_pinch_strength=("pinch_strength", "mean"),
            pinch_tests=("pinch_strength", "count"),
            pinch_test_dates=("date", "nunique"),
            last_pinch_date=("date", "max"),
        )
        .merge(team_lookup, on="name_key", how="left")
    )
    pinch_bucketed["team"] = pinch_bucketed["team"].fillna("Unassigned")
    if team_filter != "All Teams":
        pinch_bucketed = pinch_bucketed[
            pinch_bucketed["team"] == team_filter
        ].copy()

    velo_window = velo[
        (velo["date"] >= start) & (velo["date"] <= end)
    ].copy()
    velo_window = add_time_bucket_columns(
        velo_window, "date", bucket_mode
    )
    velo_bucketed = (
        velo_window.sort_values(["name_key", "date"], kind="stable")
        .groupby(
            ["name_key", "bucket_start", "bucket_end", "bucket_label"],
            as_index=False,
        )
        .tail(1)[[
            "name_key", "bucket_start", "bucket_end", "bucket_label",
            "date", "ytd_fb_velo",
        ]]
        .rename(columns={"date": "velo_date"})
    )

    columns = [
        "name_key", "athlete", "team", "pinch_hand", "date",
        "bucket_end", "bucket_label", "avg_pinch_strength", "pinch_tests",
        "pinch_test_dates", "last_pinch_date", "velo_date", "ytd_fb_velo",
        "delta_pinch", "delta_fb_velo",
    ]
    if pinch_bucketed.empty or velo_bucketed.empty:
        return pd.DataFrame(columns=columns)

    pairs = pinch_bucketed.merge(
        velo_bucketed,
        on=["name_key", "bucket_start", "bucket_end", "bucket_label"],
        how="inner",
    ).rename(columns={"bucket_start": "date"})
    pairs = pairs.dropna(
        subset=["avg_pinch_strength", "velo_date", "ytd_fb_velo"]
    ).copy()
    pairs = pairs[
        pairs["ytd_fb_velo"] >= MIN_LAST_YTD_FB_VELO
    ].copy()
    pairs = pairs.sort_values(
        ["name_key", "date"], kind="stable"
    ).reset_index(drop=True)
    if pairs.empty:
        return pairs

    first_pinch = pairs.groupby("name_key")[
        "avg_pinch_strength"
    ].transform("first")
    first_velo = pairs.groupby("name_key")[
        "ytd_fb_velo"
    ].transform("first")
    pairs["delta_pinch"] = pairs["avg_pinch_strength"] - first_pinch
    pairs["delta_fb_velo"] = pairs["ytd_fb_velo"] - first_velo
    return pairs


def build_pinch_within_summary(
    pairs: pd.DataFrame,
    min_paired_dates: int,
) -> pd.DataFrame:
    """One row per pitcher using the same change-score method as the CI tab."""
    columns = [
        "name_key", "athlete", "team", "pinch_hand", "paired_dates",
        "r", "r2", "slope", "first_date", "last_date", "delta_pinch",
        "delta_fb_velo",
    ]
    required = max(3, int(min_paired_dates))
    if pairs.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for name_key, grp in pairs.groupby("name_key", sort=False):
        grp = grp.sort_values("date")
        n = len(grp)
        if n < required:
            continue
        x = grp["delta_pinch"].to_numpy(dtype=float)
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
            "pinch_hand": grp["pinch_hand"].iloc[0],
            "paired_dates": n,
            "r": r,
            "r2": r2,
            "slope": slope,
            "first_date": grp["date"].iloc[0],
            "last_date": grp["date"].iloc[-1],
            "delta_pinch": grp["delta_pinch"].iloc[-1],
            "delta_fb_velo": grp["delta_fb_velo"].iloc[-1],
        })

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).sort_values(
        ["r", "paired_dates"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)


def build_pinch_within_scatter(player_pairs: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if player_pairs.empty:
        fig.add_annotation(
            text="No paired pinch and YTD FB velo buckets for this pitcher.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 470)

    customdata = np.column_stack([
        player_pairs["bucket_label"],
        player_pairs["avg_pinch_strength"],
        player_pairs["ytd_fb_velo"],
        player_pairs["velo_date"].map(fmt_date),
        player_pairs["pinch_tests"],
        player_pairs["pinch_test_dates"],
        player_pairs["last_pinch_date"].map(fmt_date),
        player_pairs["pinch_hand"],
    ])
    fig.add_trace(go.Scatter(
        x=player_pairs["delta_pinch"],
        y=player_pairs["delta_fb_velo"],
        mode="markers+text",
        text=player_pairs["bucket_label"],
        textposition="top center",
        textfont={"size": 10, "color": NAVY},
        marker={
            "size": 13,
            "color": GREEN,
            "opacity": 0.9,
            "line": {"color": "#FFFFFF", "width": 2},
        },
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Tested hand: %{customdata[7]}<br>"
            "Δ pinch: %{x:+.2f}<br>"
            "Δ YTD FB velo: %{y:+.2f} mph<br><br>"
            "Average pinch: %{customdata[1]:.2f} · "
            "%{customdata[4]} tests across %{customdata[5]} dates<br>"
            "Last pinch test: %{customdata[6]}<br>"
            "YTD FB velo: %{customdata[2]:.2f} mph · as of %{customdata[3]}"
            "<extra></extra>"
        ),
    ))
    fig.add_vline(x=0, line_color="#AAB5C5", line_width=1)
    fig.add_hline(y=0, line_color="#AAB5C5", line_width=1)

    if (
        len(player_pairs) >= 3
        and not np.isclose(player_pairs["delta_pinch"].std(), 0)
        and not np.isclose(player_pairs["delta_fb_velo"].std(), 0)
    ):
        x = player_pairs["delta_pinch"].to_numpy(dtype=float)
        y = player_pairs["delta_fb_velo"].to_numpy(dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        r = float(np.corrcoef(x, y)[0, 1])
        x_range = np.linspace(x.min(), x.max(), 100)
        fig.add_trace(go.Scatter(
            x=x_range,
            y=slope * x_range + intercept,
            mode="lines",
            line={"color": NAVY_MID, "width": 2.5, "dash": "dash"},
            hoverinfo="skip",
        ))
        fig.add_annotation(
            text=f"r = {r:+.2f} · {len(player_pairs)} paired buckets",
            x=0.02,
            y=0.98,
            xref="paper",
            yref="paper",
            xanchor="left",
            yanchor="top",
            showarrow=False,
            font={"color": NAVY, "size": 13},
            bgcolor="#FFFFFF",
            bordercolor=BORDER,
            borderwidth=1,
            borderpad=7,
        )

    fig.update_xaxes(
        title="Change in average pinch strength from first bucket",
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Change in YTD FB velo from first bucket (mph)",
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 470)


def build_pinch_within_timeline(player_pairs: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if player_pairs.empty:
        fig.add_annotation(
            text="No paired buckets.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 360)

    fig.add_trace(go.Scatter(
        x=player_pairs["date"],
        y=player_pairs["avg_pinch_strength"],
        mode="lines+markers",
        name="Average pinch strength",
        line={"color": GREEN, "width": 2.5},
        marker={"size": 8},
        customdata=player_pairs[["bucket_label"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Average pinch strength: %{y:.2f}<extra></extra>"
        ),
    ))
    fig.add_trace(go.Scatter(
        x=player_pairs["date"],
        y=player_pairs["ytd_fb_velo"],
        mode="lines+markers",
        name="YTD FB velo",
        yaxis="y2",
        line={"color": ACCENT_RED, "width": 2.5},
        marker={"size": 8},
        customdata=player_pairs[["bucket_label"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "YTD FB velo: %{y:.2f} mph<extra></extra>"
        ),
    ))
    fig.update_layout(
        yaxis={
            "title": "Average pinch strength",
            "showgrid": True,
            "gridcolor": GRID,
            "zeroline": False,
            "linecolor": BORDER,
            "tickfont": {"color": SUBTEXT},
            "title_font": {"color": SUBTEXT},
        },
        yaxis2={
            "title": "YTD FB velo (mph)",
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "zeroline": False,
            "linecolor": BORDER,
            "tickfont": {"color": SUBTEXT},
            "title_font": {"color": SUBTEXT},
        },
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.15,
            "font": {"color": SUBTEXT},
        },
        showlegend=True,
    )
    fig.update_xaxes(
        showgrid=False,
        linecolor=BORDER,
        tickfont={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 360)


# -----------------------------------------------------------------------------
# COMBINED CI + PINCH OVERVIEW MODEL
# -----------------------------------------------------------------------------
def build_combined_overview_summary(
    ci_summary: pd.DataFrame,
    pinch_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Create one combined-model row per pitcher, matching the overview tabs."""
    columns = [
        "name_key", "athlete", "team", "avg_fb_velo", "ytd_as_of_date",
        "fb_records", "avg_ci", "ci_jumps", "ci_test_dates",
        "first_ci_date", "last_ci_date", "pinch_hand",
        "avg_pinch_strength", "pinch_tests", "pinch_test_dates",
        "first_pinch_date", "last_pinch_date", "observation",
    ]
    if ci_summary.empty or pinch_summary.empty:
        return pd.DataFrame(columns=columns)

    ci_keep = ci_summary[[
        "name_key", "athlete", "team", "avg_fb_velo", "ytd_as_of_date",
        "fb_records", "avg_ci", "ci_jumps", "ci_test_dates",
        "first_ci_date", "last_ci_date",
    ]].copy()
    pinch_keep = pinch_summary[[
        "name_key", "avg_fb_velo", "ytd_as_of_date", "pinch_hand",
        "avg_pinch_strength", "pinch_tests", "pinch_test_dates",
        "first_pinch_date", "last_pinch_date",
    ]].copy().rename(columns={
        "avg_fb_velo": "pinch_avg_fb_velo",
        "ytd_as_of_date": "pinch_ytd_as_of_date",
    })

    combined = ci_keep.merge(pinch_keep, on="name_key", how="inner")
    if combined.empty:
        return pd.DataFrame(columns=columns)

    # The CI and pinch overview summaries independently select the same final
    # in-window YTD velocity. Keep only exact pitcher-level matches.
    velocity_agrees = np.isclose(
        combined["avg_fb_velo"].to_numpy(dtype=float),
        combined["pinch_avg_fb_velo"].to_numpy(dtype=float),
        equal_nan=False,
    )
    date_agrees = (
        pd.to_datetime(combined["ytd_as_of_date"]).dt.normalize()
        == pd.to_datetime(combined["pinch_ytd_as_of_date"]).dt.normalize()
    )
    combined = combined.loc[velocity_agrees & date_agrees].copy()
    combined = combined.drop(columns=[
        "pinch_avg_fb_velo", "pinch_ytd_as_of_date"
    ])
    combined = combined.drop_duplicates("name_key", keep="first")
    combined["observation"] = combined["athlete"]
    return combined[columns].sort_values(
        "avg_fb_velo", ascending=False
    ).reset_index(drop=True)


def _fit_cross_sectional_variant(
    work: pd.DataFrame,
    predictor_columns: list[str],
) -> dict | None:
    """Fit an ordinary pitcher-level regression with one row per pitcher."""
    needed = ["avg_fb_velo", *predictor_columns]
    data = work.dropna(subset=needed).copy().reset_index(drop=True)
    n = len(data)
    k = len(predictor_columns)
    if n <= k + 1 or k == 0:
        return None

    x_predictors = data[predictor_columns].to_numpy(dtype=float)
    x = np.column_stack([np.ones(n), x_predictors])
    y = data["avg_fb_velo"].to_numpy(dtype=float)
    if np.linalg.matrix_rank(x) < k + 1 or np.isclose(np.std(y), 0):
        return None

    coef, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    predicted = x @ coef
    residual = y - predicted
    ss_total = float(np.sum((y - y.mean()) ** 2))
    ss_residual = float(np.sum(residual ** 2))
    r2 = float(1.0 - ss_residual / ss_total) if ss_total > 0 else np.nan
    rmse = float(np.sqrt(np.mean(residual ** 2)))

    df_residual = n - k - 1
    adjusted_r2 = (
        float(1.0 - (1.0 - r2) * (n - 1) / df_residual)
        if df_residual > 0 and pd.notna(r2) else np.nan
    )

    if df_residual > 0:
        sigma2 = ss_residual / df_residual
        covariance = sigma2 * np.linalg.pinv(x.T @ x)
        standard_errors = np.sqrt(
            np.maximum(np.diag(covariance), 0.0)
        )
    else:
        standard_errors = np.full(k + 1, np.nan)

    # Leave one pitcher out at a time. Because the input has exactly one row
    # per pitcher, this is ordinary leave-one-observation-out validation.
    cv_predicted = np.full(n, np.nan, dtype=float)
    for row_index in range(n):
        train_mask = np.ones(n, dtype=bool)
        train_mask[row_index] = False
        x_train = x[train_mask]
        y_train = y[train_mask]
        if (
            len(y_train) <= k
            or np.linalg.matrix_rank(x_train) < k + 1
        ):
            continue
        train_coef, _, _, _ = np.linalg.lstsq(
            x_train, y_train, rcond=None
        )
        cv_predicted[row_index] = x[row_index] @ train_coef

    valid_cv = np.isfinite(cv_predicted)
    if valid_cv.all():
        cv_error = y - cv_predicted
        cv_rmse = float(np.sqrt(np.mean(cv_error ** 2)))
        cv_r2 = (
            float(1.0 - np.sum(cv_error ** 2) / ss_total)
            if ss_total > 0 else np.nan
        )
    else:
        cv_rmse = np.nan
        cv_r2 = np.nan

    return {
        "data": data,
        "coef": coef,
        "standard_errors": standard_errors,
        "predicted": predicted,
        "residual": residual,
        "r2": r2,
        "adjusted_r2": adjusted_r2,
        "rmse": rmse,
        "cv_predicted": cv_predicted,
        "cv_rmse": cv_rmse,
        "cv_r2": cv_r2,
        "n": n,
        "k": k,
        "df_residual": df_residual,
    }


def fit_combined_overview_model(
    summary: pd.DataFrame,
) -> dict | None:
    """Fit final YTD FB velo on average CI and average pinch strength."""
    combined = _fit_cross_sectional_variant(
        summary, ["avg_ci", "avg_pinch_strength"]
    )
    if combined is None:
        return None

    data = combined["data"].copy()
    intercept = float(combined["coef"][0])
    beta_ci = float(combined["coef"][1])
    beta_pinch = float(combined["coef"][2])
    data["predicted_fb_velo"] = combined["predicted"]
    data["residual_fb_velo"] = combined["residual"]
    data["cv_predicted_fb_velo"] = combined["cv_predicted"]

    y_sd = float(data["avg_fb_velo"].std(ddof=0))
    ci_sd = float(data["avg_ci"].std(ddof=0))
    pinch_sd = float(data["avg_pinch_strength"].std(ddof=0))
    standardized_beta_ci = (
        beta_ci * ci_sd / y_sd
        if not np.isclose(ci_sd, 0) and not np.isclose(y_sd, 0)
        else np.nan
    )
    standardized_beta_pinch = (
        beta_pinch * pinch_sd / y_sd
        if not np.isclose(pinch_sd, 0) and not np.isclose(y_sd, 0)
        else np.nan
    )
    ci_pinch_r = (
        float(np.corrcoef(
            data["avg_ci"], data["avg_pinch_strength"]
        )[0, 1])
        if not np.isclose(ci_sd, 0) and not np.isclose(pinch_sd, 0)
        else np.nan
    )
    vif = (
        float(1.0 / (1.0 - ci_pinch_r ** 2))
        if pd.notna(ci_pinch_r) and abs(ci_pinch_r) < 1.0
        else np.inf
    )

    ci_only = _fit_cross_sectional_variant(data, ["avg_ci"])
    pinch_only = _fit_cross_sectional_variant(
        data, ["avg_pinch_strength"]
    )

    return {
        "n_pitchers": combined["n"],
        "intercept": intercept,
        "beta_ci": beta_ci,
        "beta_pinch": beta_pinch,
        "se_intercept": float(combined["standard_errors"][0]),
        "se_ci": float(combined["standard_errors"][1]),
        "se_pinch": float(combined["standard_errors"][2]),
        "r2": combined["r2"],
        "adjusted_r2": combined["adjusted_r2"],
        "rmse": combined["rmse"],
        "cv_rmse": combined["cv_rmse"],
        "cv_r2": combined["cv_r2"],
        "standardized_beta_ci": standardized_beta_ci,
        "standardized_beta_pinch": standardized_beta_pinch,
        "ci_pinch_r": ci_pinch_r,
        "vif": vif,
        "ci_only_r2": ci_only["r2"] if ci_only is not None else np.nan,
        "pinch_only_r2": (
            pinch_only["r2"] if pinch_only is not None else np.nan
        ),
        "ci_only_cv_r2": (
            ci_only["cv_r2"] if ci_only is not None else np.nan
        ),
        "pinch_only_cv_r2": (
            pinch_only["cv_r2"] if pinch_only is not None else np.nan
        ),
        "data": data.sort_values(
            "avg_fb_velo", ascending=False
        ).reset_index(drop=True),
    }


def build_combined_actual_predicted_chart(
    model: dict | None,
    show_labels: bool,
) -> go.Figure:
    """Plot one actual-versus-predicted point for each pitcher."""
    fig = go.Figure()
    if model is None or model["data"].empty:
        fig.add_annotation(
            text="The combined overview model could not be fit.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 500)

    data = model["data"]
    customdata = np.column_stack([
        data["athlete"], data["team"], data["avg_ci"],
        data["avg_pinch_strength"], data["pinch_hand"],
        data["avg_fb_velo"], data["residual_fb_velo"],
        data["ytd_as_of_date"].map(fmt_date),
    ])
    fig.add_trace(go.Scatter(
        x=data["predicted_fb_velo"],
        y=data["avg_fb_velo"],
        mode="markers+text" if show_labels else "markers",
        text=data["athlete"] if show_labels else None,
        textposition="top center",
        textfont={"size": 9, "color": NAVY},
        marker={
            "size": 13, "color": ACCENT_RED, "opacity": 0.86,
            "line": {"color": "#FFFFFF", "width": 2},
        },
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Team: %{customdata[1]}<br>"
            "Average CI: %{customdata[2]:.2f} N·s<br>"
            "Average pinch: %{customdata[3]:.2f} · %{customdata[4]}<br>"
            "Final YTD FB velo: %{customdata[5]:.2f} mph<br>"
            "YTD as of %{customdata[7]}<br>"
            "Predicted FB velo: %{x:.2f} mph<br>"
            "Residual: %{customdata[6]:+.2f} mph<extra></extra>"
        ),
    ))

    all_values = np.concatenate([
        data["predicted_fb_velo"].to_numpy(dtype=float),
        data["avg_fb_velo"].to_numpy(dtype=float),
    ])
    lower = float(np.nanmin(all_values)) - 0.5
    upper = float(np.nanmax(all_values)) + 0.5
    if np.isclose(lower, upper):
        lower -= 0.5
        upper += 0.5
    fig.add_trace(go.Scatter(
        x=[lower, upper], y=[lower, upper], mode="lines",
        line={"color": NAVY_MID, "width": 2, "dash": "dash"},
        hoverinfo="skip",
    ))
    fig.update_xaxes(
        title="Predicted final YTD FB velo (mph)",
        range=[lower, upper], showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Actual final YTD FB velo (mph)",
        range=[lower, upper], showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 500)



def build_predicted_actual_roster_chart(
    model: dict | None,
) -> go.Figure:
    """Compare actual and model-predicted FB velo for every eligible pitcher."""
    fig = go.Figure()
    if model is None or model["data"].empty:
        fig.add_annotation(
            text="No eligible pitchers are available for predicted vs actual velo.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 460)

    data = model["data"].copy().sort_values(
        "avg_fb_velo", ascending=True
    ).reset_index(drop=True)
    customdata = np.column_stack([
        data["team"], data["avg_ci"], data["avg_pinch_strength"],
        data["pinch_hand"], data["residual_fb_velo"],
        data["ytd_as_of_date"].map(fmt_date),
    ])

    fig.add_trace(go.Bar(
        x=data["avg_fb_velo"],
        y=data["athlete"],
        orientation="h",
        name="Actual",
        marker={"color": NAVY_MID},
        customdata=customdata,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Team: %{customdata[0]}<br>"
            "Actual final YTD FB velo: %{x:.2f} mph<br>"
            "YTD as of %{customdata[5]}<br>"
            "Average CI: %{customdata[1]:.2f} N·s<br>"
            "Average pinch: %{customdata[2]:.2f} · %{customdata[3]}"
            "<extra></extra>"
        ),
    ))
    fig.add_trace(go.Bar(
        x=data["predicted_fb_velo"],
        y=data["athlete"],
        orientation="h",
        name="Predicted",
        marker={"color": TEAL},
        customdata=customdata,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Predicted FB velo: %{x:.2f} mph<br>"
            "Actual − predicted residual: %{customdata[4]:+.2f} mph"
            "<extra></extra>"
        ),
    ))

    all_values = np.concatenate([
        data["avg_fb_velo"].to_numpy(dtype=float),
        data["predicted_fb_velo"].to_numpy(dtype=float),
    ])
    x_min = max(0.0, float(np.nanmin(all_values)) - 1.0)
    x_max = float(np.nanmax(all_values)) + 1.0
    fig.update_xaxes(
        title="Final YTD FB velo (mph)", range=[x_min, x_max],
        showgrid=True, gridcolor=GRID, zeroline=False,
        linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Pitcher", showgrid=False, linecolor=BORDER,
        tickfont={"color": TEXT, "size": 11},
        title_font={"color": SUBTEXT}, automargin=True,
    )
    fig = base_figure_layout(
        fig, max(500, min(1500, 170 + 34 * len(data)))
    )
    fig.update_layout(
        barmode="group",
        showlegend=True,
        legend={
            "orientation": "h", "x": 0, "y": 1.04,
            "font": {"color": SUBTEXT},
        },
        margin={"l": 135, "r": 30, "t": 46, "b": 58},
    )
    return fig


def build_pitcher_whatif_chart(
    pitcher: str,
    actual_velo: float,
    current_predicted: float,
    whatif_predicted: float,
) -> go.Figure:
    """Show one pitcher's actual, current predicted, and what-if predicted velo."""
    fig = go.Figure()
    labels = ["Actual", "Current predicted", "What-if predicted"]
    values = [actual_velo, current_predicted, whatif_predicted]
    colors = [NAVY_MID, TEAL, ACCENT_RED]
    fig.add_trace(go.Bar(
        x=labels,
        y=values,
        marker={"color": colors},
        text=[f"{value:.2f}" for value in values],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>%{y:.2f} mph<extra></extra>",
    ))
    low = max(0.0, min(values) - 2.0)
    high = max(values) + 1.5
    if np.isclose(low, high):
        high = low + 3.0
    fig.update_xaxes(
        title="", showgrid=False, linecolor=BORDER,
        tickfont={"color": TEXT},
    )
    fig.update_yaxes(
        title="FB velo (mph)", range=[low, high],
        showgrid=True, gridcolor=GRID, zeroline=False,
        linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig = base_figure_layout(fig, 390)
    fig.update_layout(
        title={
            "text": f"{pitcher} · actual vs model scenarios",
            "x": 0.01,
            "xanchor": "left",
            "font": {"size": 16, "color": NAVY},
        },
        margin={"l": 66, "r": 30, "t": 55, "b": 58},
    )
    return fig


def build_combined_model_comparison_chart(
    model: dict | None,
) -> go.Figure:
    """Compare leave-one-pitcher-out cross-validated R²."""
    fig = go.Figure()
    if model is None:
        fig.add_annotation(
            text="The combined overview model could not be fit.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 390)

    labels = ["CI only", "Pinch only", "CI + Pinch"]
    values = [
        model["ci_only_cv_r2"],
        model["pinch_only_cv_r2"],
        model["cv_r2"],
    ]
    fig.add_trace(go.Bar(
        x=labels,
        y=values,
        marker={"color": [BLUE, TEAL, ACCENT_RED]},
        text=[f"{value:.2f}" if pd.notna(value) else "—" for value in values],
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{x}</b><br>Leave-one-pitcher-out CV R²: "
            "%{y:.3f}<extra></extra>"
        ),
    ))
    valid = [float(value) for value in values if pd.notna(value)]
    low = min(valid + [0.0]) - 0.12
    high = max(valid + [0.0]) + 0.12
    if high - low < 0.5:
        high = low + 0.5
    fig.update_xaxes(
        title="Pitcher-level model", showgrid=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Leave-one-pitcher-out CV R²", range=[low, high],
        showgrid=True, gridcolor=GRID, zeroline=True,
        zerolinecolor=BORDER, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 390)



# -----------------------------------------------------------------------------
# CSV EXPORTS AND S&C OPPORTUNITY FLAGS
# -----------------------------------------------------------------------------
def csv_download_button(
    df: pd.DataFrame,
    label: str,
    filename: str,
    key: str,
) -> None:
    """Render a UTF-8 CSV download button for a displayed results table."""
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=label,
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
        key=key,
    )


def build_sc_opportunity_tables(
    model: dict | None,
    low_ci_threshold: float,
    low_pinch_threshold: float,
    projected_velo_threshold: float,
    high_ci_threshold: float,
    throwing_residual_threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build pitcher-level S&C development, projection-gap, and throwing tables.

    S&C development requires all three criteria: low CI, low pinch strength,
    and combined-model projected velocity below the selected cutoff.

    The projection-gap list includes every pitcher whose combined-model
    projected velocity is at or above the selected cutoff while actual final
    YTD fastball velocity remains below that same cutoff.

    The throwing-development list requires CI above the high-CI cutoff and
    a model residual at or below the selected negative residual threshold.
    """
    output_columns = [
        "athlete",
        "team",
        "avg_fb_velo",
        "predicted_fb_velo",
        "residual_fb_velo",
        "avg_ci",
        "avg_pinch_strength",
        "pinch_hand",
        "ytd_as_of_date",
        "ci_jumps",
        "pinch_tests",
        "reasons",
    ]

    if (
        model is None
        or "data" not in model
        or model["data"] is None
        or model["data"].empty
    ):
        empty = pd.DataFrame(columns=output_columns)
        return empty.copy(), empty.copy(), empty.copy()

    required_columns = {
        "athlete",
        "team",
        "avg_fb_velo",
        "predicted_fb_velo",
        "residual_fb_velo",
        "avg_ci",
        "avg_pinch_strength",
        "pinch_hand",
        "ytd_as_of_date",
        "ci_jumps",
        "pinch_tests",
    }
    missing = required_columns.difference(model["data"].columns)
    if missing:
        raise ValueError(
            "The combined-model data is missing required S&C opportunity "
            f"column(s): {', '.join(sorted(missing))}."
        )

    data = model["data"].copy()
    data["low_ci_flag"] = data["avg_ci"] < float(low_ci_threshold)
    data["low_pinch_flag"] = (
        data["avg_pinch_strength"] < float(low_pinch_threshold)
    )
    data["low_projected_velo_flag"] = (
        data["predicted_fb_velo"] < float(projected_velo_threshold)
    )

    data["projected_at_or_above_threshold_flag"] = (
        data["predicted_fb_velo"] >= float(projected_velo_threshold)
    )
    data["actual_below_projected_threshold_flag"] = (
        data["avg_fb_velo"] < float(projected_velo_threshold)
    )
    data["throwing_ci_flag"] = (
        data["avg_ci"] > float(high_ci_threshold)
    )
    data["negative_throwing_residual_flag"] = (
        data["residual_fb_velo"] <= float(throwing_residual_threshold)
    )

    upside = data.loc[
        data["low_ci_flag"]
        & data["low_pinch_flag"]
        & data["low_projected_velo_flag"]
    ].copy()
    upside["reasons"] = (
        f"CI < {low_ci_threshold:.0f} | "
        f"Pinch < {low_pinch_threshold:.0f} | "
        f"Projected FB velo < {projected_velo_threshold:.1f} mph"
    )
    upside = upside.sort_values(
        ["predicted_fb_velo", "avg_ci", "avg_pinch_strength"],
        ascending=[True, True, True],
    )

    projection_gap = data.loc[
        data["projected_at_or_above_threshold_flag"]
        & data["actual_below_projected_threshold_flag"]
    ].copy()
    projection_gap["reasons"] = (
        f"Projected FB velo >= {projected_velo_threshold:.1f} mph | "
        f"Actual FB velo < {projected_velo_threshold:.1f} mph"
    )
    projection_gap = projection_gap.sort_values(
        ["predicted_fb_velo", "avg_fb_velo"],
        ascending=[False, True],
    )

    throwing = data.loc[
        data["throwing_ci_flag"]
        & data["negative_throwing_residual_flag"]
    ].copy()
    throwing["reasons"] = (
        f"CI > {high_ci_threshold:.0f} | "
        f"Residual <= {throwing_residual_threshold:.1f} mph"
    )
    throwing = throwing.sort_values(
        ["residual_fb_velo", "avg_ci"],
        ascending=[True, False],
    )

    return (
        upside[output_columns].reset_index(drop=True),
        projection_gap[output_columns].reset_index(drop=True),
        throwing[output_columns].reset_index(drop=True),
    )


def build_projection_gap_table(
    model: dict | None,
    projected_threshold: float,
    actual_threshold: float | None = None,
) -> pd.DataFrame:
    """Return pitchers projected above one cutoff but actually below another."""
    output_columns = [
        "athlete",
        "team",
        "avg_fb_velo",
        "predicted_fb_velo",
        "residual_fb_velo",
        "avg_ci",
        "avg_pinch_strength",
        "pinch_hand",
        "ytd_as_of_date",
        "ci_jumps",
        "pinch_tests",
        "reasons",
    ]
    if (
        model is None
        or "data" not in model
        or model["data"] is None
        or model["data"].empty
    ):
        return pd.DataFrame(columns=output_columns)

    actual_cutoff = (
        float(projected_threshold)
        if actual_threshold is None
        else float(actual_threshold)
    )
    data = model["data"].copy()
    gap = data.loc[
        (data["predicted_fb_velo"] >= float(projected_threshold))
        & (data["avg_fb_velo"] < actual_cutoff)
    ].copy()
    gap["reasons"] = (
        f"Projected FB velo >= {float(projected_threshold):.1f} mph | "
        f"Actual FB velo < {actual_cutoff:.1f} mph"
    )
    gap = gap.sort_values(
        ["predicted_fb_velo", "avg_fb_velo"],
        ascending=[False, True],
    )
    return gap[output_columns].reset_index(drop=True)


def build_hitter_sc_opportunity_tables(
    bat_pairs: pd.DataFrame,
    exit_summary: pd.DataFrame,
    low_ci_threshold: float,
    residual_threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build hitter S&C-development and CI-underperformance tables.

    The S&C-development table flags hitters whose matched CI is below the
    selected low-CI threshold in either the latest qualifying bat-speed month
    or the P90 exit-velocity observation.

    The underperformance table flags hitters with CI at or above that threshold
    whose actual bat speed or P90 exit velocity is at least the selected amount
    below the value predicted by the corresponding CI-only regression.
    """
    output_columns = [
        "athlete", "team", "month", "monthly_avg_ci", "monthly_avg_bat_speed",
        "predicted_bat_speed", "bat_speed_residual", "exit_velo_as_of",
        "ytd_avg_ci", "p90_exit_velo", "predicted_p90_exit_velo",
        "p90_exit_velo_residual", "reasons",
    ]

    bat_stats = bat_correlation_stats(bat_pairs)
    exit_stats = exit_velo_correlation_stats(exit_summary)

    if bat_pairs.empty:
        bat_work = pd.DataFrame(columns=[
            "name_key", "bat_athlete", "bat_team", "month", "monthly_avg_ci",
            "monthly_avg_bat_speed", "predicted_bat_speed", "bat_speed_residual",
        ])
    else:
        bat_work = bat_pairs[[
            "name_key", "athlete", "team", "month", "avg_ci",
            "monthly_avg_bat_speed",
        ]].copy().rename(columns={
            "athlete": "bat_athlete",
            "team": "bat_team",
            "avg_ci": "monthly_avg_ci",
        })
        if bat_stats is not None:
            bat_work["predicted_bat_speed"] = (
                bat_stats[2] * bat_work["monthly_avg_ci"] + bat_stats[3]
            )
            bat_work["bat_speed_residual"] = (
                bat_work["monthly_avg_bat_speed"] - bat_work["predicted_bat_speed"]
            )
        else:
            bat_work["predicted_bat_speed"] = np.nan
            bat_work["bat_speed_residual"] = np.nan

    if exit_summary.empty:
        exit_work = pd.DataFrame(columns=[
            "name_key", "exit_athlete", "exit_team", "exit_velo_as_of",
            "ytd_avg_ci", "p90_exit_velo", "predicted_p90_exit_velo",
            "p90_exit_velo_residual",
        ])
    else:
        exit_work = exit_summary[[
            "name_key", "athlete", "team", "exit_velo_as_of", "avg_ci",
            "p90_exit_velo",
        ]].copy().rename(columns={
            "athlete": "exit_athlete",
            "team": "exit_team",
            "avg_ci": "ytd_avg_ci",
        })
        if exit_stats is not None:
            exit_work["predicted_p90_exit_velo"] = (
                exit_stats[2] * exit_work["ytd_avg_ci"] + exit_stats[3]
            )
            exit_work["p90_exit_velo_residual"] = (
                exit_work["p90_exit_velo"] - exit_work["predicted_p90_exit_velo"]
            )
        else:
            exit_work["predicted_p90_exit_velo"] = np.nan
            exit_work["p90_exit_velo_residual"] = np.nan

    combined = bat_work.merge(exit_work, on="name_key", how="outer")
    if combined.empty:
        empty = pd.DataFrame(columns=output_columns)
        return empty.copy(), empty.copy()

    combined["athlete"] = combined.get("bat_athlete").combine_first(
        combined.get("exit_athlete")
    )
    combined["team"] = combined.get("bat_team").combine_first(
        combined.get("exit_team")
    )

    monthly_low = combined["monthly_avg_ci"].lt(float(low_ci_threshold)).fillna(False)
    ytd_low = combined["ytd_avg_ci"].lt(float(low_ci_threshold)).fillna(False)
    monthly_adequate = combined["monthly_avg_ci"].ge(float(low_ci_threshold)).fillna(False)
    ytd_adequate = combined["ytd_avg_ci"].ge(float(low_ci_threshold)).fillna(False)
    bat_under = combined["bat_speed_residual"].le(float(residual_threshold)).fillna(False)
    exit_under = combined["p90_exit_velo_residual"].le(float(residual_threshold)).fillna(False)

    sc_development = combined.loc[monthly_low | ytd_low].copy()
    def _sc_reason(row) -> str:
        reasons = []
        if pd.notna(row.get("monthly_avg_ci")) and row["monthly_avg_ci"] < float(low_ci_threshold):
            reasons.append(f"Monthly CI < {low_ci_threshold:.0f}")
        if pd.notna(row.get("ytd_avg_ci")) and row["ytd_avg_ci"] < float(low_ci_threshold):
            reasons.append(f"YTD CI < {low_ci_threshold:.0f}")
        return " | ".join(reasons)
    sc_development["reasons"] = sc_development.apply(_sc_reason, axis=1)

    underperforming = combined.loc[
        (monthly_adequate & bat_under) | (ytd_adequate & exit_under)
    ].copy()
    def _under_reason(row) -> str:
        reasons = []
        if (
            pd.notna(row.get("monthly_avg_ci"))
            and row["monthly_avg_ci"] >= float(low_ci_threshold)
            and pd.notna(row.get("bat_speed_residual"))
            and row["bat_speed_residual"] <= float(residual_threshold)
        ):
            reasons.append(f"Bat-speed residual <= {residual_threshold:.1f} mph")
        if (
            pd.notna(row.get("ytd_avg_ci"))
            and row["ytd_avg_ci"] >= float(low_ci_threshold)
            and pd.notna(row.get("p90_exit_velo_residual"))
            and row["p90_exit_velo_residual"] <= float(residual_threshold)
        ):
            reasons.append(f"P90 exit-velo residual <= {residual_threshold:.1f} mph")
        return " | ".join(reasons)
    underperforming["reasons"] = underperforming.apply(_under_reason, axis=1)

    sc_development = sc_development.sort_values(
        ["monthly_avg_ci", "ytd_avg_ci"], ascending=[True, True], na_position="last"
    )
    underperforming["worst_residual"] = underperforming[[
        "bat_speed_residual", "p90_exit_velo_residual"
    ]].min(axis=1, skipna=True)
    underperforming = underperforming.sort_values(
        "worst_residual", ascending=True, na_position="last"
    ).drop(columns=["worst_residual"])

    for frame in (sc_development, underperforming):
        if "month" in frame.columns:
            frame["month"] = pd.to_datetime(frame["month"], errors="coerce")
        if "exit_velo_as_of" in frame.columns:
            frame["exit_velo_as_of"] = pd.to_datetime(
                frame["exit_velo_as_of"], errors="coerce"
            )

    return (
        sc_development[output_columns].reset_index(drop=True),
        underperforming[output_columns].reset_index(drop=True),
    )




def build_pitcher_custom_category(
    model: dict | None,
    criteria: list[dict],
) -> pd.DataFrame:
    """Filter combined-model pitchers using only enabled category criteria."""
    output_columns = [
        "athlete", "team", "avg_fb_velo", "predicted_fb_velo",
        "residual_fb_velo", "avg_ci", "avg_pinch_strength", "pinch_hand",
        "ytd_as_of_date", "ci_jumps", "pinch_tests", "reasons",
    ]
    if model is None or model.get("data") is None or model["data"].empty:
        return pd.DataFrame(columns=output_columns)

    data = model["data"].copy()
    active = [c for c in criteria if c.get("enabled", False)]
    mask = pd.Series(True, index=data.index)

    op_map = {
        "lt": lambda s, v: s.lt(v),
        "le": lambda s, v: s.le(v),
        "gt": lambda s, v: s.gt(v),
        "ge": lambda s, v: s.ge(v),
    }
    symbol_map = {"lt": "<", "le": "≤", "gt": ">", "ge": "≥"}

    reason_parts = []
    for criterion in active:
        column = criterion["column"]
        operator = criterion["operator"]
        value = float(criterion["value"])
        if column not in data.columns:
            continue
        criterion_mask = op_map[operator](data[column], value).fillna(False)
        mask &= criterion_mask
        decimals = int(criterion.get("decimals", 1))
        unit = criterion.get("unit", "")
        label = criterion.get("label", column)
        reason_parts.append(
            f"{label} {symbol_map[operator]} {value:.{decimals}f}{unit}"
        )

    result = data.loc[mask].copy()
    result["reasons"] = " | ".join(reason_parts) if reason_parts else "No criteria enabled"
    sort_col = "residual_fb_velo" if "residual_fb_velo" in result.columns else "avg_fb_velo"
    if not result.empty:
        result = result.sort_values(sort_col, ascending=True, na_position="last")
    return result[output_columns].reset_index(drop=True)


def build_hitter_opportunity_base(
    bat_pairs: pd.DataFrame,
    exit_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Create one merged hitter row with CI, output, projections, and residuals."""
    output_columns = [
        "athlete", "team", "month", "monthly_avg_ci", "monthly_avg_bat_speed",
        "predicted_bat_speed", "bat_speed_residual", "exit_velo_as_of",
        "ytd_avg_ci", "p90_exit_velo", "predicted_p90_exit_velo",
        "p90_exit_velo_residual",
    ]
    bat_stats = bat_correlation_stats(bat_pairs)
    exit_stats = exit_velo_correlation_stats(exit_summary)

    if bat_pairs.empty:
        bat_work = pd.DataFrame(columns=[
            "name_key", "bat_athlete", "bat_team", "month", "monthly_avg_ci",
            "monthly_avg_bat_speed", "predicted_bat_speed", "bat_speed_residual",
        ])
    else:
        bat_work = bat_pairs[[
            "name_key", "athlete", "team", "month", "avg_ci", "monthly_avg_bat_speed",
        ]].copy().rename(columns={
            "athlete": "bat_athlete", "team": "bat_team", "avg_ci": "monthly_avg_ci",
        })
        if bat_stats is not None:
            bat_work["predicted_bat_speed"] = bat_stats[2] * bat_work["monthly_avg_ci"] + bat_stats[3]
            bat_work["bat_speed_residual"] = bat_work["monthly_avg_bat_speed"] - bat_work["predicted_bat_speed"]
        else:
            bat_work["predicted_bat_speed"] = np.nan
            bat_work["bat_speed_residual"] = np.nan

    if exit_summary.empty:
        exit_work = pd.DataFrame(columns=[
            "name_key", "exit_athlete", "exit_team", "exit_velo_as_of", "ytd_avg_ci",
            "p90_exit_velo", "predicted_p90_exit_velo", "p90_exit_velo_residual",
        ])
    else:
        exit_work = exit_summary[[
            "name_key", "athlete", "team", "exit_velo_as_of", "avg_ci", "p90_exit_velo",
        ]].copy().rename(columns={
            "athlete": "exit_athlete", "team": "exit_team", "avg_ci": "ytd_avg_ci",
        })
        if exit_stats is not None:
            exit_work["predicted_p90_exit_velo"] = exit_stats[2] * exit_work["ytd_avg_ci"] + exit_stats[3]
            exit_work["p90_exit_velo_residual"] = exit_work["p90_exit_velo"] - exit_work["predicted_p90_exit_velo"]
        else:
            exit_work["predicted_p90_exit_velo"] = np.nan
            exit_work["p90_exit_velo_residual"] = np.nan

    combined = bat_work.merge(exit_work, on="name_key", how="outer")
    if combined.empty:
        return pd.DataFrame(columns=output_columns)
    combined["athlete"] = combined.get("bat_athlete").combine_first(combined.get("exit_athlete"))
    combined["team"] = combined.get("bat_team").combine_first(combined.get("exit_team"))
    for col in output_columns:
        if col not in combined.columns:
            combined[col] = np.nan
    return combined[output_columns].reset_index(drop=True)


def filter_hitter_custom_category(
    base: pd.DataFrame,
    criteria: list[dict],
    mode: str = "all",
) -> pd.DataFrame:
    """Filter hitter rows with ANY or ALL enabled criteria."""
    output_columns = list(base.columns) + (["reasons"] if "reasons" not in base.columns else [])
    if base.empty:
        return pd.DataFrame(columns=output_columns)
    active = [c for c in criteria if c.get("enabled", False)]
    if not active:
        out = base.copy()
        out["reasons"] = "No criteria enabled"
        return out

    op_map = {
        "lt": lambda s, v: s.lt(v), "le": lambda s, v: s.le(v),
        "gt": lambda s, v: s.gt(v), "ge": lambda s, v: s.ge(v),
    }
    symbol_map = {"lt": "<", "le": "≤", "gt": ">", "ge": "≥"}
    masks = []
    for c in active:
        masks.append(op_map[c["operator"]](base[c["column"]], float(c["value"])).fillna(False))
    combined_mask = masks[0].copy()
    for m in masks[1:]:
        combined_mask = (combined_mask & m) if mode == "all" else (combined_mask | m)
    out = base.loc[combined_mask].copy()

    def row_reason(row) -> str:
        matched = []
        for c in active:
            val = row.get(c["column"])
            if pd.isna(val):
                continue
            passed = bool(op_map[c["operator"]](pd.Series([val]), float(c["value"])).iloc[0])
            if passed:
                decimals = int(c.get("decimals", 1))
                unit = c.get("unit", "")
                matched.append(
                    f"{c.get('label', c['column'])} {symbol_map[c['operator']]} "
                    f"{float(c['value']):.{decimals}f}{unit}"
                )
        return " | ".join(matched)
    out["reasons"] = out.apply(row_reason, axis=1)
    return out.reset_index(drop=True)


def filter_hitter_underperformance_pathways(
    base: pd.DataFrame,
    use_bat_path: bool,
    bat_require_ci: bool,
    bat_ci_min: float,
    bat_require_residual: bool,
    bat_residual_max: float,
    use_exit_path: bool,
    exit_require_ci: bool,
    exit_ci_min: float,
    exit_require_residual: bool,
    exit_residual_max: float,
    pathway_mode: str = "any",
) -> pd.DataFrame:
    """Filter hitter underperformance using configurable bat and P90 pathways."""
    if base.empty:
        return base.assign(reasons=pd.Series(dtype=str))

    pathways = []
    pathway_reasons = []

    if use_bat_path:
        m = pd.Series(True, index=base.index)
        parts = []
        if bat_require_ci:
            m &= base["monthly_avg_ci"].ge(float(bat_ci_min)).fillna(False)
            parts.append(f"Monthly CI ≥ {bat_ci_min:.0f}")
        if bat_require_residual:
            m &= base["bat_speed_residual"].le(float(bat_residual_max)).fillna(False)
            parts.append(f"Bat residual ≤ {bat_residual_max:.1f} mph")
        pathways.append(m)
        pathway_reasons.append((m, "Bat: " + " | ".join(parts) if parts else "Bat pathway"))

    if use_exit_path:
        m = pd.Series(True, index=base.index)
        parts = []
        if exit_require_ci:
            m &= base["ytd_avg_ci"].ge(float(exit_ci_min)).fillna(False)
            parts.append(f"YTD CI ≥ {exit_ci_min:.0f}")
        if exit_require_residual:
            m &= base["p90_exit_velo_residual"].le(float(exit_residual_max)).fillna(False)
            parts.append(f"P90 residual ≤ {exit_residual_max:.1f} mph")
        pathways.append(m)
        pathway_reasons.append((m, "P90: " + " | ".join(parts) if parts else "P90 pathway"))

    if not pathways:
        out = base.copy()
        out["reasons"] = "No pathways enabled"
        return out

    final = pathways[0].copy()
    for m in pathways[1:]:
        final = (final & m) if pathway_mode == "all" else (final | m)
    out = base.loc[final].copy()

    def reasons_for_index(index) -> str:
        return " || ".join(reason for mask, reason in pathway_reasons if bool(mask.loc[index]))
    out["reasons"] = [reasons_for_index(i) for i in out.index]
    return out.reset_index(drop=True)


def build_power_pitch_summary(
    jump_power: pd.DataFrame,
    velo: pd.DataFrame,
    start_date,
    end_date,
    team_filter: str,
    min_velo_records: int,
    min_power_jumps: int,
) -> pd.DataFrame:
    """Create one pitcher-level row matching average Peak Power to final in-window YTD FB velo."""
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()

    power_window = jump_power[
        (jump_power["date"] >= start) & (jump_power["date"] <= end)
    ].copy()
    velo_window = velo[
        (velo["date"] >= start) & (velo["date"] <= end)
    ].copy()

    team_lookup = (
        jump_power.sort_values("date")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
    )

    power_summary = (
        power_window.groupby("name_key", as_index=False)
        .agg(
            athlete=("athlete", "first"),
            avg_peak_power=("peak_power", "mean"),
            power_jumps=("peak_power", "count"),
            power_test_dates=("date", "nunique"),
            first_power_date=("date", "min"),
            last_power_date=("date", "max"),
        )
    )

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

    summary = velo_summary.merge(power_summary, on="name_key", how="inner")
    summary = summary.merge(team_lookup, on="name_key", how="left")
    summary["team"] = summary["team"].fillna("Unassigned")
    summary = summary[summary["avg_fb_velo"] >= MIN_LAST_YTD_FB_VELO].copy()
    summary = summary[
        (summary["fb_records"] >= max(1, int(min_velo_records)))
        & (summary["power_jumps"] >= max(1, int(min_power_jumps)))
    ].copy()

    if team_filter != "All Teams":
        summary = summary[summary["team"] == team_filter].copy()

    return summary.sort_values("avg_fb_velo", ascending=False).reset_index(drop=True)


def power_pitch_correlation_stats(
    summary: pd.DataFrame,
) -> tuple[float, float, float, float] | None:
    if len(summary) < 2:
        return None
    work = summary[["avg_peak_power", "avg_fb_velo"]].dropna()
    if len(work) < 2:
        return None
    x = work["avg_peak_power"].to_numpy(dtype=float)
    y = work["avg_fb_velo"].to_numpy(dtype=float)
    if np.isclose(np.std(x), 0) or np.isclose(np.std(y), 0):
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return r, r * r, float(slope), float(intercept)


def power_pitch_band_summary(
    summary: pd.DataFrame,
    band_width: float,
    velo_stat: str = "Mean",
) -> pd.DataFrame:
    stat = "Median" if str(velo_stat).strip().lower() == "median" else "Mean"
    velo_col = f"{stat} Last YTD FB Velo"
    if summary.empty:
        return pd.DataFrame(columns=[
            "Peak Power band", velo_col, "Pitchers", "Average Peak Power"
        ])

    width = max(float(band_width), 1e-9)
    work = summary[["avg_peak_power", "avg_fb_velo"]].dropna().copy()
    if work.empty:
        return pd.DataFrame(columns=[
            "Peak Power band", velo_col, "Pitchers", "Average Peak Power"
        ])
    work["band_start"] = np.floor(work["avg_peak_power"] / width) * width
    grouped = (
        work.groupby("band_start", as_index=False)
        .agg(**{
            velo_col: ("avg_fb_velo", "median" if stat == "Median" else "mean"),
            "Pitchers": ("avg_fb_velo", "count"),
            "Average Peak Power": ("avg_peak_power", "mean"),
        })
        .sort_values("band_start")
    )

    def _label(lower: float) -> str:
        upper = lower + width
        return f"{lower:.1f}–{upper:.1f} W"

    grouped["Peak Power band"] = grouped["band_start"].map(_label)
    grouped[velo_col] = grouped[velo_col].round(2)
    grouped["Average Peak Power"] = grouped["Average Peak Power"].round(2)
    grouped["Pitchers"] = grouped["Pitchers"].astype(int)
    return grouped[["Peak Power band", velo_col, "Pitchers", "Average Peak Power"]]


def build_power_pitch_band_chart(
    summary: pd.DataFrame,
    band_width: float,
    velo_stat: str = "Mean",
) -> go.Figure:
    stat = "Median" if str(velo_stat).strip().lower() == "median" else "Mean"
    velo_col = f"{stat} Last YTD FB Velo"
    bands = power_pitch_band_summary(summary, band_width, stat)
    fig = go.Figure()
    if bands.empty:
        fig.add_annotation(
            text="No matched pitchers are available for Peak Power bands.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 380)

    fig.add_trace(go.Bar(
        x=bands["Peak Power band"],
        y=bands[velo_col],
        marker={"color": BLUE, "line": {"color": NAVY_MID, "width": 0.8}},
        text=[f"{v:.1f}" for v in bands[velo_col]],
        textposition="outside",
        cliponaxis=False,
        customdata=np.column_stack([
            bands["Pitchers"], bands["Average Peak Power"]
        ]),
        hovertemplate=(
            f"<b>%{{x}}</b><br>{stat} last YTD FB velo: %{{y:.2f}} mph<br>"
            "Pitchers: %{customdata[0]}<br>Mean Peak Power: %{customdata[1]:.2f} W"
            "<extra></extra>"
        ),
    ))
    y_min = max(0, float(bands[velo_col].min()) - 1.5)
    y_max = float(bands[velo_col].max()) + 1.25
    fig.update_xaxes(
        title="Pitcher average Peak Power [W] band",
        showgrid=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title=f"{stat} last YTD FB velo (mph)",
        range=[y_min, y_max], showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 380)


def power_pitch_band_members(
    summary: pd.DataFrame,
    band_width: float,
    selected_band: str,
    velo_stat: str = "Mean",
) -> tuple[pd.DataFrame, float, str]:
    stat = "Median" if str(velo_stat).strip().lower() == "median" else "Mean"
    width = max(float(band_width), 1e-9)
    cols = ["athlete", "team", "avg_peak_power", "avg_fb_velo"]
    if summary.empty or any(c not in summary.columns for c in cols):
        return pd.DataFrame(columns=cols + ["Peak Power band", "Status", "Difference"]), np.nan, stat

    detail = summary[cols].dropna().copy()
    detail["band_start"] = np.floor(detail["avg_peak_power"] / width) * width
    detail["Peak Power band"] = detail["band_start"].map(
        lambda lower: f"{lower:.1f}–{lower + width:.1f} W"
    )
    detail = detail[detail["Peak Power band"] == selected_band].copy()
    if detail.empty:
        return detail, np.nan, stat

    reference = float(detail["avg_fb_velo"].median() if stat == "Median" else detail["avg_fb_velo"].mean())
    detail["Difference"] = detail["avg_fb_velo"] - reference
    detail["Status"] = np.where(
        np.isclose(detail["Difference"], 0, atol=1e-10),
        f"At {stat.lower()}",
        np.where(detail["Difference"] > 0, f"Above {stat.lower()}", f"Below {stat.lower()}"),
    )
    detail["Display"] = detail.apply(
        lambda row: f"{row['athlete']} · {row['avg_peak_power']:.1f} W", axis=1
    )
    return detail.sort_values("avg_fb_velo", ascending=False).reset_index(drop=True), reference, stat


def build_power_pitch_band_member_chart(
    summary: pd.DataFrame,
    band_width: float,
    selected_band: str,
    velo_stat: str = "Mean",
) -> go.Figure:
    detail, reference, stat = power_pitch_band_members(
        summary, band_width, selected_band, velo_stat
    )
    fig = go.Figure()
    if detail.empty:
        fig.add_annotation(
            text="No pitchers are available in this Peak Power band.",
            showarrow=False,
            font={"size": 14, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 340)

    status_style = [
        (f"Above {stat.lower()}", GREEN),
        (f"At {stat.lower()}", TEAL),
        (f"Below {stat.lower()}", ACCENT_RED),
    ]
    category_order = detail["Display"].tolist()
    for status, color in status_style:
        sub = detail[detail["Status"] == status]
        if sub.empty:
            continue
        customdata = np.column_stack([
            sub["athlete"], sub["team"], sub["avg_peak_power"],
            sub["Difference"], sub["Status"],
        ])
        fig.add_trace(go.Bar(
            x=sub["avg_fb_velo"], y=sub["Display"], orientation="h",
            name=status.title(),
            marker={"color": color, "line": {"color": "#FFFFFF", "width": 1}},
            text=[f"{v:.2f}" for v in sub["avg_fb_velo"]],
            textposition="outside", cliponaxis=False,
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Team: %{customdata[1]}<br>"
                "Average Peak Power [W]: %{customdata[2]:.2f} W<br>"
                "Last YTD FB velo: %{x:.2f} mph<br>"
                f"{stat} difference: %{{customdata[3]:+.2f}} mph<br>"
                "Flag: %{customdata[4]}<extra></extra>"
            ),
        ))

    x_min = max(0, float(detail["avg_fb_velo"].min()) - 1.5)
    x_max = float(detail["avg_fb_velo"].max()) + 1.25
    fig.add_vline(
        x=reference, line_color=NAVY_MID, line_width=2, line_dash="dash",
        annotation_text=f"{stat} {reference:.2f}",
        annotation_font_color=NAVY_MID, annotation_position="top right",
    )
    fig.update_xaxes(
        title="Last YTD FB velo (mph)", range=[x_min, x_max],
        showgrid=True, gridcolor=GRID, zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Pitcher · Average Peak Power [W]",
        categoryorder="array", categoryarray=category_order,
        autorange="reversed", showgrid=False, linecolor=BORDER,
        tickfont={"color": TEXT, "size": 12}, title_font={"color": SUBTEXT}, automargin=True,
    )
    fig = base_figure_layout(fig, max(340, len(detail) * 42 + 125))
    fig.update_layout(
        showlegend=True,
        legend={"orientation": "h", "x": 0, "y": 1.14, "font": {"color": SUBTEXT}},
        margin={"l": 210, "r": 70, "t": 50, "b": 58},
    )
    return fig


def build_power_pitch_scatter(
    summary: pd.DataFrame,
    show_labels: bool,
    power_lookup: float | None,
) -> go.Figure:
    fig = go.Figure()
    if summary.empty:
        fig.add_annotation(
            text="No matched pitchers meet the selected window and minimum-data rules.",
            showarrow=False, font={"size": 15, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 560)

    customdata = np.column_stack([
        summary["athlete"], summary["team"], summary["fb_records"],
        summary["power_jumps"], summary["power_test_dates"],
        summary["ytd_as_of_date"].map(fmt_date),
        summary["first_power_date"].map(fmt_date),
        summary["last_power_date"].map(fmt_date),
    ])
    fig.add_trace(go.Scatter(
        x=summary["avg_peak_power"], y=summary["avg_fb_velo"],
        mode="markers+text" if show_labels else "markers",
        text=summary["athlete"] if show_labels else None,
        textposition="top center", textfont={"size": 10, "color": NAVY},
        marker={"size": 13, "color": ACCENT_RED, "opacity": 0.88,
                "line": {"color": "#FFFFFF", "width": 2}},
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Team: %{customdata[1]}<br>"
            "Last YTD FB velo: %{y:.2f} mph<br>"
            "Average Peak Power [W]: %{x:.2f} W<br><br>"
            "FB records: %{customdata[2]} · YTD as of %{customdata[5]}<br>"
            "Power jumps: %{customdata[3]} across %{customdata[4]} test dates · "
            "%{customdata[6]}–%{customdata[7]}<extra></extra>"
        ),
    ))

    stats = power_pitch_correlation_stats(summary)
    if stats is not None:
        r, r2, slope, intercept = stats
        x_range = np.linspace(
            summary["avg_peak_power"].min(),
            summary["avg_peak_power"].max(), 100
        )
        fig.add_trace(go.Scatter(
            x=x_range, y=slope * x_range + intercept,
            mode="lines", line={"color": NAVY_MID, "width": 2.5, "dash": "dash"},
            hoverinfo="skip",
        ))
        fig.add_annotation(
            text=f"r = {r:+.2f} · R² = {r2:.2f}",
            x=0.02, y=0.98, xref="paper", yref="paper",
            xanchor="left", yanchor="top", showarrow=False,
            font={"color": NAVY, "size": 13}, bgcolor="#FFFFFF",
            bordercolor=BORDER, borderwidth=1, borderpad=7,
        )
        if power_lookup is not None and np.isfinite(power_lookup):
            predicted = slope * float(power_lookup) + intercept
            fig.add_vline(x=float(power_lookup), line_color=TEAL, line_width=1.5, line_dash="dot")
            fig.add_hline(y=predicted, line_color=TEAL, line_width=1.5, line_dash="dot")
            fig.add_trace(go.Scatter(
                x=[float(power_lookup)], y=[predicted], mode="markers",
                marker={"size": 15, "color": TEAL, "symbol": "diamond",
                        "line": {"color": "#FFFFFF", "width": 2}},
                hovertemplate=(
                    "<b>Peak Power lookup</b><br>Average Peak Power [W]: %{x:.1f} W<br>"
                    "Estimated last YTD FB velo: %{y:.2f} mph<extra></extra>"
                ),
            ))

    fig.update_xaxes(
        title="Average Peak Power [W]", showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Last YTD FB velocity (mph)", showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 560)

# -----------------------------------------------------------------------------
# SELECTED DEFENSIVE / BASERUNNING RELATIONSHIPS
# -----------------------------------------------------------------------------
def build_peak_power_rel_outcome_summary(
    jump_power: pd.DataFrame,
    outcome_df: pd.DataFrame,
    outcome_col: str,
    start_date,
    end_date,
    team_filter: str,
    min_power_jumps: int,
) -> pd.DataFrame:
    """Match one current S-T-D outcome to mean in-window Peak Power / BM."""
    columns = [
        "athlete", "team", "avg_peak_power_rel", "power_jumps", "power_test_dates",
        "first_power_date", "last_power_date", outcome_col,
    ]
    if jump_power.empty or outcome_df.empty or outcome_col not in outcome_df.columns:
        return pd.DataFrame(columns=columns)

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    team_lookup = (
        jump_power.sort_values("date")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
    )
    power_window = jump_power[
        (jump_power["date"] >= start)
        & (jump_power["date"] <= end)
        & jump_power["peak_power_rel"].notna()
    ].copy()
    if power_window.empty:
        return pd.DataFrame(columns=columns)

    power_summary = (
        power_window.groupby("name_key", as_index=False)
        .agg(
            athlete=("athlete", "first"),
            avg_peak_power_rel=("peak_power_rel", "mean"),
            power_jumps=("peak_power_rel", "count"),
            power_test_dates=("date", "nunique"),
            first_power_date=("date", "min"),
            last_power_date=("date", "max"),
        )
        .merge(team_lookup, on="name_key", how="left")
    )
    outcome = outcome_df[["name_key", outcome_col]].dropna().drop_duplicates("name_key")
    summary = power_summary.merge(outcome, on="name_key", how="inner")
    summary = summary[
        summary["power_jumps"] >= max(1, int(min_power_jumps))
    ].copy()
    if team_filter != "All Teams":
        summary = summary[summary["team"] == team_filter].copy()
    return summary.sort_values(outcome_col, ascending=False).reset_index(drop=True)


def peak_power_rel_outcome_stats(summary: pd.DataFrame, outcome_col: str):
    if len(summary) < 2:
        return None
    x = pd.to_numeric(summary["avg_peak_power_rel"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(summary[outcome_col], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 2 or np.isclose(np.std(x), 0) or np.isclose(np.std(y), 0):
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return r, r * r, float(slope), float(intercept)


def build_peak_power_rel_outcome_scatter(
    summary: pd.DataFrame,
    outcome_col: str,
    outcome_label: str,
    outcome_unit: str,
    show_labels: bool,
    lookup_value: float | None,
) -> go.Figure:
    fig = go.Figure()
    if summary.empty:
        fig.add_annotation(
            text="No matched players meet the selected window and minimum-data rules.",
            showarrow=False, font={"size": 15, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 560)

    customdata = np.column_stack([
        summary["athlete"], summary["team"], summary["power_jumps"],
        summary["power_test_dates"], summary["first_power_date"].map(fmt_date),
        summary["last_power_date"].map(fmt_date),
    ])
    fig.add_trace(go.Scatter(
        x=summary["avg_peak_power_rel"], y=summary[outcome_col],
        mode="markers+text" if show_labels else "markers",
        text=summary["athlete"] if show_labels else None,
        textposition="top center", textfont={"size": 10, "color": NAVY},
        marker={"size": 13, "color": TEAL, "opacity": 0.88, "line": {"color": "#FFFFFF", "width": 2}},
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Team: %{customdata[1]}<br>"
            f"{outcome_label}: %{{y:.2f}} {outcome_unit}<br>"
            "Mean Peak Power / BM: %{x:.2f} W/kg<br><br>"
            "Power jumps: %{customdata[2]} across %{customdata[3]} test dates · "
            "%{customdata[4]}–%{customdata[5]}<extra></extra>"
        ),
    ))
    stats = peak_power_rel_outcome_stats(summary, outcome_col)
    if stats is not None:
        r, r2, slope, intercept = stats
        x_range = np.linspace(summary["avg_peak_power_rel"].min(), summary["avg_peak_power_rel"].max(), 100)
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
        if lookup_value is not None and np.isfinite(lookup_value):
            predicted = slope * float(lookup_value) + intercept
            fig.add_vline(x=float(lookup_value), line_color=ACCENT_RED, line_width=1.5, line_dash="dot")
            fig.add_hline(y=predicted, line_color=ACCENT_RED, line_width=1.5, line_dash="dot")
            fig.add_trace(go.Scatter(
                x=[float(lookup_value)], y=[predicted], mode="markers",
                marker={"size": 15, "color": ACCENT_RED, "symbol": "diamond", "line": {"color": "#FFFFFF", "width": 2}},
                hovertemplate=(
                    "<b>Peak Power / BM lookup</b><br>Peak Power / BM: %{x:.1f} W/kg<br>"
                    f"Estimated {outcome_label}: %{{y:.2f}} {outcome_unit}<extra></extra>"
                ),
            ))
    fig.update_xaxes(
        title="Mean Peak Power / BM (W/kg)", showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER, tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title=f"{outcome_label}{f' ({outcome_unit})' if outcome_unit else ''}",
        showgrid=True, gridcolor=GRID, zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 560)


def render_selected_peak_power_rel_tab(
    summary: pd.DataFrame,
    *,
    outcome_col: str,
    outcome_label: str,
    outcome_unit: str,
    tab_key: str,
    default_lookup: float,
    default_bucket_width: float,
) -> None:
    stats = peak_power_rel_outcome_stats(summary, outcome_col)
    n_players = len(summary)
    r_text = f"{stats[0]:+.2f}" if stats is not None else "—"
    r2_text = f"{stats[1]:.2f}" if stats is not None else "—"
    mean_outcome = summary[outcome_col].mean() if n_players else np.nan
    mean_power = summary["avg_peak_power_rel"].mean() if n_players else np.nan

    top_cols = st.columns(4)
    for column, values in zip(top_cols, [
        ("Players", str(n_players), BLUE),
        ("Correlation", r_text, ACCENT_RED),
        ("R²", r2_text, NAVY_MID),
        ("Mean Peak Power / BM", f"{fmt(mean_power)} W/kg", GREEN),
    ]):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    st.caption(
        "The defensive/baserunning outcome is a current season-to-date snapshot. "
        "Peak Power / BM is the player's mean value inside the selected dashboard date window."
    )

    lookup_key = f"{tab_key}_lookup"
    labels_key = f"{tab_key}_show_labels"
    bucket_stat_key = f"{tab_key}_bucket_power_stat"
    bucket_width_key = f"{tab_key}_bucket_width"
    lookup_value = float(st.session_state.get(lookup_key, default_lookup))
    show_labels = bool(st.session_state.get(labels_key, False))
    bucket_stat = st.session_state.get(bucket_stat_key, "Mean")
    bucket_width = float(st.session_state.get(bucket_width_key, default_bucket_width))

    with st.container(border=True):
        st.subheader(f"Peak Power / BM × {outcome_label}", anchor=False)
        st.plotly_chart(
            build_peak_power_rel_outcome_scatter(
                summary, outcome_col, outcome_label, outcome_unit, show_labels, lookup_value,
            ),
            use_container_width=True, config={"displayModeBar": False},
            key=f"{tab_key}_scatter_{team_filter}_{start_date}_{end_date}",
        )
        st.toggle("Show player labels", value=False, key=labels_key)

    estimated = stats[2] * lookup_value + stats[3] if stats is not None else np.nan
    with st.container(border=True):
        st.subheader("Peak Power / BM Lookup", anchor=False)
        left, right = st.columns(2)
        with left:
            st.markdown("<div class='metric-label'>Peak Power / BM</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='lookup-value' style='color:#0A1F44;'>{fmt(lookup_value, 1)} W/kg</div>", unsafe_allow_html=True)
        with right:
            st.markdown(f"<div class='metric-label'>Estimated {html.escape(outcome_label)}</div>", unsafe_allow_html=True)
            unit_suffix = f" {outcome_unit}" if outcome_unit else ""
            value = f"{fmt(estimated)}{unit_suffix}" if pd.notna(estimated) else "—"
            st.markdown(f"<div class='lookup-value' style='color:#0D7E8A;'>{value}</div>", unsafe_allow_html=True)
        st.number_input(
            "Peak Power / BM lookup", min_value=0.0, step=0.5, value=float(default_lookup),
            format="%.1f", key=lookup_key,
        )

    with st.container(border=True):
        st.subheader(f"{bucket_stat} Peak Power / BM by {outcome_label} Bucket", anchor=False)
        st.plotly_chart(
            build_output_bucket_chart(
                df=summary,
                output_col=outcome_col,
                testing_col="avg_peak_power_rel",
                bucket_width=bucket_width,
                output_bucket_label=f"{outcome_label} bucket",
                testing_metric_label="Peak Power / BM",
                output_axis_title=f"{outcome_label} bucket",
                testing_axis_title=f"{bucket_stat} Peak Power / BM (W/kg)",
                output_unit=outcome_unit,
                empty_text=f"No matched players are available for {outcome_label} buckets.",
                color=TEAL,
                testing_stat=bucket_stat,
            ),
            use_container_width=True, config={"displayModeBar": False},
            key=f"{tab_key}_bucket_chart_{team_filter}_{start_date}_{end_date}_{bucket_stat}_{bucket_width}",
        )
        c1, c2 = st.columns(2)
        with c1:
            width_options = [0.02, 0.05, 0.10] if default_bucket_width < 0.2 else [0.5, 1.0, 2.0]
            st.selectbox(
                f"{outcome_label} bucket width", width_options,
                index=width_options.index(default_bucket_width) if default_bucket_width in width_options else 0,
                key=bucket_width_key,
            )
        with c2:
            st.radio("Peak Power / BM statistic", ["Mean", "Median"], horizontal=True, key=bucket_stat_key)

    with st.container(border=True):
        st.subheader("Matched Players", anchor=False)
        if summary.empty:
            st.info("No matched players are available for the selected filters.")
        else:
            display = summary[[
                "athlete", "team", "avg_peak_power_rel", outcome_col,
                "power_jumps", "power_test_dates", "first_power_date", "last_power_date",
            ]].copy()
            display.columns = [
                "Player", "Team", "Mean Peak Power / BM", outcome_label,
                "Power Jumps", "Power Test Dates", "First Power Date", "Last Power Date",
            ]
            display["First Power Date"] = display["First Power Date"].map(fmt_date)
            display["Last Power Date"] = display["Last Power Date"].map(fmt_date)
            display = display.sort_values(outcome_label, ascending=False)
            st.dataframe(
                display, hide_index=True, use_container_width=True,
                height=min(680, 44 + 36 * (len(display) + 1)),
                column_config={
                    "Mean Peak Power / BM": st.column_config.NumberColumn(format="%.2f W/kg"),
                    outcome_label: st.column_config.NumberColumn(format="%.2f"),
                },
            )
            csv_download_button(
                display,
                f"Download {outcome_label} relationship CSV",
                f"{tab_key}_relationship.csv",
                f"download_{tab_key}_relationship",
            )



# -----------------------------------------------------------------------------
# SPRINT SPEED × nBSR — BOTH FROM BASERUNNING SOURCE
# -----------------------------------------------------------------------------
def build_sprint_nbsr_summary(
    jump: pd.DataFrame,
    outcome_df: pd.DataFrame,
    team_filter: str,
) -> pd.DataFrame:
    """Match baserunning-sheet Sprint Speed directly to baserunning-sheet nBSR.

    Both performance variables are current season-to-date snapshot values from
    the same baserunning Google Sheet. Jump Data is used only to attach each
    player's current team for the dashboard team filter; it is not used to
    calculate sprint speed for this relationship.
    """
    columns = ["athlete", "team", "baserunning_sprint_speed", "nbsr"]
    required = {"name_key", "athlete", "baserunning_sprint_speed", "nbsr"}
    if jump.empty or outcome_df.empty or not required.issubset(outcome_df.columns):
        return pd.DataFrame(columns=columns)

    team_lookup = (
        jump.sort_values("date")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
    )

    summary = (
        outcome_df[["name_key", "athlete", "baserunning_sprint_speed", "nbsr"]]
        .dropna(subset=["baserunning_sprint_speed", "nbsr"])
        .drop_duplicates("name_key")
        .merge(team_lookup, on="name_key", how="left")
    )
    summary["team"] = summary["team"].fillna("Unassigned")
    if team_filter != "All Teams":
        summary = summary[summary["team"] == team_filter].copy()

    return summary[columns].sort_values("nbsr", ascending=False).reset_index(drop=True)


def sprint_nbsr_stats(summary: pd.DataFrame):
    if len(summary) < 2:
        return None
    x = pd.to_numeric(
        summary["baserunning_sprint_speed"], errors="coerce"
    ).to_numpy(dtype=float)
    y = pd.to_numeric(summary["nbsr"], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 2 or np.isclose(np.std(x), 0) or np.isclose(np.std(y), 0):
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return r, r * r, float(slope), float(intercept)


def build_sprint_nbsr_scatter(summary: pd.DataFrame, show_labels: bool) -> go.Figure:
    fig = go.Figure()
    if summary.empty:
        fig.add_annotation(
            text="No matched players have both Sprint Speed and nBSR in the baserunning source.",
            showarrow=False, font={"size": 15, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 560)

    customdata = np.column_stack([summary["athlete"], summary["team"]])
    fig.add_trace(go.Scatter(
        x=summary["baserunning_sprint_speed"], y=summary["nbsr"],
        mode="markers+text" if show_labels else "markers",
        text=summary["athlete"] if show_labels else None,
        textposition="top center", textfont={"size": 10, "color": NAVY},
        marker={"size": 13, "color": TEAL, "opacity": 0.88,
                "line": {"color": "#FFFFFF", "width": 2}},
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Team: %{customdata[1]}<br>"
            "Baserunning Sprint Speed: %{x:.2f} ft/s<br>"
            "nBSR: %{y:.2f}<extra></extra>"
        ),
    ))
    stats = sprint_nbsr_stats(summary)
    if stats is not None:
        r, r2, slope, intercept = stats
        x_range = np.linspace(
            summary["baserunning_sprint_speed"].min(),
            summary["baserunning_sprint_speed"].max(), 100,
        )
        fig.add_trace(go.Scatter(
            x=x_range, y=slope * x_range + intercept, mode="lines",
            line={"color": NAVY_MID, "width": 2.5, "dash": "dash"},
            hoverinfo="skip",
        ))
        fig.add_annotation(
            text=f"r = {r:+.2f} · R² = {r2:.2f}",
            x=0.02, y=0.98, xref="paper", yref="paper",
            xanchor="left", yanchor="top", showarrow=False,
            font={"color": NAVY, "size": 13}, bgcolor="#FFFFFF",
            bordercolor=BORDER, borderwidth=1, borderpad=7,
        )
    fig.update_xaxes(
        title="Sprint Speed from baserunning sheet (ft/s)",
        showgrid=True, gridcolor=GRID, zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="nBSR", showgrid=True, gridcolor=GRID, zeroline=False,
        linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 560)


def render_sprint_nbsr_tab(summary: pd.DataFrame) -> None:
    stats = sprint_nbsr_stats(summary)
    n_players = len(summary)
    r_text = f"{stats[0]:+.2f}" if stats is not None else "—"
    r2_text = f"{stats[1]:.2f}" if stats is not None else "—"
    mean_sprint = (
        summary["baserunning_sprint_speed"].mean() if n_players else np.nan
    )

    top_cols = st.columns(4)
    for column, values in zip(top_cols, [
        ("Players", str(n_players), BLUE),
        ("Correlation", r_text, ACCENT_RED),
        ("R²", r2_text, NAVY_MID),
        ("Mean Sprint Speed", f"{fmt(mean_sprint)} ft/s", GREEN),
    ]):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    st.caption(
        "Both Sprint Speed and nBSR come directly from the current baserunning "
        "Google Sheet snapshot. The Velo Trends date window does not alter these "
        "two values; Jump Data is used only for the current-team filter."
    )

    labels_key = "sprint_nbsr_show_labels"
    bucket_stat_key = "sprint_nbsr_bucket_stat"
    bucket_width_key = "sprint_nbsr_bucket_width"
    show_labels = bool(st.session_state.get(labels_key, False))
    bucket_stat = st.session_state.get(bucket_stat_key, "Mean")
    bucket_width = float(st.session_state.get(bucket_width_key, 1.0))

    with st.container(border=True):
        st.subheader("Sprint Speed × nBSR", anchor=False)
        st.plotly_chart(
            build_sprint_nbsr_scatter(summary, show_labels),
            use_container_width=True, config={"displayModeBar": False},
            key=f"sprint_nbsr_scatter_{team_filter}_{show_labels}",
        )
        st.toggle("Show player labels", value=False, key=labels_key)

    with st.container(border=True):
        st.subheader(f"{bucket_stat} Sprint Speed by nBSR Bucket", anchor=False)
        st.plotly_chart(
            build_output_bucket_chart(
                df=summary,
                output_col="nbsr",
                testing_col="baserunning_sprint_speed",
                bucket_width=bucket_width,
                output_bucket_label="nBSR bucket",
                testing_metric_label="Sprint Speed",
                output_axis_title="nBSR bucket",
                testing_axis_title=f"{bucket_stat} sprint speed (ft/s)",
                output_unit="",
                empty_text="No matched players are available for nBSR buckets.",
                color=TEAL,
                testing_stat=bucket_stat,
            ),
            use_container_width=True, config={"displayModeBar": False},
            key=f"sprint_nbsr_bucket_{team_filter}_{bucket_stat}_{bucket_width}",
        )
        c1, c2 = st.columns(2)
        with c1:
            st.selectbox(
                "nBSR bucket width", [0.5, 1.0, 2.0], index=1,
                key=bucket_width_key,
            )
        with c2:
            st.radio(
                "Sprint-speed statistic", ["Mean", "Median"],
                horizontal=True, key=bucket_stat_key,
            )

    with st.container(border=True):
        st.subheader("Matched Players", anchor=False)
        if summary.empty:
            st.info("No matched players are available for the selected team filter.")
        else:
            display = summary[[
                "athlete", "team", "baserunning_sprint_speed", "nbsr",
            ]].copy()
            display.columns = ["Player", "Team", "Sprint Speed", "nBSR"]
            display = display.sort_values("nBSR", ascending=False)
            st.dataframe(
                display, hide_index=True, use_container_width=True,
                height=min(680, 44 + 36 * (len(display) + 1)),
                column_config={
                    "Sprint Speed": st.column_config.NumberColumn(format="%.2f ft/s"),
                    "nBSR": st.column_config.NumberColumn(format="%.2f"),
                },
            )
            csv_download_button(
                display,
                "Download Sprint Speed × nBSR CSV",
                "sprint_speed_nbsr_relationship.csv",
                "download_sprint_nbsr_relationship",
            )



# -----------------------------------------------------------------------------
# ADDITIONAL BASERUNNING RELATIONSHIPS
# -----------------------------------------------------------------------------
def build_baserunning_sprint_outcome_summary(
    jump: pd.DataFrame,
    outcome_df: pd.DataFrame,
    outcome_col: str,
    team_filter: str,
) -> pd.DataFrame:
    """Match baserunning-sheet Sprint Speed to another baserunning-sheet outcome."""
    columns = ["athlete", "team", "baserunning_sprint_speed", outcome_col]
    required = {"name_key", "athlete", "baserunning_sprint_speed", outcome_col}
    if jump.empty or outcome_df.empty or not required.issubset(outcome_df.columns):
        return pd.DataFrame(columns=columns)

    team_lookup = (
        jump.sort_values("date")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
    )
    summary = (
        outcome_df[["name_key", "athlete", "baserunning_sprint_speed", outcome_col]]
        .dropna(subset=["baserunning_sprint_speed", outcome_col])
        .drop_duplicates("name_key")
        .merge(team_lookup, on="name_key", how="left")
    )
    summary["team"] = summary["team"].fillna("Unassigned")
    if team_filter != "All Teams":
        summary = summary[summary["team"] == team_filter].copy()
    return summary[columns].sort_values(outcome_col, ascending=False).reset_index(drop=True)


def sprint_outcome_stats(summary: pd.DataFrame, outcome_col: str):
    if len(summary) < 2:
        return None
    x = pd.to_numeric(summary["baserunning_sprint_speed"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(summary[outcome_col], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 2 or np.isclose(np.std(x), 0) or np.isclose(np.std(y), 0):
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return r, r * r, float(slope), float(intercept)


def build_sprint_outcome_scatter(
    summary: pd.DataFrame,
    outcome_col: str,
    outcome_label: str,
    show_labels: bool,
) -> go.Figure:
    fig = go.Figure()
    if summary.empty:
        fig.add_annotation(
            text=f"No matched players have both Sprint Speed and {outcome_label}.",
            showarrow=False, font={"size": 15, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 560)

    customdata = np.column_stack([summary["athlete"], summary["team"]])
    fig.add_trace(go.Scatter(
        x=summary["baserunning_sprint_speed"], y=summary[outcome_col],
        mode="markers+text" if show_labels else "markers",
        text=summary["athlete"] if show_labels else None,
        textposition="top center", textfont={"size": 10, "color": NAVY},
        marker={"size": 13, "color": TEAL, "opacity": 0.88,
                "line": {"color": "#FFFFFF", "width": 2}},
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Team: %{customdata[1]}<br>"
            "Sprint Speed: %{x:.2f} ft/s<br>"
            f"{outcome_label}: %{{y:.2f}} runs<extra></extra>"
        ),
    ))
    stats = sprint_outcome_stats(summary, outcome_col)
    if stats is not None:
        r, r2, slope, intercept = stats
        x_range = np.linspace(
            summary["baserunning_sprint_speed"].min(),
            summary["baserunning_sprint_speed"].max(), 100,
        )
        fig.add_trace(go.Scatter(
            x=x_range, y=slope * x_range + intercept, mode="lines",
            line={"color": NAVY_MID, "width": 2.5, "dash": "dash"}, hoverinfo="skip",
        ))
        fig.add_annotation(
            text=f"r = {r:+.2f} · R² = {r2:.2f}",
            x=0.02, y=0.98, xref="paper", yref="paper",
            xanchor="left", yanchor="top", showarrow=False,
            font={"color": NAVY, "size": 13}, bgcolor="#FFFFFF",
            bordercolor=BORDER, borderwidth=1, borderpad=7,
        )
    fig.update_xaxes(
        title="Sprint Speed from baserunning sheet (ft/s)",
        showgrid=True, gridcolor=GRID, zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title=f"{outcome_label} (runs)", showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 560)


def render_sprint_outcome_tab(
    summary: pd.DataFrame,
    *,
    outcome_col: str,
    outcome_label: str,
    tab_key: str,
    default_bucket_width: float = 1.0,
) -> None:
    stats = sprint_outcome_stats(summary, outcome_col)
    n_players = len(summary)
    r_text = f"{stats[0]:+.2f}" if stats is not None else "—"
    r2_text = f"{stats[1]:.2f}" if stats is not None else "—"
    mean_sprint = summary["baserunning_sprint_speed"].mean() if n_players else np.nan

    top_cols = st.columns(4)
    for column, values in zip(top_cols, [
        ("Players", str(n_players), BLUE),
        ("Correlation", r_text, ACCENT_RED),
        ("R²", r2_text, NAVY_MID),
        ("Mean Sprint Speed", f"{fmt(mean_sprint)} ft/s", GREEN),
    ]):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    st.caption(
        f"Both Sprint Speed and {outcome_label} come directly from the current "
        "baserunning Google Sheet snapshot. Jump Data is used only for the current-team filter."
    )

    labels_key = f"{tab_key}_show_labels"
    bucket_stat_key = f"{tab_key}_bucket_stat"
    bucket_width_key = f"{tab_key}_bucket_width"
    show_labels = bool(st.session_state.get(labels_key, False))
    bucket_stat = st.session_state.get(bucket_stat_key, "Mean")
    bucket_width = float(st.session_state.get(bucket_width_key, default_bucket_width))

    with st.container(border=True):
        st.subheader(f"Sprint Speed × {outcome_label}", anchor=False)
        st.plotly_chart(
            build_sprint_outcome_scatter(summary, outcome_col, outcome_label, show_labels),
            use_container_width=True, config={"displayModeBar": False},
            key=f"{tab_key}_scatter_{team_filter}_{show_labels}",
        )
        st.toggle("Show player labels", value=False, key=labels_key)

    with st.container(border=True):
        st.subheader(f"{bucket_stat} Sprint Speed by {outcome_label} Bucket", anchor=False)
        st.plotly_chart(
            build_output_bucket_chart(
                df=summary,
                output_col=outcome_col,
                testing_col="baserunning_sprint_speed",
                bucket_width=bucket_width,
                output_bucket_label=f"{outcome_label} bucket",
                testing_metric_label="Sprint Speed",
                output_axis_title=f"{outcome_label} bucket",
                testing_axis_title=f"{bucket_stat} sprint speed (ft/s)",
                output_unit="runs",
                empty_text=f"No matched players are available for {outcome_label} buckets.",
                color=TEAL,
                testing_stat=bucket_stat,
            ),
            use_container_width=True, config={"displayModeBar": False},
            key=f"{tab_key}_bucket_{team_filter}_{bucket_stat}_{bucket_width}",
        )
        c1, c2 = st.columns(2)
        with c1:
            st.selectbox(
                f"{outcome_label} bucket width", [0.25, 0.5, 1.0, 2.0],
                index=2 if default_bucket_width == 1.0 else 1,
                key=bucket_width_key,
            )
        with c2:
            st.radio(
                "Sprint-speed statistic", ["Mean", "Median"],
                horizontal=True, key=bucket_stat_key,
            )

    with st.container(border=True):
        st.subheader("Matched Players", anchor=False)
        if summary.empty:
            st.info("No matched players are available for the selected team filter.")
        else:
            display = summary[[
                "athlete", "team", "baserunning_sprint_speed", outcome_col,
            ]].copy()
            display.columns = ["Player", "Team", "Sprint Speed", outcome_label]
            display = display.sort_values(outcome_label, ascending=False)
            st.dataframe(
                display, hide_index=True, use_container_width=True,
                height=min(680, 44 + 36 * (len(display) + 1)),
                column_config={
                    "Sprint Speed": st.column_config.NumberColumn(format="%.2f ft/s"),
                    outcome_label: st.column_config.NumberColumn(format="%.2f runs"),
                },
            )
            csv_download_button(
                display,
                f"Download Sprint Speed × {outcome_label} CSV",
                f"{tab_key}_relationship.csv",
                f"download_{tab_key}_relationship",
            )


def build_sprint_power_nbsr_model_summary(
    jump_power: pd.DataFrame,
    outcome_df: pd.DataFrame,
    start_date,
    end_date,
    team_filter: str,
    min_power_jumps: int,
) -> pd.DataFrame:
    """Build one row/player for nBSR ~ Sprint Speed + mean in-window Relative Peak Power."""
    base = build_peak_power_rel_outcome_summary(
        jump_power=jump_power,
        outcome_df=outcome_df,
        outcome_col="nbsr",
        start_date=start_date,
        end_date=end_date,
        team_filter=team_filter,
        min_power_jumps=min_power_jumps,
    )
    columns = [
        "athlete", "team", "baserunning_sprint_speed", "avg_peak_power_rel",
        "nbsr", "power_jumps", "power_test_dates", "first_power_date", "last_power_date",
    ]
    if base.empty or "baserunning_sprint_speed" not in outcome_df.columns:
        return pd.DataFrame(columns=columns)
    sprint_lookup = (
        outcome_df[["name_key", "baserunning_sprint_speed"]]
        .dropna(subset=["baserunning_sprint_speed"])
        .drop_duplicates("name_key")
    )
    summary = base.merge(sprint_lookup, on="name_key", how="inner")
    summary = summary.dropna(subset=["baserunning_sprint_speed", "avg_peak_power_rel", "nbsr"])
    return summary[columns].sort_values("nbsr", ascending=False).reset_index(drop=True)


def fit_sprint_power_nbsr_model(summary: pd.DataFrame):
    """Fit nBSR ~ Sprint Speed + Relative Peak Power with NumPy OLS."""
    required = {"baserunning_sprint_speed", "avg_peak_power_rel", "nbsr"}
    if len(summary) < 4 or not required.issubset(summary.columns):
        return None
    data = summary[list(required)].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < 4:
        return None
    sprint = data["baserunning_sprint_speed"].to_numpy(dtype=float)
    power = data["avg_peak_power_rel"].to_numpy(dtype=float)
    y = data["nbsr"].to_numpy(dtype=float)
    if np.isclose(np.std(sprint), 0) or np.isclose(np.std(power), 0) or np.isclose(np.std(y), 0):
        return None

    X = np.column_stack([np.ones(len(data)), sprint, power])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    ss_res = float(np.sum((y - pred) ** 2))
    if np.isclose(ss_tot, 0):
        return None
    r2 = 1.0 - ss_res / ss_tot
    n = len(y)
    p = 2
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / (n - p - 1) if n > p + 1 else np.nan

    std_y = float(np.std(y, ddof=0))
    std_beta_sprint = float(beta[1] * np.std(sprint, ddof=0) / std_y)
    std_beta_power = float(beta[2] * np.std(power, ddof=0) / std_y)

    r2_sprint_only = float(np.corrcoef(sprint, y)[0, 1] ** 2)
    r2_power_only = float(np.corrcoef(power, y)[0, 1] ** 2)
    inc_r2_sprint = max(0.0, float(r2 - r2_power_only))
    inc_r2_power = max(0.0, float(r2 - r2_sprint_only))

    return {
        "n": n,
        "intercept": float(beta[0]),
        "sprint_coef": float(beta[1]),
        "power_coef": float(beta[2]),
        "r2": float(r2),
        "adj_r2": float(adj_r2),
        "std_beta_sprint": std_beta_sprint,
        "std_beta_power": std_beta_power,
        "incremental_r2_sprint": inc_r2_sprint,
        "incremental_r2_power": inc_r2_power,
    }


def build_sprint_power_nbsr_model_scatter(summary: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if summary.empty:
        fig.add_annotation(
            text="No players have nBSR, Sprint Speed, and qualifying Relative Peak Power data.",
            showarrow=False, font={"size": 15, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 560)

    customdata = np.column_stack([
        summary["athlete"], summary["team"], summary["avg_peak_power_rel"],
    ])
    fig.add_trace(go.Scatter(
        x=summary["baserunning_sprint_speed"],
        y=summary["nbsr"],
        mode="markers",
        marker={
            "size": 14,
            "color": summary["avg_peak_power_rel"],
            "colorscale": "Viridis",
            "showscale": True,
            "colorbar": {"title": "Rel PP<br>W/kg"},
            "opacity": 0.88,
            "line": {"color": "#FFFFFF", "width": 1.5},
        },
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Team: %{customdata[1]}<br>"
            "Sprint Speed: %{x:.2f} ft/s<br>Relative Peak Power: %{customdata[2]:.2f} W/kg<br>"
            "nBSR: %{y:.2f} runs<extra></extra>"
        ),
    ))
    fig.update_xaxes(
        title="Sprint Speed from baserunning sheet (ft/s)", showgrid=True,
        gridcolor=GRID, zeroline=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="nBSR (runs)", showgrid=True, gridcolor=GRID, zeroline=False,
        linecolor=BORDER, tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    return base_figure_layout(fig, 560)


def render_sprint_power_nbsr_model_tab(summary: pd.DataFrame) -> None:
    model = fit_sprint_power_nbsr_model(summary)
    n_players = len(summary)
    r2_text = f"{model['r2']:.2f}" if model is not None else "—"
    adj_r2_text = f"{model['adj_r2']:.2f}" if model is not None else "—"
    mean_nbsr = summary["nbsr"].mean() if n_players else np.nan

    top_cols = st.columns(4)
    for column, values in zip(top_cols, [
        ("Players", str(n_players), BLUE),
        ("Model R²", r2_text, ACCENT_RED),
        ("Adjusted R²", adj_r2_text, NAVY_MID),
        ("Mean nBSR", f"{fmt(mean_nbsr)} runs", GREEN),
    ]):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    st.caption(
        "Multiple regression: nBSR ~ Sprint Speed + Relative Peak Power. Sprint Speed and nBSR "
        "come from the current baserunning sheet; Relative Peak Power is the player's mean Peak "
        "Power / BM inside the selected Velo Trends date window."
    )

    if model is None:
        st.info("The combined model could not be fit for the current filters and minimum-data rules.")
        return

    with st.container(border=True):
        st.subheader("Combined Model", anchor=False)
        st.plotly_chart(
            build_sprint_power_nbsr_model_scatter(summary),
            use_container_width=True, config={"displayModeBar": False},
            key=f"sprint_power_nbsr_model_scatter_{team_filter}_{start_date}_{end_date}",
        )
        st.caption("Point color represents Relative Peak Power (W/kg).")

    with st.container(border=True):
        st.subheader("Model Contributions", anchor=False)
        contribution = pd.DataFrame({
            "Predictor": ["Sprint Speed", "Relative Peak Power"],
            "Coefficient": [model["sprint_coef"], model["power_coef"]],
            "Standardized Beta": [model["std_beta_sprint"], model["std_beta_power"]],
            "Incremental R²": [model["incremental_r2_sprint"], model["incremental_r2_power"]],
        })
        st.dataframe(
            contribution, hide_index=True, use_container_width=True,
            column_config={
                "Coefficient": st.column_config.NumberColumn(format="%+.3f"),
                "Standardized Beta": st.column_config.NumberColumn(format="%+.3f"),
                "Incremental R²": st.column_config.NumberColumn(format="%.3f"),
            },
        )
        st.caption(
            "Incremental R² is the additional variance explained by that predictor after the other predictor is already in the model."
        )
        st.code(
            f"nBSR = {model['intercept']:+.3f} "
            f"{model['sprint_coef']:+.3f} × Sprint Speed "
            f"{model['power_coef']:+.3f} × Relative Peak Power"
        )


# -----------------------------------------------------------------------------
# PASSWORD AUTHENTICATION
# -----------------------------------------------------------------------------
def require_password() -> None:
    """Block the dashboard until the correct Streamlit secret is entered."""
    try:
        configured_password = st.secrets.get("APP_PASSWORD")
    except Exception:
        configured_password = None

    # Optional local fallback: APP_PASSWORD environment variable.
    if not configured_password:
        configured_password = os.environ.get("APP_PASSWORD")

    # Fail closed: never expose the app if the password was not configured.
    if not configured_password:
        st.error(
            "APP_PASSWORD is not configured. Add APP_PASSWORD to this app's "
            "Streamlit Secrets before using the dashboard."
        )
        st.stop()

    if st.session_state.get("password_correct", False):
        return

    def _check_password() -> None:
        entered_password = str(st.session_state.get("app_password_input", ""))
        if hmac.compare_digest(entered_password, str(configured_password)):
            st.session_state["password_correct"] = True
            st.session_state.pop("app_password_input", None)
        else:
            st.session_state["password_correct"] = False

    st.markdown(
        "<div style='max-width:520px;margin:10vh auto 0;'>",
        unsafe_allow_html=True,
    )
    st.title("Performance × CI")
    st.write("Enter the app password to continue.")
    with st.form("app_password_form", clear_on_submit=False):
        st.text_input(
            "Password",
            type="password",
            key="app_password_input",
        )
        submitted = st.form_submit_button("Log in", use_container_width=True, type="primary")

    if submitted:
        _check_password()
        if st.session_state.get("password_correct", False):
            st.rerun()

    if st.session_state.get("password_correct") is False:
        st.error("Incorrect password.")

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# -----------------------------------------------------------------------------
# APP
# -----------------------------------------------------------------------------
require_password()

# The dashboard intentionally has no sidebar. Global data filters stay compact at
# the top of the page; chart-specific controls are rendered directly below the
# chart or lookup card they affect.
title_col, refresh_col = st.columns([5, 1])
with title_col:
    st.markdown(
        "<h1 style='margin:0;color:#0A1F44;font-size:37px;font-weight:800;'>Performance × CI</h1>"
        "<div style='color:#667085;font-size:12px;margin-top:4px;'>Defense integration build · 2026-08-13 v5</div>",
        unsafe_allow_html=True,
    )
with refresh_col:
    refresh = st.button("↻ Refresh data", use_container_width=True, type="primary")

if refresh:
    load_source_data.clear()

try:
    (
        jump, jump_power, velo, bat, pinch, sprint, exit_velo,
        infield_defense, baserunning_defense, status,
    ) = load_source_data()
except Exception as exc:
    st.error(f"Could not load data. {exc}")
    st.stop()

all_dates = pd.concat([
    jump["date"], jump_power["date"], velo["date"], bat["month"],
    pinch["date"], sprint["date"],
], ignore_index=True).dropna()
min_date = all_dates.min().date()
max_date = all_dates.max().date()
default_start = max(pd.Timestamp(year=max_date.year, month=1, day=1).date(), min_date)

available_teams = (
    set(jump["team"].dropna().unique().tolist())
    | set(jump_power["team"].dropna().unique().tolist())
    | set(bat["team"].dropna().unique().tolist())
    | set(pinch["team"].dropna().unique().tolist())
    | set(sprint["team"].dropna().unique().tolist())
    | set(exit_velo["team"].dropna().unique().tolist())
)
teams = ["All Teams"] + [team for team in INCLUDED_TEAMS if team in available_teams]

with st.container(border=True):
    filter_date_col, filter_team_col = st.columns([2, 1])
    with filter_date_col:
        selected_dates = st.date_input(
            "Date range",
            value=(default_start, max_date),
            min_value=min_date,
            max_value=max_date,
            key="global_date_range",
        )
        if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
            start_date, end_date = selected_dates
        else:
            start_date = end_date = selected_dates
    with filter_team_col:
        team_filter = st.selectbox("Team", teams, key="global_team_filter")

    with st.expander("Data requirements", expanded=False):
        req1, req2, req3, req4 = st.columns(4)
        with req1:
            min_velo_records = st.number_input(
                "Min FB records", min_value=1, step=1, value=1, key="global_min_velo_records"
            )
        with req2:
            min_ci_jumps = st.number_input(
                "Min CI jumps", min_value=1, step=1, value=1, key="global_min_ci_jumps"
            )
        with req3:
            min_pinch_tests = st.number_input(
                "Min pinch tests", min_value=1, step=1, value=1, key="global_min_pinch_tests"
            )
        with req4:
            min_power_jumps = st.number_input(
                "Min power jumps", min_value=1, step=1, value=1, key="global_min_power_jumps"
            )

# Read chart-control state before building figures. The widgets themselves are
# intentionally placed below their associated charts; Streamlit updates session
# state before the rerun, so the new value is already available here.
fb_ci_lookup = float(st.session_state.get("fb_ci_lookup", 280.0))
fb_ci_band_width = int(st.session_state.get("fb_ci_band_width", 10))
fb_ci_band_velo_stat = st.session_state.get("fb_ci_band_velo_stat", "Mean")
fb_velo_bucket_ci_stat = st.session_state.get("fb_velo_bucket_ci_stat", "Mean")
fb_show_labels = bool(st.session_state.get("fb_show_labels", False))

pinch_tab_lookup = float(st.session_state.get("pinch_tab_lookup", 40.0))
pinch_tab_band_width = float(st.session_state.get("pinch_tab_band_width", 5.0))
pinch_tab_band_velo_stat = st.session_state.get("pinch_tab_band_velo_stat", "Mean")
pinch_show_labels = bool(st.session_state.get("pinch_show_labels", False))

pitch_power_tab_lookup = float(st.session_state.get("pitch_power_tab_lookup", 5000.0))
pitch_power_tab_band_width = float(st.session_state.get("pitch_power_tab_band_width", 250.0))
pitch_power_tab_band_velo_stat = st.session_state.get("pitch_power_tab_band_velo_stat", "Mean")
pitch_power_show_labels = bool(st.session_state.get("pitch_power_show_labels", False))

combined_ci_lookup = float(st.session_state.get("combined_ci_lookup", 280.0))
combined_pinch_lookup = float(st.session_state.get("combined_pinch_lookup", 40.0))
combined_show_labels = bool(st.session_state.get("combined_show_labels", False))

sprint_power_lookup = float(st.session_state.get("sprint_power_lookup", 60.0))
sprint_power_band_width = float(st.session_state.get("sprint_power_band_width", 2.5))
sprint_power_band_stat = st.session_state.get("sprint_power_band_stat", "Mean")
sprint_show_labels = bool(st.session_state.get("sprint_show_labels", False))

bat_ci_lookup = float(st.session_state.get("bat_ci_lookup", 280.0))
bat_ci_band_width = int(st.session_state.get("bat_ci_band_width", 10))
bat_ci_band_stat = st.session_state.get("bat_ci_band_stat", "Mean")
bat_show_labels = bool(st.session_state.get("bat_show_labels", False))

exit_ci_lookup = float(st.session_state.get("exit_ci_lookup", 280.0))
exit_ci_band_width = int(st.session_state.get("exit_ci_band_width", 10))
exit_ci_band_stat = st.session_state.get("exit_ci_band_stat", "Mean")
exit_show_labels = bool(st.session_state.get("exit_show_labels", False))

summary = build_summary(
    jump=jump,
    velo=velo,
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    min_velo_records=int(min_velo_records),
    min_ci_jumps=int(min_ci_jumps),
)
power_pitch_summary = build_power_pitch_summary(
    jump_power=jump_power,
    velo=velo,
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    min_velo_records=int(min_velo_records),
    min_power_jumps=int(min_power_jumps),
)
pinch_summary = build_pinch_summary(
    pinch=pinch,
    velo=velo,
    jump=jump,
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    min_velo_records=int(min_velo_records),
    min_pinch_tests=int(min_pinch_tests),
)
combined_summary = build_combined_overview_summary(
    summary,
    pinch_summary,
)
combined_model = fit_combined_overview_model(combined_summary)

bat_monthly_pairs = build_bat_monthly_pairs(
    jump=jump,
    bat=bat,
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    min_ci_jumps=int(min_ci_jumps),
)
sprint_overview_summary = build_sprint_overview_summary(
    jump_power=jump_power,
    baserunning=baserunning_defense,
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    min_power_jumps=int(min_power_jumps),
)
exit_velo_summary = build_exit_velo_summary(
    jump=jump,
    exit_velo=exit_velo,
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    min_ci_jumps=int(min_ci_jumps),
)
if_reaction_power_summary = build_peak_power_rel_outcome_summary(
    jump_power=jump_power,
    outcome_df=infield_defense,
    outcome_col="if_reaction_3ft",
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    min_power_jumps=int(min_power_jumps),
)
sprint_nbsr_summary = build_sprint_nbsr_summary(
    jump=jump,
    outcome_df=baserunning_defense,
    team_filter=team_filter,
)
sprint_adv_runs_summary = build_baserunning_sprint_outcome_summary(
    jump=jump,
    outcome_df=baserunning_defense,
    outcome_col="adv_runs",
    team_filter=team_filter,
)
(
    overview_tab,
    pinch_overview_tab,
    power_pitch_tab,
    combined_model_tab,
    predicted_actual_tab,
    sprint_overview_tab,
    bat_overview_tab,
    exit_velo_overview_tab,
    if_reaction_power_tab,
    sprint_nbsr_tab,
    sprint_adv_runs_tab,
    sc_opportunity_tab,
) = st.tabs([
    "FB Velo Overview",
    "Pinch Grip Overview",
    "Peak Power [W] × Pitching Velo",
    "Combined CI + Pinch Overview",
    "Predicted vs Actual Velo",
    "Sprint Speed Overview",
    "Bat Speed Overview",
    "P90 Exit Velo Overview",
    "Rel PP × IF Reaction 3ft",
    "Sprint Speed × nBSR",
    "Sprint Speed × Adv Runs",
    "S&C Opportunity",
])

with overview_tab:
    stats = correlation_stats(summary)
    n_pitchers = len(summary)
    mean_velo = summary["avg_fb_velo"].mean() if n_pitchers else np.nan
    mean_ci = summary["avg_ci"].mean() if n_pitchers else np.nan
    r_text = f"{stats[0]:+.2f}" if stats is not None else "—"
    r2_text = f"{stats[1]:.2f}" if stats is not None else "—"
    potential_velo_increase = stats[2] * POTENTIAL_CI_INCREASE if stats is not None else np.nan
    potential_velo_text = (
        f"{potential_velo_increase:+.2f} mph"
        if pd.notna(potential_velo_increase)
        else "—"
    )

    top_cols = st.columns(3)
    top_metric_values = [
        ("Pitchers", str(n_pitchers), BLUE),
        ("Correlation", r_text, ACCENT_RED),
        ("R²", r2_text, NAVY_MID),
    ]
    for column, values in zip(top_cols, top_metric_values):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    bottom_cols = st.columns(3)
    bottom_metric_values = [
        ("Last YTD FB Velo", f"{fmt(mean_velo)} mph", TEAL),
        ("Average CI", f"{fmt(mean_ci)} N·s", GREEN),
        (
            f"Potential Velo Increase · +{POTENTIAL_CI_INCREASE:.0f} N·s CI",
            potential_velo_text,
            NAVY_MID,
        ),
    ]
    for column, values in zip(bottom_cols, bottom_metric_values):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    estimated_velo = np.nan
    if stats is not None:
        estimated_velo = stats[2] * float(fb_ci_lookup) + stats[3]

    with st.container(border=True):
        st.subheader("CI Lookup", anchor=False)
        lookup_left, lookup_right = st.columns(2)
        with lookup_left:
            st.markdown("<div class='metric-label'>Average CI</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='lookup-value' style='color:#0A1F44;'>{fmt(fb_ci_lookup, 1)} N·s</div>", unsafe_allow_html=True)
        with lookup_right:
            st.markdown("<div class='metric-label'>Estimated FB Velo</div>", unsafe_allow_html=True)
            lookup_value = f"{fmt(estimated_velo)} mph" if pd.notna(estimated_velo) else "—"
            st.markdown(f"<div class='lookup-value' style='color:#0D7E8A;'>{lookup_value}</div>", unsafe_allow_html=True)
        st.number_input(
            "CI lookup", min_value=0.0, step=1.0, value=280.0,
            format="%.1f", key="fb_ci_lookup",
        )

    ci_band_overview = ci_band_summary(summary, int(fb_ci_band_width), fb_ci_band_velo_stat)

    with st.container(border=True):
        st.subheader(f"{fb_ci_band_velo_stat} FB Velo by CI Band", anchor=False)
        st.plotly_chart(
            build_band_chart(summary, int(fb_ci_band_width), fb_ci_band_velo_stat),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"ci_band_chart_{fb_ci_band_width}_{fb_ci_band_velo_stat}_{team_filter}_{start_date}_{end_date}",
        )
        band_control_1, band_control_2 = st.columns(2)
        with band_control_1:
            st.selectbox(
                "CI band width", [5, 10, 15, 20], index=1,
                format_func=lambda x: f"{x} N·s", key="fb_ci_band_width",
            )
        with band_control_2:
            st.radio(
                "FB velo statistic", ["Mean", "Median"], horizontal=True,
                key="fb_ci_band_velo_stat",
            )


    with st.container(border=True):
        st.subheader(f"{fb_velo_bucket_ci_stat} CI by FB Velo Bucket", anchor=False)
        st.plotly_chart(
            build_output_bucket_chart(
                df=summary,
                output_col="avg_fb_velo",
                testing_col="avg_ci",
                bucket_width=FB_VELO_OUTPUT_BUCKET_WIDTH,
                output_bucket_label="FB velo bucket",
                testing_metric_label="CI",
                output_axis_title="Last YTD FB velo bucket",
                testing_axis_title=f"{fb_velo_bucket_ci_stat} CI (N·s)",
                output_unit="mph",
                empty_text="No matched pitchers are available for FB velo buckets.",
                color=TEAL,
                testing_stat=fb_velo_bucket_ci_stat,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"fb_velo_output_bucket_{fb_velo_bucket_ci_stat}_"
                f"{team_filter}_{start_date}_{end_date}"
            ),
        )
        st.radio(
            "CI statistic", ["Mean", "Median"], horizontal=True,
            key="fb_velo_bucket_ci_stat",
            help="Choose whether each FB-velocity bucket displays mean or median pitcher CI.",
        )


    fb_output_bands = output_bucket_summary(
        summary,
        "avg_fb_velo",
        "avg_ci",
        FB_VELO_OUTPUT_BUCKET_WIDTH,
        "FB velo bucket",
        "CI",
        "mph",
        "N·s",
        testing_stat=fb_velo_bucket_ci_stat,
    )
    if not fb_output_bands.empty:
        fb_output_options = fb_output_bands["FB velo bucket"].tolist()
        fb_output_key = "fb_velo_output_bucket_detail_selector"
        if st.session_state.get(fb_output_key) not in fb_output_options:
            st.session_state[fb_output_key] = fb_output_options[0]
        with st.container(border=True):
            st.subheader("FB Velo Bucket Pitchers", anchor=False)
            selected_fb_output_bucket = st.selectbox(
                "FB velo bucket",
                fb_output_options,
                key=fb_output_key,
            )
            st.plotly_chart(
                build_output_bucket_member_chart(
                    df=summary,
                    output_col="avg_fb_velo",
                    testing_col="avg_ci",
                    bucket_width=FB_VELO_OUTPUT_BUCKET_WIDTH,
                    selected_bucket=selected_fb_output_bucket,
                    output_bucket_label="FB velo bucket",
                    output_unit="mph",
                    testing_axis_title=f"{fb_velo_bucket_ci_stat} CI",
                    testing_unit="N·s",
                    entity_label="Pitcher",
                    output_value_label="Last YTD FB velo",
                    testing_stat=fb_velo_bucket_ci_stat,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    f"fb_output_detail_{selected_fb_output_bucket}_{fb_velo_bucket_ci_stat}_"
                    f"{team_filter}_{start_date}_{end_date}"
                ),
            )

    if not ci_band_overview.empty:
        band_options = ci_band_overview["CI band"].tolist()
        band_detail_key = "ci_band_detail_selector"
        if st.session_state.get(band_detail_key) not in band_options:
            st.session_state[band_detail_key] = band_options[0]

        with st.container(border=True):
            st.subheader("CI Band Pitchers", anchor=False)
            selected_ci_band = st.selectbox(
                "CI band",
                band_options,
                key=band_detail_key,
            )
            st.plotly_chart(
                build_ci_band_member_chart(
                    summary,
                    int(fb_ci_band_width),
                    selected_ci_band,
                    fb_ci_band_velo_stat,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    f"ci_band_detail_{selected_ci_band}_{fb_ci_band_width}_"
                    f"{fb_ci_band_velo_stat}_{team_filter}_{start_date}_{end_date}"
                ),
            )

    with st.container(border=True):
        st.subheader("CI vs YTD FB Velo", anchor=False)
        st.plotly_chart(build_scatter(summary, fb_show_labels, float(fb_ci_lookup)), use_container_width=True, config={"displayModeBar": False})
        st.checkbox("Show names", key="fb_show_labels")

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
            csv_download_button(
                display,
                "Download pitcher results CSV",
                "fb_velo_pitcher_results.csv",
                "download_fb_velo_pitcher_results",
            )



with pinch_overview_tab:
    pinch_view = pinch_summary.dropna(
        subset=["avg_pinch_strength", "avg_fb_velo"]
    ).copy()
    pinch_stats = pinch_correlation_stats(pinch_view)
    n_pinch_pitchers = len(pinch_view)
    mean_pinch_value = (
        pinch_view["avg_pinch_strength"].mean()
        if n_pinch_pitchers else np.nan
    )
    mean_pinch_velo = (
        pinch_view["avg_fb_velo"].mean()
        if n_pinch_pitchers else np.nan
    )
    pinch_r_text = (
        f"{pinch_stats[0]:+.2f}" if pinch_stats is not None else "—"
    )
    pinch_r2_text = (
        f"{pinch_stats[1]:.2f}" if pinch_stats is not None else "—"
    )
    potential_pinch_velo = (
        pinch_stats[2] * POTENTIAL_PINCH_INCREASE
        if pinch_stats is not None else np.nan
    )
    potential_pinch_text = (
        f"{potential_pinch_velo:+.2f} mph"
        if pd.notna(potential_pinch_velo) else "—"
    )

    top_cols = st.columns(3)
    top_metrics = [
        ("Pitchers", str(n_pinch_pitchers), BLUE),
        ("Correlation", pinch_r_text, ACCENT_RED),
        ("R²", pinch_r2_text, NAVY_MID),
    ]
    for column, values in zip(top_cols, top_metrics):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    bottom_cols = st.columns(3)
    bottom_metrics = [
        ("Last YTD FB Velo", f"{fmt(mean_pinch_velo)} mph", TEAL),
        ("Average Pinch Strength", fmt(mean_pinch_value), GREEN),
        (
            f"Potential Velo Increase · +{POTENTIAL_PINCH_INCREASE:.0f} Pinch",
            potential_pinch_text,
            NAVY_MID,
        ),
    ]
    for column, values in zip(bottom_cols, bottom_metrics):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    estimated_pinch_velo = (
        pinch_stats[2] * float(pinch_tab_lookup) + pinch_stats[3]
        if pinch_stats is not None else np.nan
    )
    with st.container(border=True):
        st.subheader("Pinch Lookup", anchor=False)
        lookup_left, lookup_right = st.columns(2)
        with lookup_left:
            st.markdown(
                "<div class='metric-label'>Average Pinch Strength</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='lookup-value' style='color:#0A1F44;'>"
                f"{fmt(pinch_tab_lookup, 1)}</div>",
                unsafe_allow_html=True,
            )
        with lookup_right:
            st.markdown(
                "<div class='metric-label'>Estimated FB Velo</div>",
                unsafe_allow_html=True,
            )
            lookup_value = (
                f"{fmt(estimated_pinch_velo)} mph"
                if pd.notna(estimated_pinch_velo) else "—"
            )
            st.markdown(
                f"<div class='lookup-value' style='color:#0D7E8A;'>"
                f"{lookup_value}</div>",
                unsafe_allow_html=True,
            )
        st.number_input(
            "Pinch lookup", min_value=0.0, step=1.0, value=40.0,
            format="%.1f", key="pinch_tab_lookup",
        )

    pinch_band_overview = pinch_band_summary(
        pinch_view,
        float(pinch_tab_band_width),
        pinch_tab_band_velo_stat,
    )
    with st.container(border=True):
        st.subheader(
            f"{pinch_tab_band_velo_stat} FB Velo by Pinch Band",
            anchor=False,
        )
        st.plotly_chart(
            build_pinch_band_chart(
                pinch_view,
                float(pinch_tab_band_width),
                pinch_tab_band_velo_stat,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"pinch_band_chart_{pinch_tab_band_width}_"
                f"{pinch_tab_band_velo_stat}_{team_filter}_{start_date}_{end_date}"
            ),
        )
        pinch_control_1, pinch_control_2 = st.columns(2)
        with pinch_control_1:
            st.selectbox(
                "Pinch band width", [2.5, 5.0, 10.0], index=1,
                format_func=lambda x: f"{x:g} units", key="pinch_tab_band_width",
            )
        with pinch_control_2:
            st.radio(
                "FB velo statistic", ["Mean", "Median"], horizontal=True,
                key="pinch_tab_band_velo_stat",
            )


    with st.container(border=True):
        st.subheader("Average Pinch Strength by FB Velo Bucket", anchor=False)
        st.plotly_chart(
            build_output_bucket_chart(
                df=pinch_view,
                output_col="avg_fb_velo",
                testing_col="avg_pinch_strength",
                bucket_width=FB_VELO_OUTPUT_BUCKET_WIDTH,
                output_bucket_label="FB velo bucket",
                testing_metric_label="pinch strength",
                output_axis_title="Last YTD FB velo bucket",
                testing_axis_title="Average pinch strength",
                output_unit="mph",
                empty_text="No matched pitchers are available for FB velo buckets.",
                color=TEAL,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"pinch_output_bucket_{team_filter}_{start_date}_{end_date}",
        )


    pinch_output_bands = output_bucket_summary(
        pinch_view,
        "avg_fb_velo",
        "avg_pinch_strength",
        FB_VELO_OUTPUT_BUCKET_WIDTH,
        "FB velo bucket",
        "pinch strength",
        "mph",
        "",
    )
    if not pinch_output_bands.empty:
        pinch_output_options = pinch_output_bands["FB velo bucket"].tolist()
        pinch_output_key = "pinch_fb_output_bucket_detail_selector"
        if st.session_state.get(pinch_output_key) not in pinch_output_options:
            st.session_state[pinch_output_key] = pinch_output_options[0]
        with st.container(border=True):
            st.subheader("FB Velo Bucket Pitchers", anchor=False)
            selected_pinch_output_bucket = st.selectbox(
                "Pinch-tab FB velo bucket",
                pinch_output_options,
                key=pinch_output_key,
            )
            st.plotly_chart(
                build_output_bucket_member_chart(
                    df=pinch_view,
                    output_col="avg_fb_velo",
                    testing_col="avg_pinch_strength",
                    bucket_width=FB_VELO_OUTPUT_BUCKET_WIDTH,
                    selected_bucket=selected_pinch_output_bucket,
                    output_bucket_label="FB velo bucket",
                    output_unit="mph",
                    testing_axis_title="Average pinch strength",
                    testing_unit="",
                    entity_label="Pitcher",
                    output_value_label="Last YTD FB velo",
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"pinch_output_detail_{selected_pinch_output_bucket}_{team_filter}_{start_date}_{end_date}",
            )

    if not pinch_band_overview.empty:
        pinch_band_options = pinch_band_overview["Pinch band"].tolist()
        pinch_band_detail_key = "pinch_band_detail_selector"
        if st.session_state.get(pinch_band_detail_key) not in pinch_band_options:
            st.session_state[pinch_band_detail_key] = pinch_band_options[0]

        with st.container(border=True):
            st.subheader("Pinch Band Pitchers", anchor=False)
            selected_pinch_band = st.selectbox(
                "Pinch band",
                pinch_band_options,
                key=pinch_band_detail_key,
            )
            st.plotly_chart(
                build_pinch_band_member_chart(
                    pinch_view,
                    float(pinch_tab_band_width),
                    selected_pinch_band,
                    pinch_tab_band_velo_stat,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    f"pinch_band_detail_{selected_pinch_band}_"
                    f"{pinch_tab_band_width}_{pinch_tab_band_velo_stat}_"
                    f"{team_filter}_{start_date}_{end_date}"
                ),
            )

    with st.container(border=True):
        st.subheader("Pinch Strength vs YTD FB Velo", anchor=False)
        st.plotly_chart(
            build_pinch_scatter(
                pinch_view,
                pinch_show_labels,
                float(pinch_tab_lookup),
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"pinch_scatter_{team_filter}_{start_date}_{end_date}_"
                f"{min_pinch_tests}_{pinch_tab_lookup}_{pinch_show_labels}"
            ),
        )
        st.checkbox("Show names", key="pinch_show_labels")

    with st.container(border=True):
        st.subheader("Pinch Grip Pitcher Results", anchor=False)
        if pinch_view.empty:
            st.info("No matching pitchers.")
        else:
            pinch_display = pinch_view[[
                "athlete", "team", "avg_fb_velo", "ytd_as_of_date",
                "pinch_hand", "avg_pinch_strength", "fb_records",
                "pinch_tests", "pinch_test_dates", "first_pinch_date",
                "last_pinch_date",
            ]].copy()
            pinch_display.columns = [
                "Pitcher", "Team", "Last YTD FB Velo", "YTD FB As Of",
                "Tested Hand", "Average Pinch Strength", "FB Records",
                "Pinch Tests", "Pinch Test Dates", "First Pinch", "Last Pinch",
            ]
            for date_col in ["YTD FB As Of", "First Pinch", "Last Pinch"]:
                pinch_display[date_col] = pinch_display[date_col].map(fmt_date)
            pinch_display["Last YTD FB Velo"] = (
                pinch_display["Last YTD FB Velo"].round(2)
            )
            pinch_display["Average Pinch Strength"] = (
                pinch_display["Average Pinch Strength"].round(2)
            )
            st.dataframe(
                pinch_display,
                hide_index=True,
                use_container_width=True,
                height=min(650, 44 + 36 * (len(pinch_display) + 1)),
                column_config={
                    "Last YTD FB Velo": st.column_config.NumberColumn(
                        format="%.2f mph"
                    ),
                    "Average Pinch Strength": st.column_config.NumberColumn(
                        format="%.2f"
                    ),
                },
            )
            csv_download_button(
                pinch_display,
                "Download pinch pitcher results CSV",
                "pinch_pitcher_results.csv",
                "download_pinch_pitcher_results",
            )



with power_pitch_tab:
    power_pitch_stats = power_pitch_correlation_stats(power_pitch_summary)
    n_power_pitchers = len(power_pitch_summary)
    mean_power_pitch_velo = (
        power_pitch_summary["avg_fb_velo"].mean() if n_power_pitchers else np.nan
    )
    mean_pitch_power = (
        power_pitch_summary["avg_peak_power"].mean() if n_power_pitchers else np.nan
    )
    power_pitch_r_text = (
        f"{power_pitch_stats[0]:+.2f}" if power_pitch_stats is not None else "—"
    )
    power_pitch_r2_text = (
        f"{power_pitch_stats[1]:.2f}" if power_pitch_stats is not None else "—"
    )
    potential_power_velo = (
        power_pitch_stats[2] * POTENTIAL_PEAK_POWER_INCREASE
        if power_pitch_stats is not None else np.nan
    )
    potential_power_velo_text = (
        f"{potential_power_velo:+.2f} mph" if pd.notna(potential_power_velo) else "—"
    )

    top_cols = st.columns(3)
    for column, values in zip(top_cols, [
        ("Pitchers", str(n_power_pitchers), BLUE),
        ("Correlation", power_pitch_r_text, ACCENT_RED),
        ("R²", power_pitch_r2_text, NAVY_MID),
    ]):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    bottom_cols = st.columns(3)
    for column, values in zip(bottom_cols, [
        ("Last YTD FB Velo", f"{fmt(mean_power_pitch_velo)} mph", TEAL),
        ("Average Peak Power [W]", f"{fmt(mean_pitch_power)} W", GREEN),
        (
            f"Potential Velo Increase · +{POTENTIAL_PEAK_POWER_INCREASE:.0f} W",
            potential_power_velo_text,
            NAVY_MID,
        ),
    ]):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    estimated_power_pitch_velo = (
        power_pitch_stats[2] * float(pitch_power_tab_lookup) + power_pitch_stats[3]
        if power_pitch_stats is not None else np.nan
    )
    with st.container(border=True):
        st.subheader("Peak Power [W] Lookup", anchor=False)
        lookup_left, lookup_right = st.columns(2)
        with lookup_left:
            st.markdown(
                "<div class='metric-label'>Average Peak Power [W]</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='lookup-value' style='color:#0A1F44;'>"
                f"{fmt(pitch_power_tab_lookup, 1)} W</div>",
                unsafe_allow_html=True,
            )
        with lookup_right:
            st.markdown(
                "<div class='metric-label'>Estimated FB Velo</div>",
                unsafe_allow_html=True,
            )
            lookup_value = (
                f"{fmt(estimated_power_pitch_velo)} mph"
                if pd.notna(estimated_power_pitch_velo) else "—"
            )
            st.markdown(
                f"<div class='lookup-value' style='color:#0D7E8A;'>"
                f"{lookup_value}</div>",
                unsafe_allow_html=True,
            )
        st.number_input(
            "Peak Power [W] lookup", min_value=0.0, step=100.0, value=5000.0,
            format="%.0f", key="pitch_power_tab_lookup",
        )

    power_pitch_bands = power_pitch_band_summary(
        power_pitch_summary,
        float(pitch_power_tab_band_width),
        pitch_power_tab_band_velo_stat,
    )
    with st.container(border=True):
        st.subheader(
            f"{pitch_power_tab_band_velo_stat} FB Velo by Peak Power [W] Band",
            anchor=False,
        )
        st.plotly_chart(
            build_power_pitch_band_chart(
                power_pitch_summary,
                float(pitch_power_tab_band_width),
                pitch_power_tab_band_velo_stat,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"power_pitch_band_{pitch_power_tab_band_width}_{pitch_power_tab_band_velo_stat}_"
                f"{team_filter}_{start_date}_{end_date}"
            ),
        )
        pitch_power_control_1, pitch_power_control_2 = st.columns(2)
        with pitch_power_control_1:
            st.selectbox(
                "Peak Power [W] band width", [100.0, 250.0, 500.0, 1000.0], index=1,
                format_func=lambda x: f"{x:g} W", key="pitch_power_tab_band_width",
            )
        with pitch_power_control_2:
            st.radio(
                "FB velo statistic", ["Mean", "Median"], horizontal=True,
                key="pitch_power_tab_band_velo_stat",
            )

    if not power_pitch_bands.empty:
        power_pitch_band_options = power_pitch_bands["Peak Power band"].tolist()
        power_pitch_band_key = "power_pitch_band_detail_selector"
        if st.session_state.get(power_pitch_band_key) not in power_pitch_band_options:
            st.session_state[power_pitch_band_key] = power_pitch_band_options[0]
        with st.container(border=True):
            st.subheader("Peak Power [W] Band Pitchers", anchor=False)
            selected_power_pitch_band = st.selectbox(
                "Peak Power band",
                power_pitch_band_options,
                key=power_pitch_band_key,
            )
            st.plotly_chart(
                build_power_pitch_band_member_chart(
                    power_pitch_summary,
                    float(pitch_power_tab_band_width),
                    selected_power_pitch_band,
                    pitch_power_tab_band_velo_stat,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    f"power_pitch_band_detail_{selected_power_pitch_band}_"
                    f"{pitch_power_tab_band_width}_{pitch_power_tab_band_velo_stat}_{team_filter}_"
                    f"{start_date}_{end_date}"
                ),
            )

    with st.container(border=True):
        st.subheader("Average Peak Power [W] by FB Velo Bucket", anchor=False)
        st.plotly_chart(
            build_output_bucket_chart(
                df=power_pitch_summary,
                output_col="avg_fb_velo",
                testing_col="avg_peak_power",
                bucket_width=FB_VELO_OUTPUT_BUCKET_WIDTH,
                output_bucket_label="FB velo bucket",
                testing_metric_label="peak power",
                output_axis_title="Last YTD FB velo bucket",
                testing_axis_title="Average Peak Power [W]",
                output_unit="mph",
                empty_text="No matched pitchers are available for FB velo buckets.",
                color=TEAL,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"power_pitch_output_bucket_{team_filter}_{start_date}_{end_date}",
        )

    power_pitch_output_buckets = output_bucket_summary(
        df=power_pitch_summary,
        output_col="avg_fb_velo",
        testing_col="avg_peak_power",
        bucket_width=FB_VELO_OUTPUT_BUCKET_WIDTH,
        output_bucket_label="FB velo bucket",
        testing_metric_label="peak power",
        output_unit="mph",
        testing_unit="W",
    )
    if not power_pitch_output_buckets.empty:
        power_pitch_output_options = power_pitch_output_buckets["FB velo bucket"].tolist()
        power_pitch_output_key = "power_pitch_output_bucket_detail_selector"
        if st.session_state.get(power_pitch_output_key) not in power_pitch_output_options:
            st.session_state[power_pitch_output_key] = power_pitch_output_options[0]
        with st.container(border=True):
            st.subheader("FB Velo Bucket Pitchers · Peak Power", anchor=False)
            selected_power_output_bucket = st.selectbox(
                "FB velo bucket",
                power_pitch_output_options,
                key=power_pitch_output_key,
            )
            st.plotly_chart(
                build_output_bucket_member_chart(
                    df=power_pitch_summary,
                    output_col="avg_fb_velo",
                    testing_col="avg_peak_power",
                    bucket_width=FB_VELO_OUTPUT_BUCKET_WIDTH,
                    selected_bucket=selected_power_output_bucket,
                    output_bucket_label="FB velo bucket",
                    output_unit="mph",
                    testing_axis_title="Average Peak Power [W]",
                    testing_unit="W",
                    entity_label="Pitcher",
                    output_value_label="Last YTD FB velo",
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    f"power_pitch_output_detail_{selected_power_output_bucket}_"
                    f"{team_filter}_{start_date}_{end_date}"
                ),
            )

    with st.container(border=True):
        st.subheader("Peak Power [W] vs YTD FB Velo", anchor=False)
        st.plotly_chart(
            build_power_pitch_scatter(
                power_pitch_summary,
                pitch_power_show_labels,
                float(pitch_power_tab_lookup),
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"power_pitch_scatter_{team_filter}_{start_date}_{end_date}_"
                f"{pitch_power_show_labels}_{pitch_power_tab_lookup}"
            ),
        )
        st.checkbox("Show names", key="pitch_power_show_labels")

    with st.container(border=True):
        st.subheader("Peak Power [W] Pitcher Results", anchor=False)
        if power_pitch_summary.empty:
            st.info("No matching pitchers.")
        else:
            power_pitch_display = power_pitch_summary[[
                "athlete", "team", "avg_fb_velo", "ytd_as_of_date",
                "avg_peak_power", "fb_records", "power_jumps",
                "power_test_dates", "first_power_date", "last_power_date",
            ]].copy()
            power_pitch_display.columns = [
                "Pitcher", "Team", "Last YTD FB Velo", "YTD FB As Of",
                "Average Peak Power [W]", "FB Records", "Power Jumps",
                "Power Test Dates", "First Power Test", "Last Power Test",
            ]
            for date_col in ["YTD FB As Of", "First Power Test", "Last Power Test"]:
                power_pitch_display[date_col] = power_pitch_display[date_col].map(fmt_date)
            power_pitch_display["Last YTD FB Velo"] = power_pitch_display["Last YTD FB Velo"].round(2)
            power_pitch_display["Average Peak Power [W]"] = power_pitch_display["Average Peak Power [W]"].round(2)
            st.dataframe(
                power_pitch_display,
                hide_index=True,
                use_container_width=True,
                height=min(650, 44 + 36 * (len(power_pitch_display) + 1)),
                column_config={
                    "Last YTD FB Velo": st.column_config.NumberColumn(format="%.2f mph"),
                    "Average Peak Power [W]": st.column_config.NumberColumn(format="%.2f W"),
                },
            )
            csv_download_button(
                power_pitch_display,
                "Download peak-power pitching results CSV",
                "peak_power_pitching_velo_results.csv",
                "download_peak_power_pitching_results",
            )


with combined_model_tab:
    n_combined_pitchers = len(combined_summary)

    if combined_model is None:
        cols = st.columns(4)
        values = [
            ("Pitchers", str(n_combined_pitchers), BLUE),
            ("Model R²", "—", ACCENT_RED),
            ("Adjusted R²", "—", NAVY_MID),
            ("RMSE", "—", GREEN),
        ]
        for column, metric_values in zip(cols, values):
            with column:
                st.markdown(metric_card(*metric_values), unsafe_allow_html=True)
        st.info(
            "The combined overview model needs at least four pitchers with "
            "eligible CI, pinch-grip, and final in-window YTD FB-velocity data, "
            "plus variation in both predictors. Each pitcher contributes one row."
        )
    else:
        cols = st.columns(5)
        values = [
            ("Pitchers", str(combined_model["n_pitchers"]), BLUE),
            ("Model R²", f"{combined_model['r2']:.2f}", ACCENT_RED),
            (
                "Adjusted R²",
                f"{combined_model['adjusted_r2']:.2f}"
                if pd.notna(combined_model["adjusted_r2"]) else "—",
                NAVY_MID,
            ),
            ("RMSE", f"{combined_model['rmse']:.2f} mph", GREEN),
            (
                "LOO RMSE",
                f"{combined_model['cv_rmse']:.2f} mph"
                if pd.notna(combined_model["cv_rmse"]) else "—",
                NAVY,
            ),
        ]
        for column, metric_values in zip(cols, values):
            with column:
                st.markdown(metric_card(*metric_values), unsafe_allow_html=True)

        if combined_model["n_pitchers"] < 15:
            st.warning(
                "Fewer than 15 pitchers are included. The model can be shown, "
                "but coefficients and cross-validation results may change "
                "substantially when individual pitchers are added or removed."
            )
        if pd.notna(combined_model["vif"]) and combined_model["vif"] >= 5:
            st.warning(
                f"CI and pinch strength have a VIF of {combined_model['vif']:.1f}. "
                "The two predictors overlap enough that their separate "
                "coefficients may be unstable."
            )

        ci_association_10 = combined_model["beta_ci"] * 10.0
        pinch_association_10 = combined_model["beta_pinch"] * 10.0
        both_association_10 = ci_association_10 + pinch_association_10
        effect_cols = st.columns(5)
        effect_values = [
            ("Partial CI Association · +10 N·s", f"{ci_association_10:+.2f} mph", BLUE),
            ("Partial Pinch Association · +10", f"{pinch_association_10:+.2f} mph", TEAL),
            ("Both Predictors +10", f"{both_association_10:+.2f} mph", ACCENT_RED),
            (
                "LOO CV R²",
                f"{combined_model['cv_r2']:.2f}"
                if pd.notna(combined_model["cv_r2"]) else "—",
                GREEN,
            ),
            (
                "CI–Pinch r",
                f"{combined_model['ci_pinch_r']:+.2f}"
                if pd.notna(combined_model["ci_pinch_r"]) else "—",
                NAVY_MID,
            ),
        ]
        for column, metric_values in zip(effect_cols, effect_values):
            with column:
                st.markdown(metric_card(*metric_values), unsafe_allow_html=True)

        with st.container(border=True):
            st.subheader("Combined CI + Pinch Lookup", anchor=False)
            lookup_estimate = (
                combined_model["intercept"]
                + combined_model["beta_ci"] * float(combined_ci_lookup)
                + combined_model["beta_pinch"] * float(combined_pinch_lookup)
            )
            lookup_cols = st.columns(3)
            lookup_items = [
                ("Average CI", f"{float(combined_ci_lookup):.1f} N·s", BLUE),
                ("Average Pinch", f"{float(combined_pinch_lookup):.1f}", TEAL),
                ("Estimated Final YTD FB Velo", f"{lookup_estimate:.2f} mph", ACCENT_RED),
            ]
            for column, (label, value, color) in zip(lookup_cols, lookup_items):
                with column:
                    st.markdown(
                        f"<div class='metric-label'>{html.escape(label)}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div class='lookup-value' style='color:{color};'>"
                        f"{html.escape(value)}</div>",
                        unsafe_allow_html=True,
                    )
            combined_lookup_1, combined_lookup_2 = st.columns(2)
            with combined_lookup_1:
                st.number_input(
                    "CI lookup", min_value=0.0, step=1.0, value=280.0,
                    format="%.1f", key="combined_ci_lookup",
                )
            with combined_lookup_2:
                st.number_input(
                    "Pinch lookup", min_value=0.0, step=1.0, value=40.0,
                    format="%.1f", key="combined_pinch_lookup",
                )

            model_data = combined_model["data"]
            outside_ci = not (
                model_data["avg_ci"].min()
                <= float(combined_ci_lookup)
                <= model_data["avg_ci"].max()
            )
            outside_pinch = not (
                model_data["avg_pinch_strength"].min()
                <= float(combined_pinch_lookup)
                <= model_data["avg_pinch_strength"].max()
            )
            if outside_ci or outside_pinch:
                st.warning(
                    "At least one lookup value is outside the observed pitcher "
                    "range, so this estimate is an extrapolation."
                )

        chart_left, chart_right = st.columns(2)
        with chart_left:
            with st.container(border=True):
                st.subheader("Cross-Validated Model Comparison", anchor=False)
                st.plotly_chart(
                    build_combined_model_comparison_chart(combined_model),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=(
                        f"combined_overview_comparison_{team_filter}_"
                        f"{start_date}_{end_date}_{min_ci_jumps}_"
                        f"{min_pinch_tests}_{min_velo_records}"
                    ),
                )
        with chart_right:
            with st.container(border=True):
                st.subheader("Actual vs Predicted FB Velo", anchor=False)
                st.plotly_chart(
                    build_combined_actual_predicted_chart(
                        combined_model, combined_show_labels
                    ),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=(
                        f"combined_overview_actual_predicted_{team_filter}_"
                        f"{start_date}_{end_date}_{combined_show_labels}_"
                        f"{min_ci_jumps}_{min_pinch_tests}_{min_velo_records}"
                    ),
                )
                st.checkbox("Show names", key="combined_show_labels")

        with st.container(border=True):
            st.subheader("Combined Model Coefficients", anchor=False)
            coefficient_table = pd.DataFrame({
                "Predictor": ["Intercept", "Concentric impulse", "Pinch strength"],
                "Coefficient": [
                    combined_model["intercept"],
                    combined_model["beta_ci"],
                    combined_model["beta_pinch"],
                ],
                "Standard Error": [
                    combined_model["se_intercept"],
                    combined_model["se_ci"],
                    combined_model["se_pinch"],
                ],
                "Approx. 95% Lower": [
                    combined_model["intercept"] - 1.96 * combined_model["se_intercept"],
                    combined_model["beta_ci"] - 1.96 * combined_model["se_ci"],
                    combined_model["beta_pinch"] - 1.96 * combined_model["se_pinch"],
                ],
                "Approx. 95% Upper": [
                    combined_model["intercept"] + 1.96 * combined_model["se_intercept"],
                    combined_model["beta_ci"] + 1.96 * combined_model["se_ci"],
                    combined_model["beta_pinch"] + 1.96 * combined_model["se_pinch"],
                ],
                "Standardized Beta": [
                    np.nan,
                    combined_model["standardized_beta_ci"],
                    combined_model["standardized_beta_pinch"],
                ],
                "Association per +10": [
                    np.nan,
                    ci_association_10,
                    pinch_association_10,
                ],
            })
            st.dataframe(
                coefficient_table,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Coefficient": st.column_config.NumberColumn(format="%+.4f"),
                    "Standard Error": st.column_config.NumberColumn(format="%.4f"),
                    "Approx. 95% Lower": st.column_config.NumberColumn(format="%+.4f"),
                    "Approx. 95% Upper": st.column_config.NumberColumn(format="%+.4f"),
                    "Standardized Beta": st.column_config.NumberColumn(format="%+.2f"),
                    "Association per +10": st.column_config.NumberColumn(format="%+.2f mph"),
                },
            )
            csv_download_button(
                coefficient_table,
                "Download coefficient table CSV",
                "combined_model_coefficients.csv",
                "download_combined_model_coefficients",
            )
        with st.container(border=True):
            st.subheader("Combined Pitcher Results", anchor=False)
            model_data = combined_model["data"]
            combined_display = model_data[[
                "athlete", "team", "avg_fb_velo", "predicted_fb_velo",
                "residual_fb_velo", "ytd_as_of_date", "avg_ci", "ci_jumps",
                "ci_test_dates", "first_ci_date", "last_ci_date",
                "avg_pinch_strength", "pinch_hand", "pinch_tests",
                "pinch_test_dates", "first_pinch_date", "last_pinch_date",
            ]].copy()
            combined_display.columns = [
                "Pitcher", "Team", "Actual Final YTD FB Velo",
                "Predicted FB Velo", "Residual", "YTD FB As Of",
                "Average CI", "CI Jumps", "CI Test Dates", "First CI",
                "Last CI", "Average Pinch", "Tested Hand", "Pinch Tests",
                "Pinch Test Dates", "First Pinch", "Last Pinch",
            ]
            for date_col in [
                "YTD FB As Of", "First CI", "Last CI",
                "First Pinch", "Last Pinch",
            ]:
                combined_display[date_col] = combined_display[date_col].map(
                    fmt_date
                )
            st.dataframe(
                combined_display,
                hide_index=True,
                use_container_width=True,
                height=min(700, 44 + 36 * (len(combined_display) + 1)),
                column_config={
                    "Actual Final YTD FB Velo": st.column_config.NumberColumn(
                        format="%.2f mph"
                    ),
                    "Predicted FB Velo": st.column_config.NumberColumn(
                        format="%.2f mph"
                    ),
                    "Residual": st.column_config.NumberColumn(
                        format="%+.2f mph"
                    ),
                    "Average CI": st.column_config.NumberColumn(
                        format="%.2f N·s"
                    ),
                    "Average Pinch": st.column_config.NumberColumn(
                        format="%.2f"
                    ),
                },
            )
            csv_download_button(
                combined_display,
                "Download combined pitcher results CSV",
                "combined_pitcher_results.csv",
                "download_combined_pitcher_results",
            )


with predicted_actual_tab:
    if combined_model is None or combined_model["data"].empty:
        st.info(
            "Predicted vs Actual Velo uses the same CI + pinch model as the "
            "Combined CI + Pinch Overview. There are not enough eligible "
            "pitchers to fit that model under the current filters."
        )
    else:
        model_data = combined_model["data"].copy()
        model_data["abs_residual"] = model_data["residual_fb_velo"].abs()
        mean_abs_error = float(model_data["abs_residual"].mean())
        mean_residual = float(model_data["residual_fb_velo"].mean())

        top_cols = st.columns(4)
        top_values = [
            ("Eligible Pitchers", str(len(model_data)), BLUE),
            ("Model R²", f"{combined_model['r2']:.2f}", ACCENT_RED),
            ("Mean Absolute Gap", f"{mean_abs_error:.2f} mph", TEAL),
            ("Mean Residual", f"{mean_residual:+.2f} mph", NAVY_MID),
        ]
        for column, values in zip(top_cols, top_values):
            with column:
                st.markdown(metric_card(*values), unsafe_allow_html=True)

        st.caption(
            "Predicted velo comes from the same pitcher-level model used in the "
            "Combined CI + Pinch Overview: final YTD FB velo predicted from "
            "Average CI and Average Pinch Strength. The global team, date, and "
            "minimum-data filters still apply."
        )

        with st.container(border=True):
            st.subheader("Actual vs Predicted · All Eligible Pitchers", anchor=False)
            st.plotly_chart(
                build_predicted_actual_roster_chart(combined_model),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    f"predicted_actual_roster_{team_filter}_{start_date}_{end_date}_"
                    f"{min_ci_jumps}_{min_pinch_tests}_{min_velo_records}"
                ),
            )

        with st.container(border=True):
            st.subheader("Pitcher What-If Simulator", anchor=False)
            pitcher_options = model_data.sort_values(
                ["team", "athlete"], kind="stable"
            )["athlete"].tolist()
            pitcher_selector_key = "predicted_actual_whatif_pitcher"
            if st.session_state.get(pitcher_selector_key) not in pitcher_options:
                st.session_state[pitcher_selector_key] = pitcher_options[0]
            selected_pitcher = st.selectbox(
                "Pitcher",
                pitcher_options,
                key=pitcher_selector_key,
            )
            selected = model_data.loc[
                model_data["athlete"] == selected_pitcher
            ].iloc[0]

            current_ci = float(selected["avg_ci"])
            current_pinch = float(selected["avg_pinch_strength"])
            actual_velo = float(selected["avg_fb_velo"])
            current_predicted = float(selected["predicted_fb_velo"])
            player_key = re.sub(r"[^a-zA-Z0-9]+", "_", str(selected["name_key"])).strip("_")
            filter_key = re.sub(
                r"[^a-zA-Z0-9]+", "_",
                f"{team_filter}_{start_date}_{end_date}",
            ).strip("_")
            ci_widget_key = f"predicted_actual_whatif_ci_{player_key}_{filter_key}"
            pinch_widget_key = f"predicted_actual_whatif_pinch_{player_key}_{filter_key}"

            input_left, input_right = st.columns(2)
            with input_left:
                whatif_ci = st.number_input(
                    "What-if Average CI (N·s)",
                    min_value=0.0,
                    value=current_ci,
                    step=1.0,
                    format="%.1f",
                    key=ci_widget_key,
                )
            with input_right:
                whatif_pinch = st.number_input(
                    "What-if Average Pinch Strength",
                    min_value=0.0,
                    value=current_pinch,
                    step=1.0,
                    format="%.1f",
                    key=pinch_widget_key,
                )

            whatif_predicted = (
                combined_model["intercept"]
                + combined_model["beta_ci"] * float(whatif_ci)
                + combined_model["beta_pinch"] * float(whatif_pinch)
            )
            ci_impact = combined_model["beta_ci"] * (float(whatif_ci) - current_ci)
            pinch_impact = combined_model["beta_pinch"] * (
                float(whatif_pinch) - current_pinch
            )
            total_impact = whatif_predicted - current_predicted
            whatif_gap_to_actual = actual_velo - whatif_predicted

            result_cols = st.columns(5)
            result_values = [
                ("Actual Velo", f"{actual_velo:.2f} mph", NAVY_MID),
                ("Current Predicted", f"{current_predicted:.2f} mph", TEAL),
                ("What-If Predicted", f"{whatif_predicted:.2f} mph", ACCENT_RED),
                ("Projected Change", f"{total_impact:+.2f} mph", GREEN),
                ("Actual − What-If", f"{whatif_gap_to_actual:+.2f} mph", BLUE),
            ]
            for column, values in zip(result_cols, result_values):
                with column:
                    st.markdown(metric_card(*values), unsafe_allow_html=True)

            impact_cols = st.columns(4)
            impact_values = [
                ("Current Average CI", f"{current_ci:.1f} N·s", BLUE),
                ("Current Average Pinch", f"{current_pinch:.1f}", TEAL),
                ("CI Contribution", f"{ci_impact:+.2f} mph", BLUE),
                ("Pinch Contribution", f"{pinch_impact:+.2f} mph", TEAL),
            ]
            for column, values in zip(impact_cols, impact_values):
                with column:
                    st.markdown(metric_card(*values), unsafe_allow_html=True)

            st.plotly_chart(
                build_pitcher_whatif_chart(
                    selected_pitcher,
                    actual_velo,
                    current_predicted,
                    whatif_predicted,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    f"predicted_actual_whatif_chart_{player_key}_"
                    f"{float(whatif_ci):.2f}_{float(whatif_pinch):.2f}"
                ),
            )
            st.caption(
                "This is a model-based what-if, not a causal guarantee. It holds "
                "the fitted coefficients constant and changes only CI and pinch."
            )

        with st.container(border=True):
            st.subheader("Predicted vs Actual Table", anchor=False)
            predicted_actual_display = model_data[[
                "athlete", "team", "avg_fb_velo", "predicted_fb_velo",
                "residual_fb_velo", "avg_ci", "avg_pinch_strength",
                "pinch_hand", "ytd_as_of_date",
            ]].copy()
            predicted_actual_display["Model Gap"] = (
                predicted_actual_display["avg_fb_velo"]
                - predicted_actual_display["predicted_fb_velo"]
            )
            predicted_actual_display = predicted_actual_display.drop(
                columns=["residual_fb_velo"]
            )
            predicted_actual_display.columns = [
                "Pitcher", "Team", "Actual Velo", "Predicted Velo",
                "Average CI", "Average Pinch", "Tested Hand", "YTD FB As Of",
                "Actual − Predicted",
            ]
            predicted_actual_display = predicted_actual_display[[
                "Pitcher", "Team", "Actual Velo", "Predicted Velo",
                "Actual − Predicted", "Average CI", "Average Pinch",
                "Tested Hand", "YTD FB As Of",
            ]]
            predicted_actual_display["YTD FB As Of"] = (
                predicted_actual_display["YTD FB As Of"].map(fmt_date)
            )
            predicted_actual_display = predicted_actual_display.sort_values(
                "Actual Velo", ascending=False
            ).reset_index(drop=True)
            st.dataframe(
                predicted_actual_display,
                hide_index=True,
                use_container_width=True,
                height=min(720, 44 + 36 * (len(predicted_actual_display) + 1)),
                column_config={
                    "Actual Velo": st.column_config.NumberColumn(format="%.2f mph"),
                    "Predicted Velo": st.column_config.NumberColumn(format="%.2f mph"),
                    "Actual − Predicted": st.column_config.NumberColumn(format="%+.2f mph"),
                    "Average CI": st.column_config.NumberColumn(format="%.2f N·s"),
                    "Average Pinch": st.column_config.NumberColumn(format="%.2f"),
                },
            )
            csv_download_button(
                predicted_actual_display,
                "Download predicted vs actual CSV",
                "predicted_vs_actual_velo.csv",
                "download_predicted_vs_actual_velo",
            )


with sprint_overview_tab:
    sprint_stats = sprint_correlation_stats(sprint_overview_summary)
    n_sprint_players = len(sprint_overview_summary)
    mean_sprint_speed = (
        sprint_overview_summary["monthly_max_sprint_speed"].mean()
        if n_sprint_players else np.nan
    )
    mean_power_rel = (
        sprint_overview_summary["avg_peak_power_rel"].mean()
        if n_sprint_players else np.nan
    )
    sprint_r_text = f"{sprint_stats[0]:+.2f}" if sprint_stats is not None else "—"
    sprint_r2_text = f"{sprint_stats[1]:.2f}" if sprint_stats is not None else "—"
    potential_sprint_increase = (
        sprint_stats[2] * POTENTIAL_PEAK_POWER_REL_INCREASE
        if sprint_stats is not None else np.nan
    )
    potential_sprint_text = (
        f"{potential_sprint_increase:+.2f} ft/s"
        if pd.notna(potential_sprint_increase) else "—"
    )

    top_cols = st.columns(3)
    for column, values in zip(top_cols, [
        ("Players / Observations", str(n_sprint_players), BLUE),
        ("Correlation", sprint_r_text, ACCENT_RED),
        ("R²", sprint_r2_text, NAVY_MID),
    ]):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    bottom_cols = st.columns(3)
    for column, values in zip(bottom_cols, [
        ("Baserunning Sprint Speed", f"{fmt(mean_sprint_speed)} ft/s", TEAL),
        ("Mean Peak Power / BM", f"{fmt(mean_power_rel)} W/kg", GREEN),
        (f"Sprint-Speed Association · +{POTENTIAL_PEAK_POWER_REL_INCREASE:.0f} W/kg", potential_sprint_text, NAVY_MID),
    ]):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    estimated_sprint_speed = (
        sprint_stats[2] * float(sprint_power_lookup) + sprint_stats[3]
        if sprint_stats is not None else np.nan
    )
    with st.container(border=True):
        st.subheader("Relative Peak Power Lookup", anchor=False)
        lookup_left, lookup_right = st.columns(2)
        with lookup_left:
            st.markdown("<div class='metric-label'>Mean Peak Power / BM</div>", unsafe_allow_html=True)
            st.markdown(
                f"<div class='lookup-value' style='color:#0A1F44;'>{fmt(sprint_power_lookup, 1)} W/kg</div>",
                unsafe_allow_html=True,
            )
        with lookup_right:
            st.markdown("<div class='metric-label'>Estimated Sprint Speed</div>", unsafe_allow_html=True)
            lookup_value = f"{fmt(estimated_sprint_speed)} ft/s" if pd.notna(estimated_sprint_speed) else "—"
            st.markdown(
                f"<div class='lookup-value' style='color:#0D7E8A;'>{lookup_value}</div>",
                unsafe_allow_html=True,
            )
        st.number_input(
            "Peak Power / BM lookup", min_value=0.0, step=1.0, value=60.0,
            format="%.1f", key="sprint_power_lookup",
        )

    with st.container(border=True):
        st.subheader(
            f"{sprint_power_band_stat} Sprint Speed by Peak Power / BM Band",
            anchor=False,
        )
        st.plotly_chart(
            build_sprint_band_chart(
                sprint_overview_summary,
                float(sprint_power_band_width),
                sprint_power_band_stat,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"sprint_power_band_{sprint_power_band_width}_{sprint_power_band_stat}_"
                f"{team_filter}_{start_date}_{end_date}"
            ),
        )
        sprint_band_control_1, sprint_band_control_2 = st.columns(2)
        with sprint_band_control_1:
            st.selectbox(
                "Peak Power / BM band width", [1.0, 2.0, 2.5, 5.0], index=2,
                format_func=lambda x: f"{x:g} W/kg", key="sprint_power_band_width",
            )
        with sprint_band_control_2:
            st.radio(
                "Sprint speed statistic", ["Mean", "Median"], horizontal=True,
                key="sprint_power_band_stat",
            )

    with st.container(border=True):
        st.subheader("Average Peak Power / BM by Sprint Speed Bucket", anchor=False)
        st.plotly_chart(
            build_output_bucket_chart(
                df=sprint_overview_summary,
                output_col="monthly_max_sprint_speed",
                testing_col="avg_peak_power_rel",
                bucket_width=SPRINT_SPEED_OUTPUT_BUCKET_WIDTH,
                output_bucket_label="Sprint speed bucket",
                testing_metric_label="peak power / BM",
                output_axis_title="Baserunning Sprint Speed bucket",
                testing_axis_title="Average Peak Power / BM (W/kg)",
                output_unit="ft/s",
                empty_text="No matched players are available for sprint-speed buckets.",
                color=TEAL,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"sprint_output_bucket_{team_filter}_{start_date}_{end_date}",
        )

    sprint_output_bands = output_bucket_summary(
        sprint_overview_summary,
        "monthly_max_sprint_speed",
        "avg_peak_power_rel",
        SPRINT_SPEED_OUTPUT_BUCKET_WIDTH,
        "Sprint speed bucket",
        "peak power / BM",
        "ft/s",
        "W/kg",
    )
    if not sprint_output_bands.empty:
        sprint_output_options = sprint_output_bands["Sprint speed bucket"].tolist()
        sprint_output_key = "sprint_output_bucket_detail_selector"
        if st.session_state.get(sprint_output_key) not in sprint_output_options:
            st.session_state[sprint_output_key] = sprint_output_options[0]
        with st.container(border=True):
            st.subheader("Sprint Speed Bucket Players", anchor=False)
            selected_sprint_output_bucket = st.selectbox(
                "Sprint speed bucket",
                sprint_output_options,
                key=sprint_output_key,
            )
            st.plotly_chart(
                build_output_bucket_member_chart(
                    df=sprint_overview_summary,
                    output_col="monthly_max_sprint_speed",
                    testing_col="avg_peak_power_rel",
                    bucket_width=SPRINT_SPEED_OUTPUT_BUCKET_WIDTH,
                    selected_bucket=selected_sprint_output_bucket,
                    output_bucket_label="Sprint speed bucket",
                    output_unit="ft/s",
                    testing_axis_title="Average peak power / BM",
                    testing_unit="W/kg",
                    entity_label="Player",
                    output_value_label="Baserunning Sprint Speed",
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"sprint_output_detail_{selected_sprint_output_bucket}_{team_filter}_{start_date}_{end_date}",
            )

    with st.container(border=True):
        st.subheader("Peak Power / BM vs Baserunning Sprint Speed", anchor=False)
        st.plotly_chart(
            build_sprint_scatter(
                sprint_overview_summary,
                sprint_show_labels,
                float(sprint_power_lookup),
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"sprint_scatter_{team_filter}_{start_date}_{end_date}_"
                f"{sprint_show_labels}_{sprint_power_lookup}"
            ),
        )
        st.checkbox("Show names", key="sprint_show_labels")

    sprint_residuals = build_sprint_residual_summary(sprint_overview_summary)
    with st.container(border=True):
        st.subheader("Relative Peak Power → Sprint Speed Residuals", anchor=False)
        if sprint_residuals.empty:
            st.info("Residuals could not be calculated for the current filters.")
        else:
            sprint_residual_mae = float(sprint_residuals["abs_sprint_speed_residual"].mean())
            sprint_residual_rmse = float(np.sqrt(np.mean(sprint_residuals["sprint_speed_residual"] ** 2)))
            sprint_positive = int((sprint_residuals["sprint_speed_residual"] > 0).sum())
            sprint_negative = int((sprint_residuals["sprint_speed_residual"] < 0).sum())

            residual_metric_cols = st.columns(4)
            for column, values in zip(residual_metric_cols, [
                ("Mean Absolute Residual", f"{sprint_residual_mae:.2f} ft/s", TEAL),
                ("Residual RMSE", f"{sprint_residual_rmse:.2f} ft/s", NAVY_MID),
                ("Faster Than Predicted", str(sprint_positive), GREEN),
                ("Slower Than Predicted", str(sprint_negative), ACCENT_RED),
            ]):
                with column:
                    st.markdown(metric_card(*values), unsafe_allow_html=True)

            st.plotly_chart(
                build_sprint_residual_chart(sprint_overview_summary),
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"sprint_residual_chart_{team_filter}_{start_date}_{end_date}_{min_power_jumps}",
            )

            sprint_residual_display = sprint_residuals[[
                "athlete", "team", "avg_peak_power_rel",
                "monthly_max_sprint_speed", "predicted_sprint_speed",
                "sprint_speed_residual", "abs_sprint_speed_residual",
            ]].copy()
            sprint_residual_display.columns = [
                "Player", "Team", "Mean Peak Power / BM",
                "Actual Sprint Speed", "Predicted Sprint Speed",
                "Residual", "Absolute Residual",
            ]
            st.dataframe(
                sprint_residual_display,
                hide_index=True,
                use_container_width=True,
                height=min(660, 44 + 36 * (len(sprint_residual_display) + 1)),
                column_config={
                    "Mean Peak Power / BM": st.column_config.NumberColumn(format="%.2f W/kg"),
                    "Actual Sprint Speed": st.column_config.NumberColumn(format="%.2f ft/s"),
                    "Predicted Sprint Speed": st.column_config.NumberColumn(format="%.2f ft/s"),
                    "Residual": st.column_config.NumberColumn(format="%+.2f ft/s"),
                    "Absolute Residual": st.column_config.NumberColumn(format="%.2f ft/s"),
                },
            )
            csv_download_button(
                sprint_residual_display,
                "Download sprint residuals CSV",
                "relative_peak_power_baserunning_sprint_speed_residuals.csv",
                "download_sprint_residuals",
            )

    with st.container(border=True):
        st.subheader("Player Results", anchor=False)
        if sprint_overview_summary.empty:
            st.info("No matching players.")
        else:
            sprint_display = sprint_overview_summary[[
                "athlete", "team", "monthly_max_sprint_speed",
                "avg_peak_power_rel", "power_jumps", "power_test_dates",
                "first_power_date", "last_power_date",
            ]].copy()
            sprint_display.columns = [
                "Player", "Team", "Baserunning Sprint Speed",
                "Mean Peak Power / BM", "Jump Rows", "Jump Test Dates",
                "First Jump", "Last Jump",
            ]
            for date_col in ["First Jump", "Last Jump"]:
                sprint_display[date_col] = sprint_display[date_col].map(fmt_date)
            st.dataframe(
                sprint_display,
                hide_index=True,
                use_container_width=True,
                height=min(660, 44 + 36 * (len(sprint_display) + 1)),
                column_config={
                    "Baserunning Sprint Speed": st.column_config.NumberColumn(format="%.2f ft/s"),
                    "Mean Peak Power / BM": st.column_config.NumberColumn(format="%.2f W/kg"),
                },
            )
            csv_download_button(
                sprint_display,
                "Download sprint results CSV",
                "relative_peak_power_baserunning_sprint_speed_results.csv",
                "download_sprint_speed_results",
            )


with bat_overview_tab:
    bat_stats = bat_correlation_stats(bat_monthly_pairs)
    n_hitters = len(bat_monthly_pairs)
    mean_bat_speed = (
        bat_monthly_pairs["monthly_avg_bat_speed"].mean()
        if n_hitters else np.nan
    )
    mean_monthly_ci = (
        bat_monthly_pairs["avg_ci"].mean()
        if n_hitters else np.nan
    )
    bat_r_text = (
        f"{bat_stats[0]:+.2f}" if bat_stats is not None else "—"
    )
    bat_r2_text = (
        f"{bat_stats[1]:.2f}" if bat_stats is not None else "—"
    )
    potential_bat_increase = (
        bat_stats[2] * POTENTIAL_CI_INCREASE
        if bat_stats is not None else np.nan
    )
    potential_bat_text = (
        f"{potential_bat_increase:+.2f} mph"
        if pd.notna(potential_bat_increase) else "—"
    )

    top_cols = st.columns(3)
    top_metrics = [
        ("Hitters", str(n_hitters), BLUE),
        ("Correlation", bat_r_text, ACCENT_RED),
        ("R²", bat_r2_text, NAVY_MID),
    ]
    for column, values in zip(top_cols, top_metrics):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    bottom_cols = st.columns(3)
    bottom_metrics = [
        (
            "Monthly Avg Bat Speed",
            f"{fmt(mean_bat_speed)} mph",
            TEAL,
        ),
        (
            "Monthly Average CI",
            f"{fmt(mean_monthly_ci)} N·s",
            GREEN,
        ),
        (
            f"Potential Bat Speed Increase · +{POTENTIAL_CI_INCREASE:.0f} N·s CI",
            potential_bat_text,
            NAVY_MID,
        ),
    ]
    for column, values in zip(bottom_cols, bottom_metrics):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    estimated_bat_speed = (
        bat_stats[2] * float(bat_ci_lookup) + bat_stats[3]
        if bat_stats is not None else np.nan
    )
    with st.container(border=True):
        st.subheader("Monthly CI Lookup", anchor=False)
        lookup_left, lookup_right = st.columns(2)
        with lookup_left:
            st.markdown(
                "<div class='metric-label'>Monthly Average CI</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='lookup-value' style='color:#0A1F44;'>"
                f"{fmt(bat_ci_lookup, 1)} N·s</div>",
                unsafe_allow_html=True,
            )
        with lookup_right:
            st.markdown(
                "<div class='metric-label'>Estimated Monthly Avg Bat Speed</div>",
                unsafe_allow_html=True,
            )
            lookup_value = (
                f"{fmt(estimated_bat_speed)} mph"
                if pd.notna(estimated_bat_speed) else "—"
            )
            st.markdown(
                f"<div class='lookup-value' style='color:#0D7E8A;'>"
                f"{lookup_value}</div>",
                unsafe_allow_html=True,
            )
        st.number_input(
            "CI lookup", min_value=0.0, step=1.0, value=280.0,
            format="%.1f", key="bat_ci_lookup",
        )

    with st.container(border=True):
        st.subheader(
            f"{bat_ci_band_stat} Monthly Bat Speed by CI Band",
            anchor=False,
        )
        st.plotly_chart(
            build_bat_band_chart(
                bat_monthly_pairs,
                int(bat_ci_band_width),
                bat_ci_band_stat,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"bat_ci_band_{bat_ci_band_width}_{bat_ci_band_stat}_"
                f"{team_filter}_{start_date}_{end_date}"
            ),
        )
        bat_band_control_1, bat_band_control_2 = st.columns(2)
        with bat_band_control_1:
            st.selectbox(
                "CI band width", [5, 10, 15, 20], index=1,
                format_func=lambda x: f"{x} N·s", key="bat_ci_band_width",
            )
        with bat_band_control_2:
            st.radio(
                "Bat speed statistic", ["Mean", "Median"], horizontal=True,
                key="bat_ci_band_stat",
            )


    with st.container(border=True):
        st.subheader("Average CI by Bat Speed Bucket", anchor=False)
        st.plotly_chart(
            build_output_bucket_chart(
                df=bat_monthly_pairs,
                output_col="monthly_avg_bat_speed",
                testing_col="avg_ci",
                bucket_width=BAT_SPEED_OUTPUT_BUCKET_WIDTH,
                output_bucket_label="Bat speed bucket",
                testing_metric_label="CI",
                output_axis_title="Monthly average bat speed bucket",
                testing_axis_title="Average CI (N·s)",
                output_unit="mph",
                empty_text="No matched hitters are available for bat-speed buckets.",
                color=TEAL,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"bat_output_bucket_{team_filter}_{start_date}_{end_date}",
        )


    bat_output_bands = output_bucket_summary(
        bat_monthly_pairs,
        "monthly_avg_bat_speed",
        "avg_ci",
        BAT_SPEED_OUTPUT_BUCKET_WIDTH,
        "Bat speed bucket",
        "CI",
        "mph",
        "N·s",
    )
    if not bat_output_bands.empty:
        bat_output_options = bat_output_bands["Bat speed bucket"].tolist()
        bat_output_key = "bat_output_bucket_detail_selector"
        if st.session_state.get(bat_output_key) not in bat_output_options:
            st.session_state[bat_output_key] = bat_output_options[0]
        with st.container(border=True):
            st.subheader("Bat Speed Bucket Hitters", anchor=False)
            selected_bat_output_bucket = st.selectbox(
                "Bat speed bucket",
                bat_output_options,
                key=bat_output_key,
            )
            st.plotly_chart(
                build_output_bucket_member_chart(
                    df=bat_monthly_pairs,
                    output_col="monthly_avg_bat_speed",
                    testing_col="avg_ci",
                    bucket_width=BAT_SPEED_OUTPUT_BUCKET_WIDTH,
                    selected_bucket=selected_bat_output_bucket,
                    output_bucket_label="Bat speed bucket",
                    output_unit="mph",
                    testing_axis_title="Monthly average CI",
                    testing_unit="N·s",
                    entity_label="Hitter",
                    output_value_label="Monthly average bat speed",
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"bat_output_detail_{selected_bat_output_bucket}_{team_filter}_{start_date}_{end_date}",
            )

    bat_ci_band_overview = bat_ci_band_summary(
        bat_monthly_pairs,
        int(bat_ci_band_width),
        bat_ci_band_stat,
    )

    if not bat_ci_band_overview.empty:
        bat_band_options = bat_ci_band_overview["CI band"].tolist()
        bat_band_detail_key = "bat_ci_band_detail_selector"
        if st.session_state.get(bat_band_detail_key) not in bat_band_options:
            st.session_state[bat_band_detail_key] = bat_band_options[0]

        with st.container(border=True):
            st.subheader("CI Band Hitters", anchor=False)
            selected_bat_ci_band = st.selectbox(
                "Hitter CI band",
                bat_band_options,
                key=bat_band_detail_key,
            )
            st.plotly_chart(
                build_bat_ci_band_member_chart(
                    bat_monthly_pairs,
                    int(bat_ci_band_width),
                    selected_bat_ci_band,
                    bat_ci_band_stat,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    f"bat_ci_band_detail_{selected_bat_ci_band}_"
                    f"{bat_ci_band_width}_{bat_ci_band_stat}_{team_filter}_"
                    f"{start_date}_{end_date}"
                ),
            )

    with st.container(border=True):
        st.subheader(
            "Monthly CI vs Monthly Average Bat Speed",
            anchor=False,
        )
        st.plotly_chart(
            build_bat_scatter(
                bat_monthly_pairs,
                bat_show_labels,
                float(bat_ci_lookup),
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"bat_scatter_{team_filter}_{start_date}_{end_date}_"
                f"{bat_show_labels}_{bat_ci_lookup}"
            ),
        )
        st.checkbox("Show names", key="bat_show_labels")

    with st.container(border=True):
        st.subheader("Hitter Results", anchor=False)
        if bat_monthly_pairs.empty:
            st.info("No matching hitters.")
        else:
            bat_display = bat_monthly_pairs[[
                "athlete",
                "team",
                "month",
                "monthly_avg_bat_speed",
                "bat_speed_as_of",
                "avg_ci",
                "ci_jumps",
                "ci_test_dates",
                "first_ci_date",
                "last_ci_date",
            ]].copy()
            bat_display.columns = [
                "Hitter",
                "Team",
                "Month",
                "Monthly Avg Bat Speed",
                "Bat Speed As Of",
                "Monthly Average CI",
                "CI Jumps",
                "CI Test Dates",
                "First CI",
                "Last CI",
            ]
            bat_display["Month"] = (
                pd.to_datetime(bat_display["Month"])
                .dt.strftime("%b %Y")
            )
            for date_col in [
                "Bat Speed As Of", "First CI", "Last CI"
            ]:
                bat_display[date_col] = bat_display[date_col].map(
                    fmt_date
                )
            bat_display["Monthly Avg Bat Speed"] = (
                bat_display["Monthly Avg Bat Speed"].round(2)
            )
            bat_display["Monthly Average CI"] = (
                bat_display["Monthly Average CI"].round(2)
            )
            st.dataframe(
                bat_display,
                hide_index=True,
                use_container_width=True,
                height=min(
                    660,
                    44 + 36 * (len(bat_display) + 1),
                ),
                column_config={
                    "Monthly Avg Bat Speed":
                        st.column_config.NumberColumn(
                            format="%.2f mph"
                        ),
                    "Monthly Average CI":
                        st.column_config.NumberColumn(
                            format="%.2f N·s"
                        ),
                },
            )
            csv_download_button(
                bat_display,
                "Download bat-speed results CSV",
                "bat_speed_results.csv",
                "download_bat_speed_results",
            )

with exit_velo_overview_tab:
    exit_stats = exit_velo_correlation_stats(exit_velo_summary)
    n_exit_hitters = len(exit_velo_summary)
    mean_exit_velo = (
        exit_velo_summary["p90_exit_velo"].mean()
        if n_exit_hitters else np.nan
    )
    mean_yearly_ci = (
        exit_velo_summary["avg_ci"].mean()
        if n_exit_hitters else np.nan
    )
    exit_r_text = (
        f"{exit_stats[0]:+.2f}" if exit_stats is not None else "—"
    )
    exit_r2_text = (
        f"{exit_stats[1]:.2f}" if exit_stats is not None else "—"
    )
    potential_exit_increase = (
        exit_stats[2] * POTENTIAL_CI_INCREASE
        if exit_stats is not None else np.nan
    )
    potential_exit_text = (
        f"{potential_exit_increase:+.2f} mph"
        if pd.notna(potential_exit_increase) else "—"
    )

    top_cols = st.columns(3)
    for column, values in zip(top_cols, [
        ("Hitters", str(n_exit_hitters), BLUE),
        ("Correlation", exit_r_text, ACCENT_RED),
        ("R²", exit_r2_text, NAVY_MID),
    ]):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    bottom_cols = st.columns(3)
    for column, values in zip(bottom_cols, [
        (
            "P90 Exit Velo",
            f"{fmt(mean_exit_velo)} mph",
            TEAL,
        ),
        (
            "Year-to-Date Average CI",
            f"{fmt(mean_yearly_ci)} N·s",
            GREEN,
        ),
        (
            f"Potential Exit Velo Increase · +{POTENTIAL_CI_INCREASE:.0f} N·s CI",
            potential_exit_text,
            NAVY_MID,
        ),
    ]):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    estimated_exit_velo = (
        exit_stats[2] * float(exit_ci_lookup) + exit_stats[3]
        if exit_stats is not None else np.nan
    )
    with st.container(border=True):
        st.subheader("Year-to-Date CI Lookup", anchor=False)
        lookup_left, lookup_right = st.columns(2)
        with lookup_left:
            st.markdown(
                "<div class='metric-label'>Year-to-Date Average CI</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='lookup-value' style='color:#0A1F44;'>"
                f"{fmt(exit_ci_lookup, 1)} N·s</div>",
                unsafe_allow_html=True,
            )
        with lookup_right:
            st.markdown(
                "<div class='metric-label'>Estimated P90 Exit Velo</div>",
                unsafe_allow_html=True,
            )
            lookup_value = (
                f"{fmt(estimated_exit_velo)} mph"
                if pd.notna(estimated_exit_velo) else "—"
            )
            st.markdown(
                f"<div class='lookup-value' style='color:#0D7E8A;'>"
                f"{lookup_value}</div>",
                unsafe_allow_html=True,
            )
        st.number_input(
            "CI lookup", min_value=0.0, step=1.0, value=280.0,
            format="%.1f", key="exit_ci_lookup",
        )

    with st.container(border=True):
        st.subheader(
            f"{exit_ci_band_stat} P90 Exit Velo by CI Band",
            anchor=False,
        )
        st.plotly_chart(
            build_exit_velo_band_chart(
                exit_velo_summary,
                int(exit_ci_band_width),
                exit_ci_band_stat,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"exit_ci_band_{exit_ci_band_width}_{exit_ci_band_stat}_"
                f"{team_filter}_{start_date}_{end_date}"
            ),
        )
        exit_band_control_1, exit_band_control_2 = st.columns(2)
        with exit_band_control_1:
            st.selectbox(
                "CI band width", [5, 10, 15, 20], index=1,
                format_func=lambda x: f"{x} N·s", key="exit_ci_band_width",
            )
        with exit_band_control_2:
            st.radio(
                "P90 exit velo statistic", ["Mean", "Median"], horizontal=True,
                key="exit_ci_band_stat",
            )


    with st.container(border=True):
        st.subheader("Average CI by P90 Exit Velo Bucket", anchor=False)
        st.plotly_chart(
            build_output_bucket_chart(
                df=exit_velo_summary,
                output_col="p90_exit_velo",
                testing_col="avg_ci",
                bucket_width=EXIT_VELO_OUTPUT_BUCKET_WIDTH,
                output_bucket_label="P90 exit velo bucket",
                testing_metric_label="CI",
                output_axis_title="P90 exit velo bucket",
                testing_axis_title="Average CI (N·s)",
                output_unit="mph",
                empty_text="No matched hitters are available for P90 exit-velo buckets.",
                color=TEAL,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"exit_output_bucket_{team_filter}_{start_date}_{end_date}",
        )


    exit_output_bands = output_bucket_summary(
        exit_velo_summary,
        "p90_exit_velo",
        "avg_ci",
        EXIT_VELO_OUTPUT_BUCKET_WIDTH,
        "P90 exit velo bucket",
        "CI",
        "mph",
        "N·s",
    )
    if not exit_output_bands.empty:
        exit_output_options = exit_output_bands["P90 exit velo bucket"].tolist()
        exit_output_key = "exit_output_bucket_detail_selector"
        if st.session_state.get(exit_output_key) not in exit_output_options:
            st.session_state[exit_output_key] = exit_output_options[0]
        with st.container(border=True):
            st.subheader("P90 Exit Velo Bucket Hitters", anchor=False)
            selected_exit_output_bucket = st.selectbox(
                "P90 exit velo bucket",
                exit_output_options,
                key=exit_output_key,
            )
            st.plotly_chart(
                build_output_bucket_member_chart(
                    df=exit_velo_summary,
                    output_col="p90_exit_velo",
                    testing_col="avg_ci",
                    bucket_width=EXIT_VELO_OUTPUT_BUCKET_WIDTH,
                    selected_bucket=selected_exit_output_bucket,
                    output_bucket_label="P90 exit velo bucket",
                    output_unit="mph",
                    testing_axis_title="Year-to-date average CI",
                    testing_unit="N·s",
                    entity_label="Hitter",
                    output_value_label="P90 exit velo",
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"exit_output_detail_{selected_exit_output_bucket}_{team_filter}_{start_date}_{end_date}",
            )

    exit_band_overview = exit_velo_ci_band_summary(
        exit_velo_summary,
        int(exit_ci_band_width),
        exit_ci_band_stat,
    )
    if not exit_band_overview.empty:
        exit_band_options = exit_band_overview["CI band"].tolist()
        exit_band_detail_key = "exit_ci_band_detail_selector"
        if st.session_state.get(exit_band_detail_key) not in exit_band_options:
            st.session_state[exit_band_detail_key] = exit_band_options[0]

        with st.container(border=True):
            st.subheader("CI Band Hitters", anchor=False)
            selected_exit_ci_band = st.selectbox(
                "Exit-velocity CI band",
                exit_band_options,
                key=exit_band_detail_key,
            )
            st.plotly_chart(
                build_exit_velo_ci_band_member_chart(
                    exit_velo_summary,
                    int(exit_ci_band_width),
                    selected_exit_ci_band,
                    exit_ci_band_stat,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    f"exit_ci_band_detail_{selected_exit_ci_band}_"
                    f"{exit_ci_band_width}_{exit_ci_band_stat}_{team_filter}_"
                    f"{start_date}_{end_date}"
                ),
            )

    with st.container(border=True):
        st.subheader(
            "Year-to-Date Average CI vs P90 Exit Velo",
            anchor=False,
        )
        st.plotly_chart(
            build_exit_velo_scatter(
                exit_velo_summary,
                exit_show_labels,
                float(exit_ci_lookup),
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"exit_scatter_{team_filter}_{start_date}_{end_date}_"
                f"{exit_show_labels}_{exit_ci_lookup}"
            ),
        )
        st.checkbox("Show names", key="exit_show_labels")

    with st.container(border=True):
        st.subheader("Hitter Results", anchor=False)
        if exit_velo_summary.empty:
            st.info("No matching hitters.")
        else:
            exit_display = exit_velo_summary[[
                "athlete",
                "team",
                "year",
                "p90_exit_velo",
                "exit_velo_as_of",
                "exit_velo_records",
                "avg_ci",
                "ci_jumps",
                "ci_test_dates",
                "first_ci_date",
                "last_ci_date",
            ]].copy()
            exit_display.columns = [
                "Hitter",
                "Team",
                "Year",
                "P90 Exit Velo",
                "CI Through",
                "Exit Velo Records",
                "Year-to-Date Average CI",
                "CI Jumps",
                "CI Test Dates",
                "First CI",
                "Last CI",
            ]
            for date_col in ["CI Through", "First CI", "Last CI"]:
                exit_display[date_col] = exit_display[date_col].map(fmt_date)
            exit_display["P90 Exit Velo"] = (
                exit_display["P90 Exit Velo"].round(2)
            )
            exit_display["Year-to-Date Average CI"] = (
                exit_display["Year-to-Date Average CI"].round(2)
            )
            st.dataframe(
                exit_display,
                hide_index=True,
                use_container_width=True,
                height=min(660, 44 + 36 * (len(exit_display) + 1)),
                column_config={
                    "P90 Exit Velo":
                        st.column_config.NumberColumn(format="%.2f mph"),
                    "Year-to-Date Average CI":
                        st.column_config.NumberColumn(format="%.2f N·s"),
                },
            )
            csv_download_button(
                exit_display,
                "Download P90 exit-velo results CSV",
                "p90_exit_velo_results.csv",
                "download_p90_exit_velo_results",
            )




with if_reaction_power_tab:
    render_selected_peak_power_rel_tab(
        if_reaction_power_summary,
        outcome_col="if_reaction_3ft",
        outcome_label="IF Reaction 3ft",
        outcome_unit="s",
        tab_key="if_reaction_3ft_peak_power_rel",
        default_lookup=60.0,
        default_bucket_width=0.05,
    )

with sprint_nbsr_tab:
    render_sprint_nbsr_tab(sprint_nbsr_summary)

with sprint_adv_runs_tab:
    render_sprint_outcome_tab(
        sprint_adv_runs_summary,
        outcome_col="adv_runs",
        outcome_label="Adv Runs",
        tab_key="sprint_adv_runs",
        default_bucket_width=0.5,
    )


with sc_opportunity_tab:
    st.subheader("S&C Opportunity — Pitchers", anchor=False)
    if combined_model is None:
        st.info(
            "The combined overview model could not be fit, so the pitcher "
            "opportunity tables are unavailable for the current filters."
        )
    else:
        st.markdown(
            metric_card("Combined-model pitchers", str(len(combined_model["data"])), BLUE),
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.subheader("S&C Development Flags", anchor=False)
            toggle_cols = st.columns(3)
            with toggle_cols[0]:
                dev_use_ci = st.checkbox("Require low CI", value=True, key="dev_use_ci")
                dev_ci_threshold = st.slider("Maximum CI", 220.0, 360.0, 300.0, 5.0, key="sc_dev_ci_slider")
            with toggle_cols[1]:
                dev_use_pinch = st.checkbox("Require low pinch", value=True, key="dev_use_pinch")
                dev_pinch_threshold = st.slider("Maximum pinch strength", 20.0, 65.0, 40.0, 1.0, key="sc_dev_pinch_slider")
            with toggle_cols[2]:
                dev_use_projected = st.checkbox("Require low projected velo", value=True, key="dev_use_projected")
                dev_projected_velo_threshold = st.slider("Maximum projected FB velo", 85.0, 100.0, 94.0, 0.5, key="sc_dev_projected_velo_slider")
            extra_cols = st.columns(2)
            with extra_cols[0]:
                dev_use_actual = st.checkbox("Also require low actual velo", value=False, key="dev_use_actual")
                dev_actual_max = st.slider("Maximum actual FB velo", 85.0, 100.0, 94.0, 0.5, key="dev_actual_max")
            with extra_cols[1]:
                dev_use_residual = st.checkbox("Also require negative residual", value=False, key="dev_use_residual")
                dev_residual_max = st.slider("Maximum residual", -5.0, 2.0, -0.5, 0.1, key="dev_residual_max")
            sc_upside_table = build_pitcher_custom_category(combined_model, [
                {"enabled": dev_use_ci, "column": "avg_ci", "operator": "lt", "value": dev_ci_threshold, "label": "CI", "decimals": 0},
                {"enabled": dev_use_pinch, "column": "avg_pinch_strength", "operator": "lt", "value": dev_pinch_threshold, "label": "Pinch", "decimals": 0},
                {"enabled": dev_use_projected, "column": "predicted_fb_velo", "operator": "lt", "value": dev_projected_velo_threshold, "label": "Projected FB velo", "unit": " mph"},
                {"enabled": dev_use_actual, "column": "avg_fb_velo", "operator": "lt", "value": dev_actual_max, "label": "Actual FB velo", "unit": " mph"},
                {"enabled": dev_use_residual, "column": "residual_fb_velo", "operator": "le", "value": dev_residual_max, "label": "Residual", "unit": " mph"},
            ])
            st.caption(f"{len(sc_upside_table)} pitchers meet all enabled criteria.")
            if sc_upside_table.empty:
                st.info("No pitchers met the enabled S&C development criteria.")
            else:
                upside_display = sc_upside_table.copy()
                upside_display.columns = ["Pitcher", "Team", "Actual Final YTD FB Velo", "Predicted FB Velo", "Residual", "Average CI", "Average Pinch", "Tested Hand", "YTD FB As Of", "CI Jumps", "Pinch Tests", "Reasons"]
                upside_display["YTD FB As Of"] = upside_display["YTD FB As Of"].map(fmt_date)
                st.dataframe(upside_display, hide_index=True, use_container_width=True, height=min(660, 44 + 36 * (len(upside_display) + 1)), column_config={
                    "Actual Final YTD FB Velo": st.column_config.NumberColumn(format="%.2f mph"), "Predicted FB Velo": st.column_config.NumberColumn(format="%.2f mph"), "Residual": st.column_config.NumberColumn(format="%+.2f mph"), "Average CI": st.column_config.NumberColumn(format="%.2f N·s"), "Average Pinch": st.column_config.NumberColumn(format="%.2f")})
                csv_download_button(upside_display, "Download S&C development flags CSV", "sc_development_flags.csv", "download_sc_upside_pitchers")

        def render_projection_gap_section(title, prefix, default_cutoff):
            with st.container(border=True):
                st.subheader(title, anchor=False)
                cols = st.columns(4)
                with cols[0]:
                    use_projected = st.checkbox("Require projected velo", value=True, key=f"{prefix}_use_projected")
                    projected_min = st.slider("Minimum projected FB velo", 85.0, 100.0, float(default_cutoff), 0.5, key=f"{prefix}_projected_min")
                with cols[1]:
                    use_actual = st.checkbox("Require actual velo", value=True, key=f"{prefix}_use_actual")
                    actual_max = st.slider("Maximum actual FB velo", 85.0, 100.0, float(default_cutoff), 0.5, key=f"{prefix}_actual_max")
                with cols[2]:
                    use_ci = st.checkbox("Also require low CI", value=False, key=f"{prefix}_use_ci")
                    ci_max = st.slider("Maximum CI", 220.0, 380.0, 300.0, 5.0, key=f"{prefix}_ci_max")
                with cols[3]:
                    use_pinch = st.checkbox("Also require low pinch", value=False, key=f"{prefix}_use_pinch")
                    pinch_max = st.slider("Maximum pinch", 20.0, 65.0, 40.0, 1.0, key=f"{prefix}_pinch_max")
                table = build_pitcher_custom_category(combined_model, [
                    {"enabled": use_projected, "column": "predicted_fb_velo", "operator": "ge", "value": projected_min, "label": "Projected FB velo", "unit": " mph"},
                    {"enabled": use_actual, "column": "avg_fb_velo", "operator": "lt", "value": actual_max, "label": "Actual FB velo", "unit": " mph"},
                    {"enabled": use_ci, "column": "avg_ci", "operator": "lt", "value": ci_max, "label": "CI", "decimals": 0},
                    {"enabled": use_pinch, "column": "avg_pinch_strength", "operator": "lt", "value": pinch_max, "label": "Pinch", "decimals": 0},
                ])
                st.caption(f"{len(table)} pitchers meet all enabled criteria.")
                if table.empty:
                    st.info("No pitchers met the enabled criteria.")
                else:
                    display = table.copy()
                    display.columns = ["Pitcher", "Team", "Actual Final YTD FB Velo", "Predicted FB Velo", "Residual", "Average CI", "Average Pinch", "Tested Hand", "YTD FB As Of", "CI Jumps", "Pinch Tests", "Reasons"]
                    display["YTD FB As Of"] = display["YTD FB As Of"].map(fmt_date)
                    st.dataframe(display, hide_index=True, use_container_width=True, height=min(660, 44 + 36 * (len(display) + 1)), column_config={
                        "Actual Final YTD FB Velo": st.column_config.NumberColumn(format="%.2f mph"), "Predicted FB Velo": st.column_config.NumberColumn(format="%.2f mph"), "Residual": st.column_config.NumberColumn(format="%+.2f mph"), "Average CI": st.column_config.NumberColumn(format="%.2f N·s"), "Average Pinch": st.column_config.NumberColumn(format="%.2f")})
                    csv_download_button(display, "Download projected-versus-actual CSV", f"{prefix}_pitchers.csv", f"download_{prefix}_pitchers")

        render_projection_gap_section("Projected-Velo Opportunity — 94 mph Setup", "gap94", 94.0)
        render_projection_gap_section("Projected-Velo Opportunity — 93 mph Setup", "gap93", 93.0)

        with st.container(border=True):
            st.subheader("They Need to Get Better at Throwing", anchor=False)
            cols = st.columns(3)
            with cols[0]:
                throwing_use_ci = st.checkbox("Require high CI", value=True, key="throwing_use_ci")
                throwing_ci_threshold = st.slider("Minimum CI", 250.0, 400.0, 330.0, 5.0, key="throwing_ci_slider")
            with cols[1]:
                throwing_use_residual = st.checkbox("Require negative residual", value=True, key="throwing_use_residual")
                throwing_residual_threshold = st.slider("Maximum velocity residual", -5.0, 0.0, -0.5, 0.1, key="throwing_residual_slider")
            with cols[2]:
                throwing_use_pinch = st.checkbox("Also require minimum pinch", value=False, key="throwing_use_pinch")
                throwing_pinch_threshold = st.slider("Minimum pinch strength", 20.0, 65.0, 40.0, 1.0, key="throwing_pinch_slider")
            sc_throwing_table = build_pitcher_custom_category(combined_model, [
                {"enabled": throwing_use_ci, "column": "avg_ci", "operator": "gt", "value": throwing_ci_threshold, "label": "CI", "decimals": 0},
                {"enabled": throwing_use_residual, "column": "residual_fb_velo", "operator": "le", "value": throwing_residual_threshold, "label": "Residual", "unit": " mph"},
                {"enabled": throwing_use_pinch, "column": "avg_pinch_strength", "operator": "ge", "value": throwing_pinch_threshold, "label": "Pinch", "decimals": 0},
            ])
            st.caption(f"{len(sc_throwing_table)} pitchers meet all enabled criteria.")
            if sc_throwing_table.empty:
                st.info("No pitchers met the enabled throwing-development criteria.")
            else:
                throwing_display = sc_throwing_table.copy()
                throwing_display.columns = ["Pitcher", "Team", "Actual Final YTD FB Velo", "Predicted FB Velo", "Residual", "Average CI", "Average Pinch", "Tested Hand", "YTD FB As Of", "CI Jumps", "Pinch Tests", "Reasons"]
                throwing_display["YTD FB As Of"] = throwing_display["YTD FB As Of"].map(fmt_date)
                st.dataframe(throwing_display, hide_index=True, use_container_width=True, height=min(660, 44 + 36 * (len(throwing_display) + 1)), column_config={
                    "Actual Final YTD FB Velo": st.column_config.NumberColumn(format="%.2f mph"), "Predicted FB Velo": st.column_config.NumberColumn(format="%.2f mph"), "Residual": st.column_config.NumberColumn(format="%+.2f mph"), "Average CI": st.column_config.NumberColumn(format="%.2f N·s"), "Average Pinch": st.column_config.NumberColumn(format="%.2f")})
                csv_download_button(throwing_display, "Download throwing-development CSV", "throwing_development_pitchers.csv", "download_throwing_development_pitchers")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.subheader("S&C Opportunity — Hitters", anchor=False)
    hitter_base = build_hitter_opportunity_base(bat_monthly_pairs, exit_velo_summary)

    with st.container(border=True):
        st.subheader("Hitters Needing More S&C Work", anchor=False)
        mode = st.radio("How should enabled criteria combine?", ["Any enabled criterion", "All enabled criteria"], horizontal=True, key="hitter_sc_mode")
        cols = st.columns(4)
        with cols[0]:
            use_month_ci = st.checkbox("Use monthly CI", value=True, key="hsc_use_month_ci")
            month_ci_max = st.slider("Maximum monthly CI", 220.0, 360.0, 300.0, 5.0, key="hsc_month_ci")
        with cols[1]:
            use_ytd_ci = st.checkbox("Use YTD CI", value=True, key="hsc_use_ytd_ci")
            ytd_ci_max = st.slider("Maximum YTD CI", 220.0, 360.0, 300.0, 5.0, key="hsc_ytd_ci")
        with cols[2]:
            use_bat_speed = st.checkbox("Also use bat speed", value=False, key="hsc_use_bat")
            bat_speed_max = st.slider("Maximum monthly bat speed", 55.0, 85.0, 70.0, 0.5, key="hsc_bat_max")
        with cols[3]:
            use_exit = st.checkbox("Also use P90 exit velo", value=False, key="hsc_use_exit")
            exit_max = st.slider("Maximum P90 exit velo", 75.0, 110.0, 95.0, 0.5, key="hsc_exit_max")
        hitter_sc_table = filter_hitter_custom_category(hitter_base, [
            {"enabled": use_month_ci, "column": "monthly_avg_ci", "operator": "lt", "value": month_ci_max, "label": "Monthly CI", "decimals": 0},
            {"enabled": use_ytd_ci, "column": "ytd_avg_ci", "operator": "lt", "value": ytd_ci_max, "label": "YTD CI", "decimals": 0},
            {"enabled": use_bat_speed, "column": "monthly_avg_bat_speed", "operator": "lt", "value": bat_speed_max, "label": "Bat speed", "unit": " mph"},
            {"enabled": use_exit, "column": "p90_exit_velo", "operator": "lt", "value": exit_max, "label": "P90 exit velo", "unit": " mph"},
        ], mode="any" if mode.startswith("Any") else "all")
        st.caption(f"{len(hitter_sc_table)} hitters meet the enabled criteria.")
        if hitter_sc_table.empty:
            st.info("No hitters met the enabled S&C-development criteria.")
        else:
            hitter_sc_display = hitter_sc_table.copy()
            hitter_sc_display.columns = ["Hitter", "Team", "Bat-Speed Month", "Monthly Average CI", "Monthly Avg Bat Speed", "Projected Bat Speed", "Bat-Speed Residual", "CI Through", "YTD Average CI", "P90 Exit Velo", "Projected P90 Exit Velo", "P90 Exit-Velo Residual", "Reasons"]
            hitter_sc_display["Bat-Speed Month"] = pd.to_datetime(hitter_sc_display["Bat-Speed Month"], errors="coerce").dt.strftime("%b %Y")
            hitter_sc_display["CI Through"] = hitter_sc_display["CI Through"].map(fmt_date)
            st.dataframe(hitter_sc_display, hide_index=True, use_container_width=True, height=min(660, 44 + 36 * (len(hitter_sc_display) + 1)), column_config={
                "Monthly Average CI": st.column_config.NumberColumn(format="%.2f N·s"), "Monthly Avg Bat Speed": st.column_config.NumberColumn(format="%.2f mph"), "Projected Bat Speed": st.column_config.NumberColumn(format="%.2f mph"), "Bat-Speed Residual": st.column_config.NumberColumn(format="%+.2f mph"), "YTD Average CI": st.column_config.NumberColumn(format="%.2f N·s"), "P90 Exit Velo": st.column_config.NumberColumn(format="%.2f mph"), "Projected P90 Exit Velo": st.column_config.NumberColumn(format="%.2f mph"), "P90 Exit-Velo Residual": st.column_config.NumberColumn(format="%+.2f mph")})
            csv_download_button(hitter_sc_display, "Download hitter S&C development CSV", "hitter_sc_development.csv", "download_hitter_sc_development")

    with st.container(border=True):
        st.subheader("Hitters Underperforming Their CI", anchor=False)
        pathway_mode = st.radio("How should the bat-speed and P90 pathways combine?", ["Either pathway", "Both pathways"], horizontal=True, key="hitter_under_path_mode")
        pathway_cols = st.columns(2)
        with pathway_cols[0]:
            st.markdown("**Bat-speed pathway**")
            use_bat_path = st.checkbox("Enable bat-speed pathway", value=True, key="hu_use_bat_path")
            bat_require_ci = st.checkbox("Require minimum monthly CI", value=True, key="hu_bat_require_ci")
            bat_ci_min = st.slider("Minimum monthly CI", 220.0, 380.0, 300.0, 5.0, key="hu_bat_ci_min")
            bat_require_residual = st.checkbox("Require negative bat-speed residual", value=True, key="hu_bat_require_resid")
            bat_resid_max = st.slider("Maximum bat-speed residual", -5.0, 1.0, -1.0, 0.1, key="hu_bat_resid_max")
        with pathway_cols[1]:
            st.markdown("**P90 exit-velo pathway**")
            use_exit_path = st.checkbox("Enable P90 pathway", value=True, key="hu_use_exit_path")
            exit_require_ci = st.checkbox("Require minimum YTD CI", value=True, key="hu_exit_require_ci")
            exit_ci_min = st.slider("Minimum YTD CI", 220.0, 380.0, 300.0, 5.0, key="hu_exit_ci_min")
            exit_require_residual = st.checkbox("Require negative P90 residual", value=True, key="hu_exit_require_resid")
            exit_resid_max = st.slider("Maximum P90 residual", -5.0, 1.0, -1.0, 0.1, key="hu_exit_resid_max")
        hitter_underperforming_ci_table = filter_hitter_underperformance_pathways(
            hitter_base, use_bat_path, bat_require_ci, bat_ci_min, bat_require_residual, bat_resid_max,
            use_exit_path, exit_require_ci, exit_ci_min, exit_require_residual, exit_resid_max,
            pathway_mode="any" if pathway_mode.startswith("Either") else "all",
        )
        st.caption(f"{len(hitter_underperforming_ci_table)} hitters meet the enabled underperformance pathways.")
        if hitter_underperforming_ci_table.empty:
            st.info("No hitters met the enabled CI-underperformance criteria.")
        else:
            hitter_under_display = hitter_underperforming_ci_table.copy()
            hitter_under_display.columns = ["Hitter", "Team", "Bat-Speed Month", "Monthly Average CI", "Monthly Avg Bat Speed", "Projected Bat Speed", "Bat-Speed Residual", "CI Through", "YTD Average CI", "P90 Exit Velo", "Projected P90 Exit Velo", "P90 Exit-Velo Residual", "Reasons"]
            hitter_under_display["Bat-Speed Month"] = pd.to_datetime(hitter_under_display["Bat-Speed Month"], errors="coerce").dt.strftime("%b %Y")
            hitter_under_display["CI Through"] = hitter_under_display["CI Through"].map(fmt_date)
            st.dataframe(hitter_under_display, hide_index=True, use_container_width=True, height=min(660, 44 + 36 * (len(hitter_under_display) + 1)), column_config={
                "Monthly Average CI": st.column_config.NumberColumn(format="%.2f N·s"), "Monthly Avg Bat Speed": st.column_config.NumberColumn(format="%.2f mph"), "Projected Bat Speed": st.column_config.NumberColumn(format="%.2f mph"), "Bat-Speed Residual": st.column_config.NumberColumn(format="%+.2f mph"), "YTD Average CI": st.column_config.NumberColumn(format="%.2f N·s"), "P90 Exit Velo": st.column_config.NumberColumn(format="%.2f mph"), "Projected P90 Exit Velo": st.column_config.NumberColumn(format="%.2f mph"), "P90 Exit-Velo Residual": st.column_config.NumberColumn(format="%+.2f mph")})
            csv_download_button(hitter_under_display, "Download hitters underperforming CI CSV", "hitters_underperforming_ci.csv", "download_hitters_underperforming_ci")
