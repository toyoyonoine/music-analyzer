import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.patches import FancyBboxPatch

# --- Fonts (Mac) ---
matplotlib.rcParams["font.family"] = "Hiragino Sans"

# --- Matplotlib: transparent, soft ---
matplotlib.rcParams.update({
    "figure.facecolor": "none",
    "axes.facecolor": "none",
    "axes.edgecolor": "none",
    "axes.labelcolor": "#cfd6dd",
    "xtick.color": "#b9c2cc",
    "ytick.color": "#b9c2cc",
    "text.color": "#d7dee6",
})

st.set_page_config(page_title="Music Analyzer", page_icon="", layout="wide")

st.markdown("""
<style>
/* 上の余白 */
.block-container {padding-top: 3.4rem; padding-bottom: 2rem; max-width: 1100px;}

/* タイポ */
h1 {font-size: 2.0rem; margin: 0 0 .4rem;}
h2 {font-size: 1.35rem; margin-top: 1.2rem; margin-bottom: .6rem;}
h3 {font-size: 1.05rem; margin-top: .8rem; margin-bottom: .4rem;}
.small {opacity: .72; font-size: .92rem; line-height: 1.6;}

/* バッジ */
.badges{display:flex; gap:8px; flex-wrap:wrap; margin: 0 0 10px;}
.badge{
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(110,231,183,0.25);
  background: rgba(110,231,183,0.12);
  color: rgba(255,255,255,0.86);
}
.badge.ghost{
  border-color: rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.05);
  color: rgba(255,255,255,0.72);
}

/* ✅ “カード”スタイルは card-scope の中だけに限定（ここが重要） */
.card-scope div[data-testid="stVerticalBlockBorderWrapper"]{
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 18px;
  box-shadow:
    inset 0 0 0 1px rgba(255,255,255,0.06),
    inset 0 12px 24px rgba(0,0,0,0.18);
  padding: 16px 16px;
  overflow: hidden;
}

/* 入力UI */
[data-testid="stTextInput"] input{border-radius: 12px !important;}
[data-testid="stSelectbox"] div{border-radius: 12px !important;}

/* metric（枠なし） */
.card-scope [data-testid="stMetric"]{
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255,255,255,0.02);
  border: none;
}
.card-scope [data-testid="stMetricValue"]{font-size: 1.35rem;}
.card-scope [data-testid="stMetricLabel"]{opacity: .75;}
</style>
""", unsafe_allow_html=True)

# ---- Header ----
st.markdown(
    '<div class="badges"><span class="badge">Music Analyzer</span><span class="badge ghost">Prototype</span></div>',
    unsafe_allow_html=True
)
st.title("Artist Insights Dashboard")
st.caption("アーティストの指標とトップ曲を、シンプルに可視化する分析ツール。")
st.markdown('<div style="height: 18px;"></div>', unsafe_allow_html=True)

# ✅ ここから下を “カードスタイル適用範囲” にする
st.markdown('<div class="card-scope">', unsafe_allow_html=True)

# ---- Sidebar ----
with st.sidebar:
    st.header("Inputs")
    artist_query = st.text_input("Artist name", placeholder="例：YOASOBI / Kendrick Lamar など")
    market = st.selectbox("Market", ["JP", "US", "GB", "KR"], index=0)
    mode = st.selectbox("Mode", ["Demo Data（おすすめ）", "Spotify API（後で）"], index=0)

# ====== Demo data ======
def demo_artist_data(name: str):
    artist = {
        "name": name if name else "Sample Artist",
        "popularity": 72,
        "followers": 1234567,
        "genres": ["electronic", "hip hop", "experimental"]
    }
    df = pd.DataFrame([
        {"label": "1月", "value": 100},
        {"label": "2月", "value": 210},
        {"label": "3月", "value": 320},
        {"label": "4月", "value": 420},
        {"label": "5月", "value": 500},
    ])
    top_tracks = pd.DataFrame([
        {"track": "Track A", "streams_index": 100, "duration_sec": 188},
        {"track": "Track B", "streams_index": 86,  "duration_sec": 201},
        {"track": "Track C", "streams_index": 72,  "duration_sec": 214},
        {"track": "Track D", "streams_index": 65,  "duration_sec": 179},
        {"track": "Track E", "streams_index": 54,  "duration_sec": 232},
    ])
    return artist, top_tracks, df

def soft_horizontal_bar(ax, data: pd.DataFrame):
    base = (110/255, 231/255, 183/255, 0.18)
    strong = (110/255, 231/255, 183/255, 0.55)

    labels = data["label"].tolist()[::-1]
    values = data["value"].tolist()[::-1]

    ax.set_xlim(0, max(values) * 1.15)
    ax.set_ylim(-0.6, len(values)-0.4)

    ax.set_xticks([])
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    for spine in ax.spines.values():
        spine.set_visible(False)

    height = 0.56
    vmax = max(values)
    for i, v in enumerate(values):
        color = strong if v == vmax else base
        patch = FancyBboxPatch(
            (0, i - height/2),
            v, height,
            boxstyle="round,pad=0.02,rounding_size=10",
            linewidth=0,
            facecolor=color,
        )
        ax.add_patch(patch)

        if v == vmax:
            ax.text(v + vmax*0.03, i, f"{v:,}", va="center", ha="left",
                    fontsize=18, color=(110/255, 231/255, 183/255, 0.85), weight="bold")

# ---- Guard ----
if not artist_query:
    # ✅ st.info ではなく “カード” で出す（見切れ・統一感の両方に効く）
    with st.container(border=True):
        st.markdown("### Start")
        st.write("左のサイドバーからアーティスト名を入力してください（まずは Demo Data 推奨）。")
        st.markdown('<div class="small">入力すると Overview / Top Tracks / Chart を表示します。</div>', unsafe_allow_html=True)

    # card-scope を閉じる
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

artist, top_tracks, demo_series = demo_artist_data(artist_query)

# ---- Layout ----
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("Overview")
    with st.container(border=True):
        st.markdown(f"### {artist['name']}")
        st.caption(f"Market: {market}")

        m1, m2 = st.columns(2)
        m1.metric("Popularity", artist["popularity"])
        m2.metric("Followers", f"{artist['followers']:,}")

        st.markdown("**Genres**")
        st.write(", ".join(artist["genres"]))
        st.markdown('<div class="small">※ デモ表示。API復帰後に実データへ差し替え。</div>', unsafe_allow_html=True)

    st.subheader("Top Tracks")
    with st.container(border=True):
        st.dataframe(top_tracks[["track", "streams_index", "duration_sec"]],
                     use_container_width=True, hide_index=True)
        st.markdown('<div class="small">※ streams_index はデモ用の相対指標</div>', unsafe_allow_html=True)

with col_right:
    st.subheader("Chart")
    with st.container(border=True):
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        soft_horizontal_bar(ax, demo_series)
        fig.tight_layout()
        st.pyplot(fig, clear_figure=True)

st.divider()
st.caption("次の実装候補：Spotify API復帰後に検索→artist_id→top_tracks接続 / アーティスト画像表示 / CSV export など。")

# ✅ card-scope を閉じる（通常表示時）
st.markdown("</div>", unsafe_allow_html=True)