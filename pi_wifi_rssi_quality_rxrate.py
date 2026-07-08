# pi_wifi_rssi_quality_rxrate.py
"""
On Raspberry Pi Zero 2 W, repeatedly measure and print RSSI, Link Quality,
and Tx Bit Rate of the currently connected network on interface wlan0.

Prototype for tracking signal vectors using a directional Yagi_Uda antenna.
Reads metrics continuously to signal strength changes.

Usage:
  python pi_wifi_rssi_quality_rxrate.py
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
