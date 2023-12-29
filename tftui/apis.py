import platform
import socket
import hashlib
import importlib.metadata
import requests
from posthog import Posthog
from tftui.constants import nouns, adjectives


class OutboundAPIs:
    is_new_version_available = False
    is_usage_tracking_enabled = True
    generated_handle = None
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
    def generate_handle():
        fingerprint_data = f"{platform.system()}-{platform.node()}-{platform.release()}-{socket.gethostname()}"
        fingerprint = int(hashlib.sha256(fingerprint_data.encode()).hexdigest(), 16)
        OutboundAPIs.generated_handle = (
            adjectives[fingerprint % len(adjectives)]
            + " "
            + nouns[fingerprint % len(nouns)]
        )

    @staticmethod
    def post_usage(message: str) -> None:
        if not OutboundAPIs.is_usage_tracking_enabled:
            return
        if not OutboundAPIs.generated_handle:
            OutboundAPIs.generate_handle()

        OutboundAPIs.posthog.capture(
            OutboundAPIs.generated_handle,
            message,
            {"tftui_version": OutboundAPIs.version},
        )

    @staticmethod
    def disable_usage_tracking() -> None:
        OutboundAPIs.is_usage_tracking_enabled = False
