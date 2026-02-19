import requests
import socket
import xml.etree.ElementTree as ET
import time
import queue
import threading
import os

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
        self.force_next_send = False
        self._timing_debug = (
            mode == "api_plus" and os.getenv("SCORESIGHT_VMIX_API_DEBUG", "0") == "1"
        )
        self._debug_last_summary_at = time.time()
        self._debug_last_update_at = 0.0
        self._debug_last_send_ok_at = 0.0
        self._debug_last_send_ms = 0.0
        self._debug_updates = 0
        self._debug_enqueues = 0
        self._debug_queue_drops = 0
        self._debug_send_ok = 0
        self._debug_send_fail = 0
        self._debug_last_error = ""
        self._api_plus_http_only_until = 0.0
        self._api_plus_last_send_at = 0.0
        self._api_plus_min_send_interval = 0.15
        subscribe_to_data("scoresight.json", "vmix_send_same", self.set_update_same)

    def set_update_same(self, update_same):
        self.update_same = update_same

    def request_force_send(self):
        self.force_next_send = True

    def set_field_mapping(self, field_mapping):
        self.field_mapping = field_mapping

    def set_field_input_map(self, field_input_map: dict[str, list[str]]):
        self.field_input_map = field_input_map or {}

    def _debug_timing_summary(self):
        if not self._timing_debug:
            return
        now = time.time()
        if now - self._debug_last_summary_at < 2.0:
            return
        since_ok = (
            now - self._debug_last_send_ok_at if self._debug_last_send_ok_at > 0 else -1.0
        )
        logger.info(
            "vMix API+ debug: upd=%d enq=%d ok=%d fail=%d drop=%d last_send=%.1fms last_ok=%.2fs ago last_error=%s",
            self._debug_updates,
            self._debug_enqueues,
            self._debug_send_ok,
            self._debug_send_fail,
            self._debug_queue_drops,
            self._debug_last_send_ms,
            since_ok,
            self._debug_last_error or "-",
        )
        self._debug_last_summary_at = now
        self._debug_updates = 0
        self._debug_enqueues = 0
        self._debug_send_ok = 0
        self._debug_send_fail = 0
        self._debug_queue_drops = 0
        self._debug_last_error = ""

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

    def _send_settext_http(
        self, key: str, value: str, input_number: str, apply_backoff: bool = True
    ) -> bool:
        api_url = self._api_url()
        if not api_url:
            logger.error("Failed to build vMix API URL from host/port")
            if apply_backoff:
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
                if apply_backoff:
                    self._send_suspend_until = time.time() + 0.5
                return False
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send data to {url}: {e}")
            if apply_backoff:
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

    def _send_settext_tcp_batch(
        self,
        input_number: str,
        field_values: list[tuple[str, str]],
        apply_backoff: bool = True,
    ) -> bool:
        socket_host = self._socket_host()
        if not socket_host:
            now = time.time()
            if now - self._last_tcp_error_log_at > 2.0:
                logger.error("Failed to build vMix TCP host from host/port")
                self._last_tcp_error_log_at = now
            if apply_backoff:
                self._send_suspend_until = time.time() + 0.5
            return False

        lines = []
        for key, value in field_values:
            params = urlencode(
                {
                    "Input": input_number,
                    "SelectedName": key,
                    "Value": value,
                }
            )
            lines.append(f"FUNCTION SetText {params}\r\n")
        payload = "".join(lines).encode("utf-8")

        try:
            with socket.create_connection((socket_host, int(self.tcp_port)), timeout=0.8) as s:
                s.sendall(payload)
            return True
        except OSError as e:
            now = time.time()
            if now - self._last_tcp_error_log_at > 2.0:
                logger.error(
                    "Failed to send vMix TCP batch to %s:%s: %s",
                    socket_host,
                    self.tcp_port,
                    e,
                )
                self._last_tcp_error_log_at = now
            if apply_backoff:
                self._send_suspend_until = time.time() + 0.5
            return False

    def _send_settext_http_batch(
        self,
        input_number: str,
        field_values: list[tuple[str, str]],
        apply_backoff: bool = True,
    ) -> bool:
        for key, value in field_values:
            if not self._send_settext_http(
                key, value, input_number, apply_backoff=apply_backoff
            ):
                return False
        return True

    def _enqueue_latest(self, commands: list[tuple[str, str, str, str]]):
        # Keep only the newest payload to avoid latency buildup under bursty updates.
        try:
            self._send_queue.put_nowait(commands)
            if self._timing_debug:
                self._debug_enqueues += 1
            return
        except queue.Full:
            pass

        try:
            self._send_queue.get_nowait()
            if self._timing_debug:
                self._debug_queue_drops += 1
        except queue.Empty:
            pass

        try:
            self._send_queue.put_nowait(commands)
            if self._timing_debug:
                self._debug_enqueues += 1
        except queue.Full:
            # If producer races with worker, skip this frame and keep moving.
            if self._timing_debug:
                self._debug_queue_drops += 1
            return

    def _send_worker_loop(self):
        while True:
            try:
                commands = self._send_queue.get(timeout=0.5)
            except queue.Empty:
                self._debug_timing_summary()
                continue

            if time.time() < self._send_suspend_until:
                self._debug_timing_summary()
                continue

            if all(mode == "api_plus" for mode, _, _, _ in commands):
                now = time.time()
                if now - self._api_plus_last_send_at < self._api_plus_min_send_interval:
                    self._debug_timing_summary()
                    continue

                by_input: dict[str, list[tuple[str, str]]] = {}
                for _, key, value, input_number in commands:
                    by_input.setdefault(input_number, []).append((key, value))
                worker_start = time.time()
                ok = True
                fallback_used = False
                for input_number, field_values in by_input.items():
                    if time.time() >= self._api_plus_http_only_until:
                        if self._send_settext_tcp_batch(
                            input_number, field_values, apply_backoff=False
                        ):
                            continue
                        # TCP is unstable right now; stay on HTTP fallback briefly
                        # so we avoid rapid transport flapping.
                        self._api_plus_http_only_until = time.time() + 2.0
                        fallback_used = True
                    else:
                        fallback_used = True
                    if not self._send_settext_http_batch(
                        input_number, field_values, apply_backoff=False
                    ):
                        ok = False
                        break
                self._api_plus_last_send_at = time.time()
                if self._timing_debug:
                    self._debug_last_send_ms = (time.time() - worker_start) * 1000.0
                    if ok:
                        self._debug_send_ok += 1
                        self._debug_last_send_ok_at = time.time()
                    else:
                        self._debug_send_fail += 1
                        self._debug_last_error = "tcp_batch_failed"
                    if fallback_used and ok:
                        self._debug_last_error = "tcp_fallback_http_ok"
                    self._debug_timing_summary()
                continue

            for mode, key, value, input_number in commands:
                if mode == "api_plus":
                    if not self._send_settext_tcp(key, value, input_number):
                        break
                else:
                    if not self._send_settext_http(key, value, input_number):
                        break

    def update_vmix(self, detection: list[TextDetectionTargetWithResult]):
        if not self.running:
            return
        if self._timing_debug:
            now = time.time()
            self._debug_updates += 1
            if self._debug_last_update_at > 0:
                gap = now - self._debug_last_update_at
                if gap > 1.0:
                    logger.warning("vMix API+ debug: OCR/update gap %.2fs", gap)
            self._debug_last_update_at = now
            self._debug_timing_summary()

        if not self.field_mapping:
            logger.debug("Field mapping is not set")
            return

        force_send = self.force_next_send
        look_in = [TextDetectionTargetWithResult.ResultState.Success]
        if self.update_same or force_send:
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
            if force_send:
                self.force_next_send = False
