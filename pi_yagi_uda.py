# pi_yagi_uda.py
"""
On Raspberry Pi Zero 2 W, the code repeatedly measures the RSSI, Link Quality,
and Tx Bit Rate of the currently targeted network on interface wlan0.
When connected to a Yagi-Uda Antenna and an Magnetometer we can use this to locate the Wi-Fi source.
The code handles connection drops and resumes automatically on reconnect.

Scan Rates:
 If USE_PROC_NET_WIRELESS=True in wifi_utils.py
 - Connected Mode, actual ~ 24 ms 41 Hz  (at this rate, it won't return Tx Rate (n/a in output))
 - Scan Mode,      actual ~300 ms  3 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

  If USE_PROC_NET_WIRELESS=False in wifi_utils.py
 - Connected Mode, actual ~ 50 ms 20 Hz  (at this rate, it won't return Tx Rate (n/a in output))
 - Scan Mode,      actual ~300 ms  3 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

    If LCD on and USE_PROC_NET_WIRELESS=False in wifi_utils.py  2-3 Hz likely worth the nice graphids
 - Connected Mode, actual ~300 ms  3 Hz (at this rate, it won't return Tx Rate (n/a in output))
 - Scan Mode,      actual ~630 ms  2 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

   If OLED on and USE_PROC_NET_WIRELESS=False in wifi_utils.py -- FLASHES !!!
 - Connected Mode, actual ~200 ms  5 Hz  (at this rate, it won't return Tx Rate (n/a in output))
 - Scan Mode,      actual ~461 ms  3 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call
 TODO do not clear whole OLED screen, but black out values to be updated

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
    update: lis3mdl_calibraton_parameters.py from output of hard_only_calibrate_lis3mdl_test.py

    installs:
    sudo pip3 install adafruit-circuitpython-ssd1305 --break-system-packages
    sudo apt-get install python3-pil
    pip3 install adafruit-circuitpython-lis3mdl --break-system-packages
    pip install python-dotenv --break-system-packages

 TODO measure shell-fi with Yagi-Uda antenna created by Pi Pico as Access Point
"""
import math
import os
import signal
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Literal

import board
import busio
from PIL import Image, ImageDraw
from dotenv import load_dotenv
from gpiozero import Button

import lib.lcd_st7789_utils as lcd
from assets.test_data.mock_rssi_heading_history import mock_rssi_heading_history
from lib.download_file import download_file
from lib.lcd_rssi_polar_utils import display_radar_lcd, display_radar_splash_lcd, CONNECT_RSSI_STRONG, \
    CONNECT_RSSI_WEAK, SCAN_RSSI_STRONG, SCAN_RSSI_WEAK, extract_radar_metrics
from lib.lcd_st7789_utils import create_lcd_display_canvases
from lib.lis3mdl_utils import init_lis3mdl, get_compass_8pt_string, get_compass_heading
from lib.oled_1305_utils import init_oled_display, clear_display_oled, OLED_HEIGHT
from lib.pi_zero_utils import pico_temperature, timeout
from lib.wifi_utils import get_ssid, query_wifi, scan_target_ssid, rssi_to_string, quality_to_string, connect_ssid, \
    remove_ssid


DEBUG = False
USE_MONO_TYPE = False

# TODO test Pi Pico as Access Point
TARGET_SSID = "ABox-PDX"
# TARGET_SSID = "shell-fi"
TARGET_CHANNEL = 11  # Define as None, if don't want target channel
URL_STRING = "http://192.168.4.1/download"
DESTINATION_STRING = "/home/pi-admin/downloads"

LOG_DIRECTORY = "logs_yagi_uda_rssi_heading"

try_connect = False
try_download = False

# Network Signal Lock Thresholds
RSSI_CONNECT_THRESHOLD = -77  # Minimum signal to allow a hardware connection
RSSI_DOWNLOAD_THRESHOLD = -74  # Minimum signal to execute data payload transfer

# TODO for future implementation if needed for performance
RADAR_LUT = []
for angle in range(0, 360, 5):
    rad = math.radians(90.0 - angle)  # Rotation is handled during render
    RADAR_LUT.append((math.cos(rad), math.sin(rad)))

OLED_TEXT_WIDTH = 96  # text on left 96px
CIRCLE_AREA_START_X = OLED_TEXT_WIDTH  # Graphic starts at 96px


