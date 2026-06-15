# pi-wifi-scan_rssi.py
"""
s and only measures RSSI on available 2.4GHz WiFi (not 5GHz or 6GHz). Runs on Raspberry Pi Zero 2 W in Linux
Scans repeatedly, sorted by strongest RSSI first.

Quality or Tx bitrates on unconnected networks. For connected network use:pi_wifi_rssi_quality_txrate.py

NOTES:
  1) Python MUST be enabled in System Settings > Privacy & Security> Location Services.

Usage:
  in terminal, python3 mac_wifi_scan_rssi.py
  can also run in PyCharm
"""
import os
import time
import subprocess
from datetime import datetime
from wifi_utils import init_wifi, scan_target_ssid, map_band_to_string, rssi_to_string

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


def scan_and_print(interface, target_ssid=None):
    """network scan using the interface, print sorted RSSI, current row counts header, dash row, and network count"""
    if not interface:
        print("Pi Zero Wi-Fi Error: Wi-Fi interface not found or initialized.")
        return False, 1

    data = scan_target_ssid(interface, target_ssid)

    # Handle single target case
    if target_ssid is not None:
        if data is not None:
            print(f"Target '{target_ssid}' RSSI: {data} dBm")
            return True, 1
        else:
            print(f"Target '{target_ssid}' not found.")
            return False, 1

    # Handle full list case
    if not data:
        print("Pi Zero Wi-Fi: No networks found.")
        return False, 1

    current_row = 0
    print(f"{'SSID':<23} {'Band':<7}  {'BSSID':<17}  {'RSSI':<8} {'Bars'}")
    current_row += 1
    print("-" * 67)
    current_row += 1

    for net in data:
        ssid = net.ssid() or " hidden."
        bssid = net.bssid() or "Unknown"
        rssi = net.rssi_value()

        band = map_band_to_string(net)
        rssi_string = rssi_to_string(rssi)

        if not (BLOCK_LESS_THAN_ONE_BAR and rssi <= -80):
            print(f"{ssid:<23} {band:<7}  {bssid} {rssi:>4} dBm  {rssi_string}")
            current_row += 1

    return True, current_row


def trigger_background_scan(interface):
    """Triggers an unmanaged background scan to populate the cache."""
    subprocess.run(["sudo", "iw", "dev", interface, "scan"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    last_update = time.time()

    print("Start Pi Wi-Fi scan:")
    wifi_interface = init_wifi()
    subprocess.run(["sudo", "ip", "link", "set", wifi_interface, "up"])

    # Fill the cache once before starting
    print("Pre-warming Wi-Fi cache...")
    trigger_background_scan(wifi_interface)

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
                # If the hardware was busy, retry in .1 second
                time.sleep(0.1)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
    print("\nExiting.")
