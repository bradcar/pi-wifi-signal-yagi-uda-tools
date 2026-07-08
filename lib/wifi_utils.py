# wifi_utils.py
"""
Collection of utility functions for working with Pi Zero WiFi networks.

Features
    * if set up flag constant USE_PROC_NET_WIRELESS, will use fast low-level direct reads,
      this is speed improvement over sudo nmcli method
    * new RSSI value is returned only if at least one of rssi, quality, or missed beacons has changed,
      this more often then not prevents returning stale values.

    * Connected:  /proc/net/wireless - highest cadence updates (only gets RSSI & quality), uses fingerprint
      to only return if results changed
    * Connected: iw link - slower cadence, returns RSSI, Link quality, RX & TX bitrates
    * Connected: iw scan dump - if use SCAN_CACHES_FAST_MODE=True, however this may return stale data
    * Scan:  iw scan - returns RSSI


TODOS
    * TODO added code for 'shell-fi' to use static IPs, CHECK to see if connect drops from 6 sec to 1-2sec

Requirements to avoid password:
    sudo visudo
    add pi-admin ALL=(ALL) NOPASSWD: /usr/sbin/iw (or just /usr/bin/iw depending on your path)
"""
import logging
import os
import re
import subprocess
import time

from lib.pi_zero_utils import timeout

# Fast scan only get RSSI
USE_PROC_NET_WIRELESS = False

# fast scan but stale cached data returned quickly
SCAN_CACHES_FAST_MODE = False

# Tracks (Link Quality, RSSI, Missed Beacons) to filter out results with no state change
_last_wireless_fingerprint = None

# setup model-level logger
logger = logging.getLogger(__name__)

# "iw" on Pi Zero needs this path
IW_CMD = "/usr/sbin/iw" if os.path.exists("/usr/sbin/iw") else "iw"


class PiNetworkMock:
    """Mock object mimicking CoreWLAN network objects to preserve core display loop structure"""

    def __init__(self, ssid, bssid, rssi, band, channel):
        self._ssid = ssid
        self._bssid = bssid
        self._rssi = rssi
        self._band = band
        self._channel = channel

    def ssid(self):
        return self._ssid if self._ssid != ".hidden." else None

    def bssid(self):
        return self._bssid

    def rssi_value(self):
        return self._rssi

    def parsed_band(self):
        return self._band

    def channel(self):
        return self._channel


