# pi_yagi_uda.py
"""
On Raspberry Pi Zero 2 W, the code repeatedly measures the RSSI, Link Quality,
and Tx Bit Rate of the currently targeted network on interface wlan0.
pyro

if the targeted network is connected it can download the data file.
* this is shown in the OLED SSD display as:
* "SSID = target-net"

If the targeted network is not connected, it uses a lighter weight Scan Mode which scans all available networks looking for the targeted network.
* this is shown in the OLED SSD display as:
* "ssid   target-net"
When connected to a Yagi-Uda Antenna and an Magnetometer we can use this to locate the Wi-Fi source.

It prints the results to std out and an OLED display.
It graphically shows the signal strength at a compass direction.
This is also shown graphically in a small radar screen graphic.
It gracefully handles total connection drops and resumes automatically on reconnect.

0. short press >0.1 sec
   long press >0.5 sec
1. Starts in Scan Mode
   a. If signal ≥ RSSI_CONNECT_THRESHOLD, a short press triggers Connected Mode (nmcli up).
2. In Connection Mode
   a. If signal ≥ RSSI_DOWNLOAD_THRESHOLD, a short press starts download.
      5 second timeout if no download, display will continue to show "..dload 0?"
   b. A long press returns to Scan Mode (nmcli down)

Data is shown on  SSD1305 128x32 display and printed to std out.
left 96px for text
 - 3 lines of text with 16 chars
 - using 3 lines of text, instead of 4 since 4 looks cramped
right 32px for circle graphic
 - 32x32 box with circle centered with a radius of 15px

 Pi Zero 2 W must be modified to attach an external antenna like a Yagi Uda.
 directions: https://www.youtube.com/watch?v=6R8xhSzpJTU&t=166s
  Note: I've heard Uda was the inventor and Yagi was the promoter.

 The Pi Zero 2 W is running Debian Trixie base. 64-bit
  - with no desktop environment
  - 555.1 MB download, Released: 2026-04-21
  - uname -a
Linux pi-zero 6.12.75+rpt-rpi-v8 #1 SMP PREEMPT Debian 1:6.12.75-1+rpt1 (2026-03-11) aarch64 GNU/Linux

Requirements:
 TODO TURN OFF BLUETOOTH !!!
 TODO measure shell-fi created by Pi Pico as Access Point
 TODO consider polygon vertex count
    - The radar circle (radius of 15 px) has max of 84 pixels on perimeter
    - 72 vertices every 5 degrees (360/5)
    - 40 vertices every 9 degrees (360/9)
"""
import math
import time
import subprocess
from datetime import datetime
from typing import Literal

# Import display and magnetometer
import adafruit_lis3mdl
import adafruit_ssd1305  # previous prototype used: import adafruit_ssd1306

import board
import busio
from PIL import Image, ImageDraw, ImageFont

from gpiozero import Button

# Network signal tracking dependencies
from pi_wifi_rssi_quality_txrate import get_ssid, scan_target_ssid, query_wifi, print_metrics, rssi_to_string
from download_file import download_file

# TODO test Pi Pico as Access Point
# TARGET_SSID = "shell-fi"
TARGET_SSID = "ABox-PDX"

# Network Signal Lock Thresholds
RSSI_CONNECT_THRESHOLD = -75  # Minimum signal to allow a hardware connection
RSSI_DOWNLOAD_THRESHOLD = -70  # Minimum signal to execute data payload transfer

# Radar lines Boundary
RSSI_STRONG_BOUND = -45
RSSI_WEAK_BOUND = -80

SSD_WIDTH = 128
SSD_HEIGHT = 32
# SSD_HEIGHT = 64  # Set to 64 for SSD1309
TEXT_WIDTH_LIMIT = 96  # text on left 96px
CIRCLE_AREA_START_X = TEXT_WIDTH_LIMIT  # Graphic starts at 96px

# Globals
long_press = False
short_press = False
button_press_time = 0.0
download_count = 0

# Configure Button on GPIO 26 (Physical Pin 37) with a 2.0 second hold threshold
button0 = Button(26, pull_up=True, bounce_time=0.1, hold_time=0.5)


def on_button_pressed():
    global button_press_time
    button_press_time = time.time()  # Capture raw baseline time on down-stroke


def on_button_released():
    global short_press, long_press, button_press_time

    # Calculate press time
    duration = 0.0
    if button_press_time > 0.0:
        duration = time.time() - button_press_time

    # Reset press time
    button_press_time = 0.0

    if duration >= button0.hold_time:
        long_press = True
        print(f"\n* ====== Long Press Detected ({duration:.4f}s). Reverting to Scan Mode.")
    else:
        short_press = True
        print(f"\n* ------ Short Press Detected ({duration:.4f}s).")


