"""Local dashboard: `uv run streamlit run src/rumour_pressure/dashboard/app.py`.

One view per registry group (or hand-picked markets): price lines on a shared hourly
timeline. Lanes for jumps, attention and stance are added as later tasks land.
"""

import duckdb
import plotly.graph_objects as go
import streamlit as st

from rumour_pressure import config
from rumour_pressure.dashboard import data
from rumour_pressure.registry import load_registry

st.set_page_config(page_title="Rumour pressure", layout="wide")


@st.cache_resource
def _con(path: str) -> duckdb.DuckDBPyConnection:
    return data.connect_read_only(path)


def main() -> None:
    path = config.warehouse_path()
    if not path.exists():
        st.error(f"No warehouse at {path}. Run `uv run rp collect prices` first.")
        st.stop()
    try:
        con = _con(str(path))
    except duckdb.IOException:
        st.warning("The warehouse is busy (a collector is writing). Refresh in a moment.")
        st.stop()

    registry = load_registry()
    group_of = {m.market_id: m.group for m in registry.markets}
    mk = data.markets(con)
    mk["group"] = mk["market_id"].map(group_of).fillna("(not in registry)")
    mk = mk[mk["n_bars"] > 0]

    st.sidebar.title("Rumour pressure")
    groups = sorted(mk["group"].unique())
    group = st.sidebar.selectbox("Group", groups, index=0 if groups else None)
    in_group = mk[mk["group"] == group]
    labels = {r.market_id: f"{r.question} ({r.venue})" for r in in_group.itertuples()}
    chosen = st.sidebar.multiselect(
        "Markets", list(labels), default=list(labels), format_func=labels.get
    )

    st.title(f"{group}: price on a shared hourly timeline")
    grid = data.price_grid(con, chosen)
    if grid.empty:
        st.info("No price data for the selected markets yet.")
        st.stop()

    fig = go.Figure()
    for market_id, g in grid.groupby("market_id"):
        fig.add_trace(
            go.Scatter(
                x=g["ts_utc"],
                y=g["price"],
                mode="lines",
                line_shape="hv",
                name=labels.get(market_id, market_id)[:60],
                hovertemplate=(
                    "%{x|%Y-%m-%d %H:00} UTC<br>YES %{y:.2f}<extra>%{fullData.name}</extra>"
                ),
            )
        )
    fig.update_layout(
        height=520,
        yaxis=dict(title="YES price", range=[0, 1], tickformat=".0%"),
        xaxis=dict(title="UTC"),
        legend=dict(orientation="h", yanchor="top", y=-0.15),
        margin=dict(l=40, r=20, t=20, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Markets and resolution rules"):
        for r in in_group[in_group["market_id"].isin(chosen)].itertuples():
            st.markdown(f"**[{r.question}]({r.url})** · {r.venue} · {r.n_bars:,} hourly bars")
            st.caption(r.resolution_text[:600])


main()
