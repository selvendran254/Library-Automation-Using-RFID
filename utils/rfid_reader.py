"""Real RFID hardware service — USB Serial reader + shared scan buffer."""

import os
import subprocess
import threading
from datetime import datetime, timezone

from models.settings import LibrarySetting


class RfidHardwareService:
    _lock = threading.Lock()
    _thread = None
    _running = False
    _serial = None
    _last_scan = None
    _scan_counter = 0
    _error = None
    _port = None
    _baud = 9600

    RFID_USB_KEYWORDS = [
        "rfid", "125khz", "13.56mhz", "13.56", "nfc", "em4100", "em18",
        "mifare", "rdm630", "uhf", "card reader", "tag reader", "proximity",
        "hid reader", "usb reader", "id reader",
    ]

    REGULAR_KEYBOARD_PATTERNS = [
        "dell", "logitech", "microsoft", "lenovo", "hp ", "hewlett",
        "corsair", "razer", "apple", "kb216", "kb522", "wired keyboard",
        "wireless keyboard", "mechanical keyboard", "gaming keyboard",
    ]

    READER_CHIPSETS = ["1a86", "10c4", "0403", "062a", "0c27", "1eab", "1347", "0483"]

    @classmethod
    def get_mode(cls):
        mode = LibrarySetting.get("rfid_mode", "hid")
        if mode == "simulation":
            return "hid"
        return mode if mode in ("hid", "serial") else "hid"

    @classmethod
    def get_port(cls):
        return LibrarySetting.get("rfid_serial_port", "/dev/ttyUSB0")

    @classmethod
    def get_baud(cls):
        return LibrarySetting.get_int("rfid_baud_rate", 9600)

    @classmethod
    def configure_from_settings(cls):
        cls._port = cls.get_port()
        cls._baud = cls.get_baud()

    @classmethod
    def list_serial_ports(cls):
        try:
            import serial.tools.list_ports

            ports = serial.tools.list_ports.comports()
            return [
                {"device": p.device, "description": p.description or "Unknown"}
                for p in ports
            ]
        except ImportError:
            return []
        except Exception as exc:
            return [{"device": "error", "description": str(exc)}]

    @classmethod
    def is_running(cls):
        return cls._running and cls._thread is not None and cls._thread.is_alive()

    @classmethod
    def get_status(cls):
        cls.configure_from_settings()
        return {
            "mode": cls.get_mode(),
            "port": cls._port,
            "baud": cls._baud,
            "running": cls.is_running(),
            "error": cls._error,
            "last_scan": cls._last_scan,
        }

    @classmethod
    def _set_scan(cls, tag, source="serial"):
        tag = cls._clean_tag(tag)
        if not tag:
            return
        with cls._lock:
            cls._scan_counter += 1
            cls._last_scan = {
                "id": cls._scan_counter,
                "tag": tag,
                "source": source,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            cls._error = None

    @classmethod
    def _clean_tag(cls, raw):
        tag = (raw or "").strip()
        prefix = LibrarySetting.get("rfid_tag_prefix", "") or ""
        suffix = LibrarySetting.get("rfid_tag_suffix", "") or ""
        if prefix and tag.startswith(prefix):
            tag = tag[len(prefix):]
        if suffix and tag.endswith(suffix):
            tag = tag[: -len(suffix)]
        return tag.strip().upper()

    @classmethod
    def get_scan_since(cls, since_id=0):
        with cls._lock:
            if cls._last_scan and cls._last_scan["id"] > int(since_id or 0):
                return dict(cls._last_scan)
        return None

    @classmethod
    def push_scan(cls, tag, source="manual"):
        cls._set_scan(tag, source)

    @classmethod
    def start(cls):
        cls.configure_from_settings()
        if cls.get_mode() != "serial":
            cls.stop()
            return False, "Serial reader only starts in serial mode."

        if cls.is_running():
            return True, "Reader already running."

        if not cls._port:
            return False, "Serial port not configured."

        cls._running = True
        cls._error = None
        cls._thread = threading.Thread(target=cls._read_loop, daemon=True)
        cls._thread.start()
        return True, f"Listening on {cls._port} @ {cls._baud} baud"

    @classmethod
    def stop(cls):
        cls._running = False
        if cls._serial and cls._serial.is_open:
            try:
                cls._serial.close()
            except Exception:
                pass
        cls._serial = None
        cls._thread = None

    @classmethod
    def _read_loop(cls):
        try:
            import serial

            cls._serial = serial.Serial(
                port=cls._port,
                baudrate=cls._baud,
                timeout=0.5,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            while cls._running:
                try:
                    if cls._serial.in_waiting:
                        raw = cls._serial.readline()
                        tag = raw.decode("utf-8", errors="ignore").strip()
                        if tag:
                            cls._set_scan(tag, "serial")
                    else:
                        import time

                        time.sleep(0.05)
                except Exception as exc:
                    cls._error = str(exc)
                    import time

                    time.sleep(1)
        except ImportError:
            cls._error = "pyserial not installed. Run: pip install pyserial"
            cls._running = False
        except Exception as exc:
            cls._error = f"Serial open failed: {exc}"
            cls._running = False

    @classmethod
    def test_port(cls, port=None, baud=None):
        port = port or cls.get_port()
        baud = baud or cls.get_baud()
        try:
            import serial

            ser = serial.Serial(port, baud, timeout=2)
            ser.close()
            return True, f"Port {port} is available."
        except ImportError:
            return False, "pyserial not installed."
        except Exception as exc:
            return False, str(exc)

    @classmethod
    def _has_recent_scan(cls, seconds=300):
        with cls._lock:
            if not cls._last_scan:
                return False
            ts = cls._last_scan.get("timestamp")
            if not ts:
                return False
            scanned_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if scanned_at.tzinfo is None:
                scanned_at = scanned_at.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - scanned_at).total_seconds() < seconds

    @classmethod
    def _run_command(cls, cmd):
        try:
            return subprocess.check_output(cmd, text=True, timeout=2, stderr=subprocess.DEVNULL)
        except Exception:
            return ""

    @classmethod
    def _scan_usb_devices(cls):
        output = cls._run_command(["lsusb"])
        return [line.strip() for line in output.splitlines() if line.strip()]

    @classmethod
    def _is_regular_keyboard(cls, text):
        lower = (text or "").lower()
        return any(pattern in lower for pattern in cls.REGULAR_KEYBOARD_PATTERNS)

    @classmethod
    def _get_usb_hid_inputs(cls):
        try:
            with open("/proc/bus/input/devices", encoding="utf-8", errors="ignore") as handle:
                blocks = handle.read().split("\n\n")
        except OSError:
            return []

        results = []
        for block in blocks:
            lower = block.lower()
            if "usb" not in lower or "key=" not in lower:
                continue
            if "handlers=" not in lower or "kbd" not in lower:
                continue
            if "mouse" in lower or "touchpad" in lower or "trackpad" in lower:
                continue
            if "consumer control" in lower or "system control" in lower:
                continue

            name = ""
            phys = ""
            for line in block.split("\n"):
                if line.startswith("N: Name="):
                    name = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("P: Phys="):
                    phys = line.split("=", 1)[1].strip()

            if not phys.startswith("usb"):
                continue
            if cls._is_regular_keyboard(name):
                continue

            results.append({"name": name, "phys": phys})
        return results

    @classmethod
    def _get_potential_reader_usb_lines(cls, usb_lines):
        custom = (LibrarySetting.get("rfid_usb_keyword", "") or "").strip().lower()
        candidates = []

        for line in usb_lines:
            lower = line.lower()
            if "root hub" in lower:
                continue
            if custom and custom in lower:
                candidates.append(line)
                continue
            if any(keyword in lower for keyword in cls.RFID_USB_KEYWORDS):
                candidates.append(line)
                continue
            if any(chip in lower for chip in cls.READER_CHIPSETS):
                candidates.append(line)
                continue
            if "keyboard" in lower and not cls._is_regular_keyboard(line):
                candidates.append(line)

        return candidates

    @classmethod
    def _port_exists(cls, port):
        if not port:
            return False
        if os.name == "nt":
            return port.upper().startswith("COM")
        return os.path.exists(port)

    @classmethod
    def _check_serial_connection(cls):
        cls.configure_from_settings()
        port = cls._port
        ports = cls.list_serial_ports()
        port_listed = any(p["device"] == port for p in ports)
        port_exists = cls._port_exists(port)

        if not port_listed and not port_exists:
            return cls._connection_result(
                False,
                f"Port {port} not found — USB reader not plugged in",
                mode="serial",
                device=None,
            )

        ok, test_msg = cls.test_port(port, cls._baud)
        if not ok:
            return cls._connection_result(False, f"Not Connected — {test_msg}", mode="serial")

        if not cls.is_running():
            cls.start()

        if cls._error:
            return cls._connection_result(
                False, f"Not Connected — {cls._error}", mode="serial", device=port
            )

        if cls.is_running():
            return cls._connection_result(
                True,
                f"Connected — Serial reader on {port}",
                mode="serial",
                device=port,
            )

        return cls._connection_result(
            True, f"Connected — Port {port} ready", mode="serial", device=port
        )

    @classmethod
    def _check_hid_connection(cls):
        usb_lines = cls._scan_usb_devices()
        matched_usb = cls._get_potential_reader_usb_lines(usb_lines)
        hid_inputs = cls._get_usb_hid_inputs()

        if matched_usb:
            return cls._connection_result(
                True,
                "Connected — " + matched_usb[0][:70],
                mode="hid",
                device=matched_usb[0],
            )

        if hid_inputs:
            device_name = hid_inputs[0]["name"] or hid_inputs[0]["phys"]
            return cls._connection_result(
                True,
                f"Connected — USB reader: {device_name[:50]}",
                mode="hid",
                device=device_name,
            )

        if not usb_lines or all("root hub" in line.lower() for line in usb_lines):
            return cls._connection_result(
                False,
                "Not Connected — No USB devices found",
                mode="hid",
            )

        return cls._connection_result(
            False,
            "Not Connected — Plug USB RFID reader (Settings → RFID Setup)",
            mode="hid",
        )

    @classmethod
    def _connection_result(cls, connected, message, mode, device=None):
        return {
            "connected": connected,
            "status": "connected" if connected else "not_connected",
            "label": "Connected" if connected else "Not Connected",
            "message": message,
            "mode": mode,
            "device": device,
            "real_hardware": mode in ("hid", "serial"),
            "last_scan": cls._last_scan,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def check_connection(cls):
        mode = cls.get_mode()
        if mode == "serial":
            return cls._check_serial_connection()
        return cls._check_hid_connection()