# Listen to both edges to measure button press duration
button0.when_pressed = on_button_pressed
button0.when_released = on_button_released
print("Button0 Listeners Active (GPIO 26) for Press and Release Edges.")


def scan_i2c_bus(i2c_primary):
    print("I2C device Scan...")
    lis3mdl_detected = None
    ssd_detected = None

    try:
        # Scan the two buses directly
        devices1 = i2c_primary.scan()
        if not devices1:
            print("Error: No I2C1 devices detected (primary). Check your wiring")
        else:
            print(f"\nFound I2C1 {len(devices1)} device(s):")
            for address in devices1:
                print(f" I2C1 Device: Hex: {hex(address)} ({address})")
                if address == 0x3C:
                    print(" -> likely SSD1305 OLED display")
                    ssd_detected = True
                elif address == 0x1C or address == 0x1E:
                    print(" -> likely LIS3MDL Magnetometer")
                    lis3mdl_detected = address
                else:
                    print(f" -> unknown device")
    except RuntimeError as e:
        print(f"I2C Hardware Error: {e}")
    print("\n")
    return ssd_detected, lis3mdl_detected


def init_i2c():
    # Set I2C 1M is max for SSD1305 display, i2c1 is primary on Pi Zero 2 W
    i2c1 = busio.I2C(board.SCL, board.SDA, frequency=100000)
    ssd_detected, lis_detected = scan_i2c_bus(i2c1)
    print(f"{ssd_detected=} + {lis_detected=}")
    return i2c1, ssd_detected, lis_detected


def init_ssd_display(i2c):
    # display = adafruit_ssd1306.SSD1306_I2C(SSD_WIDTH, SSD_HEIGHT, i2c)
    display = adafruit_ssd1305.SSD1305_I2C(SSD_WIDTH, SSD_HEIGHT, i2c)
    display.fill(0)
    display.show()

    image = Image.new("1", (SSD_WIDTH, SSD_HEIGHT))
    draw = ImageDraw.Draw(image)
    # Use monospace font, not variable-width default
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 10)
    except IOError:
        font = ImageFont.load_default()  # Fallback if font isn't installed
    return display, draw, font, image


def init_lis3mdl(i2c):
    try:
        sensor = adafruit_lis3mdl.LIS3MDL(i2c)
        print("Successful LIS3MDL Magnetometer Init")
        return sensor
    except Exception as e:
        print(f"WARNING: LIS3MDL Init Failed: {e}")
        return None


def change_connection(action: Literal["up", "down"]) -> bool:
    """
    Change connection state. Changes mode even if the hardware layer reports a temporary busy status.
    """
    if action not in ("up", "down"):
        return False

    timeout_duration = 8 if action == "up" else 5

    # Running without check=True bypasses transient 'device busy' status 10 errors
    subprocess.run(
        ["sudo", "nmcli", "connection", action, TARGET_SSID],
        timeout=timeout_duration
    )

    # Force the state machine to transition immediately, letting the next loop iteration handle recovery
    return (action == "up")


def get_compass_heading(sensor):
    """
    get compas heading from x-y magnetometer sensor
    todo check if upside down
    todo calibration
     - may need to rotate 360 to find the max and min X/Y, and subtract the midpoint offset
     - from mag_x and mag_y before passing them to atan2.
    """
    if sensor is None:
        return None
    try:
        mag_x, mag_y, mag_z = sensor.magnetic

        if None in (mag_x, mag_y, mag_z):
            return None

        # Compute heading in radians atan2(Y, X), convert to degrees
        heading_rad = math.atan2(mag_y, mag_x)
        heading_deg = math.degrees(heading_rad)

        # Normalize to standard 0-360° compass layout
        heading = (heading_deg + 360.0) % 360.0
        return heading
    except (ValueError, TypeError, OSError) as e:
        print(f"Magnetometer Read Error: {e}")
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


def display_metrics_ssd(draw, font, rssi, ssid: str, tx_rate, heading: float, download_count, connected: bool = True):
    left_indent = 0
    direction_str = get_compass_8pt_string(heading) if heading is not None else ""
    heading_str = f"{heading:>3.0f}°" if heading is not None else "???°"

    # if rssi is not set, display out of range messages
    if rssi is None:
        line1 = f"target: {TARGET_SSID}"
        line2 = "out of range... "
        line3 = f"{heading_str} {direction_str:<2} scanning"

    # rssi signal, either probing or connected
    else:
        if connected:
            line1 = f"SSID = {ssid}"
            # If connected, show mb/s, else print "linked"
            rate_str = f"{tx_rate:.0f} mb/s" if tx_rate is not None else "linked"
            line2 = f"{rssi} dbm  {rate_str}"

            # Notify if download is possible based on -70 dBm rule
            if rssi >= RSSI_DOWNLOAD_THRESHOLD:
                line3 = f"{heading_str} {direction_str:<2} ..dload {download_count}?"
            else:
                line3 = f"{heading_str} {direction_str:<2}"
        else:
            line1 = f"ssid   {ssid}"
            line2 = f"{rssi} dbm ...probing"

            # test if connection available
            if rssi >= RSSI_CONNECT_THRESHOLD:
                line3 = f"{heading_str} {direction_str:<2} .connect?"
            else:
                line3 = f"{heading_str} {direction_str:<2} weak signal"

    # Write text to OLED buffer
    draw.text((left_indent, 0), line1, font=font, fill=1)
    draw.text((left_indent, 10), line2, font=font, fill=1)
    draw.text((left_indent, 20), line3, font=font, fill=1)


