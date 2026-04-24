"""JISP management demo dashboard.

Single-page Streamlit app that showcases the reasoning layer end-to-end:
map of seeded assets, one clickable finding, live LLaMA 3.3 explanation.

Run:
    JISP_API_BASE_URL=http://localhost:8000 \\
      streamlit run ui/dashboards/streamlit_app.py

Responsibility (strict, per ADR 001): visualization only. All reasoning goes
through the FastAPI /explain endpoint — the UI never calls Ollama directly.
"""

from __future__ import annotations
import api_client
import streamlit as st
import folium
from streamlit_folium import st_folium


from ui.dashboards.demo_data import (
    DEMO_ASSETS,
    DEMO_FLOOD_ZONE_GEOJSON,
    build_explain_context,
    get_asset,
)


# ----------------------------------------------------------------------------
# Page setup
# ----------------------------------------------------------------------------

st.set_page_config(
    page_title="JISP — Jacobs Spatial Intelligence Platform",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Trim the default Streamlit chrome so the demo reads as a product, not a tool.
st.markdown(
    """
    <style>
      #MainMenu, footer, header {visibility: hidden;}
      .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
      .jisp-asset-row {
        padding: 0.6rem 0.8rem;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        margin-bottom: 0.5rem;
        background: #fafafa;
      }
      .jisp-asset-row.selected {
        border-color: #2563eb;
        background: #eff6ff;
      }
      .jisp-severity-bar {
        height: 6px; border-radius: 3px; background: #e5e7eb; margin-top: 4px;
      }
      .jisp-severity-fill {
        height: 100%; border-radius: 3px;
      }
      .jisp-explanation {
        padding: 1rem 1.25rem;
        border-left: 4px solid #2563eb;
        background: #f8fafc;
        border-radius: 6px;
        line-height: 1.6;
        font-size: 1.02rem;
      }
      .jisp-badge {
        display: inline-block; padding: 2px 8px; border-radius: 999px;
        font-size: 0.75rem; font-weight: 600;
      }
      .jisp-badge.ok   {background:#dcfce7; color:#166534;}
      .jisp-badge.down {background:#fee2e2; color:#991b1b;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------

health = api_client.check_health()
badge_class = "ok" if health.ok else "down"
badge_text = f"API healthy · v{health.detail}" if health.ok else f"API offline · {health.detail}"

header_left, header_right = st.columns([4, 1])
with header_left:
    st.markdown(
        "### JISP · Jacobs Spatial Intelligence Platform"
        "\n*Pre-field, AI-first, geospatial-native, explainable by design.*"
    )
with header_right:
    st.markdown(
        f"<div style='text-align:right; padding-top:0.8rem;'>"
        f"<span class='jisp-badge {badge_class}'>{badge_text}</span></div>",
        unsafe_allow_html=True,
    )

st.divider()


# ----------------------------------------------------------------------------
# Session state — stores which asset the operator has selected
# ----------------------------------------------------------------------------

if "selected_asset_id" not in st.session_state:
    st.session_state.selected_asset_id = DEMO_ASSETS[0].id
if "last_explanation" not in st.session_state:
    st.session_state.last_explanation = None
if "last_error" not in st.session_state:
    st.session_state.last_error = None


def _select(asset_id: str) -> None:
    if st.session_state.selected_asset_id != asset_id:
        st.session_state.selected_asset_id = asset_id
        st.session_state.last_explanation = None
        st.session_state.last_error = None


# ----------------------------------------------------------------------------
# Layout: sidebar (findings list) + main (map + explanation)
# ----------------------------------------------------------------------------

sidebar, main = st.columns([1, 2], gap="large")

with sidebar:
    st.markdown(f"**Findings ({len(DEMO_ASSETS)})**")
    for asset in sorted(DEMO_ASSETS, key=lambda a: -a.severity_raw):
        selected = asset.id == st.session_state.selected_asset_id
        # Severity bar color: red if >=0.7, amber 0.4–0.7, green below.
        if asset.severity_raw >= 0.7:
            color = "#dc2626"
        elif asset.severity_raw >= 0.4:
            color = "#f59e0b"
        else:
            color = "#16a34a"
        pct = int(asset.severity_raw * 100)
        st.markdown(
            f"""
            <div class='jisp-asset-row {"selected" if selected else ""}'>
              <div style='display:flex; justify-content:space-between;'>
                <strong>{asset.id}</strong>
                <span style='color:#6b7280; font-size:0.85rem;'>{asset.type.replace("_", " ")}</span>
              </div>
              <div style='font-size:0.85rem; color:#374151;'>{asset.name}</div>
              <div class='jisp-severity-bar'>
                <div class='jisp-severity-fill' style='width:{pct}%; background:{color};'></div>
              </div>
              <div style='font-size:0.75rem; color:#6b7280; margin-top:2px;'>
                severity_raw {asset.severity_raw:.2f} · {asset.proximity_km} km from flood zone
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.button(
            "Select" if not selected else "✓ Selected",
            key=f"pick-{asset.id}",
            use_container_width=True,
            on_click=_select,
            args=(asset.id,),
            disabled=selected,
        )


with main:
    selected = get_asset(st.session_state.selected_asset_id) or DEMO_ASSETS[0]

    # --- Map ----------------------------------------------------------------
    fmap = folium.Map(
        location=[selected.lat, selected.lon],
        zoom_start=12,
        tiles="CartoDB positron",
        control_scale=True,
    )

    folium.GeoJson(
        DEMO_FLOOD_ZONE_GEOJSON,
        name="Flood zone (demo)",
        style_function=lambda _f: {
            "fillColor": "#2563eb",
            "color": "#1d4ed8",
            "weight": 1,
            "fillOpacity": 0.18,
        },
    ).add_to(fmap)

    for asset in DEMO_ASSETS:
        is_selected = asset.id == selected.id
        color = (
            "#dc2626" if asset.severity_raw >= 0.7
            else "#f59e0b" if asset.severity_raw >= 0.4
            else "#16a34a"
        )
        folium.CircleMarker(
            location=[asset.lat, asset.lon],
            radius=10 if is_selected else 7,
            weight=3 if is_selected else 1,
            color="#111827" if is_selected else color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            tooltip=f"{asset.id} · {asset.name} · severity {asset.severity_raw:.2f}",
            popup=folium.Popup(
                f"<b>{asset.id}</b><br>{asset.name}<br>"
                f"severity_raw: {asset.severity_raw:.2f}<br>"
                f"proximity: {asset.proximity_km} km",
                max_width=260,
            ),
        ).add_to(fmap)

    st_folium(fmap, use_container_width=True, height=460, returned_objects=[])

    # --- Explanation panel --------------------------------------------------
    st.markdown(f"#### {selected.id} · {selected.name}")

    details_cols = st.columns(4)
    details_cols[0].metric("Severity", f"{selected.severity_raw:.2f}")
    details_cols[1].metric("Proximity", f"{selected.proximity_km} km")
    details_cols[2].metric("Elevation", f"{selected.elevation_m} m")
    details_cols[3].metric("FEMA Zone", selected.fema_zone.split(" ")[0])

    with st.expander("Observed signals", expanded=True):
        for s in selected.signals:
            st.markdown(f"- {s}")

    action_col, spacer = st.columns([1, 3])
    with action_col:
        explain_clicked = st.button(
            "🧠 Alert Reasoning",
            type="primary",
            use_container_width=True,
            disabled=not health.ok,
            help=(
                "Sends this finding to the reasoning service via POST /explain."
                if health.ok
                else "API is offline — start `uvicorn api.main:app` first."
            ),
        )

    if explain_clicked:
        st.session_state.last_error = None
        st.session_state.last_explanation = None
        with st.spinner("Generating AI model explanation..."):
            try:
                resp = api_client.explain(
                    subject=selected.id,
                    template="asset_risk",
                    context=build_explain_context(selected),
                )
                st.session_state.last_explanation = resp
            except api_client.JispApiError as exc:
                st.session_state.last_error = str(exc)

    if st.session_state.last_error:
        st.error(st.session_state.last_error)

    if st.session_state.last_explanation:
        resp = st.session_state.last_explanation
        st.markdown("##### Explanation")
        st.markdown(
            f"<div class='jisp-explanation'>{resp['explanation']}</div>",
            unsafe_allow_html=True,
        )
        caption_bits = [f"template: `{resp.get('template')}`"]
        if resp.get("model"):
            caption_bits.append(f"model: `{resp['model']}`")
        caption_bits.append("observational only — no prediction, scoring, or recommendation")
        st.caption(" · ".join(caption_bits))
