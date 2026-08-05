"""
Performance × CI — Streamlit deployment-ready dashboard.

Pitching:
  * Last in-window ytd_fb_velo matched to mean in-window raw CI.
  * Pitchers below 85 mph are excluded.

Pinch grip:
  * Pinch Grip tab uses Name, Date, Pinch - R, and Pinch - L.
  * Each row contributes the one populated hand as that athlete's pinch value.
  * Overview mirrors CI: mean in-window pinch matched to last in-window ytd_fb_velo.

Combined model:
  * One cross-sectional row per pitcher, matching average in-window CI and
    average in-window pinch strength to the final in-window ytd_fb_velo.
  * Multiple linear regression estimates the partial association of CI and
    pinch strength with fastball velocity.

Sprinting:
  * One final eligible-month monthly_max_sprint_speed observation per player from PP_Sprint.
  * A sprint month is eligible only when it contains at least 14 distinct valid PP_Sprint data dates.
  * Mean Peak Power / BM [W/kg] from Jump Data in the same calendar month.
  * Cross-sectional monthly analysis.

Hitting:
  * One final monthly_avg_bat_speed value per hitter-month.
  * Mean raw CI from the same calendar month.
  * Cross-sectional monthly analysis.
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
POTENTIAL_PINCH_INCREASE = 10.0
POTENTIAL_PEAK_POWER_REL_INCREASE = 5.0
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
def load_source_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Load Jump Data, FB Velo, Pinch Grip, bat speed, and sprint speed."""
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
    jump_team_col = first_existing(jump_raw.columns.tolist(), ["Team", "team", "Level", "level"])

    missing_jump = [
        label for label, col in {
            "athlete name": jump_name_col,
            "date": jump_date_col,
            "concentric impulse": jump_ci_col,
            "Peak Power / BM [W/kg]": jump_peak_power_rel_col,
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
        jump_base.dropna(subset=["date", "peak_power_rel"])[
            ["athlete", "date", "peak_power_rel", "team", "name_key"]
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

    status = (
        f"Loaded {len(jump):,} CI rows, {len(jump_power):,} relative-power rows, "
        f"{len(velo):,} FB Velo rows, {len(pinch):,} Pinch Grip rows, "
        f"{len(sprint):,} valid sprint-speed source rows, and {len(bat):,} "
        f"hitter-month bat-speed rows · "
        f"{datetime.now().strftime('%I:%M %p').lstrip('0')}"
    )
    return jump, jump_power, velo, bat, pinch, sprint, status


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
# FINAL ELIGIBLE-MONTH SPRINT SPEED × RELATIVE PEAK POWER
# -----------------------------------------------------------------------------
def build_sprint_overview_summary(
    jump_power: pd.DataFrame,
    sprint: pd.DataFrame,
    start_date,
    end_date,
    team_filter: str,
    min_power_jumps: int,
) -> pd.DataFrame:
    """Create one player-level observation from each player's final eligible month.

    An eligible month must contain a valid final monthly_max_sprint_speed value,
    at least 14 distinct PP_Sprint data dates inside the selected dashboard date
    range, and at least min_power_jumps Peak Power / BM rows from Jump Data in
    that same month and selected date range. The regression therefore receives
    exactly one row per player.
    """
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()

    # Apply the ACTUAL selected dates before assigning rows to calendar months.
    # This prevents days before the selected start date or after the selected end
    # date from helping a partial month qualify.
    power_window = jump_power[
        (jump_power["date"] >= start) & (jump_power["date"] <= end)
    ].copy()
    power_window["month"] = (
        power_window["date"].dt.to_period("M").dt.to_timestamp()
    )
    power_monthly = (
        power_window.groupby(["name_key", "month"], as_index=False)
        .agg(
            athlete=("athlete", "first"),
            avg_peak_power_rel=("peak_power_rel", "mean"),
            power_jumps=("peak_power_rel", "count"),
            power_test_dates=("date", "nunique"),
            first_power_date=("date", "min"),
            last_power_date=("date", "max"),
        )
    )

    team_lookup = (
        jump_power.sort_values("date")
        .groupby("name_key", as_index=False)
        .tail(1)[["name_key", "team"]]
        .drop_duplicates("name_key")
        .rename(columns={"team": "current_team"})
    )

    sprint_window = sprint[
        (sprint["date"] >= start) & (sprint["date"] <= end)
    ].copy()
    sprint_window["month"] = (
        sprint_window["date"].dt.to_period("M").dt.to_timestamp()
    )
    sprint_window = sprint_window.sort_values(
        ["name_key", "month", "date"], kind="stable"
    )

    sprint_monthly_coverage = (
        sprint_window.groupby(["name_key", "month"], as_index=False)
        .agg(
            first_sprint_date=("date", "min"),
            last_sprint_date=("date", "max"),
            sprint_data_dates=("date", "nunique"),
            sprint_source_rows=("date", "size"),
        )
    )
    sprint_monthly_coverage["sprint_coverage_days"] = (
        sprint_monthly_coverage["last_sprint_date"]
        - sprint_monthly_coverage["first_sprint_date"]
    ).dt.days + 1

    sprint_monthly_final = (
        sprint_window.groupby(["name_key", "month"], as_index=False)
        .tail(1)[[
            "name_key", "athlete", "month", "date",
            "monthly_max_sprint_speed", "team",
        ]]
        .rename(columns={"date": "sprint_speed_as_of"})
        .merge(
            sprint_monthly_coverage,
            on=["name_key", "month"],
            how="left",
        )
    )

    eligible = power_monthly.merge(
        sprint_monthly_final,
        on=["name_key", "month"],
        how="inner",
        suffixes=("", "_sprint"),
    )
    eligible = eligible.merge(team_lookup, on="name_key", how="left")
    eligible["team"] = eligible["current_team"].combine_first(
        eligible["team"]
    )
    eligible = eligible.drop(columns=["current_team"])
    eligible["team"] = eligible["team"].fillna("Unassigned")
    eligible = eligible[
        (eligible["power_jumps"] >= max(1, int(min_power_jumps)))
        & (
            eligible["sprint_data_dates"]
            >= MIN_SPRINT_MONTH_DATA_DATES
        )
    ].copy()

    if team_filter != "All Teams":
        eligible = eligible[eligible["team"] == team_filter].copy()

    if eligible.empty:
        eligible["month_label"] = pd.Series(dtype=str)
        eligible["observation"] = pd.Series(dtype=str)
        return eligible.reset_index(drop=True)

    # Select the final qualifying month only after all matching and minimum-data
    # rules are applied, preserving one independent observation per player.
    summary = (
        eligible.sort_values(
            ["name_key", "month", "sprint_speed_as_of"],
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


def sprint_power_band_summary(
    pairs: pd.DataFrame,
    band_width: float,
    sprint_stat: str = "Mean",
) -> pd.DataFrame:
    stat = "Median" if str(sprint_stat).strip().lower() == "median" else "Mean"
    speed_col = f"{stat} Monthly Max Sprint Speed"
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
            showarrow=False,
            font={"size": 15, "color": SUBTEXT},
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base_figure_layout(fig, 560)

    customdata = np.column_stack([
        pairs["athlete"],
        pairs["team"],
        pairs["month_label"],
        pairs["power_jumps"],
        pairs["power_test_dates"],
        pairs["first_power_date"].map(fmt_date),
        pairs["last_power_date"].map(fmt_date),
        pairs["sprint_speed_as_of"].map(fmt_date),
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
            "<b>%{customdata[0]}</b> · %{customdata[2]}<br>"
            "Team: %{customdata[1]}<br>"
            "Monthly max sprint speed: %{y:.2f} ft/s<br>"
            "Final-month average Peak Power / BM: %{x:.2f} W/kg<br><br>"
            "Jump rows: %{customdata[3]} across %{customdata[4]} dates · "
            "%{customdata[5]}–%{customdata[6]}<br>"
            "Sprint-speed value as of %{customdata[7]}<extra></extra>"
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
                    "Final-month average Peak Power / BM: %{x:.1f} W/kg<br>"
                    "Estimated monthly max sprint speed: %{y:.2f} ft/s"
                    "<extra></extra>"
                ),
            ))

    fig.update_xaxes(
        title="Average Peak Power / BM in final eligible month (W/kg)",
        showgrid=True, gridcolor=GRID, zeroline=False,
        linecolor=BORDER, tickfont={"color": SUBTEXT},
        title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title="Monthly max sprint speed (ft/s)",
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
    speed_col = f"{stat} Monthly Max Sprint Speed"
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
            f"<b>%{{x}}</b><br>{stat} monthly max sprint speed: "
            "%{y:.2f} ft/s<br>"
            "Players: %{customdata[0]}<br>"
            "Mean Peak Power / BM within band: %{customdata[1]:.2f} W/kg"
            "<extra></extra>"
        ),
    ))
    y_min = max(0, float(bands[speed_col].min()) - 1.5)
    y_max = float(bands[speed_col].max()) + 1.0
    fig.update_xaxes(
        title="Final-month average Peak Power / BM band",
        showgrid=False, linecolor=BORDER,
        tickfont={"color": SUBTEXT}, title_font={"color": SUBTEXT},
    )
    fig.update_yaxes(
        title=f"{stat} monthly max sprint speed (ft/s)",
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
# APP
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("<div style='height:4px;width:42px;border-radius:999px;background:#C8102E;margin:2px 0 16px;'></div>", unsafe_allow_html=True)
    st.markdown("<h2 style='color:#FFFFFF;margin:0 0 18px;font-size:27px;letter-spacing:-.03em;'>Performance × CI</h2>", unsafe_allow_html=True)
    refresh = st.button("↻ Refresh", use_container_width=True, type="primary")

if refresh:
    load_source_data.clear()

try:
    jump, jump_power, velo, bat, pinch, sprint, status = load_source_data()
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
        | set(jump_power["team"].dropna().unique().tolist())
        | set(bat["team"].dropna().unique().tolist())
        | set(pinch["team"].dropna().unique().tolist())
        | set(sprint["team"].dropna().unique().tolist())
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
    pinch_lookup = st.number_input(
        "Pinch lookup", min_value=0.0, step=1.0, value=40.0, format="%.1f"
    )
    pinch_band_width = st.selectbox(
        "Pinch band", [2.5, 5.0, 10.0], index=1,
        format_func=lambda x: f"{x:g} units",
    )
    pinch_band_velo_stat = st.selectbox(
        "Pinch band FB velo",
        ["Mean", "Median"],
        index=0,
        key="pinch_band_fb_velo_stat",
    )
    ci_band_bat_stat = st.selectbox(
        "CI band bat speed",
        ["Mean", "Median"],
        index=0,
        key="ci_band_bat_speed_stat",
    )
    power_lookup = st.number_input(
        "Peak Power / BM lookup",
        min_value=0.0, step=1.0, value=60.0, format="%.1f",
    )
    power_band_width = st.selectbox(
        "Peak Power / BM band",
        [1.0, 2.0, 2.5, 5.0],
        index=2,
        format_func=lambda x: f"{x:g} W/kg",
    )
    power_band_sprint_stat = st.selectbox(
        "Power band sprint speed",
        ["Mean", "Median"],
        index=0,
        key="power_band_sprint_speed_stat",
    )

    st.markdown("---")
    min_velo_records = st.number_input("Min FB records", min_value=1, step=1, value=1)
    min_ci_jumps = st.number_input("Min CI jumps", min_value=1, step=1, value=1)
    min_pinch_tests = st.number_input("Min pinch tests", min_value=1, step=1, value=1)
    min_power_jumps = st.number_input(
        "Min relative-power jumps", min_value=1, step=1, value=1
    )
    show_labels = st.checkbox("Show names")


summary = build_summary(
    jump=jump,
    velo=velo,
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    min_velo_records=int(min_velo_records),
    min_ci_jumps=int(min_ci_jumps),
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
    sprint=sprint,
    start_date=start_date,
    end_date=end_date,
    team_filter=team_filter,
    min_power_jumps=int(min_power_jumps),
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

(
    overview_tab,
    pinch_overview_tab,
    combined_model_tab,
    sprint_overview_tab,
    bat_overview_tab,
) = st.tabs([
    "FB Velo Overview",
    "Pinch Grip Overview",
    "Combined CI + Pinch Overview",
    "Sprint Speed Overview",
    "Bat Speed Overview",
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
    potential_pinch_velo = (
        pinch_stats[2] * POTENTIAL_PINCH_INCREASE
        if pinch_stats is not None else np.nan
    )
    potential_pinch_text = (
        f"{potential_pinch_velo:+.2f} mph"
        if pd.notna(potential_pinch_velo) else "—"
    )

    cols = st.columns(5)
    metrics = [
        ("Pitchers", str(n_pinch_pitchers), BLUE),
        ("Correlation", pinch_r_text, ACCENT_RED),
        ("Last YTD FB Velo", f"{fmt(mean_pinch_velo)} mph", TEAL),
        ("Average Pinch Strength", fmt(mean_pinch_value), GREEN),
        (
            f"Potential Velo Increase · +{POTENTIAL_PINCH_INCREASE:.0f} Pinch",
            potential_pinch_text,
            NAVY_MID,
        ),
    ]
    for column, values in zip(cols, metrics):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    st.caption(
        "This mirrors the CI overview calculation. Each pitcher contributes "
        "the mean of the populated Pinch - R or Pinch - L values inside the "
        "selected window, matched to that pitcher's final in-window "
        "ytd_fb_velo. The +10 estimate is the sample regression slope × 10 "
        "pinch-strength units and is not a guaranteed individual response."
    )

    estimated_pinch_velo = (
        pinch_stats[2] * float(pinch_lookup) + pinch_stats[3]
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
                f"{fmt(pinch_lookup, 1)}</div>",
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

    pinch_band_overview = pinch_band_summary(
        pinch_view,
        float(pinch_band_width),
        pinch_band_velo_stat,
    )
    with st.container(border=True):
        st.subheader(
            f"{pinch_band_velo_stat} FB Velo by Pinch Band",
            anchor=False,
        )
        st.plotly_chart(
            build_pinch_band_chart(
                pinch_view,
                float(pinch_band_width),
                pinch_band_velo_stat,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"pinch_band_chart_{pinch_band_width}_"
                f"{pinch_band_velo_stat}_{team_filter}_{start_date}_{end_date}"
            ),
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
                    float(pinch_band_width),
                    selected_pinch_band,
                    pinch_band_velo_stat,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    f"pinch_band_detail_{selected_pinch_band}_"
                    f"{pinch_band_width}_{pinch_band_velo_stat}_"
                    f"{team_filter}_{start_date}_{end_date}"
                ),
            )

    with st.container(border=True):
        st.subheader("Pinch Strength vs YTD FB Velo", anchor=False)
        st.plotly_chart(
            build_pinch_scatter(
                pinch_view,
                show_labels,
                float(pinch_lookup),
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"pinch_scatter_{team_filter}_{start_date}_{end_date}_"
                f"{min_pinch_tests}_{pinch_lookup}_{show_labels}"
            ),
        )

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

        st.caption(
            "This model is calculated like the overview tabs: each pitcher "
            "contributes exactly one observation. Average in-window CI and "
            "average in-window pinch strength are matched to that pitcher's "
            "final in-window ytd_fb_velo. The coefficients describe partial "
            "between-pitcher associations and should not be interpreted as "
            "causal individual velocity gains."
        )
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
                + combined_model["beta_ci"] * float(ci_lookup)
                + combined_model["beta_pinch"] * float(pinch_lookup)
            )
            lookup_cols = st.columns(3)
            lookup_items = [
                ("Average CI", f"{float(ci_lookup):.1f} N·s", BLUE),
                ("Average Pinch", f"{float(pinch_lookup):.1f}", TEAL),
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

            model_data = combined_model["data"]
            outside_ci = not (
                model_data["avg_ci"].min()
                <= float(ci_lookup)
                <= model_data["avg_ci"].max()
            )
            outside_pinch = not (
                model_data["avg_pinch_strength"].min()
                <= float(pinch_lookup)
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
                st.caption(
                    "Each value leaves one pitcher out, fits the model on all "
                    "remaining pitchers, and predicts the held-out pitcher. "
                    "Unlike ordinary in-sample R², adding pinch is not "
                    "guaranteed to improve this metric."
                )
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
                        combined_model, show_labels
                    ),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=(
                        f"combined_overview_actual_predicted_{team_filter}_"
                        f"{start_date}_{end_date}_{show_labels}_"
                        f"{min_ci_jumps}_{min_pinch_tests}_{min_velo_records}"
                    ),
                )

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
            st.caption(
                "Pitcher-level equation: final YTD FB velo = "
                f"{combined_model['intercept']:.4f} + "
                f"({combined_model['beta_ci']:.4f} × average CI) + "
                f"({combined_model['beta_pinch']:.4f} × average pinch). "
                "The intervals are ordinary OLS approximations and are "
                "especially uncertain with small samples."
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
    sprint_r_text = (
        f"{sprint_stats[0]:+.2f}" if sprint_stats is not None else "—"
    )
    potential_sprint_increase = (
        sprint_stats[2] * POTENTIAL_PEAK_POWER_REL_INCREASE
        if sprint_stats is not None else np.nan
    )
    potential_sprint_text = (
        f"{potential_sprint_increase:+.2f} ft/s"
        if pd.notna(potential_sprint_increase) else "—"
    )

    sprint_r2_text = (
        f"{sprint_stats[1]:.2f}" if sprint_stats is not None else "—"
    )
    top_cols = st.columns(3)
    top_metrics = [
        ("Players / Observations", str(n_sprint_players), BLUE),
        ("Correlation", sprint_r_text, ACCENT_RED),
        ("R²", sprint_r2_text, NAVY_MID),
    ]
    for column, values in zip(top_cols, top_metrics):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    bottom_cols = st.columns(3)
    bottom_metrics = [
        (
            "Monthly Max Sprint Speed",
            f"{fmt(mean_sprint_speed)} ft/s",
            TEAL,
        ),
        (
            "Final-Month Avg Peak Power / BM",
            f"{fmt(mean_power_rel)} W/kg",
            GREEN,
        ),
        (
            f"Sprint-Speed Association · +{POTENTIAL_PEAK_POWER_REL_INCREASE:.0f} W/kg",
            potential_sprint_text,
            NAVY_MID,
        ),
    ]
    for column, values in zip(bottom_cols, bottom_metrics):
        with column:
            st.markdown(metric_card(*values), unsafe_allow_html=True)

    st.caption(
        "Each observation is one player. The app finds that player’s final eligible "
        "month in the selected range. A month is eligible only when it contains "
        "at least 14 distinct valid PP_Sprint data dates inside the selected date "
        "range. The app then uses the "
        "final monthly_max_sprint_speed value and matches it to mean Peak Power "
        "/ BM [W/kg] from Jump Data in that same month. "
        "The +5 W/kg card is the selected sample's regression slope × 5 and "
        "is an association, not a guaranteed individual improvement."
    )

    estimated_sprint_speed = (
        sprint_stats[2] * float(power_lookup) + sprint_stats[3]
        if sprint_stats is not None else np.nan
    )
    with st.container(border=True):
        st.subheader("Relative Peak Power Lookup", anchor=False)
        lookup_left, lookup_right = st.columns(2)
        with lookup_left:
            st.markdown(
                "<div class='metric-label'>Final-Month Average Peak Power / BM</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='lookup-value' style='color:#0A1F44;'>"
                f"{fmt(power_lookup, 1)} W/kg</div>",
                unsafe_allow_html=True,
            )
        with lookup_right:
            st.markdown(
                "<div class='metric-label'>Estimated Monthly Max Sprint Speed</div>",
                unsafe_allow_html=True,
            )
            lookup_value = (
                f"{fmt(estimated_sprint_speed)} ft/s"
                if pd.notna(estimated_sprint_speed) else "—"
            )
            st.markdown(
                f"<div class='lookup-value' style='color:#0D7E8A;'>"
                f"{lookup_value}</div>",
                unsafe_allow_html=True,
            )

    with st.container(border=True):
        st.subheader(
            f"{power_band_sprint_stat} Monthly Max Sprint Speed by Peak Power / BM Band",
            anchor=False,
        )
        st.plotly_chart(
            build_sprint_band_chart(
                sprint_overview_summary,
                float(power_band_width),
                power_band_sprint_stat,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"sprint_power_band_{power_band_width}_{power_band_sprint_stat}_"
                f"{team_filter}_{start_date}_{end_date}"
            ),
        )

    with st.container(border=True):
        st.subheader(
            "Final-Month Peak Power / BM vs Monthly Max Sprint Speed",
            anchor=False,
        )
        st.plotly_chart(
            build_sprint_scatter(
                sprint_overview_summary,
                show_labels,
                float(power_lookup),
            ),
            use_container_width=True,
            config={"displayModeBar": False},
            key=(
                f"sprint_scatter_{team_filter}_{start_date}_{end_date}_"
                f"{show_labels}_{power_lookup}"
            ),
        )

    with st.container(border=True):
        st.subheader("Player Results", anchor=False)
        if sprint_overview_summary.empty:
            st.info("No matching players.")
        else:
            sprint_display = sprint_overview_summary[[
                "athlete",
                "team",
                "month",
                "monthly_max_sprint_speed",
                "sprint_speed_as_of",
                "first_sprint_date",
                "last_sprint_date",
                "sprint_coverage_days",
                "sprint_data_dates",
                "avg_peak_power_rel",
                "power_jumps",
                "power_test_dates",
                "first_power_date",
                "last_power_date",
            ]].copy()
            sprint_display.columns = [
                "Player",
                "Team",
                "Month",
                "Monthly Max Sprint Speed",
                "Sprint Speed As Of",
                "First Sprint Record",
                "Last Sprint Record",
                "Sprint Coverage Days",
                "Sprint Data Dates",
                "Final-Month Avg Peak Power / BM",
                "Jump Rows",
                "Jump Test Dates",
                "First Jump",
                "Last Jump",
            ]
            sprint_display["Month"] = (
                pd.to_datetime(sprint_display["Month"]).dt.strftime("%b %Y")
            )
            for date_col in [
                "Sprint Speed As Of", "First Sprint Record",
                "Last Sprint Record", "First Jump", "Last Jump"
            ]:
                sprint_display[date_col] = sprint_display[date_col].map(fmt_date)
            sprint_display["Monthly Max Sprint Speed"] = (
                sprint_display["Monthly Max Sprint Speed"].round(2)
            )
            sprint_display["Final-Month Avg Peak Power / BM"] = (
                sprint_display["Final-Month Avg Peak Power / BM"].round(2)
            )
            st.dataframe(
                sprint_display,
                hide_index=True,
                use_container_width=True,
                height=min(660, 44 + 36 * (len(sprint_display) + 1)),
                column_config={
                    "Monthly Max Sprint Speed": st.column_config.NumberColumn(
                        format="%.2f ft/s"
                    ),
                    "Final-Month Avg Peak Power / BM": st.column_config.NumberColumn(
                        format="%.2f W/kg"
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