def init_wifi():
    """Initialize CoreWLAN client and returns the active Wi-Fi"""

    # Validate 'iw' utility executes
    try:
        subprocess.run([IW_CMD, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError):
        raise FileNotFoundError(
            f"CRITICAL: Failed to execute '{IW_CMD}'. Check environment variables or run 'sudo apt install iw'."
        )

    # For Raspberry Pi, check that wlan0 interface is accessible via iwlist
    if os.path.exists("/sys/class/net/wlan0"):
        return "wlan0"
    return None


def get_ssid():
    """
    get ESSID string from iw

    Returns:
        str: ESSID string, or "wlan0 essid unknown"
    """
    try:
        out = subprocess.check_output([IW_CMD, "dev", "wlan0", "link"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "SSID:" in line:
                return line.split("SSID:")[1].strip()
    except Exception as e:
        logger.exception(e)
        pass

    return "wlan0 essid unknown"


def get_ssid_bssid():
    """
    get ESSID and bssid strings from iw

    Returns:
        str: ESSID string, or "wlan0 essid unknown"
        str: BSSID string, or "wlan0 bssid unknown"
    """
    ssid = "wlan0 essid unknown"
    bssid = "wlan0 bssid unknown"
    try:
        out = subprocess.check_output([IW_CMD, "dev", "wlan0", "link"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "Connected to" in line:
                bssid = line.split("Connected to")[1].split("(")[0].strip()
            elif "SSID:" in line:
                ssid = line.split("SSID:")[1].strip()
    except Exception as e:
        logger.exception(e)
        pass

    return ssid, bssid


def query_wifi():
    """
    Queries connection RSSI dynamically. Uses fast direct kernel space parser if USE_PROC_NET_WIRELESS is configured.
    Otherwise, use iw reports for full information.

    Features:
    * USE_PROC_NET_WIRELESS /proc/net/wireless for quickly just updating RSSI
    * if not set 'iw' iw will also get these values
    * rx_bitrate - Mbps for download rate from Pi Zero AP
    * tx_bitrate - Mbps for upload rate to Pi Zero AP
    * BSSID - of connected link

    Returns:
        USE_PROC_NET_WIRELESS=True
            (rssi, quality, None, None, None)
            tuple: (rssi [int], quality [int]  None, None, None, is_new_rssi)

        USE_PROC_NET_WIRELESS=False
            tuple: (rssi [int], quality [int], rx_bitrate [float], tx_bitrate [float], bssid [str], is_new_rssi [bool])
    """
    rssi = None
    rx_bitrate = None
    tx_bitrate = None
    bssid = None
    is_new_rssi = False

    if USE_PROC_NET_WIRELESS:
        try:
            rssi, quality, is_new_rssi = query_wifi_proc_net_wireless_fast()

            # If the fingerprint matches old state, drop out to prevent stale UI redraws
            if not is_new_rssi:
                return None, None, None, None, None, is_new_rssi

            if rssi is not None:
                return rssi, quality, None, None, None, is_new_rssi
        except Exception as e:
            logger.exception(e)
            pass

        return None, None, None, None, None, is_new_rssi

    # Standard iw for all metrics
    try:
        out = subprocess.check_output([IW_CMD, "dev", "wlan0", "link"], text=True, stderr=subprocess.DEVNULL)

        for line in out.splitlines():
            if "Connected to" in line:
                match = re.search(r'Connected to\s+([0-9a-fA-F:]{17})', line)
                if match:
                    bssid = match.group(1)
            elif "signal:" in line:
                match = re.search(r'signal:\s*([-0-9.]+)\s*dBm', line)
                if match:
                    rssi = int(float(match.group(1)))
            elif "rx bitrate:" in line:
                match = re.search(r'rx bitrate:\s*([0-9.]+)', line)
                if match:
                    rx_bitrate = float(match.group(1))
            elif "tx bitrate:" in line:
                match = re.search(r'tx bitrate:\s*([0-9.]+)', line)
                if match:
                    tx_bitrate = float(match.group(1))

    except Exception as e:
        logger.exception(e)
        return None, None, None, None, None, is_new_rssi

    if rssi is not None:
        quality = max(0, min(100, int(2 * (rssi + 100))))
        is_new_rssi = True
        return rssi, quality, rx_bitrate, tx_bitrate, bssid, is_new_rssi

    return None, None, None, None, None, is_new_rssi


def query_wifi_proc_net_wireless_fast():
    """
    Direct memory-mapped read of /proc/net/wireless with data change detection.
    Bypasses nmcli subprocess overhead entirely to maximize connected data speeds.

    Data change detected by fingerprint of combined quality, rssi, and missed_beacons metrics.

    We expect 102.4 ms between changes which is the default Beacon Interval for most Wi-Fi hardware.

    Returns:
        tuple: (rssi [int], quality [int], is_new_data [bool]) or (None, None, False)
    """
    global _last_wireless_fingerprint

    try:
        with open("/proc/net/wireless", "r") as f:
            lines = f.readlines()

        for line in lines:
            if "wlan0" in line:
                clean_line = line.replace("wlan0:", "").strip()
                parts = clean_line.split()
                quality = int(parts[1].replace('.', ''))
                rssi = int(parts[2].replace('.', ''))
                missed_beacons = int(parts[7])

                # handle 8-bit unsigned conversion (RSSI−256)
                if rssi > 0:
                    rssi = rssi - 256
                elif rssi == 0:
                    rssi = None

                current_fingerprint = (quality, rssi, missed_beacons)

                if current_fingerprint == _last_wireless_fingerprint:
                    return rssi, quality, False

                _last_wireless_fingerprint = current_fingerprint
                return rssi, quality, True

    except Exception as e:
        logger.exception(e)
        pass

    return None, None, False


def parse_band_from_cell(cell) -> tuple:
    """Parses channel and frequency from text to calculate the band string and explicit channel number"""
    # capture explicit channel from text
    channel_match = re.search(r'Channel:\s*(\d+)', cell, re.IGNORECASE)
    channel = int(channel_match.group(1)) if channel_match else None

    # capture frequency (freq: 2412" or "freq: 5180")
    freq_match = re.search(r'freq:\s*(\d+\.?\d*)', cell, re.IGNORECASE)
    freq = float(freq_match.group(1)) if freq_match else None

    # Fallback if channel parsing fails but frequency exists
    if channel is None and freq:
        if freq > 100:
            freq = freq / 1000.0

        if 2.400 <= freq <= 2.495:
            if freq == 2.484:
                channel = 14
            else:
                channel = int((freq - 2.412) / 0.005) + 1

        elif 5.150 <= freq <= 5.895:
            channel = int((freq - 5.000) / 0.005) / 4
            channel = int(channel)

        elif 5.925 <= freq <= 7.125:
            channel = int((freq - 5.940) / 0.005) / 4 + 1
            channel = int(channel)
        else:
            channel = None

    if channel is None:
        band = "Unknown"
    elif channel <= 14:
        band = "2.4 GHz"
    elif channel <= 177:  # Standard upper limit boundary for regional 5GHz bands
        band = "5 GHz"
    else:
        band = "6 GHz"

    return band, channel


def channel_to_frequency(channel: int, band: str) -> int:
    """
    Maps a given channel number and band back to its standard MHz.

    Args:
        channel (int): The Wi-Fi channel number (ex: 1, 6, 36, 149).
        band (str): The string descriptor of the band ("2.4 GHz", "5 GHz", "6 GHz").

    Returns:
        int: The center frequency in MHz, or None if the mapping is invalid.
    """
    if channel is None or not band:
        return None

    band_clean = band.replace(" ", "").lower()

    # 2.4 GHz
    if "2.4" in band_clean:
        if channel == 14:
            return 2484
        if 1 <= channel <= 13:
            return 2412 + (channel - 1) * 5

    # 5 GHz Band
    elif "5" in band_clean:
        if 32 <= channel <= 177:
            return 5000 + (channel * 5)

    # 6 GHz Band (Wi-Fi 6E / 7)
    elif "6" in band_clean:
        if 1 <= channel <= 233:
            return 5940 + (channel * 5)

    return None


def scan_target_ssid(interface, target_ssid=None, channel: int = None):
    """
    High-speed scan. Uses kernel cache (fastest) with fallback option
    for forced hardware scan (moderate).

    TODO: only works for 2.4GHz in this implementation.

    Args:
        interface (str): The network interface to scan (default: "wlan0").
        target_ssid (str): The SSID to search for in the scan results.
        channel (int): The Wi-Fi channel number (ex: 1, 6, 11),

        Moderate is slower but guarantees fresh data.

    Returns:
        int: The signal strength (RSSI) in dBm if found, otherwise None.
    """

    try:
        if SCAN_CACHES_FAST_MODE:
            cmd = ["sudo", IW_CMD, "dev", interface, "scan", "dump"]
        else:
            cmd = ["sudo", IW_CMD, "dev", interface, "scan"]

        # Append channel frequency scoping if running physical scans to speed up turnaround times
        if channel is not None and not SCAN_CACHES_FAST_MODE:
            freq_mhz = channel_to_frequency(channel, "2.4 GHz")
            if freq_mhz:
                cmd.extend(["freq", str(freq_mhz)])

        scan = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)

    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    # Parse 'iw' output cleanly regardless of leading newlines
    if scan.startswith("BSS "):
        scan = "\n" + scan
    bss_blocks = re.split(r'\nBSS ', scan)
    networks = []

    for block in bss_blocks[1:]:
        ssid_match = re.search(r'SSID: (.*)', block)
        ssid = ssid_match.group(1).strip() if ssid_match else ".hidden."

        rssi_match = re.search(r'signal: ([-0-9.]+) dBm', block)
        rssi = int(float(rssi_match.group(1))) if rssi_match else -100

        # If found target_ssid, return immediately
        if target_ssid and (target_ssid in ssid):
            return rssi

        bssid_match = re.search(r'([0-9a-fA-F:]{17})', block)
        bssid = bssid_match.group(1) if bssid_match else "Unknown"

        band, channel = parse_band_from_cell(block)
        networks.append(PiNetworkMock(ssid, bssid, rssi, band, channel))

    logger.debug(f"Checking SSID: {target_ssid} on channel: {channel}")
    if target_ssid is not None:
        return None

    return sorted(networks, key=lambda net: net.rssi_value(), reverse=True) if target_ssid is None else None


def map_band_to_string(net) -> str:
    """
    Duck-typed for Linux mock objects to keep the display same function signature as
    CoreWLAN Map bands using CoreWLAN's band integers
    """
    if hasattr(net, 'parsed_band'):
        return net.parsed_band()
    return "Unknown"


def rssi_to_string(rssi):
    """
    Generates text strings from RSSI value.

        Args:
            rssi (int): The signal strength in dBm.

        Returns:
            str: A string representing signal strength ("3 bars").
        """
    if rssi is None:
        return "None"
    if rssi > -50: return "4 bars"
    if rssi > -60: return "3 bars"
    if rssi > -70: return "2 bars"
    if rssi > -80: return "1 bar"
    return "0 bar"


def rssi_to_bars(rssi):
    """
    Integer number of bars from RSSI values.

        Args:
            rssi (int): The signal strength in dBm.

        Returns:
            str: A string representing signal strength ("3 bars").
        """
    if rssi is None:
        return 0

    if rssi > -50:
        return 4
    elif rssi > -60:
        return 3
    elif rssi > -70:
        return 2
    elif rssi > -80:
        return 1
    else:
        return 0


def quality_to_string(quality):
    """
    Generates text strings for signal metrics.
    Args:
        quality (int): The link quality metric from the system.

    Returns:
        str: A descriptive string ("Excellent" to "Unstable Link").
    """
    if quality is not None:
        if quality >= 90:
            return "Excellent"
        elif quality >= 80:
            return "Very Good"
        elif quality >= 70:
            return "Good"
        elif quality >= 50:
            return "Low Quality"
        else:
            return "Unstable Link"
    else:
        return "Disconnected"


def frequency_to_channel(frequency):
    """Converts MHz frequency to a standard 2.4GHz channel number."""
    if frequency == 2484:
        return 14
    if 2412 <= frequency <= 2472:
        return (frequency - 2412) // 5 + 1
    return "???"


def get_password_for_ssid(ssid):
    """
    Gets the Wi-Fi password for a given SSID from environment variables.

    Args:
        ssid (str): The SSID to look up in the environment.

    Returns:
        str: The password string if found, otherwise None.
    """
    env_key = f"WIFI_PASS_{ssid}"
    return os.getenv(env_key)


def connect_ssid(ssid):
    """
    Connect to WiFi network with SSID selected.
    Fast connection skips profile generation if it already exists.

    CLI version for "shell-fi"
    sudo nmcli device wifi connect "shell-fi"
    sudo nmcli device wifi connect "shell-fi" password "YOUR_PASSWORD_HERE"
    sudo nmcli connection show

    # Disable Bluetooth for better Wi-Fi, since they share same antenna
    sudo nano /boot/firmware/config.txt
    dtoverlay=disable-bt

    # disable hardware auto-attempting to wake up disabled Bluetooth
    sudo systemctl disable hciuart.service
    sudo systemctl disable bluetooth.service

    Args:
        ssid (str): The SSID to connect to.

    Returns:
        bool: True if connection is verified as successful, False otherwise.
    """
    password = get_password_for_ssid(ssid)
    if not password:
        logger.warning(f"No password found in .env for {ssid}")
        return False

    # Check if NetworkManager already has this profile saved
    check_profile = subprocess.run(
        ["nmcli", "-t", "-f", "NAME", "connection", "show"],
        capture_output=True, text=True
    )

    if ssid in check_profile.stdout:
        logger.info(f"Profile exists for '{ssid}'. Bringing interface UP instantly...")
        try:
            # Drop the timeout to 6 seconds; on a local AP with strong signal, this is plenty
            connect_attempt = subprocess.run(
                ["sudo", "nmcli", "connection", "up", ssid],
                capture_output=True, text=True, timeout=6
            )
            if connect_attempt.returncode == 0:
                logger.info(f"'{ssid}' Connected successfully via fast-path profile load.")
                return True
            else:
                logger.warning("Fast-path up failed. Falling back to profile rebuild...")
        except subprocess.TimeoutExpired:
            logger.warning("Fast-path timed out. Attempting profile rebuild...")

    # Profile creation/rebuild fallback
    logger.info(f"Rebuilding profile configurations for '{ssid}'")
    subprocess.run(["sudo", "nmcli", "connection", "delete", ssid], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    subprocess.run(
        ["sudo", "nmcli", "connection", "add", "type", "wifi", "con-name", ssid, "ifname", "wlan0", "ssid", ssid],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "wifi-sec.key-mgmt", "wpa-psk"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "wifi-sec.psk", password], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "connection.autoconnect-priority", "10"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Hi-speed static for "shell-fi"
    if ssid == "shell-fi":
        logger.info("Applying high-speed static IP bypass for 'shell-fi'")
        subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "ipv4.method", "manual"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "ipv4.addresses", "192.168.4.10/24"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "ipv4.gateway", "192.168.4.1"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "ipv6.method", "disabled"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Explicitly ensure standard networks use standard DHCP
        subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "ipv4.method", "auto"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        connect_attempt = subprocess.run(["sudo", "nmcli", "connection", "up", ssid], capture_output=True, text=True,
                                         timeout=10)
        if connect_attempt.returncode != 0:
            logger.error(f"WiFi connection rebuild failed:\n{connect_attempt.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.warning("Rebuilt profile up-command timed out.")
        return False

    time.sleep(0.5)
    status_check = subprocess.run(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device"], capture_output=True,
                                  text=True)
    return f"wlan0:connected:{ssid}" in status_check.stdout


def remove_ssid(ssid="shell-fi"):
    """
    Deletes a specific WiFi connection profile from NetworkManager.

    Args:
        ssid (str): The SSID profile name to remove.
    """
    logger.info(f"\nCleaning up: Removing NetworkManager profile '{ssid}'...")
    subprocess.run([
        "sudo", "nmcli", "connection", "delete", ssid
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logger.debug(f" -> '{ssid}' deleted successfully.")


def perform_wifi_scan(interface, target_ssid=None, channel: int = None):
    """
    scan and returns the raw data or None.

        TODO: only works for 2.4GHz in this implementation.
    Args:
        interface (str): The network interface to scan (default: "wlan0").
        target_ssid (str): The SSID to search for in the scan results.
        channel (int): The Wi-Fi channel number (ex: 1, 6, 11),

    """
    try:
        with timeout(3, "Wi-Fi scan timed out!"):
            return scan_target_ssid(interface, target_ssid, channel=channel)
    except TimeoutError:
        logger.info("Hardware hang detected. Resetting interface...")
        subprocess.run(["sudo", "nmcli", "device", "reconnect", "wlan0"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return None


def trigger_background_scan(interface):
    """Trigger background scan with timeout."""
    try:
        # Wrap the iw system call in a 4-second timeout guard
        with timeout(4, "Pre-warm scan timed out!"):
            subprocess.run(["sudo", IW_CMD, "dev", interface, "scan"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except TimeoutError:
        logger.info("Wi-Fi Hardware hang during pre-warm. Power-cycle Wi-Fi...")
        subprocess.run(["sudo", "nmcli", "device", "disconnect", interface], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        subprocess.run(["sudo", "nmcli", "device", "connect", interface], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
