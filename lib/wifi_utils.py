# wifi_utils.py
"""
Requirements to avoid password:
    sudo visudo
    add pi-admin ALL=(ALL) NOPASSWD: /usr/sbin/iw (or just /usr/bin/iw depending on your path)
"""
import os
import re
import subprocess
import time
from typing import Literal

from lib.pi_zero_utils import timeout


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
    # For Raspberry Pi, we ensure the wlan0 interface is accessible via iwlist
    if os.path.exists("/sys/class/net/wlan0"):
        return "wlan0"
    return None


def get_ssid():
    """
    get ESSID string from iwconfig
    Returns:
        str: ESSID string, or "uknown"
    """
    try:
        # query iwconfig to get the ESSID string
        out = subprocess.check_output(["/sbin/iwconfig", "wlan0"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "ESSID" in line:
                return line.split('"')[1].strip()
    except Exception:
        pass

    # Final default so avoid empty 'None' type
    return "wlan0 essid unknown"


def query_wifi():
    """
    Queries RSSI, Link Quality, and current Tx Bit Rate dynamically.
    Execution time is kept low to ensure dense logging updates.

    :Returns:
        tuple: (rssi [int], quality [int], tx_rate [float]) or
               (None, None, None) if the interface cannot be queried.
    """
    rssi = None
    quality = None
    tx_rate = None

    # Get RSSI and Link Quality from the Linux Kernel network stats
    try:
        with open("/proc/net/wireless", "r") as f:
            lines = f.readlines()
            for line in lines:
                if "wlan0" in line:
                    parts = line.split()
                    quality = int(parts[2].replace('.', ''))
                    rssi = int(parts[3].replace('.', ''))

                    if rssi > 0:
                        rssi = rssi - 256
    except Exception:
        return None, None, None

    # Get Tx Rate as a raw float/int numerical value
    try:
        out = subprocess.check_output(["/sbin/iwconfig", "wlan0"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "Bit Rate" in line:
                parts = line.split("Bit Rate=")
                if len(parts) > 1:
                    raw_rate_str = parts[1].split("   ")[0].strip()
                    # regex match to isolate only numbers/decimals
                    match = re.findall(r"[+-]?\d*(?:\.\d+)?", raw_rate_str)
                    if match and match[0] != "":
                        tx_rate = float(match[0])
                    break
    except Exception:
        pass

    return rssi, quality, tx_rate


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


def scan_target_ssid(interface, target_ssid=None):
    """
    High-speed scan. Uses kernel cache (fastest) with fallback option
    for forced hardware scan (moderate).

    Args:
        interface (str): The network interface to scan (default: "wlan0").
        target_ssid (str): The SSID to search for in the scan results.

        Moderate is slower but guarantees fresh data.

    Returns:
        int: The signal strength (RSSI) in dBm if found, otherwise None.
    """
    FAST_SCAN_MODE = False
    try:
        if FAST_SCAN_MODE:
            # FASTEST: Read the kernel's active BSS cache
            cmd = ["sudo", "iw", "dev", interface, "scan", "dump"]
        else:
            # MODERATE: Force a physical radio hop
            cmd = ["sudo", "iw", "dev", interface, "scan"]

        scan = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)

    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    # Parse 'iw' output: BSS blocks start with "BSS "
    bss_blocks = re.split(r'\nBSS ', scan)
    networks = []

    for block in bss_blocks[1:]:  # Skip the first element (interface info)
        ssid_match = re.search(r'SSID: (.*)', block)
        ssid = ssid_match.group(1) if ssid_match else ".hidden."

        rssi_match = re.search(r'signal: ([-0-9.]+) dBm', block)
        rssi = int(float(rssi_match.group(1))) if rssi_match else -100

        # If found target_ssid, return immediately
        if target_ssid and ssid == target_ssid:
            return rssi

        bssid_match = re.search(r'([0-9a-fA-F:]{17})', block)
        bssid = bssid_match.group(1) if bssid_match else "Unknown"

        band, channel = parse_band_from_cell(block)
        networks.append(PiNetworkMock(ssid, bssid, rssi, band, channel))

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

    if rssi > -50:
        rssi_string = "4 bars"
    elif rssi > -60:
        rssi_string = "3 bars"
    elif rssi > -70:
        rssi_string = "2 bars"
    elif rssi > -80:
        rssi_string = "1 bar"
    else:
        rssi_string = "0 bar"
    return rssi_string


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
        str: A descriptive string (e.g., "Hi Quality" or "Unstable Link").
    """
    if quality is not None:
        if quality >= 60:
            quality_string = "Hi Quality"
        elif quality >= 45:
            quality_string = "Stable Link"
        elif quality >= 30:
            quality_string = "Low Quality"
        else:
            quality_string = "Unstable Link"
    else:
        quality_string = "Disconnected"

    return quality_string


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
    Programmatic way to connect to WiFi network.

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
    print(f"\nProvisioning NetworkManager for target: {ssid}...")

    # Get password from env
    password = get_password_for_ssid(ssid)
    if not password:
        print(f"No password found in .env for {ssid}")
        return False
    print(f"\nProvisioning NetworkManager for: {ssid} using stored password...")

    print(f"Flush old {ssid} configurations...")
    subprocess.run(["sudo", "nmcli", "connection", "delete", ssid], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)

    # Use clean explicit parameters for device activation to let nmcli autoconfigure security structures
    cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid, "ifname", "wlan0"]
    if password is not None:
        cmd.extend(["password", password])

    # Catch weak-signal handshaking hangs gracefully instead of dropping execution
    try:
        connect_attempt = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if connect_attempt.returncode != 0:
            print(f"ERROR: WiFi connection failed:\n{connect_attempt.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"WARNING: Connection handshake timed out after 15 seconds. Signal likely too weak.")
        return False

    # Elevate network priority now that the profile is safely auto-generated
    subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "connection.autoconnect-priority", "10"],
                   check=True)

    print(f"Verifying '{ssid}' on state and IP assignment...")
    time.sleep(1.5)

    # Query NetworkManager for the current state
    status_check = subprocess.run(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device"], capture_output=True,
                                  text=True)

    if f"wlan0:connected:{ssid}" in status_check.stdout:
        print(f" {ssid} Connection successful! Network interface is active.\n")
        return True
    else:
        print("WARNING Profile created, but interface failed to verify an active state.\n")
        return False


def remove_ssid(ssid: Literal["shell-fi"]):
    """
    Deletes a specific WiFi connection profile from NetworkManager.

    Args:
        ssid (str): The SSID profile name to remove.
    """
    print(f"\nCleaning up: Removing NetworkManager profile '{ssid}'...")
    subprocess.run([
        "sudo", "nmcli", "connection", "delete", ssid
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(" -> \"shell-fi\" deleted successfully.")


def perform_wifi_scan(interface, target_ssid=None):
    """scan and returns the raw data or None."""
    try:
        with timeout(3, "Wi-Fi scan timed out!"):
            return scan_target_ssid(interface, target_ssid)
    except TimeoutError:
        print("Hardware hang detected. Resetting interface...")
        subprocess.run(["sudo", "nmcli", "device", "reconnect", "wlan0"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return None


def trigger_background_scan(interface):
    """Trigger background scan with timeout."""
    try:
        # Wrap the blocking system call in a 4-second timeout guard
        with timeout(4, "Pre-warm scan timed out!"):
            subprocess.run(["sudo", "iw", "dev", interface, "scan"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except TimeoutError:
        print("Wi-Fi Hardware hang during pre-warm. Power-cycle Wi-Fi...")
        subprocess.run(["sudo", "nmcli", "device", "disconnect", interface], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        subprocess.run(["sudo", "nmcli", "device", "connect", interface], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
