from app.config import settings


def is_risk_viewer(username: str | None) -> bool:
    return username is not None and username in settings.risk_viewer_usernames
