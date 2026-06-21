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
import time
import subprocess
from datetime import datetime
import signal
from contextlib import contextmanager

from lib.wifi_utils import init_wifi, scan_target_ssid, map_band_to_string, rssi_to_string, rssi_to_bars
import board
import busio
from lib.oled_1305_utils import init_oled_display, clear_display_oled
from lib.lis3mdl_utils import init_lis3mdl, get_compass_heading
from lib.e_ink_utils import init_e_ink_display, refresh_e_ink_display, blank_canvas_e_ink

BLOCK_LESS_THAN_ONE_BAR = False


@contextmanager
def timeout(seconds):
    def signal_handler(signum, frame):
        raise TimeoutError("Wi-Fi scan timed out!")

    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


def scan_and_print(interface, target_ssid=None):
    """network scan using the interface, print sorted RSSI, current row counts header, dash row, and network count"""
    if not interface:
        print("Error: Wi-Fi interface not found or initialized.")
        return False

    data = None
    try:
        with timeout(3):  # 3-second limit
            data = scan_target_ssid(interface, target_ssid)
    except TimeoutError:
        print("Hardware hang detected. Resetting interface...")
        subprocess.run(["sudo", "nmcli", "device", "reconnect", "wlan0"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"{'SSID':<23} {'Band':<7}  {'BSSID':<17}  {'RSSI':<8} {'Bars'}")
    print("-" * 67)

    if not data:
        print("       ...No networks found...")
        return False

    for net in data:
        ssid = net.ssid() or "_hidden_"
        bssid = net.bssid() or "Unknown"
        rssi = net.rssi_value()
        band = map_band_to_string(net)
        rssi_string = rssi_to_string(rssi)

        if not (BLOCK_LESS_THAN_ONE_BAR and rssi <= -80):
            print(f"{ssid:<23} {band:<7}  {bssid} {rssi:>4} dBm  {rssi_string}")

    return True


def oled_print(draw, font, image, lis3mdl, oled_display, data):
    heading = get_compass_heading(lis3mdl) if lis3mdl else 0.0

    clear_display_oled(oled_display, draw, image)

    if heading is not None:
        draw.text((0, 0), f"dir: {heading:.0f}°", font=font, fill=1)
    else:
        draw.text((0, 0), f"no compass", font=font, fill=1)
    draw.text((86, 0), f"{datetime.now().strftime('%H:%M:%S')}", font=font, fill=1)

    y = 8
    for net in (data or [])[:3]:
        ssid = (net.ssid() or "_hidden_")[:10]
        rssi = net.rssi_value()
        num_bars = rssi_to_bars(rssi)
        bar_string = ("*" * num_bars).ljust(4)


        draw.text((0, y), f"{ssid:<10}", font=font, fill=1)
        draw.text((7 * 8 + 1, y), f"{rssi:>4} dbm", font=font, fill=1)
        draw.text((12 * 8 + 4, y), f"{bar_string}", font=font, fill=1)
        y += 8

    oled_display.image(image)
    oled_display.show()


def e_ink_print(draw, font, image, lis3mdl, epd_display, data):
    """print for E-ink hardware."""
    heading = get_compass_heading(lis3mdl)

    blank_canvas_e_ink(draw)

    if heading is not None:
        draw.text((1, 2), f"dir: {heading:.0f}°", font=font, fill=255)
    else:
        draw.text((1, 2), f"no compass", font=font, fill=255)

    draw.text((195, 2), f"{datetime.now().strftime('%H:%M:%S')}", font=font, fill=255)

    y = 22
    for net in (data or [])[:3]:
        ssid = (net.ssid() or "_hidden_")[:11]
        rssi = net.rssi_value()
        num_bars = rssi_to_bars(rssi)
        num_bars = 4
        bar_string = ("*" * num_bars).ljust(4)
        bssid = net.bssid() or "Unknown"

        draw.text((2, y), f"{ssid:<14}", font=font, fill=255)
        draw.text((10 * 8, y), f"{rssi:>4} dbm", font=font, fill=255)
        draw.text((17 * 8 + 4, y), f"{bar_string}", font=font, fill=255)
        draw.text((23 * 8, y), f"{bssid}", font=font, fill=255)

        y += 16

    refresh_e_ink_display(epd_display, draw, image, partial=True)


def trigger_background_scan(interface):
    """Triggers an unmanaged background scan to populate the cache."""
    subprocess.run(["sudo", "iw", "dev", interface, "scan"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    last_update = time.time()

    print("Start Pi Wi-Fi scan:")
    wifi_interface = init_wifi()
    subprocess.run(["sudo", "ip", "link", "set", wifi_interface, "up"])

    # Initialize Display and Magnetometer
    i2c1 = busio.I2C(board.SCL, board.SDA, frequency=400000)
    devices1 = i2c1.scan()

    oled_detected = 0x3C in devices1
    lis3mdl_detected = (0x1C in devices1) or (0x1E in devices1)
    print(f"{oled_detected=}, {lis3mdl_detected=}")

    oled_display, draw, font, image = None, None, None, None
    if oled_detected:
        oled_display, draw, font, image = init_oled_display(i2c1, use_mono_type=False)

    e_ink_detected = True
    epd_display, epd_draw, epd_font, epd_image = None, None, None, None
    if e_ink_detected:
        epd_display, epd_draw, epd_font, epd_image = init_e_ink_display()

    lis3mdl = None
    if lis3mdl_detected:
        lis3mdl = init_lis3mdl(i2c1)

    # Fill Wi-Fi cache once before starting
    print("Pre-warming Wi-Fi cache...")
    trigger_background_scan(wifi_interface)
    if oled_detected:
        draw.text((0, 0), "Warming Wi-Fi cache", font=font, fill=1)
        oled_display.image(image)
        oled_display.show()

    try:
        while True:
            wifi_data = None
            try:
                with timeout(3):
                    wifi_data = scan_target_ssid(wifi_interface)
            except TimeoutError:
                print("Hardware hang detected. Resetting interface...")
                subprocess.run(["sudo", "nmcli", "device", "reconnect", "wlan0"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1)
                continue

            success = bool(wifi_data)
            if success:
                scan_and_print(wifi_interface, target_ssid=None)
                if oled_detected:
                    oled_print(draw, font, image, lis3mdl, oled_display, wifi_data)
                if e_ink_detected:
                    e_ink_print(epd_draw, epd_font, epd_image, lis3mdl, epd_display, wifi_data)

            if success:
                duration = time.time() - last_update
                last_update = time.time()
                print(f"  Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, Update every {duration:.2f} secs")
                print(
                    f"  {'Blocked <1-bar and Pi Zero only sees 2.4GHz' if BLOCK_LESS_THAN_ONE_BAR else 'Pi Zero only sees 2.4GHz'}")
                print()
            else:
                time.sleep(0.1)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
    print("\nExiting.")
