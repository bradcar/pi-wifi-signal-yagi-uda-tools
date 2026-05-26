# pi_yagi_uda.py
"""
On Raspberry Pi Zero 2 W, repeatedly measure and print RSSI, Link Quality,
and Tx Bit Rate of the currently connected network on interface wlan0.
It reads metrics continuously to signal strength changes.

This code displays some of this data onto a SSD1306 display and prints data to std out.

this Zero 2 W hardware will eventually be connected to a directional Yagi Uda antenna.

Usage:
  sudo python3 pi_yagi_uda.py
"""

import time
from datetime import datetime
from pi_wifi_rssi_quality_txrate import get_ssid, query_wifi, rssi_quality_to_string, print_with_string


def main():
    print("Starting Pi Zero 2 W Signal Tracking Loop...\n")

    # Get the network SSID text
    ssid = get_ssid()

    try:
        start_time = time.time()
        while True:
            # RSSI, Quality, and Bit Rate are measured on every pass
            rssi, quality, tx_rate = query_wifi()
            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time

            print_with_string(quality, rssi, ssid, tx_rate)
            print(f"\nUpdates:  {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    except KeyboardInterrupt:
        print("\nTracking Stopped. Exiting.")


if __name__ == "__main__":
    main()
