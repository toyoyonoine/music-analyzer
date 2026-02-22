# app.py
# Music Analyzer (Stable: Spotify Client Credentials ONLY) + Revenue Simulator
# - No OAuth / No PKCE
# - Uses reliable endpoints:
#   /search, /artists/{id}, /search (track)
# - Avoids /tracks (403 issues) and /artists/{id}/top-tracks (sometimes 403)
# - Stylish UI: no emoji, minimal labels, keeps your chart style

import os
import base64
import requests

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.patches import FancyBboxPatch


# =========================
# Spotify (Client Credentials)
# =========================
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"

CLIENT_ID = st.secrets.get("SPOTIFY_CLIENT_ID", os.getenv("SPOTIFY_CLIENT_ID"))
CLIENT_SECRET = st.secrets.get("SPOTIFY_CLIENT_SECRET", os.getenv("SPOTIFY_CLIENT_SECRET"))


@st.cache_data(ttl=3300)
def get_app_token() -> str:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET is missing (check secrets.toml)")

    auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    r = requests.post(
        TOKEN_URL,
        headers={"Authorization": f"Basic {auth}"},
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Token error {r.status_code} {r.reason}: {r.text}")
    return r.json()["access_token"]


def spotify_get(path: str, access_token: str, params=None) -> dict:
    r = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        params=params,
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason}: {r.text}")
    return r.json()


def search_artists(name: str, access_token: str, market: str, limit: int = 5):
    data = spotify_get(
        "/search",
        access_token,
        params={"q": name, "type": "artist", "limit": int(limit), "market": market},
    )
    return data.get("artists", {}).get("items", [])


def get_artist(artist_id: str, access_token: str) -> dict:
    return spotify_get(f"/artists/{artist_id}", access_token)


def search_tracks_by_artist_name(artist_name: str, access_token: str, market: str, limit: int = 10):
    limit = max(1, min(20, int(limit)))
    data = spotify_get(
        "/search",
        access_token,
        params={"q": f'artist:"{artist_name}"', "type": "track", "limit": limit, "market": market},
    )
    return data.get("tracks", {}).get("items", [])


def make_rank_index(n, top=100, floor=45):
    if n <= 1:
        return [top]
    out = []
    for i in range(n):
        t = i / float(max(1, n - 1))
        v = int(round(top - (top - floor) * t))
        out.append(v)
    return out


# =========================
# Revenue simulator helpers
# =========================
def revenue_forecast_compound(spotify_streams, youtube_streams, spotify_rate, youtube_rate, growth_rate_pct, months):
    data = []
    cs = float(spotify_streams)
    cy = float(youtube_streams)
    g = 1.0 + (float(growth_rate_pct) / 100.0)
    for m in range(1, int(months) + 1):
        rev = (cs * float(spotify_rate)) + (cy * float(youtube_rate))
        data.append({"Month": m, "Revenue": rev})
        cs *= g
        cy *= g
    return pd.DataFrame(data)


def revenue_forecast_linear(spotify_streams, youtube_streams, spotify_rate, youtube_rate, linear_add_spotify, linear_add_youtube, months):
    data = []
    cs = float(spotify_streams)
    cy = float(youtube_streams)
    for m in range(1, int(months) + 1):
        rev = (cs * float(spotify_rate)) + (cy * float(youtube_rate))
        data.append({"Month": m, "Revenue": rev})
        cs += float(linear_add_spotify)
        cy += float(linear_add_youtube)
    return pd.DataFrame(data)


def reach_month(df, target_monthly_income):
    for i, rev in enumerate(df["Revenue"], start=1):
        if float(rev) >= float(target_monthly_income):
            return i
    return None


def required_growth_rate_to_reach(r0, target, months):
    months = int(months)
    if months <= 0:
        return None, "Invalid duration."
    if float(target) <= 0:
        return None, "Target is zero."
    if float(r0) <= 0:
        return None, "Current revenue is zero."
    if float(r0) >= float(target):
        return 0.0, None
    if months == 1:
        return None, "Duration is 1 month."
    g = (float(target) / float(r0)) ** (1.0 / (months - 1)) - 1.0
    return max(0.0, g * 100.0), None


