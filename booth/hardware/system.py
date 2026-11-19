"""System monitoring: temperature, CPU, memory, disk and Pi throttling flags.

Pure standard library on purpose - no psutil - so the tool keeps its short
dependency list and installs on a fresh Pi without extra packages.

The most valuable part is not the temperature but `vcgencmd get_throttled`:
it reports under-voltage and thermal throttling both live and since boot, and
under-voltage is by far the most common cause of a Raspberry Pi behaving
strangely for no apparent reason.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Bit meanings of vcgencmd get_throttled. The low bits are "right now",
# the high bits are "has happened at some point since boot".
_THROTTLE_BITS = {
    0: ("under_voltage_now", "Unterspannung: Netzteil oder Kabel zu schwach"),
    1: ("freq_capped_now", "Taktfrequenz begrenzt"),
    2: ("throttled_now", "Drosselung aktiv: zu heiß oder zu wenig Spannung"),
    3: ("soft_temp_limit_now", "Temperaturgrenze erreicht, Takt wird gesenkt"),
    16: ("under_voltage_seen", "Unterspannung war seit dem Start schon einmal aufgetreten"),
    17: ("freq_capped_seen", "Taktbegrenzung war seit dem Start schon einmal aktiv"),
    18: ("throttled_seen", "Drosselung war seit dem Start schon einmal aktiv"),
    19: ("soft_temp_limit_seen", "Temperaturgrenze war seit dem Start schon einmal erreicht"),
}

_TEMP_WARN = 70.0
_TEMP_CRIT = 80.0


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


#: The name the bridge registers its virtual touchscreen under.
#: Must match NAME in autostart/touch-bridge.py.
BRIDGE_NAME = "Fotobox Touchscreen"

_INPUT_DEVICES = Path("/proc/bus/input/devices")


def touch_status() -> dict[str, Any]:
    """Is the touchscreen there - and does it arrive as touch?

    Two separate questions, because there are two kinds of failure. If the
    screen drops off USB, nothing is left. If only the bridge dies, the device
    is still attached but reports itself as a mouse: tapping works, swiping
    does not. Otherwise you find that out when somebody is standing in front
    of it.

    Reads /proc/bus/input/devices - no process, costs nothing.
    """
    namen: list[str] = []
    try:
        for zeile in _INPUT_DEVICES.read_text(errors="replace").splitlines():
            if zeile.startswith("N: Name="):
                namen.append(zeile.split("=", 1)[1].strip().strip('"'))
    except OSError:
        return {"present": None, "bridged": None, "name": ""}
    gebrueckt = BRIDGE_NAME in namen
    # The real screen, not the bridge's own device.
    roh = [n for n in namen if "touch" in n.lower() and n != BRIDGE_NAME]
    return {"present": bool(roh), "bridged": gebrueckt, "name": roh[0] if roh else ""}


#: Answers that cost something are kept for a while.
_NETZ_CACHE: dict[str, Any] = {"ssid": ("", 0.0), "draussen": (None, 0.0)}
_SSID_GILT_S = 20.0
_PROBE_GILT_S = 60.0
_PROBE_PORT = 443
_PROBE_TIMEOUT_S = 2.0


def _standardroute() -> str | None:
    """The interface everything leaves by - or None.

    /proc/net/route rather than a call to `ip route`: the file is sitting
    ready in the kernel and costs nothing, and the status is fetched every
    three seconds. The default route is the line with destination 00000000.
    """
    try:
        zeilen = Path("/proc/net/route").read_text().splitlines()[1:]
    except OSError:
        return None
    for zeile in zeilen:
        teile = zeile.split()
        if len(teile) > 1 and teile[1] == "00000000":
            return teile[0]
    return None


def _ssid(gerät: str) -> str:
    """The name of the Wi-Fi network, asked again at most every 20 seconds."""
    wert, stand = _NETZ_CACHE["ssid"]
    if time.monotonic() - stand < _SSID_GILT_S:
        return wert
    name = ""
    if shutil.which("iwgetid"):
        try:
            name = subprocess.run(["iwgetid", gerät, "-r"], capture_output=True,
                                  text=True, timeout=3).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            name = ""
    _NETZ_CACHE["ssid"] = (name, time.monotonic())
    return name


def _erreichbar(host: str) -> bool | None:
    """Can we actually get out? Asked at most once a minute.

    A default route only means a path is registered. Whether anyone answers at
    the other end takes an actual connection attempt - and that is exactly the
    difference between "the cable is in" and "pictures are going out". The
    host checked is the one the box talks to anyway.
    """
    wert, stand = _NETZ_CACHE["draussen"]
    if time.monotonic() - stand < _PROBE_GILT_S:
        return wert
    import socket  # noqa: PLC0415 - needed here and nowhere else

    try:
        with socket.create_connection((host, _PROBE_PORT), _PROBE_TIMEOUT_S):
            ergebnis = True
    except OSError:
        ergebnis = False
    _NETZ_CACHE["draussen"] = (ergebnis, time.monotonic())
    return ergebnis


def network_status(probe_host: str | None = None) -> dict[str, Any]:
    """Is the box on a network - and does that get it to the internet?

    Two questions, two answers. The box carries on without a network:
    pictures are taken, printed and written to the stick. Only the uploading
    to EventPics waits. So "no network" is not a fault here, it is something
    to look into.
    """
    gerät = _standardroute()
    if not gerät:
        return {"up": False, "kind": "", "device": "", "ssid": "", "online": False}
    drahtlos = Path(f"/sys/class/net/{gerät}/wireless").exists() or gerät.startswith("w")
    carrier = _read(f"/sys/class/net/{gerät}/carrier")
    up = carrier == "1" or _read(f"/sys/class/net/{gerät}/operstate") == "up"
    return {
        "up": bool(up),
        "kind": "WLAN" if drahtlos else "LAN",
        "device": gerät,
        "ssid": _ssid(gerät) if drahtlos else "",
        "online": _erreichbar(probe_host) if (up and probe_host) else None,
    }


class SystemMonitor:
    """Samples system health and keeps a short temperature history."""

    def __init__(self, capture_dir: Path, history_seconds: int = 3600, interval: float = 5.0) -> None:
        self.capture_dir = capture_dir
        self.interval = interval
        self.history: deque[tuple[float, float | None]] = deque(maxlen=int(history_seconds / interval))
        self._prev_cpu: tuple[int, int] | None = None
        self._throttled_cache: tuple[float, dict[str, Any]] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._cpu_mhz_max: int | None = None
        self.cpu_percent()  # prime the delta so the first reading is sane
        self._thread = threading.Thread(target=self._sample_loop, name="sysmon", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _sample_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                self.history.append((time.time(), self.temperature()))
            self._stop.wait(self.interval)

    # -- individual readings ----------------------------------------------
    def temperature(self) -> float | None:
        raw = _read("/sys/class/thermal/thermal_zone0/temp")
        if raw is None:
            return None
        try:
            return round(int(raw) / 1000.0, 1)
        except ValueError:
            return None

    def cpu_percent(self) -> float | None:
        """Overall CPU load since the previous call, from /proc/stat."""
        raw = _read("/proc/stat")
        if raw is None:
            return None
        fields = raw.splitlines()[0].split()[1:]
        try:
            values = [int(v) for v in fields]
        except ValueError:
            return None
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        previous, self._prev_cpu = self._prev_cpu, (idle, total)
        if previous is None:
            return None
        idle_delta = idle - previous[0]
        total_delta = total - previous[1]
        if total_delta <= 0:
            return None
        return round(100.0 * (1.0 - idle_delta / total_delta), 1)

    def cpu_mhz(self) -> int | None:
        raw = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
        try:
            return int(raw) // 1000 if raw else None
        except ValueError:
            return None

    def cpu_mhz_max(self) -> int | None:
        """The highest clock this processor is allowed to run at.

        Does not change while running, so it is read once and kept. Without it
        the current clock says nothing: 600 MHz can mean idle or mean thermal
        throttling - only the comparison with the ceiling decides.
        """
        if self._cpu_mhz_max is None:
            raw = _read("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
            try:
                self._cpu_mhz_max = int(raw) // 1000 if raw else 0
            except ValueError:
                self._cpu_mhz_max = 0
        return self._cpu_mhz_max or None

    def memory(self) -> dict[str, Any]:
        raw = _read("/proc/meminfo")
        if raw is None:
            return {"available": False}
        values: dict[str, int] = {}
        for line in raw.splitlines():
            key, _, rest = line.partition(":")
            try:
                values[key] = int(rest.split()[0])  # kB
            except (IndexError, ValueError):
                continue
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        swap_total = values.get("SwapTotal", 0)
        swap_free = values.get("SwapFree", 0)
        return {
            "available": True,
            "total_mb": round(total / 1024),
            "available_mb": round(available / 1024),
            "used_mb": round((total - available) / 1024),
            "used_percent": round(100.0 * (total - available) / total, 1) if total else None,
            "swap_used_mb": round((swap_total - swap_free) / 1024),
        }

    def process_rss_mb(self) -> float | None:
        raw = _read("/proc/self/status")
        if raw is None:
            return None
        for line in raw.splitlines():
            if line.startswith("VmRSS:"):
                try:
                    return round(int(line.split()[1]) / 1024, 1)
                except (IndexError, ValueError):
                    return None
        return None

    def disk(self) -> dict[str, Any]:
        try:
            usage = shutil.disk_usage(self.capture_dir)
        except OSError:
            return {"available": False}
        return {
            "available": True,
            "total_gb": round(usage.total / 1e9, 1),
            "free_gb": round(usage.free / 1e9, 1),
            "used_percent": round(100.0 * usage.used / usage.total, 1) if usage.total else None,
        }

    def loadavg(self) -> list[float] | None:
        try:
            return [round(v, 2) for v in os.getloadavg()]
        except (OSError, AttributeError):
            return None

    def uptime_s(self) -> float | None:
        raw = _read("/proc/uptime")
        try:
            return round(float(raw.split()[0])) if raw else None
        except (IndexError, ValueError):
            return None

    def throttled(self) -> dict[str, Any]:
        """Raspberry Pi under-voltage and throttling flags, cached for 5 s."""
        now = time.monotonic()
        if self._throttled_cache and now - self._throttled_cache[0] < 5.0:
            return self._throttled_cache[1]

        result: dict[str, Any] = {"available": False}
        if shutil.which("vcgencmd"):
            try:
                out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True,
                                     text=True, timeout=5, check=False).stdout.strip()
                value = int(out.split("=")[1], 16)
                flags = {name: bool(value & (1 << bit)) for bit, (name, _) in _THROTTLE_BITS.items()}
                result = {"available": True, "raw": hex(value), **flags}
            except Exception as exc:  # noqa: BLE001 - never break the status call
                result = {"available": False, "error": str(exc)}

        self._throttled_cache = (now, result)
        return result

    # -- combined ----------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        temperature = self.temperature()
        memory = self.memory()
        disk = self.disk()
        throttled = self.throttled()

        warnings: list[str] = []
        if temperature is not None:
            if temperature >= _TEMP_CRIT:
                warnings.append(f"Temperatur {temperature} °C, der Pi drosselt gleich. Kühlung prüfen.")
            elif temperature >= _TEMP_WARN:
                warnings.append(f"Temperatur {temperature} °C, wird warm, Belüftung im Auge behalten.")
        for bit, (name, text) in _THROTTLE_BITS.items():
            if throttled.get(name):
                warnings.append(text)
        if memory.get("used_percent") is not None and memory["used_percent"] >= 85:
            warnings.append(f"Arbeitsspeicher zu {memory['used_percent']} % belegt.")
        if memory.get("swap_used_mb", 0) > 50:
            warnings.append(f"Auslagerung aktiv ({memory['swap_used_mb']} MB), der Speicher wird knapp.")
        if disk.get("available") and disk.get("free_gb", 99) < 1.0:
            warnings.append(f"Nur noch {disk['free_gb']} GB frei.")

        return {
            "temperature_c": temperature,
            "temp_warn": _TEMP_WARN,
            "temp_crit": _TEMP_CRIT,
            "cpu_percent": self.cpu_percent(),
            "cpu_mhz": self.cpu_mhz(),
            "cpu_mhz_max": self.cpu_mhz_max(),
            "loadavg": self.loadavg(),
            "memory": memory,
            "process_rss_mb": self.process_rss_mb(),
            "disk": disk,
            "uptime_s": self.uptime_s(),
            "throttled": throttled,
            "warnings": warnings,
        }

    def temperature_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"t": round(t), "c": c} for t, c in self.history if c is not None]
