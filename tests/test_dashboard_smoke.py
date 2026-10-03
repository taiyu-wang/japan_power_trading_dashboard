from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def test_explicit_navigation_has_no_competing_legacy_pages_directory():
    assert not (ROOT / "pages").exists()


@pytest.fixture
def dashboard(monkeypatch):
    def offline(*args, **kwargs):
        raise OSError("Offline smoke test")

    monkeypatch.setattr("src.data_loader.load_published_csv", offline)
    monkeypatch.setattr("src.utils.load_runtime_manifest",
                        lambda: ({"overall_status": "unavailable", "datasets": []}, "Offline test"))
    st.cache_data.clear()
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    assert not app.exception
    yield app
    st.cache_data.clear()


@pytest.mark.parametrize("page", [
    "views/1_Power_Market.py", "views/2_Fuel_Dispatch.py", "views/3_Forward_Curves.py",
    "views/4_Weather_Seasonality.py", "views/5_Trading_Signals.py",
    "views/6_Supply_Mix.py", "views/7_Market_Structure.py",
])
def test_all_routes_work_without_network(dashboard, page):
    dashboard.switch_page(page).run()
    assert not dashboard.exception, [error.message for error in dashboard.exception]
    assert dashboard.title


@pytest.mark.parametrize("view", ["Dispatch economics", "Fuel inputs", "Relative value"])
def test_fuel_views_render_without_network(dashboard, view):
    dashboard.switch_page("views/2_Fuel_Dispatch.py").run()
    dashboard.segmented_control[0].set_value(view).run()
    assert not dashboard.exception
    assert dashboard.get("plotly_chart")


@pytest.mark.parametrize("view", ["Generation mix", "Supply shape", "Weather & seasonality"])
def test_fundamental_views_render_without_network(dashboard, view):
    dashboard.switch_page("views/6_Supply_Mix.py").run()
    dashboard.segmented_control[0].set_value(view).run()
    assert not dashboard.exception


def test_analysis_period_survives_page_navigation(dashboard):
    dashboard.selectbox[0].select("Feb 2026 onward").run()
    dashboard.switch_page("views/2_Fuel_Dispatch.py").run()
    assert dashboard.selectbox[0].value == "Feb 2026 onward"
    dashboard.switch_page("views/1_Power_Market.py").run()
    assert dashboard.selectbox[0].value == "Feb 2026 onward"
    assert not dashboard.exception


def test_empty_curve_date_selection_does_not_crash(dashboard):
    dashboard.switch_page("views/3_Forward_Curves.py").run()
    dates = next(control for control in dashboard.multiselect if control.label == "Curve dates")
    dates.set_value([]).run()
    assert not dashboard.exception
    assert any("at least one curve date" in item.value for item in dashboard.info)