def display_radar_ssd(draw, cadence_fill, heading: float, signal_history):
    """
    Draw a white box with a black radar circle in it.
    Add white directional orientation lines for North, East, South, and West.
    Calculates a solid white polygon tracking signal strength vs compass directions.
    """
    center_x = 112
    center_y = 15
    max_radius = 15

    if heading is None:
        heading = 0.0

    # Radar graphics: white background block, black circle mask
    draw.rectangle((96, 0, 127, 31), fill=1)
    draw.ellipse((center_x - max_radius, center_y - max_radius, center_x + max_radius, center_y + max_radius),
                 outline=0, fill=0)

    # Cadence indicator box
    draw.rectangle((97, 26, 101, 30), fill=0)
    draw.rectangle((98, 27, 100, 29), fill=int(cadence_fill))

    # Standard math puts 0° at East. To make 0° North and clockwise:
    # Screen Angle = 90 - (angle - heading)

    # Solid North Crosshair
    north_rad = math.radians(90.0 - (0.0 - heading))
    nx = int(center_x + max_radius * math.cos(north_rad))
    ny = int(center_y - max_radius * math.sin(north_rad))  # Subtracted for screen-space Y
    draw.line((center_x, center_y, nx, ny), fill=1)

    # Dashed Crosshairs (South, West, East)
    south_rad = math.radians(90.0 - (180.0 - heading))
    west_rad = math.radians(90.0 - (270.0 - heading))
    east_rad = math.radians(90.0 - (90.0 - heading))
    for r in range(0, max_radius + 1, 2):
        # South
        sx = int(center_x + r * math.cos(south_rad))
        sy = int(center_y - r * math.sin(south_rad))
        draw.point((sx, sy), fill=1)

        # West
        wx = int(center_x + r * math.cos(west_rad))
        wy = int(center_y - r * math.sin(west_rad))
        draw.point((wx, wy), fill=1)

        # East
        ex = int(center_x + r * math.cos(east_rad))
        ey = int(center_y - r * math.sin(east_rad))
        draw.point((ex, ey), fill=1)

    # Antenna strength polygon vertex points at 5 degrees intervals, 72 vertices
    polygon_points = []
    for angle in range(0, 360, 5):
        window_values = []
        for offset in range(-2, 3):
            neighbor_index = (angle + offset) % 360
            window_values.append(signal_history[neighbor_index])

        saved_rssi = max(window_values)

        # Clamp RSSI bounds safely
        if saved_rssi < RSSI_WEAK_BOUND:
            saved_rssi = RSSI_WEAK_BOUND
        elif saved_rssi > RSSI_STRONG_BOUND:
            saved_rssi = RSSI_STRONG_BOUND

        proportion = (saved_rssi - RSSI_WEAK_BOUND) / (RSSI_STRONG_BOUND - RSSI_WEAK_BOUND)
        line_length = max_radius * proportion

        # Apply identical screen space angle mapping
        angle_rad = math.radians(90.0 - (angle - heading))

        target_x = int(center_x + line_length * math.cos(angle_rad))
        target_y = int(center_y - line_length * math.sin(angle_rad))  # Subtracted for screen-space Y

        polygon_points.append((target_x, target_y))

    # Draw the white Antenna strength/direction polygon
    if len(polygon_points) >= 3:
        draw.polygon(polygon_points, fill=1, outline=1)

    # Center axis markers & black center doc on top of everything
    draw.point((center_x, center_y - 1), fill=0)
    draw.point((center_x, center_y + 1), fill=0)
    draw.point((center_x - 1, center_y), fill=0)
    draw.point((center_x + 1, center_y), fill=0)
    draw.point((center_x, center_y), fill=0)


