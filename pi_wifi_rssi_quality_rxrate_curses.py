#
"""
pi_wifi_rssi_quality_rxrate_curses.py

On Raspberry Pi Zero 2 W running Linux, continuously measures real-time RSSI,
Link Quality, and RX Bitrate (download rate from the AP) for the currently connected
wlan0 network. Utilizes Python's ncurses library (`curses`) to perform in-place terminal
screen updates without scrolling.  Companion code to: pi_wifi_rssi_quality_rxrate.py

Operational Modes:
    * Full-Screen Curses Terminal Mode:
      - Uses `curses` to create a clean, fixed-position terminal dashboard with a hidden cursor.
      - Polls network metrics on wlan0 via system utilities (`iw` / `/proc/net/wireless`).
      - Overwrites telemetry fields in place to present continuously refreshed RSSI (dBm),
        Link Quality (%), and RX Rate (Mb/s).
      - Tracks iteration duration (msec) and update frequency (Hz).
      - Polling Cadence: ~10 Hz (100 ms sleep cycle) on Pi Zero 2 W.

Display Layouts & Hardware Mapping:
    * Curses Terminal Dashboard (Standard Terminal / SSH Session):
      - Line 1 : Header displaying target SSID network name
      - Line 3 : RSSI strength in dBm with visual bar indicator
      - Line 4 : Link Quality percentage and text rating
      - Line 5 : RX Rate (download speed from AP in Mb/s)
      - Line 7 : Polling loop performance metrics (msec / Hz)
      - Line 8 : System clock timestamp (YYYY-MM-DD HH:MM:SS)

Features:
    * Continuous real-time Wi-Fi telemetry for the active connection.
    * In-place continuous terminal UI updates via `curses`.
    * Non-blocking execution with automatic terminal state setup/teardown via `curses.wrapper`.
    * Tracks RX Bitrate and download rate from AP.
    * High-frequency telemetry updates for real-time physical antenna alignment.

Sensors & Antenna Integration:
    * BSSID tracking to maintain telemetry targeting on the active Access Point.

Usage:
    Terminal : python3 pi_wifi_rssi_quality_rxrate_curses.py
    IDE      : Run in interactive terminal window / PyCharm Terminal

Notes:
    * Requires an active, connected Wi-Fi network on wlan0 (`is_connected == True`).
    * For non-curses standard console output, use: pi_wifi_rssi_quality_rxrate.py
    * For scanning unconnected/surrounding 2.4GHz Wi-Fi networks, use: pi-wifi-scan_rssi.py
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