class DisplayContextOLED:
    def __init__(self, draw, font, oled, image):
        self.draw = draw
        self.font = font
        self.oled = oled
        self.image = image

    def update_line3_oled(self, text):
        """Clear only the bottom line (20px to 30px) and write new text."""
        # 96 is TEXT_WIDTH_LIMIT
        self.draw.rectangle((0, 20, OLED_TEXT_WIDTH - 1, OLED_HEIGHT - 1), fill=0)
        self.draw.text((0, 20), text, font=self.font, fill=1)
        self.oled.image(self.image)
        self.oled.show()


# Globals
button0_long_press = False
button0_short_press = False
button1_pressed = False
button2_pressed = False
button0_press_time = 0.0
download_count = 0

# Configure Button on GPIO 26 (Physical Pin 37) with a 2.0 second hold threshold
button1 = Button(25, pull_up=True, bounce_time=0.1)
# TODO if lCD fix these definitions
button0 = Button(14, pull_up=True, bounce_time=0.1, hold_time=0.5)  # todo CHANGED FOR LCDm was 26, 14 safe?
# button0 = Button(26, pull_up=True, bounce_time=0.1, hold_time=0.5)  # todo CHANGED FOR LCDm was 26, 14 safe?
button2 = Button(26, pull_up=True, bounce_time=0.1)  # TODO CHANGE THIS TO 26 with LCD
# button2 = Button(14, pull_up=True, bounce_time=0.1)  # TODO CHANGE THIS TO 26 with LCD


def on_button0_pressed():
    global button0_press_time
    button0_press_time = time.time()  # Capture raw baseline time on down-stroke


def on_button0_released():
    global button0_short_press, button0_long_press, button0_press_time

    # Calculate press time
    duration = 0.0
    if button0_press_time > 0.0:
        duration = time.time() - button0_press_time

    # Reset press time for next press
    button0_press_time = 0.0

    if duration >= button0.hold_time:
        button0_long_press = True
        print(f"\n* ====== Long Press Detected ({duration:.4f}s). Reverting to Scan Mode.")
    else:
        button0_short_press = True
        print(f"\n* ------ Short Press Detected ({duration:.4f}s).")


def button1_callback():
    global button1_pressed
    button1_pressed = True
    print("\n[Hardware] Button 1 Activated (GPIO 25)")


def button2_callback():
    global button2_pressed
    button2_pressed = True
    print("\n[Hardware] Button 2 Activated (GPIO 24)")


# Button0: Listen to both edges to measure button press duration
button0.when_pressed = on_button0_pressed
button0.when_released = on_button0_released
print("Button0 Listeners Active (GPIO 26) for Press and Release Edges.")
button1.when_pressed = button1_callback
button2.when_pressed = button2_callback
print("Button1 & 2  Listeners Active (GPIO 25 26) for Press and Release Edges.")


def scan_i2c_bus(i2c_primary):
    print("I2C device Scan...")
    lis3mdl_detected = None
    oled_detected = None

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
                    oled_detected = True
                elif address == 0x1C or address == 0x1E:
                    print(" -> likely LIS3MDL Magnetometer")
                    lis3mdl_detected = address
                else:
                    print(f" -> unknown device")
    except RuntimeError as e:
        print(f"I2C Hardware Error: {e}")
    print("\n")
    return oled_detected, lis3mdl_detected


def init_i2c():
    # Magnetometer has 400K frequency limit, SSD1305 display has 1M, i2c1 is primary I2C on Pi Zero 2 W
    i2c1 = busio.I2C(board.SCL, board.SDA, frequency=400000)
    oled_detected, lis_detected = scan_i2c_bus(i2c1)
    print(f"{oled_detected=} + {lis_detected=}")
    return i2c1, oled_detected, lis_detected


def change_connection(action: Literal["up", "down"]) -> bool:
    change_timeout = 5
    try:
        if action == "down":
            subprocess.run(["sudo", "nmcli", "connection", "down", TARGET_SSID],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=True, timeout=change_timeout)
            return False

        if action == "up":
            # bring up the existing profile
            result = subprocess.run(["sudo", "nmcli", "connection", "up", TARGET_SSID],
                                    capture_output=True, text=True,
                                    check=True, timeout=15)
            if result.returncode == 0:
                return True

    except subprocess.TimeoutExpired:
        print(f"CRITICAL: NetworkManager command timed out ({change_timeout} sec) - possible system hang.")
    except subprocess.CalledProcessError as e:
        print(f"CRITICAL: NetworkManager issue (nmcli): {e}")
    except Exception as e:
        print(f"CRITICAL: Unexpected error in change_connection: {e}")

    # Fallback: Re-connect using the .env password
    print(f"Profile '{TARGET_SSID}' failed. Trying to reconnect...")
    return connect_ssid(TARGET_SSID)


