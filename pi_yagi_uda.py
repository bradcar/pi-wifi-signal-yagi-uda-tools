# pi_yagi_uda.py
"""
On Raspberry Pi Zero 2 W, the code repeatedly measures the RSSI, Link Quality,
and Tx Bit Rate of the currently targeted network on interface wlan0.
When connected to a Yagi-Uda Antenna and an Magnetometer we can use this to locate the Wi-Fi source.
The code handles connection drops and resumes automatically on reconnect.

Scan Rates:
 - Connected Mode, actual ~85ms 12 Hz
 - Scan Mode,      actual ~46ms 22 Hz
 - Out of range,   actual ~85ms 12 Hz

If the targeted network is not connected, it uses a lighter weight Scan Mode which scans all available networks looking for the targeted network.
 - The OLED SSD display shows:
 - ssid <target-ssid>
If the targeted network is connected, it can download the data file.
 - The OLED SSD display shows:
 - SSID = <target-ssid>

Metrics are printed to std out and show on the OLED display.
The OLED display on the left has 96px for text:
 - 3 lines of text with 16 chars
 - using 3 lines of text, instead of 4 since 4 looks cramped
On the right 32px, graphically shows the signal strength at a compass direction as a radar-style screen.
 - 32x32 box with circle centered with a radius of 15px

0. short press >0.1 sec
   long press >0.5 sec
1. Starts in Scan Mode
   a. If signal ≥ RSSI_CONNECT_THRESHOLD, a short press starts Connected Mode (nmcli up).
2. In Connection Mode
   a. If signal ≥ RSSI_DOWNLOAD_THRESHOLD, a short press starts download.
      if no download after 5 second timeout, display will continue to show "..dload 0?"
   b. A long press returns to Scan Mode (nmcli down)

 Pi Zero 2 W must be modified to attach an external antenna like a Yagi-Uda Antenna.
 directions:
 https://www.youtube.com/watch?v=6R8xhSzpJTU&t=166s   (great peal trace back idea)
 https://www.briandorey.com/post/raspberry-pi-zero-2-w-external-antenna-mod  (maybe beter on uFL soldering?)
  Note: I've read that Uda was the inventor and Yagi was the promoter.

Compass angles calculated with LIS3MDL sensor with hard-iron calbration.
hard_only_calibrate_lis3mdl_test.py
Explanation of why only hard-iron needed:
Compass headings (atan2) computes the differences of the angles of X- and Y-values.
The Soft-iron calibrations would make sure the vector lengths are calibrated, which doesn't affect the angle.

 The Pi Zero 2 W is running Debian Trixie base. 64-bit
  - with no desktop environment
  - 555.1 MB download, Released: 2026-04-21
  - uname -a
Linux pi-zero 6.12.75+rpt-rpi-v8 #1 SMP PREEMPT Debian 1:6.12.75-1+rpt1 (2026-03-11) aarch64 GNU/Linux

Update rates:
Updates: 546.5 msec, 2 Hz - Out of Range

"Radar display" Polygon vertex count
    - The radar circle (radius of 15 px) has max of 84 pixels on perimeter
    - 72 vertices every 5 degrees (360/5) -- likely best for clean signals
    - 40 vertices every 9 degrees (360/9)

Requirements (beyond normal i2c):
    sudo pip3 install adafruit-circuitpython-ssd1305 --break-system-packages
    sudo apt-get install python3-pil
    pip3 install adafruit-circuitpython-lis3mdl --break-system-packages
    pip install python-dotenv --break-system-packages

 TODO measure shell-fi with Yagi-Uda antenna created by Pi Pico as Access Point
"""
import getpass
import math
import os
import time
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from typing import Literal

# Display and magnetometer
import adafruit_lis3mdl
import adafruit_ssd1305  # previous prototype used: import adafruit_ssd1306

import board
import busio
from PIL import Image, ImageDraw, ImageFont

from gpiozero import Button

# Network signal tracking
from pi_wifi_rssi_quality_txrate import get_ssid, scan_target_ssid, query_wifi, quality_to_string, rssi_to_string
from download_file import download_file

DEBUG = False

# TODO test Pi Pico as Access Point
TARGET_SSID = "ABox-PDX"
# TARGET_SSID = "shell-fi"
URL_STRING = "http://192.168.4.1/download"
DESTINATION_STRING = "/home/pi-admin/downloads"

# Network Signal Lock Thresholds
RSSI_CONNECT_THRESHOLD = -77  # Minimum signal to allow a hardware connection
RSSI_DOWNLOAD_THRESHOLD = -74  # Minimum signal to execute data payload transfer

# Radar lines Boundary
RSSI_STRONG_BOUND = -45
RSSI_WEAK_BOUND = -80

