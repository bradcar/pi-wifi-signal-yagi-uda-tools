# pi_yagi_uda.py
"""
On Raspberry Pi Zero 2 W, the code repeatedly measures the RSSI, Link Quality,
and Tx Bit Rate of the currently connected network on interface wlan0.
It prints the results to std out and an OLED display.
It gracefully handles total connection drops and resumes automatically on reconnect.

Usage:
  sudo python3 pi_yagi_uda.py
"""
import math
import time
from datetime import datetime
import re

import adafruit_ssd1306
import board
import busio
from PIL import Image, ImageDraw, ImageFont
from adafruit_bno08x import BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR
from adafruit_bno08x.i2c import BNO08X_I2C

# network signal code
from pi_wifi_rssi_quality_txrate import get_ssid, query_wifi, print_with_string

DOWNLOAD_LIMIT_RATE = 2.5  # Mb/s
SSD_WIDTH = 128
SSD_HEIGHT = 64  # Set to 64 for SSD1309 hardware panel compatibility
TEXT_WIDTH_LIMIT = 96  # text on left 96px
CIRCLE_AREA_START_X = TEXT_WIDTH_LIMIT  # Graphic starts at 96px


def scan_i2c_bus(i2c):
    print("Scan for I2C devices...")
    bno_detected = None
    ssd_detected = None

    while not i2c.try_lock():
        pass

    try:
        devices = i2c.scan()
        if not devices:
            print("Error: No I2C devices detected. Check your wiring")
        else:
            print(f"\nFound {len(devices)} device(s):")
            for address in devices:
                print(f" Device detected at Address: Hex: {hex(address)} ({address})")
                if address == 0x3C:
                    print(" -> likely SSD1306/SSD1309 OLED display")
                    ssd_detected = True
                if address == 0x4B or address == 0x4A:
                    print(" -> likely BNO086 IMU")
                    bno_detected = address
    finally:
        i2c.unlock()
    print("\n")
    return ssd_detected, bno_detected


def init_ssd_display(i2c):
    display = adafruit_ssd1306.SSD1306_I2C(SSD_WIDTH, SSD_HEIGHT, i2c)
    display.fill(0)
    display.show()

    image = Image.new("1", (SSD_WIDTH, SSD_HEIGHT))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    return display, draw, font, image


def init_bno086(i2c, address=0x4B):
    try:
        bno = BNO08X_I2C(i2c, address=address)
        bno.enable_feature(BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR)
        print("Successful BNO086 sensor Initialization.")
        return bno
    except Exception as e:
        print(f"WARNING: Failed to initialize BNO086: {e}")
        return None


def get_compass_heading(bno):
    if bno is None:
        return None
    try:
        quat_i, quat_j, quat_k, quat_real = bno.geomagnetic_quaternion
        siny_cosp = 2.0 * (quat_real * quat_k + quat_i * quat_j)
        cosy_cosp = 1.0 - 2.0 * (quat_j * quat_j + quat_k * quat_k)
        yaw_rad = math.atan2(siny_cosp, cosy_cosp)
        heading_deg = math.degrees(yaw_rad)
        heading = (360.0 - heading_deg) % 360.0
        return heading
    except Exception:
        return None


def get_compass_direction(heading: float):
    if heading is None:
        return ""
    heading = heading % 360.0
    if (heading >= 337.5) or (heading < 22.5):
        return "N"
    elif 22.5 <= heading < 67.5:
        return "NE"
    elif 67.5 <= heading < 112.5:
        return "E"
    elif 112.5 <= heading < 157.5:
        return "SE"
    elif 157.5 <= heading < 202.5:
        return "S"
    elif 202.5 <= heading < 247.5:
        return "SW"
    elif 247.5 <= heading < 292.5:
        return "W"
    elif 292.5 <= heading < 337.5:
        return "NW"
    return ""


def define_circle_bounding_box():
    circle_margin = 2
    x0 = CIRCLE_AREA_START_X + circle_margin
    y0 = 0 + circle_margin
    x1 = SSD_WIDTH - 1 - circle_margin
    y1 = 32 - 1 - circle_margin
    return [x0, y0, x1, y1]