def main():
    global short_press, long_press, download_count

    print("Start Wi-Fi Signal & Antenna Tracking...\n")
    scan_mode = True
    connected_mode = False

    i2c1, ssd_detected, lis3mdl_detected = init_i2c()

    lis3mdl = None
    if lis3mdl_detected:
        lis3mdl = init_lis3mdl(i2c1)

    if ssd_detected:
        display, draw, font, image = init_ssd_display(i2c1)

    # signal history tracking of 360 discrete headings
    signal_history = [-99.0] * 360

    ssid, rssi, quality, tx_rate = None, None, None, None
    connected_mode = False  # Track state: False = Probing, True = Hard Connection Lock

    try:
        start_time = time.time()
        cadence_fill = False
        while True:
            cadence_fill = not cadence_fill
            current_loop_time = time.time()

            # On long_press revert to Scan Mode
            if long_press:
                print("\nLong_press: disconnecting")
                if connected_mode:
                    connected_mode = change_connection("down")

                tx_rate = None
                quality = None
                long_press = False
                short_press = False

            # Connected Mode - measure rssi, quality, txrate
            if connected_mode:
                current_ssid = get_ssid()
                if current_ssid == TARGET_SSID:
                    rssi, quality, tx_rate = query_wifi()
                    ssid = current_ssid

                    # Signal above download threshold, look for download request (single pulse)
                    if rssi is not None and rssi >= RSSI_DOWNLOAD_THRESHOLD:
                        if short_press:
                            print(f"\n* Button pressed ({rssi} dBm). Downloading {download_count}...")
                            url_string = "http://192.168.4.1/download"
                            destination_string = "/home/pi-admin/downloads"
                            print(f" -> download from {url_string} to destination directory: {destination_string}")
                            success, filename = download_file(url_string, destination_directory=destination_string)
                            if success:
                                download_count += 1
                                print(f" -> successfully downloaded {destination_string}/{filename}")

                else:
                    # Connection broken, return to Scan Mode
                    connected_mode = False
                    tx_rate = None
                    quality = None

            # Scan Mode - Scan for remote target, only measure rssi
            else:
                tx_rate = None
                quality = None

                # Scan all unconnected signals, but only return rssi for target ssid
                rssi = scan_target_ssid(interface="wlan0", target_ssid=TARGET_SSID)
                ssid = TARGET_SSID if rssi is not None else None

                # When signal is stronger than connection threshold, short press changes mode to connected
                if rssi is not None and rssi >= RSSI_CONNECT_THRESHOLD:
                    if short_press:
                        print(f"\n* Button pressed ({rssi} dBm). Connecting...")
                        connected_mode = change_connection("up")

            short_press = False

            heading = get_compass_heading(lis3mdl)
            print(f"heading - after get_compass_heading: {heading}")

            # Save rssi signal strength telemetry at heading index
            if rssi is not None and heading is not None:
                signal_history[int(heading) % 360] = rssi

            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time

            # Print metrics to standard out
            if connected_mode:
                # Print connected mode metrics to standard out
                print_metrics(quality, rssi, ssid, tx_rate)
                if rssi >= RSSI_DOWNLOAD_THRESHOLD:
                    print(f"-> download possible (download #{download_count})?)")
                else:
                    print("-> connected, but signal too weak for download")

            else:
                # Print Scan Mode metrics to standard out
                print(f"**Probing ssid: {TARGET_SSID} un-connected")
                if rssi is not None:
                    print(f"RSSI:    {rssi:>3} dBm  {rssi_to_string(rssi)}")
                    if rssi >= RSSI_CONNECT_THRESHOLD:
                        print("-> connection possible (connect?)")

            if heading is not None:
                print(f"Compass Heading: {heading:.0f}° (Magnetic North = 0°)")
            else:
                print("Compass Heading: ???° - no Magnetometer")

            print(f"Updates: {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            # Update OLED SSD Display, Left side is text metrics, right side is radar graphic
            if ssd_detected:
                draw.rectangle((0, 0, SSD_WIDTH, SSD_HEIGHT), fill=0)  # clear canvas

                # Text Metrics
                display_metrics_ssd(draw, font, rssi, ssid, tx_rate, heading, download_count, connected=connected_mode)

                # use rssi strength and angle to render "radar" graphic
                render_heading = heading if heading is not None else 0.0
                display_radar_ssd(draw, cadence_fill, render_heading, signal_history)

                display.image(image)
                display.show()

            # Dynamic sleep, sleep longer when WiFi out of range
            if connected_mode:
                time.sleep(0.05)  # Connected Mode
            elif rssi is not None:
                time.sleep(0.01)  # Scan Mode
            else:
                time.sleep(0.5)  # Out of range fallback

    except KeyboardInterrupt:
        if ssd_detected:
            draw.rectangle((0, 0, SSD_WIDTH, SSD_HEIGHT), fill=0)
            display.image(image)
            display.show()
        print("\nEnded Tracking (^c).")


if __name__ == "__main__":
    main()
