import requests

from text_detection_target import TextDetectionTargetWithResult
from sc_logging import logger
from storage import subscribe_to_data, fetch_data
from urllib.parse import urlencode
from urllib.parse import urlparse


class VMixAPI:
    def __init__(self, host, port, input_number, field_mapping):
        self.host = host
        self.port = port
        self.input_number = input_number
        self.field_mapping = field_mapping
        self.running = False
        self.update_same = fetch_data("scoresight.json", "vmix_send_same", False)
        subscribe_to_data("scoresight.json", "vmix_send_same", self.set_update_same)

    def set_update_same(self, update_same):
        self.update_same = update_same

    def set_field_mapping(self, field_mapping):
        self.field_mapping = field_mapping

    def _http_base(self) -> str:
        raw_host = (self.host or "").strip()
        if not raw_host:
            return ""
        if not raw_host.startswith(("http://", "https://")):
            raw_host = f"http://{raw_host}"
        parsed = urlparse(raw_host)
        scheme = parsed.scheme or "http"
        hostname = parsed.hostname
        if not hostname:
            return ""
        port = parsed.port or int(self.port)
        return f"{scheme}://{hostname}:{port}"

    def update_vmix(self, detection: list[TextDetectionTargetWithResult]):
        if not self.running:
            return

        if not self.field_mapping:
            logger.debug("Field mapping is not set")
            return

        look_in = [TextDetectionTargetWithResult.ResultState.Success]
        if self.update_same:
            # If we want to send the same values as well
            look_in.append(TextDetectionTargetWithResult.ResultState.SameNoChange)

        # Prepare the data to send
        data = {}
        for target in detection:
            if target.result_state in look_in:
                if target.name in self.field_mapping:
                    data[self.field_mapping[target.name]] = target.result

        if data == {}:
            logger.debug("No data to send")
            return

        for key, value in data.items():
            base = self._http_base()
            if not base:
                logger.error("Failed to build vMix URL from host/port")
                return
            # Prepare the URL
            query = {
                "Function": "SetText",
                "Input": self.input_number,
                "SelectedName": key,
                "Value": value,
            }
            url = f"{base}/api/?{urlencode(query)}"
            try:
                # Send the request
                response = requests.post(url, timeout=0.5)

                # Check the response
                if response.status_code != 200:
                    logger.error(
                        f"Failed to send data, status code: {response.status_code}"
                    )
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to send data to {url}: {e}")
