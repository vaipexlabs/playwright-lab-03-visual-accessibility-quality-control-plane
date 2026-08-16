"""Deterministic reference application for visual and accessibility checks."""

from enum import StrEnum
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

PACKAGE_ROOT = Path(__file__).parent


class DashboardState(StrEnum):
    """Supported deterministic interface states."""

    READY = "ready"
    EMPTY = "empty"
    DEGRADED = "degraded"


PROJECTS = (
    {
        "name": "Checkout experience",
        "owner": "Commerce",
        "status": "Ready",
        "status_class": "success",
        "coverage": "18 states",
        "last_review": "Today, 09:25 UTC",
    },
    {
        "name": "Account onboarding",
        "owner": "Identity",
        "status": "Review",
        "status_class": "warning",
        "coverage": "12 states",
        "last_review": "Today, 08:40 UTC",
    },
    {
        "name": "Billing settings",
        "owner": "Finance Platform",
        "status": "Ready",
        "status_class": "success",
        "coverage": "9 states",
        "last_review": "Yesterday, 16:10 UTC",
    },
)

app = FastAPI(
    title="Vaipex Experience Quality Review",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=PACKAGE_ROOT / "templates")


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    """Expose a stable readiness signal for local orchestration."""

    return {"status": "ready"}


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    state: DashboardState = DashboardState.READY,
    dialog: bool = Query(default=False),
) -> HTMLResponse:
    """Render a controlled dashboard state with no external dependencies."""

    projects = () if state is DashboardState.EMPTY else PROJECTS
    metrics = {
        DashboardState.READY: {
            "approved": "39",
            "review": "3",
            "coverage": "96%",
            "finding": "0",
        },
        DashboardState.EMPTY: {
            "approved": "0",
            "review": "0",
            "coverage": "—",
            "finding": "0",
        },
        DashboardState.DEGRADED: {
            "approved": "34",
            "review": "8",
            "coverage": "82%",
            "finding": "2",
        },
    }[state]

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "state": state.value,
            "dialog_open": dialog,
            "metrics": metrics,
            "projects": projects,
        },
    )