def display_text_ssd(draw, font, rssi, ssid: str, tx_rate, heading: float, connected: bool = True):
    left_indent = 2

    if not connected:
        # Clear, prominent message across the layout lines when offline
        line1 = "NO WI-FI LINK"
        line2 = "Searching..."
        if heading is not None:
            direction_str = get_compass_direction(heading)
            line3 = f"Heading: {heading:.0f}° {direction_str}"
        else:
            line3 = "Heading: n/a"
        line4 = "DISCONNECTED"
    else:
        # Parse numbers safely out of raw outputs
        try:
            if isinstance(rssi, str):
                rssi_clean = re.findall(r"[-+]?\d+", rssi)[0]
                numeric_rssi = int(rssi_clean)
            else:
                numeric_rssi = int(rssi)
        except (ValueError, TypeError, IndexError):
            numeric_rssi = -99

        try:
            if isinstance(tx_rate, str):
                tx_rate_clean = re.findall(r"[+-]?\d*(?:\.\d+)?", tx_rate)
                tx_rate_clean = [x for x in tx_rate_clean if x][0]
                numeric_tx_rate = float(tx_rate_clean)
            else:
                numeric_tx_rate = float(tx_rate)
        except (ValueError, TypeError, IndexError):
            numeric_tx_rate = 0.0

        line1 = f"ssid  = {ssid if ssid else 'Unknown'}"
        line2 = f"{numeric_rssi} dBm  {numeric_tx_rate:.0f} Mb/s"

        if heading is not None:
            direction_str = get_compass_direction(heading)
            line3 = f"Heading: {heading:.0f}° {direction_str}"
        else:
            line3 = "Heading: n/a"

        line4 = "Download viable" if numeric_rssi < -75 else ""

    draw.text((left_indent, 0), line1, font=font, fill=1)
    draw.text((left_indent, 16), line2, font=font, fill=1)
    draw.text((left_indent, 32), line3, font=font, fill=1)
    draw.text((left_indent, 48), line4, font=font, fill=1)


def display_radar_ssd1305(circle_bbox, draw, rssi, connected: bool = True):
    # Base layout ring
    draw.chord(circle_bbox, start=0, end=360, outline=1, fill=0)

    if not connected:
        return  # Leave the radar loop graphic empty if disconnected

    try:
        if isinstance(rssi, str):
            rssi_clean = re.findall(r"[-+]?\d+", rssi)[0]
            numeric_rssi = float(rssi_clean)
        else:
            numeric_rssi = float(rssi)

        percentage = max(0.0, min(1.0, (numeric_rssi - (-100)) / (-30 - (-100))))
        if percentage > 0.01:
            draw.pieslice(circle_bbox, start=-90, end=(-90 + (360 * percentage)), outline=0, fill=1)
    except (ValueError, TypeError, IndexError):
        pass


def main():
    print("Starting Pi Zero 2 W Signal & Antenna Tracking Loop...\n")

    i2c = busio.I2C(board.SCL, board.SDA)
    ssd1305_detected, bno_detected = scan_i2c_bus(i2c)

    bno_sensor = None
    if bno_detected:
        bno_sensor = init_bno086(i2c, address=bno_detected)

    if ssd1305_detected:
        display, draw, font, image = init_ssd_display(i2c)
        circle_bbox = define_circle_bounding_box()

    try:
        start_time = time.time()
        while True:
            # Safely fetch SSID and network stats
            try:
                ssid = get_ssid()
                rssi, quality, tx_rate = query_wifi()

                # Check if we got empty or invalid outputs from the wireless interface
                if not ssid or rssi is None or quality is None:
                    is_connected = False
                else:
                    is_connected = True
            except Exception as e:
                is_connected = False
                ssid, rssi, quality, tx_rate = None, None, None, None

            heading = get_compass_heading(bno_sensor)

            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time

            # Print Metrics to Standard Out
            if is_connected:
                print_with_string(quality, rssi, ssid, tx_rate)
            else:
                print("====================================")
                print("  STATUS: DISCONNECTED FROM WI-FI  ")
                print("Scanning & waiting for reconnect...")
                print("====================================")
                if ssd1305_detected:
                    draw.text((2, 0),  "================", font=font, fill=1)
                    draw.text((2, 16), "Wi-Fi Disconnect", font=font, fill=1)
                    draw.text((2, 32), "Wait for connect", font=font, fill=1)
                    draw.text((2t, 48), "================", font=font, fill=1)


            if heading is not None:
                print(f"Compass Heading: {heading:.2f}° (Magnetic North = 0°)")
            else:
                print("Compass Heading: n/a")

            print(f"Updates:  {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            # Update OLED Display
            if ssd1305_detected:
                draw.rectangle((0, 0, SSD_WIDTH, SSD_HEIGHT), fill=0)
                display_text_ssd(draw, font, rssi, ssid, tx_rate, heading, connected=is_connected)
                display_radar_ssd1305(circle_bbox, draw, rssi, connected=is_connected)
                display.image(image)
                display.show()

            # Dynamic sleep rhythm: faster tracking when online, slower checking when looking for a signal
            time.sleep(0.1 if is_connected else 1.0)

    except KeyboardInterrupt:
        if ssd1305_detected:
            draw.rectangle((0, 0, SSD_WIDTH, SSD_HEIGHT), fill=0)
            display.image(image)
            display.show()
        print("\nTracking Stopped. Exiting.")


if __name__ == "__main__":
    main()