def reverse_required_streams(spotify_streams, youtube_streams, spotify_rate, youtube_rate, target_monthly_income):
    total_streams_now = float(spotify_streams) + float(youtube_streams)
    if total_streams_now > 0:
        spotify_ratio = float(spotify_streams) / total_streams_now
        youtube_ratio = float(youtube_streams) / total_streams_now
    else:
        spotify_ratio = 0.5
        youtube_ratio = 0.5

    weighted_rate = spotify_ratio * float(spotify_rate) + youtube_ratio * float(youtube_rate)
    if weighted_rate <= 0:
        return None

    required_total_streams = float(target_monthly_income) / weighted_rate
    return {
        "spotify_ratio": spotify_ratio,
        "youtube_ratio": youtube_ratio,
        "weighted_rate": weighted_rate,
        "required_total_streams": required_total_streams,
        "required_spotify_streams": required_total_streams * spotify_ratio,
        "required_youtube_streams": required_total_streams * youtube_ratio,
    }


def estimate_streams_from_artist(popularity, followers):
    followers = max(0, int(followers))
    popularity = max(0, min(100, int(popularity)))

    base_ratio = 0.08 + (popularity / 100.0) * 0.10
    spotify_streams = max(5000, int(followers * base_ratio))

    yt_ratio = 0.40 + (popularity / 100.0) * 0.40
    youtube_streams = max(0, int(spotify_streams * yt_ratio))
    return spotify_streams, youtube_streams


def sync_revenue_defaults_from_selected_artist():
    sel = st.session_state.get("selected_artist")
    if not sel:
        return

    artist_key = sel.get("key")
    if not artist_key:
        return
    if st.session_state.get("_last_artist_key_for_revenue") == artist_key:
        return

    pop = int(sel.get("popularity", 60))
    fol = int(sel.get("followers", 200000))
    sp0, yt0 = estimate_streams_from_artist(pop, fol)

    st.session_state["spotify_streams"] = sp0
    st.session_state["youtube_streams"] = yt0

    st.session_state.setdefault("spotify_rate", 0.30)
    st.session_state.setdefault("youtube_rate", 0.20)
    st.session_state.setdefault("growth_rate", max(0, min(50, int(round(pop / 10)))))
    st.session_state.setdefault("months", 12)
    st.session_state.setdefault("linear_add_spotify", 0)
    st.session_state.setdefault("linear_add_youtube", 0)
    st.session_state.setdefault("target_income", 100_000)

    st.session_state["_last_artist_key_for_revenue"] = artist_key


# =========================
# Chart (keep your style)
# =========================
def soft_horizontal_bar(ax, data: pd.DataFrame):
    base = (110 / 255, 231 / 255, 183 / 255, 0.18)
    strong = (110 / 255, 231 / 255, 183 / 255, 0.55)

    labels = data["label"].tolist()[::-1]
    values = data["value"].tolist()[::-1]

    vmax = max(values) if values else 0
    ax.set_xlim(0, vmax * 1.15 if vmax > 0 else 1)
    ax.set_ylim(-0.6, len(values) - 0.4)

    ax.set_xticks([])
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)

    for spine in ax.spines.values():
        spine.set_visible(False)

    height = 0.56
    for i, v in enumerate(values):
        color = strong if (vmax > 0 and v == vmax) else base
        patch = FancyBboxPatch(
            (0, i - height / 2),
            v,
            height,
            boxstyle="round,pad=0.02,rounding_size=10",
            linewidth=0,
            facecolor=color,
        )
        ax.add_patch(patch)

        if vmax > 0 and v == vmax:
            ax.text(
                v + vmax * 0.03,
                i,
                f"{int(v):,}",
                va="center",
                ha="left",
                fontsize=18,
                color=(110 / 255, 231 / 255, 183 / 255, 0.85),
                weight="bold",
            )


# =========================
# UI setup (stylish, no emoji)
# =========================
matplotlib.rcParams["font.family"] = "Hiragino Sans"
matplotlib.rcParams.update(
    {
        "figure.facecolor": "none",
        "axes.facecolor": "none",
        "axes.edgecolor": "none",
        "axes.labelcolor": "#cfd6dd",
        "xtick.color": "#b9c2cc",
        "ytick.color": "#b9c2cc",
        "text.color": "#d7dee6",
    }
)

st.set_page_config(page_title="Music Analyzer", page_icon="", layout="wide")