# LIS3MDL Magnetic Calibration Constants - Hard-iron only needed for compass
# Constants created by hard_only_calibrate_lis3mdl_test.py
# Hard-iron calibration offsets from high-speed calibration run
CALIBRATED_MAG_MIN = [-58.7548, -38.7898, -102.2800]
CALIBRATED_MAG_MAX = [44.9284, 63.4171, -4.4870]

# Create offsets based on calibration constants - true magnetic midpoint offset for X and Y
X_OFFSET = (CALIBRATED_MAG_MAX[0] + CALIBRATED_MAG_MIN[0]) / 2.0
Y_OFFSET = (CALIBRATED_MAG_MAX[1] + CALIBRATED_MAG_MIN[1]) / 2.0

# create scale factors to normalize the field to a 1.0 radius
X_SCALE = (CALIBRATED_MAG_MAX[0] - CALIBRATED_MAG_MIN[0]) / 2.0
Y_SCALE = (CALIBRATED_MAG_MAX[1] - CALIBRATED_MAG_MIN[1]) / 2.0

SSD_WIDTH = 128
SSD_HEIGHT = 32
# SSD_HEIGHT = 64  # Set to 64 for SSD1309
TEXT_WIDTH_LIMIT = 96  # text on left 96px
CIRCLE_AREA_START_X = TEXT_WIDTH_LIMIT  # Graphic starts at 96px


class DisplayContext:
    def __init__(self, draw, font, oled, image):
        self.draw = draw
        self.font = font
        self.oled = oled
        self.image = image

    def update_line3(self, text):
        """Clear only the bottom line (20px to 30px) and write new text."""
        # 96 is your TEXT_WIDTH_LIMIT
        self.draw.rectangle((0, 20, 95, 31), fill=0)
        self.draw.text((0, 20), text, font=self.font, fill=1)
        self.oled.image(self.image)
        self.oled.show()


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

    # Reset press time for next press
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
    # Magnetometer has 400K frequency limit, SSD1305 display has 1M, i2c1 is primary I2C on Pi Zero 2 W
    i2c1 = busio.I2C(board.SCL, board.SDA, frequency=400000)
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
    # Use monospace font
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 10)
    except IOError:
        font = ImageFont.load_default()  # Fallback if font isn't loaded
    return display, draw, font, image


def init_lis3mdl(i2c):
    try:
        sensor = adafruit_lis3mdl.LIS3MDL(i2c)
        print("Successful LIS3MDL Magnetometer Init\n")
        return sensor
    except Exception as e:
        print(f"WARNING: LIS3MDL Init Failed: {e}\n")
        return None


def pico_temperature():
    """ Reads system temperature as substitute for Pico ADC(4) """
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            celsius = float(f.read()) / 1000.0
        if DEBUG: print(f"Pi Zero chip temp = {celsius:.3f}C")
        return celsius
    except Exception:
        return None


load_dotenv()


def get_password_for_ssid(ssid):
    # .env has password with WIFI_PASS_ followed by SSID
    env_key = f"WIFI_PASS_{ssid}"
    return os.getenv(env_key)


def connect_ssid(ssid):
    """
    Programmatic way to connect to WiFi network.

    CLI version for "shell-fi"
    sudo nmcli device wifi connect "shell-fi"
    sudo nmcli device wifi connect "shell-fi" password "YOUR_PASSWORD_HERE"
    sudo nmcli connection show

    # Disable Bluetooth for better Wi-Fi, since they share same antenna
    sudo nano /boot/firmware/config.txt
    dtoverlay=disable-bt

    # disable hardware auto-attempting to wake up disabled Bluetooth
    sudo systemctl disable hciuart.service
    sudo systemctl disable bluetooth.service

    """
    print(f"\nProvisioning NetworkManager for target: {ssid}...")

    # Get password from env
    password = get_password_for_ssid(ssid)
    if not password:
        print(f"No password found in .env for {ssid}")
        return False
    print(f"\nProvisioning NetworkManager for: {ssid} using stored password...")

    print(f"Flush old {ssid} configurations...")
    subprocess.run(["sudo", "nmcli", "connection", "delete", ssid], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)

    # Use clean explicit parameters for device activation to let nmcli autoconfigure security structures
    cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid, "ifname", "wlan0"]
    if password is not None:
        cmd.extend(["password", password])

    # Catch weak-signal handshaking hangs gracefully instead of dropping execution
    try:
        connect_attempt = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if connect_attempt.returncode != 0:
            print(f"ERROR: WiFi connection failed:\n{connect_attempt.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"WARNING: Connection handshake timed out after 15 seconds. Signal likely too weak.")
        return False

    # Elevate priority for network now that the profile is safely auto-generated
    subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "connection.autoconnect-priority", "10"],
                   check=True)

    print(f"Verifying '{ssid}' on state and IP assignment...")
    time.sleep(1.5)

    # Query NetworkManager for the current state
    status_check = subprocess.run(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device"], capture_output=True,
                                  text=True)

    if f"wlan0:connected:{ssid}" in status_check.stdout:
        print(f" {ssid} Connection successful! Network interface is active.\n")
        return True
    else:
        print("WARNING Profile created, but interface failed to verify an active state.\n")
        return False


