# pi_yagi_uda.py
"""
On Raspberry Pi Zero 2 W, the code repeatedly measures the RSSI, Link Quality,
and Tx Bit Rate of the currently connected network on interface wlan0.
It prints the results to std out and an OLED display.
It gracefully handles total connection drops and resumes automatically on reconnect.

This code displays data on a SSD1305 128x32 display (left 96px for text,
right 32px for circle graphic) and also prints data to std out.
https://learn.adafruit.com/adafruit-2-23-monochrome-oled-bonnet/usage

The Zero 2 W will be connected to a directional Yagi Uda antenna.
"""
import math
import time
from datetime import datetime

import adafruit_ssd1306
# TODO uncomment this when get ssd 1305 bonnet.
# import adafruit_ssd1305

import board
import busio
from PIL import Image, ImageDraw, ImageFont
from adafruit_bno08x import BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR
from adafruit_bno08x.i2c import BNO08X_I2C

# network signal code
from pi_wifi_rssi_quality_txrate import get_ssid, query_wifi, print_with_string

DOWNLOAD_LIMIT_RATE = 2.5  # Mb/s
SSD_WIDTH = 128
SSD_HEIGHT = 64  # Set to 64 for SSD1309
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
                print(f" I2C Device at Address: Hex: {hex(address)} ({address})")
                if address == 0x3C:
                    print(" -> likely SSD1305 OLED display")
                    ssd_detected = True
                if address == 0x4B or address == 0x4A:
                    print(" -> likely BNO086 IMU")
                    bno_detected = address
    finally:
        i2c.unlock()
    print("\n")
    return ssd_detected, bno_detected


def init_ssd_display(i2c):
    # TODO uncomment this when get ssd 1305 bonnet.
    # display = adafruit_ssd1305.SSD1305_I2C(SSD_WIDTH, SSD_HEIGHT, i2c)
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
        print("Successful BNO086 sensor Init.")
        return bno
    except Exception as e:
        print(f"WARNING: BNO086 sensor Init Failed: {e}")
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
        return "n"
    elif 22.5 <= heading < 67.5:
        return "ne"
    elif 67.5 <= heading < 112.5:
        return "e"
    elif 112.5 <= heading < 157.5:
        return "se"
    elif 157.5 <= heading < 202.5:
        return "s"
    elif 202.5 <= heading < 247.5:
        return "sw"
    elif 247.5 <= heading < 292.5:
        return "w"
    elif 292.5 <= heading < 337.5:
        return "nw"
    return ""


def define_circle_bounding_box():
    circle_margin = 0
    x0 = CIRCLE_AREA_START_X + circle_margin
    y0 = 0 + circle_margin
    x1 = SSD_WIDTH - 1 - circle_margin
    y1 = 32 - 1 - circle_margin  # Keep radar matching top 32px area
    return [x0, y0, x1, y1]


def display_text_ssd(draw, font, rssi, ssid: str, tx_rate, heading: float, connected: bool = True):
    left_indent = 2

    if not connected or rssi is None or tx_rate is None:
        line1 = "================"
        line2 = "wifi  disconnect"
        line3 = "wait for connect"
        if heading is not None:
            direction_str = get_compass_direction(heading)
            line4 = f"compass {heading:.0f}° {direction_str}"
        else:
            line4 = "================"
    else:
        line1 = f"ssid  = {ssid if ssid else 'Unknown'}"
        line2 = f"{rssi} dbm  {tx_rate:.0f} mbps"

        download_str = ",  dload ?" if rssi > -75 else ""
        if heading is not None:
            direction_str = get_compass_direction(heading)
            line3 = f"{heading:.0f}° {direction_str}{download_str}"
        else:
            line3 = f"???° {download_str}"

    draw.text((left_indent, 1), line1, font=font, fill=1)
    draw.text((left_indent, 11), line2, font=font, fill=1)
    draw.text((left_indent, 21), line3, font=font, fill=1)


def display_radar_ssd(circle_bbox, draw, angle: float, rssi: float, connected: bool = True):
    """
    Draws a white radar circle with a black center indicator dot.
    Sweeps an active line proportional to the real-time signal strength.
    -20dBm or greater: Full length vector line extending to circle border.
    -80dBm or lower: Zero length vector line, hidden inside center point.
    """
    # Draw solid white circle indicator backdrop
    draw.ellipse(circle_bbox, outline=1, fill=1)

    # Calculate exact center point of the radar bounding box
    center_x = (circle_bbox[0] + circle_bbox[2]) // 2
    center_y = (circle_bbox[1] + circle_bbox[3]) // 2

    # Calculate full boundary radius
    max_radius = (circle_bbox[2] - circle_bbox[0]) // 2

    # Default to floor limit if completely disconnected
    current_rssi = rssi if (connected and rssi is not None) else -80.0

    # Enforce strict ceiling and floor logic limits
    if current_rssi > -20.0:
        current_rssi = -20.0
    elif current_rssi < -80.0:
        current_rssi = -80.0

    # Calculate proportional line length factor
    # -20 dBm -> 1.0 (Full length) | -80 dBm -> 0.0 (Zero length)
    proportion = (current_rssi - (-80.0)) / (-20.0 - (-80.0))
    line_length = max_radius * proportion

    # Convert angle to standard coordinate math (0 degrees = Straight Up)
    angle_rad = math.radians(angle - 90.0)

    # Compute target line destination coordinates
    target_x = int(center_x + line_length * math.cos(angle_rad))
    target_y = int(center_y + line_length * math.sin(angle_rad))

    # Draw vector line out from center point
    if line_length > 0:
        draw.line((center_x, center_y, target_x, target_y), fill=0)

    # Draw the black center point dot over everything
    draw.point((center_x, center_y), fill=0)


def main():
    print("Starting Pi Zero 2 W Signal & Antenna Tracking...\n")

    i2c = busio.I2C(board.SCL, board.SDA)
    ssd1305_detected, bno_detected = scan_i2c_bus(i2c)

    bno_sensor = None
    if bno_detected:
        bno_sensor = init_bno086(i2c, address=bno_detected)

    if ssd1305_detected:
        display, draw, font, image = init_ssd_display(i2c)
        circle_bbox = define_circle_bounding_box()

    # Initialize radar sweep tracker angle to start straight up (0 degrees)
    sweep_angle = 0.0

    try:
        start_time = time.time()
        while True:
            # Get SSID and network stats
            try:
                ssid = get_ssid()
                rssi, quality, tx_rate = query_wifi()

                if not ssid or rssi is None or quality is None or tx_rate is None:
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

            print(f"Sweep Vector Angle: {sweep_angle}°")
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

                # Execute the new proportional display_radar_ssd routine
                display_radar_ssd(circle_bbox, draw, sweep_angle, rssi, connected=is_connected)

                display.image(image)
                display.show()

            # Increment the sweep angle by 5 degree for next pass
            sweep_angle = (sweep_angle + 5) % 360

            # Dynamic sleep
            time.sleep(0.1 if is_connected else 1.0)

    except KeyboardInterrupt:
        if ssd1305_detected:
            draw.rectangle((0, 0, SSD_WIDTH, SSD_HEIGHT), fill=0)
            display.image(image)
            display.show()
        print("\nTracking Stopped. Exiting.")


if __name__ == "__main__":
    main()