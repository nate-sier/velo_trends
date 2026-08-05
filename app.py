"""
Performance × CI — Streamlit deployment-ready dashboard.

Pitching:
  * Last in-window ytd_fb_velo matched to mean in-window raw CI.
  * Pitchers below 85 mph are excluded.

Pinch grip:
  * Pinch Grip tab uses Name, Date, Pinch - R, and Pinch - L.
  * Each row contributes the one populated hand as that athlete's pinch value.
  * In-window pinch tests are matched to the same last in-window ytd_fb_velo.

Hitting:
  * One final monthly_avg_bat_speed value per hitter-month.
  * Mean raw CI from the same calendar month.
  * Cross-sectional and within-individual monthly analysis.
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
DEFAULT_BAT_TAB = "PP_Sprint"
DEFAULT_PINCH_TAB = "Pinch Grip"
LOCAL_SERVICE_ACCOUNT_FILE = Path.home() / "Desktop" / "service_account.json"
MIN_LAST_YTD_FB_VELO = 85.0
POTENTIAL_CI_INCREASE = 10.0

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
def load_source_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Load and normalize Jump Data, FB Velo, Pinch Grip, and bat-speed data."""
    sheet_id = secret_or_default("SHEET_ID", DEFAULT_SHEET_ID)
    jump_tab = secret_or_default("JUMP_TAB", DEFAULT_JUMP_TAB)
    velo_tab = secret_or_default("VELO_TAB", DEFAULT_VELO_TAB)
    bat_tab = secret_or_default("BAT_TAB", DEFAULT_BAT_TAB)
    pinch_tab = secret_or_default("PINCH_TAB", DEFAULT_PINCH_TAB)

    creds = get_credentials()
    client = gspread.authorize(creds)
    jump_raw = read_tab(client, sheet_id, jump_tab)
    velo_raw = read_tab(client, sheet_id, velo_tab)
    bat_raw = read_tab(client, sheet_id, bat_tab)
    pinch_raw = read_tab(client, sheet_id, pinch_tab)

    if jump_raw.empty:
        raise ValueError(f"The '{jump_tab}' tab did not return any rows.")
    if velo_raw.empty:
        raise ValueError(f"The '{velo_tab}' tab did not return any rows.")
    if bat_raw.empty:
        raise ValueError(f"The '{bat_tab}' tab did not return any rows.")
    if pinch_raw.empty:
        raise ValueError(f"The '{pinch_tab}' tab did not return any rows.")

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

    status = (
        f"Loaded {len(jump):,} Jump Data rows, {len(velo):,} FB Velo rows, "
        f"{len(pinch):,} Pinch Grip rows, and {len(bat):,} hitter-month "
        f"bat-speed rows · {datetime.now().strftime('%I:%M %p').lstrip('0')}"
    )
    return jump, velo, bat, pinch, status


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
    work["band_start"] = np.floor(work["avg_ci"] / width) * width
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
    grouped["CI band"] = grouped["band_start"].map(lambda lower: f"{lower:.0f}–{lower + width:.0f} N·s")
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
    detail["band_start"] = np.floor(detail["avg_ci"] / width) * width
    detail["CI band"] = detail["band_start"].map(
        lambda lower: f"{lower:.0f}–{lower + width:.0f} N·s"
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
    """Match calendar-month CI averages to monthly_avg_bat_speed."""
    start_month = pd.Timestamp(start_date).to_period("M").start_time.normalize()
    end_month = pd.Timestamp(end_date).to_period("M").start_time.normalize()

    jump_monthly = jump.copy()
    jump_monthly["month"] = jump_monthly["date"].dt.to_period("M").dt.to_timestamp()
    jump_monthly = jump_monthly[
        (jump_monthly["month"] >= start_month)
        & (jump_monthly["month"] <= end_month)
    ]
    ci_monthly = (
        jump_monthly.groupby(["name_key", "month"], as_index=False)
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

    bat_window = bat[
        (bat["month"] >= start_month) & (bat["month"] <= end_month)
    ].copy()
    pairs = ci_monthly.merge(
        bat_window, on=["name_key", "month"], how="inner"
    )
    pairs = pairs.merge(team_lookup, on="name_key", how="left")
    pairs["team"] = pairs["current_team"].combine_first(pairs["team"])
    pairs = pairs.drop(columns=["current_team"])
    pairs["team"] = pairs["team"].fillna("Unassigned")
    pairs = pairs[
        pairs["ci_jumps"] >= max(1, int(min_ci_jumps))
    ].copy()

    if team_filter != "All Teams":
        pairs = pairs[pairs["team"] == team_filter].copy()

    pairs["month_label"] = pairs["month"].dt.strftime("%b %Y")
    pairs["observation"] = (
        pairs["athlete"] + " · " + pairs["month_label"]
    )
    return pairs.sort_values(
        ["month", "athlete"], kind="stable"
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
            columns=[
                "CI band", speed_col, "Hitter-Months", "Hitters", "Average CI"
            ]
        )

    width = max(1, int(band_width))
    work = pairs[
        ["name_key", "avg_ci", "monthly_avg_bat_speed"]
    ].dropna().copy()
    work["band_start"] = np.floor(work["avg_ci"] / width) * width
    grouped = (
        work.groupby("band_start", as_index=False)
        .agg(
            **{
                speed_col: (
                    "monthly_avg_bat_speed",
                    "median" if stat == "Median" else "mean",
                ),
                "Hitter-Months": ("monthly_avg_bat_speed", "count"),
                "Hitters": ("name_key", "nunique"),
                "Average CI": ("avg_ci", "mean"),
            }
        )
        .sort_values("band_start")
    )
    grouped["CI band"] = grouped["band_start"].map(
        lambda lower: f"{lower:.0f}–{lower + width:.0f} N·s"
    )
    grouped[speed_col] = grouped[speed_col].round(2)
    grouped["Average CI"] = grouped["Average CI"].round(2)
    return grouped[
        ["CI band", speed_col, "Hitter-Months", "Hitters", "Average CI"]
    ]


def build_bat_scatter(
    pairs: pd.DataFrame,
    show_labels: bool,
    ci_lookup: float | None,
) -> go.Figure:
    fig = go.Figure()
    if pairs.empty:
        fig.add_annotation(
            text="No matched hitter-months meet the selected rules.",
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
            text="No matched hitter-months are available for CI bands.",
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
            bands["Hitter-Months"],
            bands["Hitters"],
            bands["Average CI"],
        ]),
        hovertemplate=(
            f"<b>%{{x}}</b><br>{stat} monthly bat speed: %{{y:.2f}} mph<br>"
            "Hitter-months: %{customdata[0]}<br>"
            "Hitters: %{customdata[1]}<br>"
            "Mean CI within band: %{customdata[2]:.2f} N·s"
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
    """Match in-window pinch-grip averages to last in-window YTD FB velo."""
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
    value_col: str,
) -> tuple[float, float, float, float] | None:
    work = summary[[value_col, "avg_fb_velo"]].dropna()
    if len(work) < 2:
        return None
    x = work[value_col].to_numpy(dtype=float)
    y = work["avg_fb_velo"].to_numpy(dtype=float)
    if np.isclose(np.std(x), 0) or np.isclose(np.std(y), 0):
        return None
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return r, r * r, float(slope), float(intercept)


def build_pinch_scatter(
    summary: pd.DataFrame,
    show_labels: bool,
) -> go.Figure:
    value_col = "avg_pinch_strength"
    measure_label = "Average pinch strength"
    work = summary.dropna(subset=[value_col, "avg_fb_velo"]).copy()
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
        x=work[value_col],
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

    stats = pinch_correlation_stats(work, value_col)
    if stats is not None:
        r, r2, slope, intercept = stats
        x_range = np.linspace(
            work[value_col].min(), work[value_col].max(), 100
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

    fig.update_xaxes(
        title=measure_label,
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


# -----------------------------------------------------------------------------
# APP
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("<div style='height:4px;width:42px;border-radius:999px;background:#C8102E;margin:2px 0 16px;'></div>", unsafe_allow_html=True)
    st.markdown("<h2 style='color:#FFFFFF;margin:0 0 18px;font-size:27px;letter-spacing:-.03em;'>Performance × CI</h2>", unsafe_allow_html=True)
    refresh = st.button("↻ Refresh", use_container_width=True, type="primary")

if refresh:
    load_source_data.clear()

try:
    jump, velo, bat, pinch, status = load_source_data()
except Exception as exc:
    st.error(f"Could not load data. {exc}")
    st.stop()

all_dates = pd.concat([jump["date"], velo["date"], bat["month"], pinch["date"]], ignore_index=True).dropna()
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

    available_teams = (
        set(jump["team"].dropna().unique().tolist())
        | set(bat["team"].dropna().unique().tolist())
        | set(pinch["team"].dropna().unique().tolist())
    )
    teams = ["All Teams"] + [team for team in INCLUDED_TEAMS if team in available_teams]
    team_filter = st.selectbox("Team", teams)

    st.markdown("---")
    ci_lookup = st.number_input("CI lookup", min_value=0.0, step=1.0, value=280.0, format="%.1f")
    ci_band_width = st.selectbox("CI band", [5, 10, 15, 20], index=1, format_func=lambda x: f"{x} N·s")
    ci_band_velo_stat = st.selectbox(
        "CI band FB velo",
        ["Mean", "Median"],
        index=0,
        key="ci_band_fb_velo_stat",
    )
    ci_band_bat_stat = st.selectbox(
        "CI band bat speed",
        ["Mean", "Median"],
        index=0,
        key="ci_band_bat_speed_stat",
    )

    st.markdown("---")
    min_velo_records = st.number_input("Min FB records", min_value=1, step=1, value=1)
    min_ci_jumps = st.number_input("Min CI jumps", min_value=1, step=1, value=1)
    min_pinch_tests = st.number_input("Min pinch tests", min_value=1, step=1, value=1)
    show_labels = st.checkbox("Show names")

    st.markdown("---")
    bucket_mode = st.selectbox("Within bucket", ["Week", "Half-Month"])
    min_paired_dates = st.number_input("Min paired FB buckets", min_value=3, max_value=30, step=1, value=3)
    min_paired_months = st.number_input("Min paired bat months", min_value=3, max_value=24, step=1, value=3)

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

bat_monthly_pairs = build_bat_monthly_pairs(
    jump=jump,
    bat=bat,
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    min_ci_jumps=int(min_ci_jumps),
)
bat_within_pairs = build_bat_within_pairs(bat_monthly_pairs)
bat_within_summary = build_bat_within_summary(
    bat_within_pairs,
    int(min_paired_months),
)

period_text = f"{fmt_date(start_date)} – {fmt_date(end_date)}"
title_col, filter_col = st.columns([4, 1])
with title_col:
    st.markdown("<h1 style='margin:0;color:#0A1F44;font-size:37px;font-weight:800;'>Performance × CI</h1>", unsafe_allow_html=True)
with filter_col:
    st.markdown(
        f"<div style='text-align:right;color:#667085;font-weight:700;font-size:13px;padding-top:13px;'>{html.escape(team_filter)}</div>",
        unsafe_allow_html=True,
    )
st.markdown(f"<div style='color:#667085;font-size:13px;margin:3px 0 20px;'>{html.escape(period_text)}</div>", unsafe_allow_html=True)

overview_tab, within_tab, pinch_tab, bat_overview_tab, bat_within_tab = st.tabs([
    "FB Velo Overview", "FB Velo Within Individual",
    "Pinch Grip × FB Velo", "Bat Speed Overview",
    "Bat Speed Within Individual",
])

with overview_tab:
    stats = correlation_stats(summary)
    n_pitchers = len(summary)
    mean_velo = summary["avg_fb_velo"].mean() if n_pitchers else np.nan
    mean_ci = summary["avg_ci"].mean() if n_pitchers else np.nan
    r_text = f"{stats[0]:+.2f}" if stats is not None else "—"
    potential_velo_increase = stats[2] * POTENTIAL_CI_INCREASE if stats is not None else np.nan
    potential_velo_text = (
        f"{potential_velo_increase:+.2f} mph"
        if pd.notna(potential_velo_increase)
        else "—"
    )

    cols = st.columns(5)
    metric_values = [
        ("Pitchers", str(n_pitchers), BLUE),
        ("Correlation", r_text, ACCENT_RED),
        ("Last YTD FB Velo", f"{fmt(mean_velo)} mph", TEAL),
        ("Average CI", f"{fmt(mean_ci)} N·s", GREEN),
        (f"Potential Velo Increase · +{POTENTIAL_CI_INCREASE:.0f} N·s CI", potential_velo_text, NAVY_MID),
    ]
    for column, values in zip(cols, metric_values):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    st.caption(
        "Potential velo increase is the current regression slope multiplied by a +10 N·s CI change. "
        "It reflects the selected sample's association and is not a guaranteed individual response."
    )

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

    ci_band_overview = ci_band_summary(summary, int(ci_band_width), ci_band_velo_stat)

    with st.container(border=True):
        st.subheader(f"{ci_band_velo_stat} FB Velo by CI Band", anchor=False)
        st.plotly_chart(
            build_band_chart(summary, int(ci_band_width), ci_band_velo_stat),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"ci_band_chart_{ci_band_width}_{ci_band_velo_stat}_{team_filter}_{start_date}_{end_date}",
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
                    int(ci_band_width),
                    selected_ci_band,
                    ci_band_velo_stat,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    f"ci_band_detail_{selected_ci_band}_{ci_band_width}_"
                    f"{ci_band_velo_stat}_{team_filter}_{start_date}_{end_date}"
                ),
            )

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

        # Keep the dropdown state stable, but give the selected player's plots
        # their own keys so Streamlit/Plotly always replaces the old figures.
        selector_key = "within_individual_pitcher"
        if st.session_state.get(selector_key) not in athlete_options:
            st.session_state[selector_key] = athlete_options[0]

        selected_key = st.selectbox(
            "Pitcher",
            athlete_options,
            format_func=lambda key: name_map.get(key, key),
            key=selector_key,
        )

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
                st.plotly_chart(
                    build_within_scatter(player_pairs),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"within_scatter_{selected_key}_{bucket_mode}",
                )
        with right:
            with st.container(border=True):
                st.subheader("CI + YTD FB Velo", anchor=False)
                st.plotly_chart(
                    build_within_timeline(player_pairs),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"within_timeline_{selected_key}_{bucket_mode}",
                )

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
                key=f"within_bucket_table_{selected_key}_{bucket_mode}",
                column_config={
                    "Average CI": st.column_config.NumberColumn(format="%.2f N·s"),
                    "YTD FB Velo": st.column_config.NumberColumn(format="%.2f mph"),
                    "Δ CI": st.column_config.NumberColumn(format="%+.2f N·s"),
                    "Δ FB Velo": st.column_config.NumberColumn(format="%+.2f mph"),
                },
            )



with pinch_tab:
    pinch_value_col = "avg_pinch_strength"
    pinch_view = pinch_summary.dropna(
        subset=[pinch_value_col, "avg_fb_velo"]
    ).copy()
    pinch_stats = pinch_correlation_stats(pinch_view, pinch_value_col)
    n_pinch_pitchers = len(pinch_view)
    mean_pinch_value = (
        pinch_view[pinch_value_col].mean()
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

    cols = st.columns(5)
    metrics = [
        ("Pitchers", str(n_pinch_pitchers), BLUE),
        ("Correlation", pinch_r_text, ACCENT_RED),
        ("R²", pinch_r2_text, NAVY_MID),
        ("Last YTD FB Velo", f"{fmt(mean_pinch_velo)} mph", TEAL),
        ("Average Pinch Strength", fmt(mean_pinch_value), GREEN),
    ]
    for column, values in zip(cols, metrics):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    st.caption(
        "Source: the Google Sheet tab named 'Pinch Grip', using Name, Date, "
        "Pinch - R, and Pinch - L. Each test contributes whichever hand is "
        "populated for that athlete; left and right values are not averaged "
        "together. The athlete's pinch value is the mean of those single-hand "
        "tests inside the selected date window. Fastball velocity is the same "
        "final in-window ytd_fb_velo used by the FB Velo tabs; pitchers below "
        "85 mph are excluded."
    )

    with st.container(border=True):
        st.subheader("Pinch Strength vs YTD FB Velo", anchor=False)
        st.plotly_chart(
            build_pinch_scatter(
                pinch_view,
                show_labels,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"pinch_scatter_{team_filter}_"
                f"{start_date}_{end_date}_{min_pinch_tests}"
            ),
        )

    with st.container(border=True):
        st.subheader("Pinch Grip Pitcher Results", anchor=False)
        if pinch_view.empty:
            st.info("No matching pitchers.")
        else:
            pinch_display = pinch_view[[
                "athlete",
                "team",
                "avg_fb_velo",
                "ytd_as_of_date",
                "pinch_hand",
                "avg_pinch_strength",
                "pinch_tests",
                "pinch_test_dates",
                "first_pinch_date",
                "last_pinch_date",
            ]].copy()
            pinch_display.columns = [
                "Pitcher",
                "Team",
                "Last YTD FB Velo",
                "YTD FB As Of",
                "Tested Hand",
                "Average Pinch Strength",
                "Pinch Tests",
                "Pinch Test Dates",
                "First Pinch",
                "Last Pinch",
            ]
            for date_col in [
                "YTD FB As Of", "First Pinch", "Last Pinch"
            ]:
                pinch_display[date_col] = pinch_display[date_col].map(fmt_date)
            for value_column in [
                "Last YTD FB Velo",
                "Average Pinch Strength",
            ]:
                pinch_display[value_column] = pinch_display[value_column].round(2)
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


with bat_overview_tab:
    bat_stats = bat_correlation_stats(bat_monthly_pairs)
    n_hitter_months = len(bat_monthly_pairs)
    n_hitters = (
        bat_monthly_pairs["name_key"].nunique()
        if n_hitter_months else 0
    )
    mean_bat_speed = (
        bat_monthly_pairs["monthly_avg_bat_speed"].mean()
        if n_hitter_months else np.nan
    )
    mean_monthly_ci = (
        bat_monthly_pairs["avg_ci"].mean()
        if n_hitter_months else np.nan
    )
    bat_r_text = (
        f"{bat_stats[0]:+.2f}" if bat_stats is not None else "—"
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
        ("Hitter-Months", str(n_hitter_months), BLUE),
        ("Hitters", str(n_hitters), NAVY_MID),
        ("Correlation", bat_r_text, ACCENT_RED),
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

    st.caption(
        "Each observation is one hitter-month: mean raw CI from the "
        "calendar month matched to the final monthly_avg_bat_speed value "
        "for that same month. Potential bat-speed increase is the selected "
        "sample's regression slope × 10 N·s and is not a guaranteed "
        "individual response."
    )

    estimated_bat_speed = (
        bat_stats[2] * float(ci_lookup) + bat_stats[3]
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
                f"{fmt(ci_lookup, 1)} N·s</div>",
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

    with st.container(border=True):
        st.subheader(
            f"{ci_band_bat_stat} Monthly Bat Speed by CI Band",
            anchor=False,
        )
        st.plotly_chart(
            build_bat_band_chart(
                bat_monthly_pairs,
                int(ci_band_width),
                ci_band_bat_stat,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"bat_ci_band_{ci_band_width}_{ci_band_bat_stat}_"
                f"{team_filter}_{start_date}_{end_date}"
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
                show_labels,
                float(ci_lookup),
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"bat_scatter_{team_filter}_{start_date}_{end_date}_"
                f"{show_labels}_{ci_lookup}"
            ),
        )

    with st.container(border=True):
        st.subheader("Hitter-Month Results", anchor=False)
        if bat_monthly_pairs.empty:
            st.info("No matching hitter-months.")
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


with bat_within_tab:
    bat_eligible_count = len(bat_within_summary)
    bat_valid_r = (
        bat_within_summary["r"].dropna()
        if not bat_within_summary.empty
        else pd.Series(dtype=float)
    )
    bat_mean_within_r = (
        bat_valid_r.mean() if not bat_valid_r.empty else np.nan
    )

    cols = st.columns(4)
    metrics = [
        ("Hitters", str(bat_eligible_count), BLUE),
        (
            "Mean Within r",
            f"{bat_mean_within_r:+.2f}"
            if pd.notna(bat_mean_within_r)
            else "—",
            ACCENT_RED,
        ),
        (
            "Paired Hitter-Months",
            str(len(bat_within_pairs)),
            TEAL,
        ),
        ("Bucket", "Calendar Month", GREEN),
    ]
    for column, values in zip(cols, metrics):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    if bat_within_summary.empty:
        st.info("No hitters meet the paired-month rule.")
    else:
        hitter_options = bat_within_summary["name_key"].tolist()
        hitter_name_map = dict(zip(
            bat_within_summary["name_key"],
            bat_within_summary["athlete"],
        ))
        hitter_selector_key = "bat_within_individual_hitter"
        if (
            st.session_state.get(hitter_selector_key)
            not in hitter_options
        ):
            st.session_state[hitter_selector_key] = hitter_options[0]

        selected_hitter_key = st.selectbox(
            "Hitter",
            hitter_options,
            format_func=lambda key: hitter_name_map.get(key, key),
            key=hitter_selector_key,
        )
        hitter_pairs = bat_within_pairs[
            bat_within_pairs["name_key"] == selected_hitter_key
        ].sort_values("month").copy()
        hitter_row = bat_within_summary[
            bat_within_summary["name_key"] == selected_hitter_key
        ].iloc[0]

        player_cols = st.columns(4)
        player_metrics = [
            (
                "Paired Months",
                str(int(hitter_row["paired_months"])),
                BLUE,
            ),
            (
                "Within r",
                f"{hitter_row['r']:+.2f}"
                if pd.notna(hitter_row["r"])
                else "—",
                ACCENT_RED,
            ),
            (
                "Δ CI",
                f"{hitter_row['delta_ci']:+.1f} N·s",
                TEAL,
            ),
            (
                "Δ Bat Speed",
                f"{hitter_row['delta_bat_speed']:+.2f} mph",
                GREEN,
            ),
        ]
        for column, values in zip(player_cols, player_metrics):
            with column:
                st.markdown(
                    metric_card(*values),
                    unsafe_allow_html=True,
                )

        left, right = st.columns([1.25, 1])
        with left:
            with st.container(border=True):
                st.subheader(
                    "Δ Monthly CI vs Δ Monthly Bat Speed",
                    anchor=False,
                )
                st.plotly_chart(
                    build_bat_within_scatter(hitter_pairs),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=(
                        f"bat_within_scatter_"
                        f"{selected_hitter_key}"
                    ),
                )
        with right:
            with st.container(border=True):
                st.subheader(
                    "Monthly CI + Bat Speed",
                    anchor=False,
                )
                st.plotly_chart(
                    build_bat_within_timeline(hitter_pairs),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=(
                        f"bat_within_timeline_"
                        f"{selected_hitter_key}"
                    ),
                )

        with st.container(border=True):
            st.subheader(
                "Within-Individual Hitter Results",
                anchor=False,
            )
            hitter_summary_display = bat_within_summary[[
                "athlete",
                "team",
                "paired_months",
                "r",
                "r2",
                "delta_ci",
                "delta_bat_speed",
                "first_month",
                "last_month",
            ]].copy()
            hitter_summary_display.columns = [
                "Hitter",
                "Team",
                "Paired Months",
                "Within r",
                "R²",
                "Δ CI",
                "Δ Bat Speed",
                "First Month",
                "Last Month",
            ]
            for col in ["First Month", "Last Month"]:
                hitter_summary_display[col] = (
                    pd.to_datetime(hitter_summary_display[col])
                    .dt.strftime("%b %Y")
                )
            hitter_summary_display["Within r"] = (
                hitter_summary_display["Within r"].round(2)
            )
            hitter_summary_display["R²"] = (
                hitter_summary_display["R²"].round(2)
            )
            hitter_summary_display["Δ CI"] = (
                hitter_summary_display["Δ CI"].round(1)
            )
            hitter_summary_display["Δ Bat Speed"] = (
                hitter_summary_display["Δ Bat Speed"].round(2)
            )
            st.dataframe(
                hitter_summary_display,
                hide_index=True,
                use_container_width=True,
                height=min(
                    620,
                    44 + 36 * (len(hitter_summary_display) + 1),
                ),
                column_config={
                    "Within r":
                        st.column_config.NumberColumn(
                            format="%+.2f"
                        ),
                    "R²":
                        st.column_config.NumberColumn(
                            format="%.2f"
                        ),
                    "Δ CI":
                        st.column_config.NumberColumn(
                            format="%+.1f N·s"
                        ),
                    "Δ Bat Speed":
                        st.column_config.NumberColumn(
                            format="%+.2f mph"
                        ),
                },
            )

        with st.container(border=True):
            st.subheader("Monthly Pair Data", anchor=False)
            hitter_pair_display = hitter_pairs[[
                "month",
                "avg_ci",
                "monthly_avg_bat_speed",
                "bat_speed_as_of",
                "ci_jumps",
                "last_ci_date",
                "delta_ci",
                "delta_bat_speed",
            ]].copy()
            hitter_pair_display.columns = [
                "Month",
                "Monthly Average CI",
                "Monthly Avg Bat Speed",
                "Bat Speed As Of",
                "CI Jumps",
                "Last CI",
                "Δ CI",
                "Δ Bat Speed",
            ]
            hitter_pair_display["Month"] = (
                pd.to_datetime(hitter_pair_display["Month"])
                .dt.strftime("%b %Y")
            )
            for date_col in ["Bat Speed As Of", "Last CI"]:
                hitter_pair_display[date_col] = (
                    hitter_pair_display[date_col].map(fmt_date)
                )
            for col in [
                "Monthly Average CI",
                "Monthly Avg Bat Speed",
                "Δ CI",
                "Δ Bat Speed",
            ]:
                hitter_pair_display[col] = (
                    hitter_pair_display[col].round(2)
                )
            st.dataframe(
                hitter_pair_display,
                hide_index=True,
                use_container_width=True,
                height=min(
                    460,
                    44 + 36 * (len(hitter_pair_display) + 1),
                ),
                key=(
                    f"bat_monthly_pair_table_"
                    f"{selected_hitter_key}"
                ),
                column_config={
                    "Monthly Average CI":
                        st.column_config.NumberColumn(
                            format="%.2f N·s"
                        ),
                    "Monthly Avg Bat Speed":
                        st.column_config.NumberColumn(
                            format="%.2f mph"
                        ),
                    "Δ CI":
                        st.column_config.NumberColumn(
                            format="%+.2f N·s"
                        ),
                    "Δ Bat Speed":
                        st.column_config.NumberColumn(
                            format="%+.2f mph"
                        ),
                },
            )
