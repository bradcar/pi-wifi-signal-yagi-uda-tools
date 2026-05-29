# pi-wifi-signal-yagi-uda-tools.py
"""
Scans and only measures RSSI on available 2.4GHz WiFi (not 5GHz or 6GHz). Runs on Raspberry Pi Zero 2 W in Linux
Scans repeatedly, sorted by strongest RSSI first.

Quality or Tx bitrates on unconnected networks. For connected network use:pi_wifi_rssi_quality_txrate.py

NOTES:
  1) Python MUST be enabled in System Settings > Privacy & Security> Location Services.

Usage:
  in terminal, python3 mac_wifi_scan_rssi.py
  can also run in PyCharm
"""
import os
import re
import subprocess
import time
from datetime import datetime

BLOCK_LESS_THAN_ONE_BAR = True
# NEVER USED on Pi Zero 2 W: BLOCK_NON_2_4_G = True  #Zero can only scan 2.4GH


class PiNetworkMock:
    """Mock object mimicking CoreWLAN network objects to preserve core display loop structure"""

    def __init__(self, ssid, bssid, rssi, band):
        self._ssid = ssid
        self._bssid = bssid
        self._rssi = rssi
        self._band = band

    def ssid(self):
        return self._ssid if self._ssid != " hidden." else None

    def bssid(self):
        return self._bssid

    def rssi_value(self):
        return self._rssi

    def parsed_band(self):
        return self._band


def init_wifi():
    """Initialize CoreWLAN client and returns the active Wi-Fi"""
    # For Raspberry Pi, we ensure the wlan0 interface is accessible via iwlist
    if os.path.exists("/sys/class/net/wlan0"):
        return "wlan0"
    return None


def parse_band_from_cell(cell) -> str:
    """Parses channel and frequency from text to calculate the band string"""
    channel_match = re.search(r'Channel:(\d+)', cell)
    channel = int(channel_match.group(1)) if channel_match else None

    freq_match = re.search(r'Frequency:(\d+\.?\d*)', cell)
    freq = float(freq_match.group(1)) if freq_match else None

    if channel is None and freq:
        if freq > 10:
            freq = freq / 1000

        if 2.4 <= freq <= 2.5:
            channel = int((freq - 2.412) / 0.005) + 1
        elif 5.1 <= freq <= 5.9:
            channel = 36
        else:
            channel = None

    if channel is None:
        band = "Unknown"
    elif channel <= 14:
        band = "2.4 GHz"
    elif channel <= 64:
        band = "5 GHz"
    else:
        band = "6 GHz"

    return band


def map_band_to_string(net) -> str:
    """
    Duck-typed for Linux mock objects to keep the display same function signature as
    CoreWLAN Map bands using CoreWLAN's band integers
    """
    if hasattr(net, 'parsed_band'):
        return net.parsed_band()
    return "Unknown"


def rssi_bar_string(rssi) -> str:
    """RSSI quality strings, higher is better"""
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


def scan_and_print(interface):
    """network scan using the interface, print sorted RSSI, current row counts header, dash row, and network count"""
    if not interface:
        print("Pi WiFi Error: Wi-Fi interface not found or initialized.")
        return False, 1

    # Scan for networks, include (None) and hidden networks (True)
    try:
        scan = subprocess.check_output(
            ["sudo", "iwlist", interface, "scan"],
            text=True
        )
        error = None
    except subprocess.CalledProcessError as e:
        scan = ""
        error = e

    if error:
        # Code 16 "Resource busy" (EBUSY), return for retry
        # In Linux, a busy interface throws a matching code 16 or device busy error string
        if "Pi WiFi scan error: Device or resource busy" in str(error) or (hasattr(error, 'returncode') and error.returncode == 16):
            return False, 1

        print(f"Pi WiFi scan error: {error}")
        return False, 1

    # Split reliably by AP address (each real network has one)
    cells = re.split(r'Cell \d+ - Address: ', scan)
    networks = []

    for cell in cells[1:]:
        bssid_match = re.match(r'([0-9A-Fa-f:]+)', cell)
        bssid = bssid_match.group(1) if bssid_match else "Unknown"

        ssid_match = re.search(r'ESSID:"(.*)"', cell)
        ssid = ssid_match.group(1) if ssid_match else ""
        ssid = ssid if ssid else ".hidden."

        rssi_match = re.search(r'Signal level[=:](-?\d+)', cell)
        rssi = int(rssi_match.group(1)) if rssi_match else -100

        # Parse band from cell text
        band = parse_band_from_cell(cell)

        # Construct raw records inside our mock wrapper class
        networks.append(PiNetworkMock(ssid, bssid, rssi, band))

    if not networks:
        print("Pi Wifi: No networks found. Ensure Terminal/IDE has Location Services permissions.")
        return False, 1

    # Sort networks, show best RSSI at top (strongest first)
    sorted_networks = sorted(networks, key=lambda net: net.rssi_value(), reverse=True)

    current_row = 0

    print(f"{'SSID':<23} {'Band':<7}  {'BSSID':<17}  {'RSSI':<8} {'Bars'}")
    current_row += 1
    print("-" * 67)
    current_row += 1

    for net in sorted_networks:
        ssid = net.ssid() or " hidden."
        bssid = net.bssid() or "Unknown"
        rssi = net.rssi_value()

        band = map_band_to_string(net)
        rssi_string = rssi_bar_string(rssi)

        if not (BLOCK_LESS_THAN_ONE_BAR and rssi <= -80):
            print(f"{ssid:<23} {band:<7}  {bssid} {rssi:>4} dBm  {rssi_string}")
            current_row += 1

    return True, current_row


def main():
    last_update = time.time()
    wifi_interface = init_wifi()
    print("Start Pi Wi-Fi scan:")

    try:
        while True:
            # scan and print all detected WiFi's
            success, current_row = scan_and_print(wifi_interface)
            if success:
                duration = time.time() - last_update
                last_update = time.time()
                print(f"  Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, Update every {duration:.2f} secs")
                print(
                    f"  Blocked <1-bar and Pi Zero only sees 2.4GHz" if BLOCK_LESS_THAN_ONE_BAR else "  Pi Zero only sees 2.4GHz")
                print()
                # Pi Zero 2 W doesn't need retry delay like Mac does (macOS slow)
            else:
                # If the hardware was busy, retry in 1 second
                time.sleep(0.1)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
    print("\nExiting.")
