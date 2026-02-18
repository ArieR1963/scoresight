import requests
import socket
import xml.etree.ElementTree as ET
import time
import queue
import threading

from text_detection_target import TextDetectionTargetWithResult
from sc_logging import logger
from storage import subscribe_to_data, fetch_data
from urllib.parse import urlencode
from urllib.parse import urlparse


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
        self.field_input_map: dict[str, list[str]] = {}
        self.mode = mode
        self.running = False
        self._last_tcp_error_log_at = 0.0
        self._send_suspend_until = 0.0
        self._send_queue: queue.Queue[list[tuple[str, str, str, str]]] = queue.Queue(
            maxsize=1
        )
        self._send_worker_thread = threading.Thread(
            target=self._send_worker_loop,
            daemon=True,
            name="vmix-send-worker",
        )
        self._send_worker_thread.start()
        self.update_same = fetch_data("scoresight.json", "vmix_send_same", False)
        subscribe_to_data("scoresight.json", "vmix_send_same", self.set_update_same)

    def set_update_same(self, update_same):
        self.update_same = update_same

    def set_field_mapping(self, field_mapping):
        self.field_mapping = field_mapping

    def set_field_input_map(self, field_input_map: dict[str, list[str]]):
        self.field_input_map = field_input_map or {}

    def _api_base_url(self) -> str:
        raw_host = (self.host or "").strip()
        if not raw_host:
            return ""

        if not raw_host.startswith(("http://", "https://")):
            raw_host = f"http://{raw_host}"

        parsed = urlparse(raw_host)
        scheme = parsed.scheme or "http"
        netloc = parsed.netloc or parsed.path
        netloc = netloc.split("/")[0]
        if not netloc:
            return ""

        if ":" in netloc:
            return f"{scheme}://{netloc}"
        return f"{scheme}://{netloc}:{self.port}"

    def _api_url(self) -> str:
        base = self._api_base_url()
        if not base:
            return ""
        return f"{base}/api"

    def _socket_host(self) -> str:
        raw_host = (self.host or "").strip()
        if not raw_host:
            return ""

        if not raw_host.startswith(("http://", "https://")):
            raw_host = f"http://{raw_host}"

        parsed = urlparse(raw_host)
        if parsed.hostname:
            return parsed.hostname

        netloc = parsed.netloc or parsed.path
        if not netloc:
            return ""
        return netloc.split("/")[0].split(":")[0]

    def ping_api(self) -> bool:
        url = self._api_url()
        if not url:
            return False
        try:
            response = requests.get(url, timeout=1.5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def fetch_fields(self) -> list[str]:
        # vMix API endpoint returns XML with input and text field names.
        url = self._api_url()
        if not url:
            logger.error("Failed to build vMix API URL from host/port")
            return []
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
        input_number = str(self.input_number).strip()
        if input_number:
            for input_elem in root.findall(".//inputs/input"):
                if (
                    input_elem.get("number") == input_number
                    or input_elem.get("key") == input_number
                    or input_elem.get("title") == input_number
                ):
                    target_input = input_elem
                    break

        field_names = set()
        field_input_map: dict[str, list[str]] = {}
        search_roots = [target_input] if target_input is not None else root.findall(
            ".//inputs/input"
        )
        for input_elem in search_roots:
            if input_elem is None:
                continue
            input_ref = input_elem.get("number") or input_elem.get("key") or input_number
            for text_elem in input_elem.findall(".//text"):
                name = text_elem.get("name")
                if name:
                    field_names.add(name)
                    if input_ref:
                        if name not in field_input_map:
                            field_input_map[name] = []
                        input_ref_str = str(input_ref)
                        if input_ref_str not in field_input_map[name]:
                            field_input_map[name].append(input_ref_str)

        fields = sorted(field_names)
        self.field_input_map = field_input_map
        if not fields:
            logger.warning(
                "No vMix title text fields found for input '%s' at %s",
                self.input_number,
                url,
            )
        return fields

    def _send_settext_http(self, key: str, value: str, input_number: str) -> bool:
        api_url = self._api_url()
        if not api_url:
            logger.error("Failed to build vMix API URL from host/port")
            self._send_suspend_until = time.time() + 0.5
            return False
        query = {
            "Function": "SetText",
            "Input": input_number,
            "SelectedName": key,
            "Value": value,
        }
        url = f"{api_url}/?{urlencode(query)}"
        try:
            response = requests.post(url, timeout=0.35)
            if response.status_code != 200:
                logger.error(f"Failed to send data, status code: {response.status_code}")
                self._send_suspend_until = time.time() + 0.5
                return False
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send data to {url}: {e}")
            self._send_suspend_until = time.time() + 0.5
            return False

    def _send_settext_tcp(self, key: str, value: str, input_number: str) -> bool:
        socket_host = self._socket_host()
        if not socket_host:
            now = time.time()
            if now - self._last_tcp_error_log_at > 2.0:
                logger.error("Failed to build vMix TCP host from host/port")
                self._last_tcp_error_log_at = now
            self._send_suspend_until = time.time() + 0.5
            return False

    def _enqueue_latest(self, commands: list[tuple[str, str, str, str]]):
        # Keep only the newest payload to avoid latency buildup under bursty updates.
        try:
            self._send_queue.put_nowait(commands)
            return
        except queue.Full:
            pass

        try:
            self._send_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            self._send_queue.put_nowait(commands)
        except queue.Full:
            # If producer races with worker, skip this frame and keep moving.
            return

    def _send_worker_loop(self):
        while True:
            try:
                commands = self._send_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if time.time() < self._send_suspend_until:
                continue

            for mode, key, value, input_number in commands:
                if mode == "api_plus":
                    if not self._send_settext_tcp(key, value, input_number):
                        break
                else:
                    if not self._send_settext_http(key, value, input_number):
                        break
        params = urlencode(
            {
                "Input": input_number,
                "SelectedName": key,
                "Value": value,
            }
        )
        command = f"FUNCTION SetText {params}\r\n".encode("utf-8")
        try:
            with socket.create_connection((socket_host, int(self.tcp_port)), timeout=0.35) as s:
                s.sendall(command)
            return True
        except OSError as e:
            now = time.time()
            if now - self._last_tcp_error_log_at > 2.0:
                logger.error(
                    "Failed to send vMix TCP command to %s:%s: %s",
                    socket_host,
                    self.tcp_port,
                    e,
                )
                self._last_tcp_error_log_at = now
            self._send_suspend_until = time.time() + 0.5
            return False

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

        if time.time() < self._send_suspend_until:
            return

        commands: list[tuple[str, str, str, str]] = []
        for key, value in data.items():
            input_numbers = self.field_input_map.get(key, [])
            if not input_numbers:
                input_numbers = [str(self.input_number or "1")]

            for input_number in input_numbers:
                commands.append((self.mode, key, value, str(input_number)))

        if commands:
            self._enqueue_latest(commands)