def display_metrics_oled(draw, font, rssi, ssid: str, tx_rate, heading: float, download_count, connected: bool = True):
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
            # If connected, show Mb/s, else print "linked"
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


def display_radar_oled(draw, cadence_fill, heading: float, signal_history, connected):
    """
    Draw a white box with a black radar circle in it.
    Add white directional orientation lines for North, East, South, and West.
    Calculates a solid white polygon tracking signal strength vs compass directions.
    """
    center_x = 112
    center_y = 15
    max_radius = 16

    # Select radar line length bounds based on mode
    strong_bound = CONNECT_RSSI_STRONG if connected else SCAN_RSSI_STRONG
    weak_bound = CONNECT_RSSI_WEAK if connected else SCAN_RSSI_WEAK

    if heading is None:
        heading = 0.0

    # Radar graphics: white background block, black circle mask
    draw.rectangle((96, 0, 127, 31), fill=1)
    draw.ellipse((center_x - max_radius, center_y - max_radius + 1,
                  center_x + max_radius - 1, center_y + max_radius),
                 outline=0, fill=0)

    # Cadence indicator box in text region, for lower right x_box=97, ybox=27
    x_box = 90
    y_box = 0
    dot_size = 3  # for 2px x 2px dot, add one to position
    draw.rectangle((x_box, y_box, x_box + dot_size + 1, y_box + dot_size + 1), fill=1 - int(cadence_fill))  # Outer Box
    draw.rectangle((x_box + 1, y_box + 1, x_box + dot_size, y_box + dot_size), fill=int(cadence_fill))  # Inner dot

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

        # Apply the dynamic bounds
        if saved_rssi < weak_bound:
            saved_rssi = weak_bound
        elif saved_rssi > strong_bound:
            saved_rssi = strong_bound

        # Calculate proportion using dynamic bounds
        proportion = (saved_rssi - weak_bound) / (strong_bound - weak_bound)
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
    # draw.point((center_x, center_y - 1), fill=0)
    # draw.point((center_x, center_y + 1), fill=0)
    # draw.point((center_x - 1, center_y), fill=0)
    # draw.point((center_x + 1, center_y), fill=0)
    # draw.point((center_x, center_y), fill=0)
    draw.point((111, 14), fill=0)
    draw.point((112, 14), fill=0)
    draw.point((111, 15), fill=0)
    draw.point((112, 15), fill=0)


def display_metrics_lcd(lcd, disp_0, disp_1, rssi, ssid: str, tx_rate, heading: float, download_count,
                        connected: bool = True, try_connect: bool = False, try_download: bool = False):
    # SCREEN 0: Connection & Downloads
    disp0_image = Image.new("RGB", (disp_0.width, disp_0.height), "black")

    if try_connect:
        lcd.print_270(text="Trying", pos=(132, 0), image=disp0_image, font=lcd.font0_28pt,
                      color="green")
        lcd.print_270(text="to link", pos=(108, 0), image=disp0_image, font=lcd.font0_28pt,
                      color="green")
    elif not connected and rssi is not None and rssi >= RSSI_CONNECT_THRESHOLD:
        lcd.print_270(text="Con-", pos=(132, 0), image=disp0_image, font=lcd.font0_28pt, color="green")
        lcd.print_270(text="nect?", pos=(108, 0), image=disp0_image, font=lcd.font0_28pt,
                      color="green")
    if try_download:
        lcd.print_270(text="Trying", pos=(70, 0), image=disp0_image, font=lcd.font0_28pt, color="blue")
        lcd.print_270(text="File dl", pos=(44, 0), image=disp0_image, font=lcd.font0_28pt,
                      color="blue")
    elif connected and rssi >= RSSI_DOWNLOAD_THRESHOLD:
        lcd.print_270(text="down", pos=(70, 0), image=disp0_image, font=lcd.font0_28pt, color="blue")
        lcd.print_270(text="load?", pos=(44, 0), image=disp0_image, font=lcd.font0_28pt, color="blue")
    if download_count > 0:
        lcd.print_270(text=f"#{download_count}", pos=(2, 4), image=disp0_image, font=lcd.font0_34pt,
                      color="blue")
    disp_0.ShowImage(disp0_image)

    # SCREEN 1 Signal Metrics & Mode Status
    disp1_image = Image.new("RGB", (disp_1.width, disp_1.height), "black")
    lcd.print_270(text="RSSI:", pos=(132, 0), image=disp1_image, font=lcd.font0_34pt, color="red")
    if rssi is not None:
        lcd.print_270(text=f"{rssi}", pos=(84, 2), image=disp1_image, font=lcd.font0_50pt, color="red")
    else:
        lcd.print_270(text=f"no dBm", pos=(84, 2), image=disp1_image, font=lcd.font0_20pt, color="red")

    if heading is not None:
        lcd.print_270(text=f"{heading}°", pos=(48, 8), image=disp1_image, font=lcd.font0_34pt,
                      color="red")
    else:
        lcd.print_270(text=f"? °", pos=(48, 30), image=disp1_image, font=lcd.font0_34pt, color="red")

    if connected:
        lcd.print_270(text="Wi-Fi", pos=(11, 1), image=disp1_image, font=lcd.font0_33pt, color="green")
        lcd.print_270(text="connected", pos=(0, 3), image=disp1_image, font=lcd.font0_13pt,
                      color="green")
    else:
        lcd.print_270(text="Scan", pos=(5, 0), image=disp1_image, font=lcd.font0_33pt, color="yellow")

    disp_1.ShowImage(disp1_image)