st.markdown(
    """
<style>
:root{
  --panel: rgba(255,255,255,0.03);
  --border: rgba(255,255,255,0.10);
  --text: rgba(255,255,255,0.92);
  --muted: rgba(255,255,255,0.68);
}

.block-container {padding-top: 3.2rem; padding-bottom: 2.0rem; max-width: 1100px;}
h1 {font-size: 2.0rem; margin: 0 0 .35rem;}
h2 {font-size: 1.35rem; margin-top: 1.15rem; margin-bottom: .55rem;}
h3 {font-size: 1.05rem; margin-top: .8rem; margin-bottom: .4rem;}
.small {opacity: .72; font-size: .92rem; line-height: 1.6;}

.badges{display:flex; gap:8px; flex-wrap:wrap; margin: 0 0 10px;}
.badge{
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(110,231,183,0.25);
  background: rgba(110,231,183,0.10);
  color: rgba(255,255,255,0.90);
}
.badge.ghost{
  border-color: rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.04);
  color: rgba(255,255,255,0.78);
}

.card-scope div[data-testid="stVerticalBlockBorderWrapper"]{
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 18px;
  box-shadow:
    inset 0 0 0 1px rgba(255,255,255,0.06),
    inset 0 12px 24px rgba(0,0,0,0.18);
  padding: 16px 16px;
  overflow: hidden;
}

[data-testid="stTextInput"] input{border-radius: 12px !important;}
[data-testid="stSelectbox"] div{border-radius: 12px !important;}
[data-testid="stNumberInput"] input{border-radius: 12px !important;}

.card-scope [data-testid="stMetric"]{
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255,255,255,0.02);
  border: none;
}
.card-scope [data-testid="stMetricValue"]{font-size: 1.35rem;}
.card-scope [data-testid="stMetricLabel"]{opacity: .75;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="badges"><span class="badge">Music Analyzer</span><span class="badge ghost">Stable</span></div>',
    unsafe_allow_html=True,
)
st.title("Artist Insights + Revenue Simulator")
st.caption("Spotify API (client credentials) + revenue simulation. No login required.")
st.markdown('<div style="height: 12px;"></div>', unsafe_allow_html=True)

st.markdown('<div class="card-scope">', unsafe_allow_html=True)

# =========================
# Sidebar inputs
# =========================
with st.sidebar:
    st.header("Inputs")
    market = st.selectbox("Market", ["JP", "US", "GB", "KR"], index=0)
    artist_query = st.text_input("Artist", placeholder="YOASOBI / Kendrick Lamar ...")
    mode = st.selectbox("Mode", ["Spotify API", "Demo Data"], index=0)
    debug = st.checkbox("Debug", value=False)

# =========================
# Demo data
# =========================
def demo_artist_data(name: str):
    artist = {
        "name": name if name else "Sample Artist",
        "popularity": 72,
        "followers": 1234567,
        "genres": ["electronic", "hip hop", "experimental"],
        "image_url": None,
        "id": "demo",
    }
    series = pd.DataFrame(
        [{"label": "1", "value": 100}, {"label": "2", "value": 86}, {"label": "3", "value": 72}, {"label": "4", "value": 65}, {"label": "5", "value": 54}]
    )
    top_tracks = pd.DataFrame(
        [
            {"track": "Track A", "streams_index": 100, "duration_sec": 188},
            {"track": "Track B", "streams_index": 86, "duration_sec": 201},
            {"track": "Track C", "streams_index": 72, "duration_sec": 214},
            {"track": "Track D", "streams_index": 65, "duration_sec": 179},
            {"track": "Track E", "streams_index": 54, "duration_sec": 232},
        ]
    )
    return artist, top_tracks, series


# =========================
# Guard
# =========================
if not artist_query:
    with st.container(border=True):
        st.markdown("### Start")
        st.write("Enter an artist name in the sidebar.")
        st.markdown('<div class="small">Spotify API mode fetches real metadata. Demo Data is always available.</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# =========================
# Data fetch
# =========================
debug_log = []

try:
    if mode == "Spotify API":
        token = get_app_token()
        if debug:
            debug_log.append(f"token head: {token[:10]}...")

        candidates = search_artists(artist_query, token, market, limit=5)
        debug_log.append("step: /search artist ok")

        if not candidates:
            raise RuntimeError("Artist not found")

        artist_id = candidates[0]["id"]
        artist_full = get_artist(artist_id, token)
        debug_log.append("step: /artists/{id} ok")

        images = artist_full.get("images") or candidates[0].get("images") or []
        image_url = images[0]["url"] if images else None

        artist = {
            "name": artist_full.get("name", candidates[0].get("name", "")),
            "popularity": int(artist_full.get("popularity", 0) or 0),
            "followers": int(((artist_full.get("followers") or {}).get("total", 0)) or 0),
            "genres": artist_full.get("genres", []) or [],
            "image_url": image_url,
            "id": artist_id,
        }

        tracks = search_tracks_by_artist_name(artist["name"], token, market, limit=10)
        debug_log.append("step: /search track ok")

        idx = make_rank_index(len(tracks), top=100, floor=45)
        top_tracks = pd.DataFrame(
            [
                {
                    "track": t.get("name", ""),
                    "streams_index": int(idx[i]) if i < len(idx) else 0,
                    "duration_sec": int((t.get("duration_ms") or 0) / 1000),
                }
                for i, t in enumerate(tracks)
            ]
        )

        series = pd.DataFrame(
            [{"label": str(i + 1), "value": int(top_tracks.loc[i, "streams_index"])} for i in range(len(top_tracks))]
        ) if len(top_tracks) else pd.DataFrame([{"label": "1", "value": 1}])

    else:
        artist, top_tracks, series = demo_artist_data(artist_query)

except Exception as e:
    st.warning("Spotify API is unavailable. Switched to Demo Data.")
    st.caption(f"Error: {e}")
    artist, top_tracks, series = demo_artist_data(artist_query)
    mode = "Demo Data"

if debug and debug_log:
    with st.sidebar:
        st.caption("Debug log")
        for line in debug_log[-20:]:
            st.write(line)

# Save selection for revenue defaults
st.session_state["selected_artist"] = {
    "name": artist["name"],
    "popularity": artist.get("popularity", 0),
    "followers": artist.get("followers", 0),
    "genres": artist.get("genres", []),
    "image_url": artist.get("image_url"),
    "key": f"{artist.get('id','')}|{artist.get('followers',0)}|{artist.get('popularity',0)}",
}
sync_revenue_defaults_from_selected_artist()

# =========================
# Tabs
# =========================
tab1, tab2 = st.tabs(["Artist Insights", "Revenue Simulator"])

with tab1:
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("Overview")
        with st.container(border=True):
            aimg, ainfo = st.columns([1, 2], vertical_alignment="top")
            with aimg:
                if artist.get("image_url"):
                    st.image(artist["image_url"], use_container_width=True)
            with ainfo:
                st.markdown(f"### {artist['name']}")
                st.caption(f"Market: {market} · Source: {mode}")

            m1, m2 = st.columns(2)
            m1.metric("Popularity", int(artist.get("popularity", 0)))
            m2.metric("Followers", f"{int(artist.get('followers', 0)):,}")

            st.markdown("**Genres**")
            st.write(", ".join(artist.get("genres", [])) if artist.get("genres") else "-")
            st.markdown('<div class="small">Spotify Web API does not provide stream counts. Track index is relative.</div>', unsafe_allow_html=True)

        st.subheader("Tracks")
        with st.container(border=True):
            st.dataframe(top_tracks[["track", "streams_index", "duration_sec"]], use_container_width=True, hide_index=True)

    with col_right:
        st.subheader("Chart")
        with st.container(border=True):
            fig, ax = plt.subplots(figsize=(7.2, 4.2))
            soft_horizontal_bar(ax, series)
            fig.tight_layout()
            st.pyplot(fig, clear_figure=True)

with tab2:
    sel = st.session_state.get("selected_artist")

    with st.container(border=True):
        s1, s2 = st.columns([1, 2], vertical_alignment="top")
        with s1:
            if sel and sel.get("image_url"):
                st.image(sel["image_url"], use_container_width=True)
        with s2:
            if sel:
                st.markdown(f"### {sel.get('name')}")
                sm1, sm2 = st.columns(2)
                sm1.metric("Popularity", int(sel.get("popularity", 0)))
                sm2.metric("Followers", f"{int(sel.get('followers', 0)):,}")
                st.markdown('<div class="small">Defaults are estimated from artist metadata. Adjust freely.</div>', unsafe_allow_html=True)

    with st.container(border=True):
        r1, r2 = st.columns(2, vertical_alignment="top")
        with r1:
            spotify_streams = st.number_input(
                "Spotify monthly streams",
                min_value=0,
                value=int(st.session_state.get("spotify_streams", 100_000)),
                step=10_000,
                key="spotify_streams",
            )
            youtube_streams = st.number_input(
                "YouTube monthly streams",
                min_value=0,
                value=int(st.session_state.get("youtube_streams", 50_000)),
                step=10_000,
                key="youtube_streams",
            )
            growth_rate = st.slider("Monthly growth (%)", 0, 50, int(st.session_state.get("growth_rate", 5)), key="growth_rate")
            months = st.slider("Duration (months)", 1, 24, int(st.session_state.get("months", 12)), key="months")
            linear_add_spotify = st.number_input(
                "Spotify linear add / month",
                min_value=0,
                value=int(st.session_state.get("linear_add_spotify", 0)),
                step=1000,
                key="linear_add_spotify",
            )
            linear_add_youtube = st.number_input(
                "YouTube linear add / month",
                min_value=0,
                value=int(st.session_state.get("linear_add_youtube", 0)),
                step=1000,
                key="linear_add_youtube",
            )
        with r2:
            spotify_rate = st.number_input(
                "Spotify rate (JPY / stream)",
                min_value=0.0,
                value=float(st.session_state.get("spotify_rate", 0.30)),
                step=0.01,
                format="%.2f",
                key="spotify_rate",
            )
            youtube_rate = st.number_input(
                "YouTube rate (JPY / stream)",
                min_value=0.0,
                value=float(st.session_state.get("youtube_rate", 0.20)),
                step=0.01,
                format="%.2f",
                key="youtube_rate",
            )
            target_monthly_income = st.number_input(
                "Target monthly revenue (JPY)",
                min_value=0,
                value=int(st.session_state.get("target_income", 100_000)),
                step=10_000,
                key="target_income",
            )

    monthly_spotify_revenue = float(spotify_streams) * float(spotify_rate)
    monthly_youtube_revenue = float(youtube_streams) * float(youtube_rate)
    monthly_total = monthly_spotify_revenue + monthly_youtube_revenue
    yearly_total = monthly_total * 12.0

    df = revenue_forecast_compound(spotify_streams, youtube_streams, spotify_rate, youtube_rate, growth_rate, int(months))
    df_lin = revenue_forecast_linear(spotify_streams, youtube_streams, spotify_rate, youtube_rate, linear_add_spotify, linear_add_youtube, int(months))

    reach = reach_month(df, target_monthly_income)
    req_g, req_note = required_growth_rate_to_reach(monthly_total, float(target_monthly_income), int(months))
    rev_req = reverse_required_streams(spotify_streams, youtube_streams, spotify_rate, youtube_rate, target_monthly_income)

    left, right = st.columns([1, 1])

    with left:
        st.subheader("Now")
        with st.container(border=True):
            k1, k2, k3 = st.columns(3)
            k1.metric("Monthly (JPY)", f"{int(monthly_total):,}")
            k2.metric("Yearly (JPY)", f"{int(yearly_total):,}")
            k3.metric("Growth", f"{int(growth_rate)}%")

        st.subheader("Breakdown")
        with st.container(border=True):
            b1, b2 = st.columns(2)
            b1.metric("Spotify (JPY)", f"{int(monthly_spotify_revenue):,}")
            b2.metric("YouTube (JPY)", f"{int(monthly_youtube_revenue):,}")

        st.subheader("Target")
        if reach is not None:
            st.success(f"Estimated to reach target in month {reach}.")
        else:
            last_rev = float(df["Revenue"].iloc[-1])
            st.warning("Target not reached within the selected duration.")
            st.caption(f"Last month: {int(last_rev):,} JPY (Target: {int(target_monthly_income):,} JPY)")

        st.markdown("#### Required growth (approx.)")
        if req_g is not None:
            st.info(f"To reach {int(target_monthly_income):,} JPY by month {int(months)}, growth needs ~ {float(req_g):.2f}%.")
        else:
            st.caption(req_note if req_note else "Unavailable.")

        if rev_req is not None:
            with st.container(border=True):
                st.write(f"Weighted rate: **{rev_req['weighted_rate']:.3f} JPY / stream**")
                c1, c2, c3 = st.columns(3)
                c1.metric("Total streams / month", f"{int(rev_req['required_total_streams']):,}")
                c2.metric("Spotify / month", f"{int(rev_req['required_spotify_streams']):,}")
                c3.metric("YouTube / month", f"{int(rev_req['required_youtube_streams']):,}")

    with right:
        st.subheader("Forecast")
        with st.container(border=True):
            fig, ax = plt.subplots()
            ax.plot(df["Month"], df["Revenue"], label="Compound")
            ax.plot(df_lin["Month"], df_lin["Revenue"], label="Linear")
            ax.set_xlabel("Month")
            ax.set_ylabel("Revenue (JPY)")
            ax.grid(True, alpha=0.2)
            ax.legend()
            st.pyplot(fig, clear_figure=True)

        with st.expander("Data"):
            st.dataframe(df, use_container_width=True)

        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download CSV", data=csv_bytes, file_name="revenue_forecast.csv", mime="text/csv")

st.markdown("</div>", unsafe_allow_html=True)