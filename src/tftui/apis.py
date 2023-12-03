import uuid
import importlib.metadata
import requests
from posthog import Posthog


class OutboundAPIs:
    is_new_version_available = False
    is_usage_tracking_enabled = True
    session_id = uuid.uuid4()
    version = importlib.metadata.version("tftui")

    POSTHOG_API_KEY = "phc_tjGzx7V6Y85JdNfOFWxQLXo5wtUs6MeVLvoVfybqz09"  # + "uncomment-while-developing"

    posthog = Posthog(
        project_api_key=POSTHOG_API_KEY,
        host="https://app.posthog.com",
        disable_geoip=False,
    )

    response = requests.get("https://pypi.org/pypi/tftui/json")
    if response.status_code == 200:
        ver = response.json()["info"]["version"]
        if ver != version:
            is_new_version_available = True

    @staticmethod
    def post_usage(message: str) -> None:
        if OutboundAPIs.is_usage_tracking_enabled:
            OutboundAPIs.posthog.capture(
                OutboundAPIs.session_id,
                message,
                {"tftui_version": OutboundAPIs.version},
            )

    @staticmethod
    def disable_usage_tracking() -> None:
        OutboundAPIs.is_usage_tracking_enabled = False
