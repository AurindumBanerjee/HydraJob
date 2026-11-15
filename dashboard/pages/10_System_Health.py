"""System Health page: FastAPI, PostgreSQL, Ollama, n8n, scan runs, and retries."""

from __future__ import annotations

import streamlit as st

from components.system_view import render_phase0_dashboard


def main() -> None:
    """Render the HydraJob System Health diagnostics page."""
    st.set_page_config(page_title="HydraJob — System Health", layout="wide")
    render_phase0_dashboard(show_endpoint_breakdown=True)


if __name__ == "__main__":
    main()
