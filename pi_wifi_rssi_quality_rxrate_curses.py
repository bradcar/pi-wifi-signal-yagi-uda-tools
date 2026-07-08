# pi_wifi_rssi_quality_rxrate_curses.py
"""
Simple terminal output using curses to overwrite results to show continuous updates
of RSSI, Quality, RX_bitrate(download from AP) with update duration in msec, frequency and current datetime.
Also prints out the name of the en0 Wifi network it is monitoring.

Usage:
  in terminal:  python3 pi_wifi_rssi_quality_rxrate_curses.py

Sample output:

"""
import curses
import time
from datetime import datetime

from lib.wifi_utils import get_ssid_bssid, query_wifi, rssi_to_string, quality_to_string


def main_window(stdscr):
    curses.curs_set(0)  # hide cursor
    stdscr.nodelay(True)

    ssid, bssid = get_ssid_bssid()
    while True:
        start_time = time.time()
        # Get RSSI, Quality, and Mb/s (RX rate is download from AP), ignore is_new_rssi last return
        rssi, quality, rx_rate, tx_rate, bssid, _ = query_wifi()

        duration = time.time() - start_time

        rssi_string = rssi_to_string(rssi)
        quality_string = quality_to_string(quality)

        stdscr.clear()
        stdscr.addstr(1, 1, f"WiFi Signal Monitor (Pi Zero): {ssid}")
        if rssi is not None:
            stdscr.addstr(3, 4, f"RSSI:    {rssi:>3} dBm   {rssi_string}")
            stdscr.addstr(4, 4, f"Link Q:  {quality:>2}%     {quality_string}")
        else:
            stdscr.addstr(3, 4, f"RSSI:     no dBm")
            stdscr.addstr(4, 4, f"Link Q:     0%")
        stdscr.addstr(5, 4, f"RX Rate:  {rx_rate}")

        stdscr.addstr(7, 4, f"Updates:  {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
        stdscr.addstr(8, 4, f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        stdscr.refresh()
        time.sleep(0.1)


if __name__ == "__main__":
    curses.wrapper(main_window)
