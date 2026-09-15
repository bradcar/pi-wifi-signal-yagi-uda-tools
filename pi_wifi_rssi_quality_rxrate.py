#
"""
pi_wifi_rssi_quality_rxrate.py

On Raspberry Pi Zero 2 W running Linux, repeatedly measures and prints real-time RSSI,
Link Quality, and RX Bitrate (download rate from the AP) for the connected
network on wlan0. Serves as a console-only telemetry prototype.

Operational Modes:
    * Terminal Output Mode (Console-Only):
      - Polls Linux network interface wlan0 continuously via system calls (`iw` / `/proc/net/wireless`).
      - Reads real-time RSSI (dBm), Link Quality (/70 rating), and RX bitrate (Mb/s).
      - Renders formatted text interpretation with signal bar indicators directly to stdout.
      - Displays loop latency (msec) and update frequency (Hz).
      - Polling Cadence: ~10 Hz (100 ms sleep cycle) on Pi Zero 2 W.

Display Layouts & Hardware Mapping:
    * Console text output of signals per iteration.

Features:
    * Real-time Wi-Fi telemetry for the active connection.
    * Signal quality classification mapping (RSSI dBm to visual bar representation).
    * Tracks RX Bitrate download rate from AP.
    * High-frequency refresh rate monitoring.

Sensors & Antenna Integration:
    * BSSID tracking to ensure telemetry continuity on the target Access Point.

Usage:
    Terminal : python3 pi_wifi_rssi_quality_rxrate.py
    IDE      : Run directly in PyCharm

Notes:
    * Requires an active, connected Wi-Fi connection on wlan0 (`is_connected == True`).
    * For scanning unconnected/surrounding 2.4GHz Wi-Fi networks, use: pi-wifi-scan_rssi.py
"""

import time
from datetime import datetime

from lib.wifi_utils import get_ssid_bssid, query_wifi, rssi_to_string, quality_to_string


def print_metrics(quality, rssi, ssid, rx_rate):
    """Prints RSSI, Link Quality, and RX Rate (download from AP) with text interpretation."""
    rssi_string = rssi_to_string(rssi)
    quality_string = quality_to_string(quality)

    print(f"WiFi Signal Monitor (Pi Zero): {ssid}")
    print(f"SSID:    {ssid}")

    if rssi is not None:
        print(f"RSSI:    {rssi:>3} dBm  {rssi_string}")
        print(f"Link Q:  {f'{quality:>2}/70' if quality is not None else 'n/a'}    {quality_string}")
        print(f"RX Rate: {f'{rx_rate:.1f} Mb/s' if rx_rate is not None else 'n/a'}")
    else:
        print("RSSI:    n/a")
        print("Link Q:  n/a")
        print("RX Rate: n/a")


def main():
    print("Starting Pi Zero 2 W Signal Tracking Loop...\n")

    # Get the network SSID text
    ssid, bssid = get_ssid_bssid()
    print(f"SSID: {ssid}, associated with BSSID: {bssid}\n")

    try:
        start_time = time.time()
        while True:
            # Get RSSI, Quality, and Mb/s (RX rate is download from AP), ignore is_new_rssi last return
            rssi, quality, rx_rate, tx_rate, bssid, _ = query_wifi()

            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time

            print_metrics(quality, rssi, ssid, rx_rate)
            print(f"Updates:  {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nTracking Stopped. Exiting.")


if __name__ == "__main__":
    main()
