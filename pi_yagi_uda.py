# pi_yagi_uda.py
"""
On Raspberry Pi Zero 2 W, the code repeatedly measures the RSSI, Link Quality,
and Tx Bit Rate of the currently connected network on interface wlan0.
When connected to a Yagi-Uda Antenna and an IMU we can use this to locate the WiFi source.

It prints the results to std out and an OLED display.
It graphically shows the signal strength at a compass direction.
This is also shown graphically in a small radar screen graphic.
It gracefully handles total connection drops and resumes automatically on reconnect.

Data is shown on  SSD1305 128x32 display and printed to std out.
left 96px for text
 - 3 lines of text with 16 chars
 - using 3 lines of text, instead of 4 since 4 looks cramped
right 32px for circle graphic
 - 32x32 box with circle centered with a radius of 15px

 Pi Zero 2 W must be modified to attach an external antenna like a Yagi Uda.
 directions: https://www.youtube.com/watch?v=6R8xhSzpJTU&t=166s

 Note: I've heard Uda was the inventor and Yagi was the promoter.

"""
import math
import time
from datetime import datetime

import adafruit_ssd1306
# TODO uncomment when get ssd 1305 bonnet.
# import adafruit_ssd1305

import board
import busio
from PIL import Image, ImageDraw, ImageFont
from adafruit_bno08x import BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR
from adafruit_bno08x.i2c import BNO08X_I2C

# Network signal tracking dependencies
from pi_wifi_rssi_quality_txrate import get_ssid, query_wifi, print_with_string

# TODO REMOVE WHEN YAGI-UDA ADDED: Import the mock test environment
from cardiod_test_data_generator import measured_signal_strength, MOCK_SIGNAL_ARRAY

# Radar lines Boundary
RSSI_STRONG_BOUND = -45
RSSI_WEAK_BOUND = -80

SSD_WIDTH = 128
# TODO uncomment when get ssd 1305 bonnet.
# SSD_HEIGHT = 32  # TODO uncomment this when get ssd 1305 bonnet
SSD_HEIGHT = 64  # Set to 64 for SSD1309
TEXT_WIDTH_LIMIT = 96  # text on left 96px
CIRCLE_AREA_START_X = TEXT_WIDTH_LIMIT  # Graphic starts at 96px


def scan_i2c_bus(i2c):
    print("I2C device Scan...")
    bno_detected = None
    ssd_detected = None

    while not i2c.try_lock(): pass
    try:
        devices = i2c.scan()
        if not devices:
            print("Error: No I2C devices detected. Check your wiring")
        else:
            print(f"\nFound {len(devices)} device(s):")
            for address in devices:
                print(f" I2C Device: Hex: {hex(address)} ({address})")
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
    # Use monospace font instead of the variable-width default
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 10)
    except IOError:
        font = ImageFont.load_default()  # Fallback if font isn't installed
    #font = ImageFont.load_default()
    return display, draw, font, image


def init_bno086(i2c, address=0x4B):
    try:
        bno = BNO08X_I2C(i2c, address=address)
        bno.enable_feature(BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR)
        print(f"Successful BNO086 sensor Init {hex(address)}")
        return bno
    except Exception as e:
        print(f"WARNING: BNO086 sensor Init {hex(address)} Failed: {e}")
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


def get_compass_8pt_string(heading: float):
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