def handle_scan_mode(rssi_heading_history, heading, target_ssid, target_channel, oled_context: DisplayContextOLED, lcd,
                     disp0, disp1):
    """ Scan for rssi metric, connect if sufficient strength and button pressed."""
    global button0_short_press, button1_pressed, button2_pressed

    # Only short press (Button 0) or Button 2 can trigger a connection
    connect_triggered = button0_short_press or button2_pressed

    # Flush all button inputs instantly to clear background states
    button0_short_press = False
    button1_pressed = False

    rssi = None
    scan_timeout = 3
    try:
        with timeout(scan_timeout):
            rssi = scan_target_ssid(interface="wlan0", target_ssid=target_ssid, channel=target_channel)
    except TimeoutError:
        print(f"CRITICAL: scan_target_ssid hung for ({scan_timeout} seconds), nmcli reconnect.")
        subprocess.run(["sudo", "nmcli", "device", "reconnect", "wlan0"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Error during scan: {e}")

    ssid = target_ssid if rssi is not None else None

    if connect_triggered:
        if rssi is not None and rssi >= RSSI_CONNECT_THRESHOLD:
            print(f"\n* Connection Triggered ({rssi} dBm). Trying to connect...")
            if oled_context:
                oled_context.update_line3_oled("trying to connect...")
            if lcd and disp0 and disp1:
                display_metrics_lcd(lcd, disp0, disp1, rssi, ssid, None, heading, download_count,
                                    connected=False, try_connect=True, try_download=False)
            if change_connection("up"):
                rssi_heading_history[:] = [-99.0] * 360
                return True, rssi, ssid
        else:
            print(f"\n* Connection ignored: Signal ({rssi} dBm) below threshold.")

    return False, rssi, ssid


def handle_connected_mode(download_count, heading, target_ssid, url, destination_dir, oled_context: DisplayContextOLED,
                          lcd, disp0, disp1):
    """Get signal metrics, download file if sufficient strength and button pressed."""
    global button0_short_press, button1_pressed, button2_pressed

    # Only short press (Button 0) or Button 1 can trigger a download
    download_triggered = button0_short_press or button1_pressed

    # Flush all button inputs instantly for the next async frame pass
    button0_short_press = False
    button1_pressed = False

    rssi, quality, tx_rate = query_wifi()
    if rssi is None:
        current_ssid = get_ssid()
        if current_ssid != target_ssid:
            return False, None, None, None, None
    else:
        current_ssid = target_ssid

    if download_triggered:
        if rssi is not None and rssi >= RSSI_DOWNLOAD_THRESHOLD:
            print(f"\n* Download Triggered ({rssi} dBm). Executing Transfer...")
            if oled_context:
                oled_context.update_line3_oled("trying download...")
            if lcd and disp0 and disp1:
                display_metrics_lcd(lcd, disp0, disp1, rssi, target_ssid, None, heading, download_count,
                                    connected=True, try_connect=False, try_download=True)
            success, filename = download_file(url, destination_directory=destination_dir)
            if success:
                download_count += 1
                print(f" -> successfully downloaded {destination_dir}/{filename}")
        else:
            print(f"\n* Download aborted: Signal ({rssi} dBm) below threshold.")

    return True, rssi, current_ssid, quality, tx_rate, download_count


def print_metrics(connected, ssid, rssi, quality, tx_rate, heading, download_count):
    """
    Console print metrics
    """
    if connected:
        print(f"** Connected {TARGET_SSID} (channel = {TARGET_CHANNEL}) RSSI: {f'{rssi} dBm' if rssi is not None else 'None'}")
        if rssi is not None:
            quality_string = quality_to_string(quality)
            print(f"Bars:      {rssi_to_string(rssi)}")
            print(f"Link Qual: {f'{quality:>2}/70' if quality is not None else 'n/a'}    {quality_string}")
            print(f"Tx Rate:   {f'{tx_rate:.1f} Mb/s' if tx_rate is not None else 'n/a'}")

            if rssi >= RSSI_DOWNLOAD_THRESHOLD:
                print("-> download possible, use button?")
            else:
                print("-> connected, weak signal")
        else:
            print("Link Qual: n/a")
            print("Tx Rate:   n/a")
            print("-> connected, but signal is lost")

    else:
        print(f"** Scanning {TARGET_SSID} (channel={TARGET_CHANNEL}) RSSI: {f'{rssi} dBm' if rssi is not None else 'None'}")
        print(f"Bars:      {rssi_to_string(rssi)}")

    if heading is not None:
        print(f"Compass Heading: {heading:.0f}° {get_compass_8pt_string(heading)}")
    else:
        print("Compass Heading: ???° - no Magnetometer")


def write_history_to_csv(history):
    log_dir = LOG_DIRECTORY
    os.makedirs(log_dir, exist_ok=True)
    filename = os.path.join(log_dir, f"yagi_uda_rssi_heading_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
    with open(filename, "w") as f:
        f.write("degree,rssi\n")
        for i, val in enumerate(history):
            f.write(f"{i},{val}\n")
    print(f"-> Saved scan data to {filename}")


def main():
    global button0_short_press, button0_long_press, download_count

    print("Start Wi-Fi Signal & Antenna Tracking...\n")
    i2c1, oled_detected, lis3mdl_detected = init_i2c()

    lis3mdl = None
    if lis3mdl_detected:
        lis3mdl = init_lis3mdl(i2c1)

    # TODO switching displays by hardcoding
    lcd_detected = False
    if not oled_detected:
        lcd_detected = True
    # TODO FIX EASY WAY TO SWAP OLED TO LCD !!!!!!!!!!!!!!!!!!!!!!!!!!!!
    else:
        disp_0 = None
        disp_1 = None
        disp_2 = None

    # Initialize OLED DisplayContext
    oled_context = None
    if oled_detected:
        oled_display, draw, font, image = init_oled_display(i2c1, use_mono_type=USE_MONO_TYPE)
        oled_context = DisplayContextOLED(draw, font, oled_display, image)

    # Initialize 3 LCD displays, splash radiant ether image
    if lcd_detected:
        disp_0, disp_1, disp_2 = create_lcd_display_canvases()

    LOG_DIRECTORY = "logs_yagi_uda_rssi_heading"

    print(f"\nScanning SSID = {TARGET_SSID}, channel = {TARGET_CHANNEL}")
    print(f"Fetch from: {URL_STRING} and then saved to: {DESTINATION_STRING}")
    print(f"Plots on Pi Zero are logged to: {LOG_DIRECTORY}\n")

    print("Display being used:")
    print(f"{lcd_detected=}")
    print(f"{oled_detected=}")

    scan_mode = True
    connected_mode = False
    load_dotenv()

    # clear signal history on all 360 discrete degree headings
    rssi_heading_history = [-99.0] * 360

    ssid, rssi, quality, tx_rate = None, None, None, None

    try:
        duration = 0.0
        temp_duration = 0.0
        cadence_fill = False
        start_time = time.time()
        last_csv_write = time.time()
        pi_celsius = pico_temperature() or 0.0

        loop_counter = 0
        while True:
            loop_counter += 1
            cadence_fill = not cadence_fill
            start_loop = time.time()

            # write CSV of heading, rssi strength for entire 360 degrees, every 61 seconds
            if start_loop - last_csv_write > 61:
                write_history_to_csv(rssi_heading_history)
                last_csv_write = time.time()

            temp_duration += duration
            if temp_duration > 60.0:
                print(f"Updated Temperature (sys call) after): {temp_duration:.1f} sec")
                pi_celsius = pico_temperature()
                temp_duration = 0.0
                if pi_celsius and pi_celsius > 60.0:
                    print(f"Warning: ** High Temp: {pi_celsius:.1f}°C")

            # On long press, disconnect and revert to scanning, reset radar history
            if button0_long_press:
                if connected_mode:
                    change_connection("down")
                    rssi_heading_history = [-99.0] * 360
                connected_mode = False
                button0_long_press = False

            # Record RSSI at integer heading angles
            heading = get_compass_heading(lis3mdl)

            # Logic for connected or scanning
            if connected_mode:
                connected_mode, rssi, ssid, quality, tx_rate, download_count = handle_connected_mode(
                    download_count, heading, TARGET_SSID, URL_STRING, DESTINATION_STRING, oled_context,
                    lcd, disp_0,
                    disp_1)
            else:
                connected_mode, rssi, ssid = handle_scan_mode(rssi_heading_history, heading, TARGET_SSID,
                                                              TARGET_CHANNEL, oled_context,
                                                              lcd, disp_0, disp_1)
                quality, tx_rate = None, None

            if rssi:
                if heading:
                    idx = int(heading) % 360
                    rssi_heading_history[idx] = rssi
                # else:
                #     rssi_heading_history[:] = [rssi] * 360

            # Print and display metrics
            print_metrics(connected_mode, ssid, rssi, quality, tx_rate, heading, download_count)

            # Display output
            if oled_detected:
                clear_display_oled(oled_display, draw, image)
                display_metrics_oled(draw, font, rssi, ssid, tx_rate, heading, download_count, connected_mode)
                display_radar_oled(draw, cadence_fill, heading or 0.0, rssi_heading_history, connected_mode)
                oled_display.image(image)
                oled_display.show()

            if lcd_detected:
                display_metrics_lcd(lcd, disp_0, disp_1, rssi, ssid, tx_rate, heading, download_count, connected_mode)
                disp2_image = Image.new("RGB", (disp_2.width, disp_2.height), "black")
                disp2_draw = ImageDraw.Draw(disp2_image)
                # display_radar_lcd(disp2_draw, cadence_fill, heading, rssi_heading_history, connected_mode)
                peak_rssi, peak_degree, peak_cluster, has_valid_history = extract_radar_metrics(rssi_heading_history)
                display_radar_lcd(
                    disp2_draw,
                    cadence_fill=cadence_fill,
                    heading=heading,
                    signal_history=rssi_heading_history,
                    connected=connected_mode,
                    peak_degree=peak_degree,
                    peak_rssi=peak_rssi,
                    peak_cluster=peak_cluster
                )
                disp_2.ShowImage(disp2_image)

            # Print update frequency and period
            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time
            print(f"Pi Zero 2W temp: {pi_celsius:.1f}°C")
            print(f"Updates: {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            # # Dynamic sleep, sleep longer when Wi-Fi out of range
            # if connected_mode:
            #     time.sleep(0.02)  # Connected Mode, actual ~85ms 12 Hz
            # elif rssi is not None:
            #     time.sleep(0.01)  # Scan Mode, actual ~46ms 22 Hz
            # else:
            #     time.sleep(0.04)  # Out of range fallback, actual ~85ms 12 Hz

    except KeyboardInterrupt:
        print("\nEnded Tracking (^c).")

    finally:
        # remove shell-fi on normal exit, crashes, or KeyboardInterrupt
        if TARGET_SSID == "shell-fi":
            remove_ssid(TARGET_SSID)

        if lcd_detected:
            black_0 = Image.new("RGB", (disp_0.width, disp_0.height), "black")
            disp_0.ShowImage(black_0)
            black_1 = Image.new("RGB", (disp_1.width, disp_1.height), "black")
            disp_1.ShowImage(black_1)
            display_radar_splash_lcd(disp_2)
            disp_0.module_exit()
            disp_1.module_exit()
            disp_2.module_exit()

        if oled_detected:
            clear_display_oled(oled_display, draw, image)


if __name__ == "__main__":
    main()