def remove_ssid(ssid: Literal["shell-fi"]):
    print(f"\nCleaning up: Removing NetworkManager profile '{ssid}'...")
    subprocess.run([
        "sudo", "nmcli", "connection", "delete", ssid
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(" -> \"shell-fi\" deleted successfully.")


def change_connection(action: Literal["up", "down"]) -> bool:
    if action == "down":
        subprocess.run(["sudo", "nmcli", "connection", "down", TARGET_SSID],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False

    if action == "up":
        # bring up the existing profile
        result = subprocess.run(["sudo", "nmcli", "connection", "up", TARGET_SSID],
                                capture_output=True, text=True)
        if result.returncode == 0:
            return True

        # Fallback: Re-connect using the .env password
        print(f"Profile '{TARGET_SSID}' failed. Trying to reconnect...")
        return connect_ssid(TARGET_SSID)

    return False


def get_compass_heading(sensor):
    """
    Gets a calibrated compass heading from the X-Y magnetometer axes.
    For compass angles only need hard-iron offsets.
    """
    if sensor is None:
        return None
    try:
        mag_x, mag_y, mag_z = sensor.magnetic

        if None in (mag_x, mag_y, mag_z):
            return None

        # APPLY HARD-IRON SPATIAL CALIBRATION
        # Shift data cluster centers to 0.0 and scale to a perfect 1.0 radius sphere
        cal_x = (mag_x - X_OFFSET) / X_SCALE
        cal_y = (mag_y - Y_OFFSET) / Y_SCALE

        # use calibrated vectors into the arc-tangent calculator, notice only hard-iron calibration needed due to atan2
        heading_rad = math.atan2(cal_y, cal_x)
        heading_deg = math.degrees(heading_rad)

        # Normalize to 0-360°
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
        line2 = "out of range scan"
        line3 = f"{heading_str} {direction_str:<2}"

    # Update metrics for Connect Mode or Scan Mode
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
            line2 = f"{rssi} dbm ...Scan"

            # test if connection available
            if rssi >= RSSI_CONNECT_THRESHOLD:
                line3 = f"{heading_str} {direction_str:<2} .connect?"
            else:
                line3 = f"{heading_str} {direction_str:<2}"

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

    # dashes every 4px, which are easier to see under rotation
    for r in range(0, max_radius + 1, 4):
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
        line_length = (max_radius - 2) * proportion

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


def handle_scan_mode(short_press, rssi_heading_history, target_ssid, oled_context: DisplayContext):
    rssi = scan_target_ssid(interface="wlan0", target_ssid=target_ssid)
    ssid = target_ssid if rssi is not None else None

    if short_press and rssi is not None and rssi >= RSSI_CONNECT_THRESHOLD:
        print(f"\n* Button pressed ({rssi} dBm). Trying to connect...")
        if oled_context: oled_context.update_line3("trying to connect...")  # Targeted OLED update

        if change_connection("up"):
            rssi_heading_history[:] = [-99.0] * 360
            return True, rssi, ssid
    return False, rssi, ssid

def handle_connected_mode(short_press, download_count, target_ssid, url, destination_dir, oled_context: DisplayContext):
    """Get signal metrics, download file if sufficient strength and button pressed."""
    current_ssid = get_ssid()
    # If doesn't connect first time give it one more attempt, may add 0.05sec delay before 2nd attempt
    if current_ssid != target_ssid:
        current_ssid = get_ssid()
        if current_ssid != target_ssid:
            return False, None, None, None, None

    rssi, quality, tx_rate = query_wifi()
    if short_press and rssi >= RSSI_DOWNLOAD_THRESHOLD:
        print(f"\n* Button pressed ({rssi} dBm). Trying Download...")
        if oled_context: oled_context.update_line3("trying download...")  # Targeted update
        success, filename = download_file(url, destination_directory=destination_dir)
        if success:
            download_count += 1
            print(f" -> successfully downloaded {destination_dir}/{filename}")

    return True, rssi, current_ssid, quality, tx_rate


def print_and_display_metrics(ssd_detected, connected, ssid, rssi, quality, tx_rate, heading, download_count, draw,
                              font, oled_display,
                              image, cadence,
                              rssi_at_heading):
    # Print to console log
    if connected:
        print(f"** Connected {TARGET_SSID}, RSSI: {f'{rssi} dBm' if rssi is not None else 'None'}")
        if rssi is not None:
            quality_string = quality_to_string(quality)
            print(f"Bars:      {rssi_to_string(rssi)}")
            print(f"Link Qual: {f'{quality:>2}/70' if quality is not None else 'n/a'}    {quality_string}")
            print(f"Tx Rate:   {f'{tx_rate:.1f} Mb/s' if tx_rate is not None else 'n/a'}")
        else:
            print("Link Qual: n/a")
            print("Tx Rate:   n/a")

        print("-> download possible, use button?" if rssi >= RSSI_DOWNLOAD_THRESHOLD else "-> connected, weak signal")
    else:
        print(f"** Scanning {TARGET_SSID}, RSSI: {f'{rssi} dBm' if rssi is not None else 'None'}")

    if heading is not None:
        print(f"Compass Heading: {heading:.0f}° {get_compass_8pt_string(heading)}")
    else:
        print("Compass Heading: ???° - no Magnetometer")

    # OLED Display output
    if ssd_detected:
        draw.rectangle((0, 0, SSD_WIDTH, SSD_HEIGHT), fill=0)
        display_metrics_ssd(draw, font, rssi, ssid, tx_rate, heading, download_count, connected)
        display_radar_ssd(draw, cadence, heading or 0.0, rssi_at_heading)
        oled_display.image(image)
        oled_display.show()


def main():
    global short_press, long_press, download_count

    print("Start Wi-Fi Signal & Antenna Tracking...\n")

    i2c1, ssd_detected, lis3mdl_detected = init_i2c()

    lis3mdl = None
    if lis3mdl_detected:
        lis3mdl = init_lis3mdl(i2c1)

    # Initialize DisplayContext
    oled_context = None
    if ssd_detected:
        oled_display, draw, font, image = init_ssd_display(i2c1)
        oled_context = DisplayContext(draw, font, oled_display, image)

    scan_mode = True
    connected_mode = False

    # clear signal history on all 360 discrete degree headings
    rssi_heading_history = [-99.0] * 360

    ssid, rssi, quality, tx_rate = None, None, None, None

    try:
        start_time = time.time()
        cadence_fill = False
        while True:
            cadence_fill = not cadence_fill
            start_loop = time.time()

            pi_celsius = pico_temperature()
            if pi_celsius and pi_celsius > 60.0:
                print(f"Warning: ** High Temp: {pi_celsius:.1f}°C")

            # On long press revert to scanning, disconnect and reset radar history
            if long_press:
                if connected_mode:
                    change_connection("down")
                    rssi_heading_history = [-99.0] * 360
                connected_mode = False
                long_press = False

            # Handle Auto-Connect on first pass if needed
            if TARGET_SSID == "shell-fi" and not auto_connect_attempted:
                if oled_context: oled_context.update_line3("connecting...")
                connected_mode = connect_ssid(TARGET_SSID)
                auto_connect_attempted = True

            # Logic for connected or scanning
            if connected_mode:
                connected_mode, rssi, ssid, quality, tx_rate = handle_connected_mode(
                    short_press, download_count, TARGET_SSID, URL_STRING, DESTINATION_STRING, oled_context
                )
            else:
                connected_mode, rssi, ssid = handle_scan_mode(
                    short_press, rssi_heading_history, TARGET_SSID, oled_context
                )
                quality, tx_rate = None, None

            short_press = False

            # record signal strength at heading direction
            heading = get_compass_heading(lis3mdl)
            if rssi is not None and heading is not None:
                idx = (round(heading / 5.0) * 5) % 360
                rssi_heading_history[int(idx)] = rssi

            # print and display metrics
            print_and_display_metrics(
                ssd_detected, connected_mode, ssid, rssi, quality, tx_rate,
                heading, download_count, draw, font, oled_display, image, cadence_fill, rssi_heading_history
            )

            # capture and print update frequency and period
            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time
            print(f"Updates: {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            # Dynamic sleep, sleep longer when WiFi out of range
            if connected_mode:
                time.sleep(0.02)  # Connected Mode, actual ~85ms 12 Hz
            elif rssi is not None:
                time.sleep(0.01)  # Scan Mode, actual ~46ms 22 Hz
            else:
                time.sleep(0.04)  # Out of range fallback, actual ~85ms 12 Hz

    except KeyboardInterrupt:
        if ssd_detected:
            draw.rectangle((0, 0, SSD_WIDTH, SSD_HEIGHT), fill=0)
            oled_display.image(image)
            oled_display.show()
        print("\nEnded Tracking (^c).")

    finally:
        # remove shell-fi on normal exit, crashes, or KeyboardInterrupt
        if TARGET_SSID == "shell-fi":
            remove_ssid(TARGET_SSID)


if __name__ == "__main__":
    main()
