"""Opdracht 1 en 2: systeeminformatie verzamelen en filteren tot één dict."""
from __future__ import annotations
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import psutil
except ImportError as exc:
    raise SystemExit(
        "This program requires psutil. Install it with: python -m pip install psutil"
    ) from exc

BYTES_PER_GIB = 1024 ** 3

# Waarden die fabrikanten invullen als er geen echt serienummer is
SERIAL_PLACEHOLDERS = {
    "", "to be filled by o.e.m.", "default string", "system serial number", "none", "n/a", "na",
    "null", "not specified", "not applicable", "unknown", "serial number", "default", "0",
}


def run_command(command: List[str]) -> Optional[str]:
    """Run a local command and return non-empty stdout on success."""
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    output = completed.stdout.strip()
    return output if completed.returncode == 0 and output else None


def run_powershell(script: str) -> Optional[str]:
    """Run PowerShell when available on Windows."""
    for executable in ("powershell", "pwsh"):
        if shutil.which(executable):
            return run_command([executable, "-NoProfile", "-Command", script])
    return None


def first_nonempty_line(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return None


def first_existing_text(paths: Iterable[str]) -> Optional[str]:
    """Read the first accessible, non-empty text file from paths."""
    for filename in paths:
        try:
            value = Path(filename).read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if value:
            return value
    return None


def get_device_model() -> Optional[str]:
    """Return the hardware model using an OS-specific source."""
    system = platform.system()
    if system == "Linux":
        vendor = first_existing_text(["/sys/class/dmi/id/sys_vendor"])
        model = first_existing_text(
            ["/sys/class/dmi/id/product_name", "/sys/class/dmi/id/board_name"]
        )
        if vendor and model:
            return model if vendor.lower() in model.lower() else f"{vendor} {model}"
        return model or vendor
    if system == "Darwin":
        return first_nonempty_line(run_command(["sysctl", "-n", "hw.model"]))
    if system == "Windows":
        return first_nonempty_line(
            run_powershell("(Get-CimInstance -ClassName Win32_ComputerSystem).Model")
        )
    return platform.machine() or None


def clean_serial(value: Optional[str]) -> Optional[str]:
    """Geef None terug als het 'serienummer' een placeholder van de fabrikant is."""
    if value is None:
        return None
    value = str(value).strip()
    if value.lower() in SERIAL_PLACEHOLDERS or set(value) <= {"0"}:
        return None
    return value


def get_serial_number() -> Optional[str]:
    """Return the serial number of the computer (BIOS/system serial), if readable."""
    system = platform.system()
    value: Optional[str] = None
    if system == "Windows":
        value = first_nonempty_line(
            run_powershell("(Get-CimInstance -ClassName Win32_BIOS).SerialNumber")
        )
    elif system == "Linux":
        # product_serial is vaak enkel leesbaar met beheerdersrechten
        value = first_existing_text(
            [
                "/sys/class/dmi/id/product_serial",
                "/sys/class/dmi/id/board_serial",
                "/sys/class/dmi/id/chassis_serial",
            ]
        )
    elif system == "Darwin":
        output = run_command(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
        if output:
            match = re.search(r'"IOPlatformSerialNumber"\s*=\s*"([^"]+)"', output)
            value = match.group(1) if match else None
    return clean_serial(value)


def get_processor_name() -> Optional[str]:
    """Return the processor model rather than a logical processor index."""
    system = platform.system()
    if system == "Linux":
        try:
            fields: Dict[str, str] = {}
            for line in Path("/proc/cpuinfo").read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                if ":" not in line:
                    continue
                key, value = (part.strip() for part in line.split(":", 1))
                if key.lower() in {"model name", "hardware", "processor"} and value:
                    fields.setdefault(key.lower(), value)
            for key in ("model name", "hardware", "processor"):
                if fields.get(key):
                    return fields[key]
        except OSError:
            pass
    if system == "Darwin":
        value = first_nonempty_line(
            run_command(["sysctl", "-n", "machdep.cpu.brand_string"])
        )
        if value:
            return value
    if system == "Windows":
        value = first_nonempty_line(
            run_powershell(
                "(Get-CimInstance -ClassName Win32_Processor | "
                "Select-Object -First 1 -ExpandProperty Name)"
            )
        )
        if value:
            return value
    return platform.processor() or platform.uname().processor or platform.machine() or None


def get_physical_core_count() -> Optional[int]:
    """Return physical CPU cores, with native fallbacks when needed."""
    count = psutil.cpu_count(logical=False)
    if count is not None:
        return int(count)
    system = platform.system()
    if system == "Darwin":
        value = first_nonempty_line(run_command(["sysctl", "-n", "hw.physicalcpu"]))
    elif system == "Windows":
        value = first_nonempty_line(
            run_powershell(
                "(Get-CimInstance -ClassName Win32_Processor | "
                "Measure-Object -Property NumberOfCores -Sum).Sum"
            )
        )
    else:
        value = None
    try:
        return int(float(value)) if value is not None else None
    except ValueError:
        return None


def get_max_cpu_frequency_mhz() -> Optional[float]:
    """Return the maximum CPU frequency in MHz."""
    frequency = psutil.cpu_freq()
    if frequency is not None and frequency.max and frequency.max > 0:
        return round(float(frequency.max), 2)
    system = platform.system()
    if system == "Linux":
        value = first_existing_text(
            [
                "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq",
                "/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq",
            ]
        )
        try:
            return round(float(value) / 1000, 2) if value is not None else None
        except ValueError:
            return None
    if system == "Darwin":
        value = first_nonempty_line(run_command(["sysctl", "-n", "hw.cpufrequency_max"]))
        try:
            return round(float(value) / 1_000_000, 2) if value else None
        except ValueError:
            return None
    if system == "Windows":
        value = first_nonempty_line(
            run_powershell(
                "(Get-CimInstance -ClassName Win32_Processor | "
                "Measure-Object -Property MaxClockSpeed -Maximum).Maximum"
            )
        )
        try:
            return round(float(value), 2) if value else None
        except ValueError:
            return None
    return None


def get_system_root_partition() -> Tuple[Optional[Any], Any]:
    """Find the mounted partition containing the operating system root."""
    root = os.path.abspath(os.sep)
    root_normalized = os.path.normcase(os.path.normpath(root))
    partitions = psutil.disk_partitions(all=False)
    for partition in partitions:
        mount = os.path.normcase(os.path.normpath(partition.mountpoint))
        if mount == root_normalized:
            try:
                return partition, psutil.disk_usage(partition.mountpoint)
            except OSError:
                pass
    candidates = []
    for partition in partitions:
        mount = os.path.normcase(os.path.normpath(partition.mountpoint))
        try:
            contains_root = os.path.commonpath([root_normalized, mount]) == mount
        except ValueError:
            contains_root = False
        if contains_root:
            candidates.append(partition)
    for partition in sorted(candidates, key=lambda item: len(item.mountpoint), reverse=True):
        try:
            return partition, psutil.disk_usage(partition.mountpoint)
        except OSError:
            continue
    return None, psutil.disk_usage(root)


def get_storage_info() -> Dict[str, Optional[Any]]:
    """Describe the filesystem containing the operating system."""
    partition, usage = get_system_root_partition()
    return {
        "mount_point": partition.mountpoint if partition else os.path.abspath(os.sep),
        "device": partition.device if partition else None,
        "file_system": partition.fstype if partition else None,
        "capacity_gib": round(usage.total / BYTES_PER_GIB, 2),
    }


def get_linux_default_route_interface() -> Optional[str]:
    """Return the Linux interface with the lowest-metric default IPv4 route."""
    raw_json = run_command(["ip", "-j", "route", "show", "default"])
    if raw_json:
        try:
            routes = json.loads(raw_json)
            candidates = [route for route in routes if route.get("dev")]
            if candidates:
                candidates.sort(key=lambda route: int(route.get("metric", 0)))
                return str(candidates[0]["dev"])
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    raw_text = run_command(["ip", "route", "show", "default"])
    if raw_text:
        candidates: List[Tuple[int, str]] = []
        for line in raw_text.splitlines():
            fields = line.split()
            if "dev" not in fields:
                continue
            try:
                interface = fields[fields.index("dev") + 1]
            except IndexError:
                continue
            metric = 0
            if "metric" in fields:
                try:
                    metric = int(fields[fields.index("metric") + 1])
                except (IndexError, ValueError):
                    pass
            candidates.append((metric, interface))
        if candidates:
            return min(candidates)[1]
    return None


def get_default_route_interface() -> Optional[str]:
    """Return the OS interface carrying the default IPv4 route."""
    system = platform.system()
    if system == "Linux":
        return get_linux_default_route_interface()
    if system == "Darwin":
        output = run_command(["route", "-n", "get", "default"])
        if output:
            match = re.search(r"^\s*interface:\s*(\S+)", output, re.MULTILINE)
            return match.group(1) if match else None
    if system == "Windows":
        return first_nonempty_line(
            run_powershell(
                "Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' | "
                "Sort-Object RouteMetric, InterfaceMetric | "
                "Select-Object -First 1 -ExpandProperty InterfaceAlias"
            )
        )
    return None


def normalized_ip(value: str) -> str:
    """Remove an IPv6 zone identifier such as %en0 before validation."""
    return value.split("%", 1)[0]


def non_loopback_ipv4_addresses(addresses: Iterable[Any]) -> List[str]:
    values = []
    for address in addresses:
        if address.family != socket.AF_INET:
            continue
        try:
            parsed = ipaddress.IPv4Address(address.address)
        except ipaddress.AddressValueError:
            continue
        if not parsed.is_loopback and not parsed.is_unspecified:
            values.append(str(parsed))
    return sorted(set(values), key=lambda value: int(ipaddress.IPv4Address(value)))


def get_mac_address(addresses: Iterable[Any]) -> Optional[str]:
    """Extract a real MAC address across supported psutil/OS families."""
    link_families = {
        getattr(psutil, "AF_LINK", object()),
        getattr(socket, "AF_PACKET", object()),
    }
    for address in addresses:
        if address.family not in link_families:
            continue
        hex_digits = re.sub(r"[^0-9a-f]", "", address.address.strip().lower())
        if len(hex_digits) == 12 and hex_digits != "0" * 12:
            return ":".join(hex_digits[index : index + 2] for index in range(0, 12, 2))
    return None


def get_outbound_interface(addresses_by_interface: Dict[str, List[Any]]) -> Optional[str]:
    """Map the local address selected by UDP routing to an interface."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # UDP connect selects a local route; it does not send a packet.
            sock.connect(("8.8.8.8", 53))
            local_address = sock.getsockname()[0]
    except OSError:
        return None
    for interface, addresses in addresses_by_interface.items():
        if local_address in non_loopback_ipv4_addresses(addresses):
            return interface
    return None


def get_interface_fallback(
    addresses_by_interface: Dict[str, List[Any]], stats: Dict[str, Any]
) -> Optional[str]:
    """Choose an active non-loopback IPv4 interface deterministically."""
    virtual_prefixes = ("docker", "br-", "veth", "virbr", "vmnet", "vboxnet", "zt")
    candidates = []
    for interface, addresses in addresses_by_interface.items():
        info = stats.get(interface)
        if not info or not info.isup:
            continue
        if not non_loopback_ipv4_addresses(addresses):
            continue
        is_virtual = interface.lower().startswith(virtual_prefixes)
        has_mac = get_mac_address(addresses) is not None
        candidates.append((is_virtual, not has_mac, interface))
    return min(candidates)[-1] if candidates else None


def get_interface_addresses(addresses: Iterable[Any]) -> Dict[str, Optional[str]]:
    """Select MAC, IPv4, global IPv6, and IPv6 link-local address."""
    addresses = list(addresses)
    ipv4 = non_loopback_ipv4_addresses(addresses)
    ipv6_global: List[str] = []
    ipv6_link_local: List[str] = []
    for address in addresses:
        if address.family != socket.AF_INET6:
            continue
        try:
            parsed = ipaddress.IPv6Address(normalized_ip(address.address))
        except ipaddress.AddressValueError:
            continue
        if parsed.is_link_local:
            ipv6_link_local.append(str(parsed))
        elif parsed.is_global:
            ipv6_global.append(str(parsed))
    return {
        "mac_address": get_mac_address(addresses),
        "ipv4_address": ipv4[0] if ipv4 else None,
        "ipv6_address": sorted(set(ipv6_global))[0] if ipv6_global else None,
        "ipv6_link_local_address": sorted(set(ipv6_link_local))[0]
        if ipv6_link_local
        else None,
    }


def get_primary_network_info() -> Dict[str, Optional[str]]:
    """Identify and describe the primary network interface."""
    addresses_by_interface = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    interface = get_default_route_interface()
    selection_method = "default_ipv4_route"
    if interface not in addresses_by_interface:
        interface = get_outbound_interface(addresses_by_interface)
        selection_method = "local_address_selected_by_outbound_route" if interface else ""
    if interface is None:
        interface = get_interface_fallback(addresses_by_interface, stats)
        selection_method = "active_interface_with_ipv4" if interface else "no_interface_found"
    result: Dict[str, Optional[str]] = {
        "interface": interface,
        "selection_method": selection_method,
        "mac_address": None,
        "ipv4_address": None,
        "ipv6_address": None,
        "ipv6_link_local_address": None,
    }
    if interface:
        result.update(get_interface_addresses(addresses_by_interface[interface]))
    return result


def collect_selected_system_info() -> Dict[str, Any]:
    """Build the requested dictionary with explicit, consistent units."""
    return {
        "device_name": socket.gethostname(),
        "device_model": get_device_model(),
        "serial_number": get_serial_number(),
        "processor": get_processor_name(),
        "physical_cpu_cores": get_physical_core_count(),
        "maximum_cpu_frequency_mhz": get_max_cpu_frequency_mhz(),
        "total_ram_gib": round(psutil.virtual_memory().total / BYTES_PER_GIB, 2),
        "storage": get_storage_info(),
        "primary_network_interface": get_primary_network_info(),
    }


if __name__ == "__main__":
    selected_info = collect_selected_system_info()  # A Python dict
    print(json.dumps(selected_info, indent=2, ensure_ascii=False))