def display_text_ssd(draw, font, rssi, ssid: str, tx_rate, heading: float, connected: bool = True):
    left_indent = 0  # anything greater than 0 limits row length

    if not connected or rssi is None or tx_rate is None:
        line1 = "================"
        line2 = "wifi  disconnect"
        if heading is not None:
            direction_str = get_compass_8pt_string(heading)
            line3 = f"compass {heading:.0f}° {direction_str}"
        else:
            line3 = "================"
    else:
        line1 = f"ssid  = {ssid if ssid else 'Unknown'}"
        line2 = f"{rssi} dbm  {tx_rate:.0f} mbps"

        download_str = ",  dload ?" if rssi > -75 else ""
        if heading is not None:
            direction_str = get_compass_8pt_string(heading)
            line3 = f"{heading:>3.0f}° {direction_str:<2}{download_str}"
        else:
            line3 = f"???° {download_str}"

    draw.text((left_indent, 0), line1, font=font, fill=1)
    draw.text((left_indent, 10), line2, font=font, fill=1)
    draw.text((left_indent, 20), line3, font=font, fill=1)


def display_radar_ssd(draw, current_sweep_angle: float, heading: float = 0.0):
    """
    Draw a white box with a black radar circle in it.
    Add white directional orientation lines for North, East, South, and West.
    Calculates a solid white polygon tracking signal strength vs compass directions.
    """
    # circle coordinates centering in the 32x32 right panel
    center_x = 112
    center_y = 15
    max_radius = 15

    # Safe fallback if heading is not active yet
    if heading is None:
        heading = 0.0

    # Radar graphics (white outside, black circle with black center dots
    draw.rectangle((96, 0, 127, 31), fill=1)
    draw.ellipse((center_x - max_radius, center_y - max_radius, center_x + max_radius, center_y + max_radius),
                 outline=0, fill=0)

    # Draw the four cardinal compass North in white, other 3 in dashed lines
    # Dynamic crosshairs rotate based on heading relative to fixed screen space
    north_rad = math.radians(0.0 - heading - 90.0)
    south_rad = math.radians(180.0 - heading - 90.0)
    west_rad = math.radians(270.0 - heading - 90.0)
    east_rad = math.radians(90.0 - heading - 90.0)

    # Dynamic Solid North Line
    nx = int(center_x + max_radius * math.cos(north_rad))
    ny = int(center_y + max_radius * math.sin(north_rad))
    draw.line((center_x, center_y, nx, ny), fill=1)  # North
    # draw.line((center_x, center_y + max_radius, center_x, center_y), fill=1)  # South
    # draw.line((center_x - max_radius, center_y, center_x, center_y), fill=1)  # West
    # draw.line((center_x + max_radius, center_y, center_x, center_y), fill=1)  # East
    # --
    # for y in range(center_y - max_radius, center_y, 2):
    #    draw.point((center_x, y), fill=1)  # North (from center going up)

    # Rotated Dashed Crosshairs
    for r in range(0, max_radius + 1, 2):
        # South dot array
        sx = int(center_x + r * math.cos(south_rad))
        sy = int(center_y + r * math.sin(south_rad))
        draw.point((sx, sy), fill=1)  # South (from center going down)

        # West dot array
        wx = int(center_x + r * math.cos(west_rad))
        wy = int(center_y + r * math.sin(west_rad))
        draw.point((wx, wy), fill=1)  # West (from center going left)

        # East dot array
        ex = int(center_x + r * math.cos(east_rad))
        ey = int(center_y + r * math.sin(east_rad))
        draw.point((ex, ey), fill=1)  # East (from center going right)

    # Array for "antenna strength" polygon vertex points
    polygon_points = []

    # Loop through all 72 (every 5 degrees) to find the "antenna strength" boundary points
    for angle in range(0, 360, 5):
        # Look up what the mock data vector has saved for this exact angle entry
        saved_rssi = MOCK_SIGNAL_ARRAY[angle]

        # Clamp rssi values (es: -45 to -80 dBm)
        if saved_rssi > RSSI_STRONG_BOUND:
            saved_rssi = RSSI_STRONG_BOUND
        elif saved_rssi < RSSI_WEAK_BOUND:
            saved_rssi = RSSI_WEAK_BOUND

        # Calculate proportional line length based on rssi
        proportion = (saved_rssi - RSSI_WEAK_BOUND) / (RSSI_STRONG_BOUND - RSSI_WEAK_BOUND)
        line_length = max_radius * proportion

        # Shift geometry relative to current compass heading so layout updates dynamically
        angle_rad = math.radians(angle - heading - 90.0)

        # Compute polygon vertex coordinates
        target_x = int(center_x + line_length * math.cos(angle_rad))
        target_y = int(center_y + line_length * math.sin(angle_rad))

        # Append the calculated outer coordinate point to our vertex tracker list
        polygon_points.append((target_x, target_y))

    # Draw the white Antenna strength/direction polygon over black circle
    if len(polygon_points) >= 3:
        draw.polygon(polygon_points, fill=1, outline=1)

    # Layer black crosshairs *on top* of the white strength pattern
    # TODO decide if +/- 1px or 2px
    draw.point((center_x, center_y - 1), fill=0)  # North micro-marker
    draw.point((center_x, center_y + 1), fill=0)  # South micro-marker
    draw.point((center_x - 1, center_y), fill=0)  # West micro-marker
    draw.point((center_x + 1, center_y), fill=0)  # East micro-marker

    # black center point dot over everything
    draw.point((center_x, center_y), fill=0)


