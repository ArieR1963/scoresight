import requests
import socket
import xml.etree.ElementTree as ET

from text_detection_target import TextDetectionTargetWithResult
from sc_logging import logger
from storage import subscribe_to_data, fetch_data
from urllib.parse import urlencode


class VMixAPI:
    def __init__(
        self,
        host,
        port,
        input_number,
        field_mapping,
        mode: str = "legacy_http",
        tcp_port: str = "8099",
    ):
        self.host = host
        self.port = port
        self.tcp_port = tcp_port
        self.input_number = input_number
        self.field_mapping = field_mapping
        self.mode = mode
        self.running = False
        self.update_same = fetch_data("scoresight.json", "vmix_send_same", False)
        subscribe_to_data("scoresight.json", "vmix_send_same", self.set_update_same)

    def set_update_same(self, update_same):
        self.update_same = update_same

    def set_field_mapping(self, field_mapping):
        self.field_mapping = field_mapping

    def fetch_fields(self) -> list[str]:
        # vMix API endpoint returns XML with input and text field names.
        url = f"http://{self.host}:{self.port}/api"
        try:
            response = requests.get(url, timeout=3)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch vMix fields from {url}: {e}")
            return []

        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as e:
            logger.error(f"Failed to parse vMix XML from {url}: {e}")
            return []

        target_input = None
        for input_elem in root.findall(".//inputs/input"):
            if (
                input_elem.get("number") == str(self.input_number)
                or input_elem.get("key") == str(self.input_number)
                or input_elem.get("title") == str(self.input_number)
            ):
                target_input = input_elem
                break

        field_names = set()
        search_roots = [target_input] if target_input is not None else root.findall(
            ".//inputs/input"
        )
        for input_elem in search_roots:
            if input_elem is None:
                continue
            for text_elem in input_elem.findall(".//text"):
                name = text_elem.get("name")
                if name:
                    field_names.add(name)

        fields = sorted(field_names)
        if not fields:
            logger.warning(
                "No vMix title text fields found for input '%s' at %s",
                self.input_number,
                url,
            )
        return fields

    def _send_settext_http(self, key: str, value: str):
        query = {
            "Function": "SetText",
            "Input": self.input_number,
            "SelectedName": key,
            "Value": value,
        }
        url = f"http://{self.host}:{self.port}/api/?{urlencode(query)}"
        try:
            response = requests.post(url, timeout=2)
            if response.status_code != 200:
                logger.error(f"Failed to send data, status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send data to {url}: {e}")

    def _send_settext_tcp(self, key: str, value: str):
        params = urlencode(
            {
                "Input": self.input_number,
                "SelectedName": key,
                "Value": value,
            }
        )
        command = f"FUNCTION SetText {params}\r\n".encode("utf-8")
        try:
            with socket.create_connection((self.host, int(self.tcp_port)), timeout=2) as s:
                s.sendall(command)
        except OSError as e:
            logger.error(
                "Failed to send vMix TCP command to %s:%s: %s",
                self.host,
                self.tcp_port,
                e,
            )

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
            if self.mode == "api_plus":
                self._send_settext_tcp(key, value)
            else:
                self._send_settext_http(key, value)
