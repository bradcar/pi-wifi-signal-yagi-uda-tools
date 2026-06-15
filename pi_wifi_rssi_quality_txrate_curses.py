# pi_wifi_rssi_quality_txrate_curses.py
"""
Simple terminal output using curses to overwrite results to show continuous updates
of RSSI, noise, SNR with update duration in msec, frequency and current datetime.
Also prints out the name of the en0 Wifi network it is monitoring.

Usage:
  in terminal, python3 mac_wifi_rssi_snr_noise_curses.py

Sample output:

"""
import curses
import time
from datetime import datetime

from pi_wifi_rssi_quality_txrate import rssi_quality_to_string
from wifi_utils import get_ssid, query_wifi


def main_window(stdscr):
    curses.curs_set(0)  # hide cursor
    stdscr.nodelay(True)

    ssid = get_ssid()
    while True:
        start_time = time.time()
        rssi, quality, tx_rate = query_wifi()
        duration = time.time() - start_time

        rssi_string, quality_string = rssi_quality_to_string(rssi, quality)

        stdscr.clear()
        stdscr.addstr(1, 1, f"WiFi Signal Monitor (Pi Zero): {ssid}")
        stdscr.addstr(3, 4, f"RSSI:    {rssi:>3} dBm   {rssi_string}")
        stdscr.addstr(4, 4, f"Link Q:  {quality:>2}/70     {quality_string}")
        stdscr.addstr(5, 4, f"Tx Rate: {tx_rate}")

        stdscr.addstr(7, 4, f"Updates:  {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
        stdscr.addstr(8, 4, f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        stdscr.refresh()
        time.sleep(0.1)


if __name__ == "__main__":
    curses.wrapper(main_window)
