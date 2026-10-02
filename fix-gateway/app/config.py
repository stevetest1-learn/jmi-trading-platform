import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    fix_version: str = "FIX.4.4"
    listen_host: str = os.environ.get("FIX_LISTEN_HOST", "0.0.0.0")
    listen_port: int = int(os.environ.get("FIX_LISTEN_PORT", "9878"))
    sender_comp_id: str = os.environ.get("FIX_SENDER_COMP_ID", "JMIGW")  # us, from the counterparty's view we're the target
    heartbeat_interval: int = int(os.environ.get("FIX_HEARTBEAT_INTERVAL", "30"))

    backend_base_url: str = os.environ.get("BACKEND_BASE_URL", "http://localhost:8000")
    backend_ws_url: str = os.environ.get("BACKEND_WS_URL", "ws://localhost:8000/ws")

    # TEMPLATE SIMPLIFICATION: a real deployment would provision one
    # (SenderCompID, account) mapping per counterparty via some onboarding
    # flow, not a hardcoded dict. See fix-gateway/README.md.
    comp_id_to_credentials: dict[str, tuple[str, str]] = field(
        default_factory=lambda: {
            "CLIENT1": (
                os.environ.get("FIX_CLIENT1_USERNAME", "bob"),
                os.environ.get("FIX_CLIENT1_PASSWORD", "demo1234"),
            ),
        }
    )


settings = Settings()
