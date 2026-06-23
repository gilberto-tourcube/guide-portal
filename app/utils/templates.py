"""Template helpers shared by route modules."""

from datetime import date

from fastapi import Request
from fastapi.templating import Jinja2Templates


def current_year_context(request: Request) -> dict[str, int]:
    return {"current_year": date.today().year}


def create_templates() -> Jinja2Templates:
    return Jinja2Templates(
        directory="templates",
        context_processors=[current_year_context],
    )
