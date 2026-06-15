# pi_wifi_rssi_quality_txrate.py
"""
On Raspberry Pi Zero 2 W, repeatedly measure and print RSSI, Link Quality,
and Tx Bit Rate of the currently connected network on interface wlan0.

Prototype for tracking signal vectors using a directional Yagi_Uda antenna.
Reads metrics continuously to signal strength changes.

Usage:
  python pi_wifi_rssi_quality_txrate.py
"""

import time
from datetime import datetime

from wifi_utils import get_ssid, query_wifi, rssi_to_string, quality_to_string


def print_metrics(quality, rssi, ssid, tx_rate):
    """Prints RSSI, Link Quality, and Tx Rate with text interpretation."""
    rssi_string = rssi_to_string(rssi)
    quality_string = quality_to_string(quality)

    print(f"WiFi Signal Monitor (Pi Zero): {ssid}")
    print(f"SSID:    {ssid}")

    if rssi is not None:
        print(f"RSSI:    {rssi:>3} dBm  {rssi_string}")
        print(f"Link Q:  {f'{quality:>2}/70' if quality is not None else 'n/a'}    {quality_string}")
        print(f"Tx Rate: {f'{tx_rate:.1f} Mb/s' if tx_rate is not None else 'n/a'}")
    else:
        print("RSSI:    n/a")
        print("Link Q:  n/a")
        print("Tx Rate: n/a")


def main():
    print("Starting Pi Zero 2 W Signal Tracking Loop...\n")

    # Get the network SSID text
    ssid = get_ssid()

    try:
        start_time = time.time()
        while True:
            # Get RSSI, Quality, and Mb/s
            rssi, quality, tx_rate = query_wifi()
            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time

            print_metrics(quality, rssi, ssid, tx_rate)
            print(f"Updates:  {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nTracking Stopped. Exiting.")


if __name__ == "__main__":
    main()