def main():
    print("Starting Pi Zero 2 W Signal & Antenna Tracking...\n")

    i2c = busio.I2C(board.SCL, board.SDA)
    ssd_detected, bno_detected = scan_i2c_bus(i2c)

    bno_sensor = None
    if bno_detected:
        bno_sensor = init_bno086(i2c, address=bno_detected)

    if ssd_detected:
        display, draw, font, image = init_ssd_display(i2c)

    # Initialize radar sweep tracker angle to start straight up (0 degrees)
    sweep_angle = 0.0

    # TODO REMOVE WHEN REAL IMU ROTATING: Mock tracking variable to force screen rotation animation
    mock_heading_tracker = 0.0

    try:
        start_time = time.time()
        while True:
            # Get data for text display box
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

            # TODO REMOVE WHEN REAL IMU ROTATING: Fallback to animated loop tracker if physical IMU returns None
            if heading is None:
                heading = mock_heading_tracker

            # TODO: change to real data. now Pulls directly from your cardiod_test_data_generator.py MOCK_SIGNAL_ARRAY configuration
            # Get signal strength in each direction for radar graphic
            _, mock_rssi = measured_signal_strength(sweep_angle)

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

            print(f"Sweep Vector Angle: {sweep_angle}° --> Mock RSSI: {mock_rssi} dBm")
            if heading is not None:
                print(f"Compass Heading: {heading:.2f}° (Magnetic North = 0°)")
            else:
                print("Compass Heading: n/a")

            print(f"Updates:  {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            # Update OLED SSD Display
            if ssd_detected:
                # Clear buffer canvas
                draw.rectangle((0, 0, SSD_WIDTH, SSD_HEIGHT), fill=0)

                # Left side is text output for connected WiFi
                display_text_ssd(draw, font, rssi, ssid, tx_rate, heading, connected=is_connected)

                # Right side track strength/compass for radar graphic
                display_radar_ssd(draw, sweep_angle, heading=heading)

                display.image(image)
                display.show()

            # Increment the sweep angle by exactly 5 degrees for the next pass
            sweep_angle = (sweep_angle + 5) % 360

            # TODO REMOVE WHEN REAL IMU ROTATING: Increment mockup heading loop by 2 degrees per frame to animate screen
            mock_heading_tracker = (mock_heading_tracker + 2.0) % 360

            # Dynamic sleep, sleep longer when wifi is disconnected
            time.sleep(0.1 if is_connected else 1.0)

    except KeyboardInterrupt:
        if ssd_detected:
            draw.rectangle((0, 0, SSD_WIDTH, SSD_HEIGHT), fill=0)
            display.image(image)
            display.show()
        print("\nTracking Stopped. Exiting.")


if __name__ == "__main__":
    main()
