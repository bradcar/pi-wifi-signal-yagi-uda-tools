# pi_yagi_uda.py
"""
On Raspberry Pi Zero 2 W, the code repeatedly measures the RSSI, Link Quality,
and RX Bit Rate of the currently targeted network on interface wlan0.
When connected to a Yagi-Uda Antenna and an Magnetometer we can use this to locate the Wi-Fi source.
The code handles connection drops and resumes automatically on reconnect.

Scan Rates:
 If USE_PROC_NET_WIRELESS=True in wifi_utils.py
 - Connected Mode, actual ~ 24 ms 41 Hz  (at this rate, it won't return RX Rate (n/a in output))
 - Scan Mode,      actual ~300 ms  3 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

  If USE_PROC_NET_WIRELESS=False in wifi_utils.py
 - Connected Mode, actual ~ 50 ms 20 Hz
 - Scan Mode,      actual ~300 ms  3 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

    If LCD on and USE_PROC_NET_WIRELESS=False in wifi_utils.py  2-3 Hz likely worth the nice graphids
 - Connected Mode, actual ~300 ms  3 Hz (at this rate, it won't return RX Rate (n/a in output))
 - Scan Mode,      actual ~630 ms  2 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

   If OLED on and USE_PROC_NET_WIRELESS=False in wifi_utils.py -- FLASHES !!!
 - Connected Mode, actual ~200 ms  5 Hz  (at this rate, it won't return RX Rate (n/a in output))
 - Scan Mode,      actual ~461 ms  3 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call
 TODO consider do not clear whole OLED screen, but black out values to be updated

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

Metrics Data Structure:
    The state is maintained via `metrics = types.SimpleNamespace(...)` containing:
        - is_connected (bool): Active hardware link status to TARGET_SSID.
        - rssi (int/None): RSSI in dBm.
        - quality (int/None): Link quality percentage (0-100%).
        - rx_rate (float/None): Receiver bit rate in Mbps.
        - tx_rate (float/None): Transmitter bit rate in Mbps.
        - bssid (str/None): BSSID (MAC) address of the connected Access Point.
        - heading (float): Current magnetometer compass direction (0.0 - 359.9°).
        - is_new_rssi (bool): Event flag indicating an unconsumed RSSI update.
        - rssi_heading_history (list): 360-element array mapping degrees to last known RSSI value.
        - update_period (float/None): Async duration in seconds of metrics update_period

    Data Structure Rules:
        1. ALL reads and writes to metrics when USE_ASYNCH_METRICS must be protected with metrics_lock.
        2. Connected Mode Lifecycle (is_connected == True):
            - BACKGROUND THREAD: Owns exclusive mutation rights for metrics
              (rssi, quality, rx_rate, tx_rate, bssid, is_new_rssi). It polls the hardware interface
              via `handle_connected_mode()` and flushes state safely down to the metrics namespace.
            - MAIN THREAD: operates strictly in READ-ONLY pass-through mode for network metrics.
              It handles button modes and display.
            - EXCEPTION: If a hardware interrupt occurs (or Button0 long_press), the Main Thread
              can clear `is_connected` and clean up tracking histories.
        3. Scan Mode (is_connected == False):
            - BACKGROUND THREAD: Becomes idle/throttled. It safely halts writing to metrics SimpleNamespace.
            - MAIN THREAD: Regains READ/WRITE ownership. It directly invokes handle_scan_mode()
              to update metrics, hand buttons, and display results.


Requirements (beyond normal i2c):
    update: lis3mdl_calibraton_parameters.py from output of hard_only_calibrate_lis3mdl_test.py

    installs:
    sudo pip3 install adafruit-circuitpython-ssd1305 --break-system-packages
    sudo apt-get install python3-pil
    pip3 install adafruit-circuitpython-lis3mdl --break-system-packages
    pip install python-dotenv --break-system-packages

TODO measure shell-fi with Yagi-Uda antenna created by Pi Pico as Access Point
TODO uncomment logging code to Pi Zero flash
TODO uncomment saving Actual RSSI to heading, instead of fake testing code

"""
import os
import subprocess
import time
import threading
import types
from datetime import datetime
from typing import Literal

import board
import busio
from PIL import Image, ImageDraw
from dotenv import load_dotenv
from gpiozero import Button

import lib.lcd_st7789_utils as lcd
from lib.download_file_utils import download_file
from lib.fake_testing_utils import fake_heading_sweep, fake_rssi_history_fill
from lib.lcd_rssi_radar_utils import display_radar_lcd, extract_radar_metrics, arrow_annotation, rotation_to_peak
from lib.lcd_st7789_utils import create_lcd_display_canvases, display_2_splash_lcd
from lib.lis3mdl_utils import init_lis3mdl, get_compass_8pt_string, get_compass_heading
from lib.oled_1305_utils import init_oled_display, clear_display_oled, OLED_HEIGHT
from lib.oled_rssi_radar_utils import display_radar_oled
from lib.pi_zero_utils import pico_temperature, timeout
from lib.wifi_utils import get_ssid, query_wifi, scan_target_ssid, rssi_to_string, quality_to_string, connect_ssid, \
    remove_ssid

DEBUG = False
USE_MONO_TYPE = False
USE_ASYNC_METRICS = False
metrics_lock = threading.Lock() # Protects SimpleNamespace data transitions

TARGET_SSID = "ABox-PDX"
# TODO #1 test Pi Pico as Access Point, make sure on channel=11 !
# TODO #2 Try shell-fi with static-IP for faster connection wifi_utils.py
# TARGET_SSID = "shell-fi"  #
TARGET_CHANNEL = 11  # Set to None, if not target channel

URL_STRING = "http://192.168.4.1/download"
DESTINATION_STRING = "/home/pi-admin/downloads"
LOG_DIRECTORY = "logs_yagi_uda_rssi_heading"

try_connect = False
try_download = False

# Network Signal Lock Thresholds
RSSI_CONNECT_THRESHOLD = -80  # Minimum signal to allow a hardware connection
RSSI_DOWNLOAD_THRESHOLD = -75  # Minimum signal to execute data payload transfer

OLED_TEXT_WIDTH = 96  # text on left 96px
OLED_CIRCLE_AREA_START_X = OLED_TEXT_WIDTH  # Graphic starts at 96px


class DisplayContextOLED:
    def __init__(self, draw, font, oled, image):
        self.draw = draw
        self.font = font
        self.oled = oled
        self.image = image

    def update_line3_oled(self, text):
        """Clear only the bottom line (20px to 30px) and write new text."""
        # OLED_TEXT_WIDTH_LIMIT extends to 96px
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
# Button Definitions for OLED Display
# TODO TOGGLE FOR OLED
# button0 = Button(26, pull_up=True, bounce_time=0.1, hold_time=0.5)  # todo OLED currently solder to 26
# button2 = Button(6, pull_up=True, bounce_time=0.1)  # # todo OLED currently solder to 26
# Button Definitions for LCD Display
# TODO TOGGLE FOR LCD
button0 = Button(6, pull_up=True, bounce_time=0.1, hold_time=0.5)  # todo resolder OLED to gpio6 p31
button2 = Button(26, pull_up=True, bounce_time=0.1)  # todo resolder OLED to gpio6 p31


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
print("Button1 & Button2  Listeners Active (GPIO 25 & GPIO 26) for Presses.")


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
    # i2c1 is primary I2C on Pi Zero, Magnetometer has 400K frequency limit, SSD1305 display has 1M, can't set in python
    i2c1 = busio.I2C(board.SCL, board.SDA)
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
            # Call connect directly
            return connect_ssid(TARGET_SSID)

    except subprocess.TimeoutExpired:
        print(f"CRITICAL: NetworkManager command timed out ({change_timeout} sec) - possible system hang.")
    except subprocess.CalledProcessError as e:
        print(f"CRITICAL: NetworkManager issue (nmcli): {e}")
    except Exception as e:
        print(f"CRITICAL: Unexpected error in change_connection: {e}")

    # Fallback: Re-connect using the .env password
    print(f"Profile '{TARGET_SSID}' failed. Trying to reconnect...")
    return connect_ssid(TARGET_SSID)


def display_metrics_oled(draw, font, rssi, ssid: str, rx_rate, heading: float, download_count, connected: bool = True):
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
            rate_str = f"{rx_rate:.0f} mb/s" if rx_rate is not None else "linked"
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


def display_0_metrics_lcd(lcd, disp_0, rssi, download_count, connected, try_connect):
    """" Screen 0: Mode Status"""
    if not try_connect and rssi is None and download_count == 0:
        return

    disp0_image = Image.new("RGB", (disp_0.width, disp_0.height), "black")
    if try_connect:
        lcd.print_270(text="Trying", pos=(132, 0), image=disp0_image, font=lcd.font0_28pt, color="green")
        lcd.print_270(text="to link", pos=(108, 0), image=disp0_image, font=lcd.font0_28pt, color="green")
        lcd.print_270(text="Pause", pos=(108 - 26, 0), image=disp0_image, font=lcd.font0_24pt, color="green")

    elif not connected and rssi is not None and rssi >= RSSI_CONNECT_THRESHOLD:
        lcd.print_270(text="Con-", pos=(132, 0), image=disp0_image, font=lcd.font0_28pt, color="green")
        lcd.print_270(text="nect?", pos=(108, 0), image=disp0_image, font=lcd.font0_28pt, color="green")

    elif connected and rssi is not None and rssi >= RSSI_DOWNLOAD_THRESHOLD:
        lcd.print_270(text="down", pos=(70, 0), image=disp0_image, font=lcd.font0_28pt, color="blue")
        lcd.print_270(text="load?", pos=(44, 0), image=disp0_image, font=lcd.font0_28pt, color="blue")

    if download_count > 0:
        lcd.print_270(text=f"#{download_count}", pos=(2, 4), image=disp0_image, font=lcd.font0_34pt, color="blue")
    disp_0.ShowImage(disp0_image)


def display_0_trying_download_lcd(lcd, disp_0, download_count):
    """ Display 'trying download' on lcd screen 0"""
    disp0_image = Image.new("RGB", (disp_0.width, disp_0.height), "black")
    lcd.print_270(text="Trying", pos=(70, 0), image=disp0_image, font=lcd.font0_28pt, color="blue")
    lcd.print_270(text="File dl", pos=(44, 0), image=disp0_image, font=lcd.font0_28pt, color="blue")
    lcd.print_270(text="Pause", pos=(44 - 26, 0), image=disp0_image, font=lcd.font0_24pt, color="blue")
    disp_0.ShowImage(disp0_image)


def display_1_metrics_lcd(lcd, disp_1, rssi, compass_heading, shortest_angle, connected: bool):
    """ Screen 1 Signal Metrics"""
    disp1_image = Image.new("RGB", (disp_1.width, disp_1.height), "black")
    disp1_draw = ImageDraw.Draw(disp1_image)

    heading_text = "RSSI:"
    metric_color = "yellow"
    # show RSSI & heading with orange font if +/- 30°, label as "PEAK" within +/- 15 degrees and red font
    if shortest_angle is not None and abs(shortest_angle) < 30:
        metric_color = "orange"
        if abs(shortest_angle) < 15:
            heading_text = "PEAK"
            metric_color = "red"

    lcd.print_270(text=heading_text, pos=(132, 0), image=disp1_image, font=lcd.font0_34pt, color=metric_color)
    if rssi is not None:
        lcd.print_270(text=f"{rssi}", pos=(84, 2), image=disp1_image, font=lcd.font0_50pt, color=metric_color)
    else:
        lcd.print_270(text=f"no dBm", pos=(84, 2), image=disp1_image, font=lcd.font0_20pt, color="yellow")

    if compass_heading is not None:
        indent = 3 - (1 if compass_heading < 10 else (2 if compass_heading < 100 else 3))
        lcd.print_270(text=f"{compass_heading:.0f}°", pos=(49, 8 + (9 * indent)), image=disp1_image,
                      font=lcd.font0_34pt,
                      color=metric_color)

        # Arrows to indicate rotation direction to align with the peak rssi
        arrow_annotation(disp1_draw, shortest_angle, left_arrow_position=(41, 0),
                         right_arrow_position=(41, 80 - 17))
    else:
        lcd.print_270(text=f"? °", pos=(48, 30), image=disp1_image, font=lcd.font0_34pt, color="yellow")

    if connected:
        lcd.print_270(text="Wi-Fi", pos=(11, 1), image=disp1_image, font=lcd.font0_33pt, color="green")
        lcd.print_270(text="connected", pos=(0, 3), image=disp1_image, font=lcd.font0_13pt, color="green")
    else:
        lcd.print_270(text="Scan", pos=(5, 0), image=disp1_image, font=lcd.font0_33pt, color="yellow")

    disp_1.ShowImage(disp1_image)


def annotate_display_2_rotate_to_peak(disp2_image, disp2_draw, heading, shortest_angle):
    """ """
    disp2_draw.rectangle([212, 91, 240, 154], fill="black")
    indent = 3 - (1 if heading < 10 else (2 if heading < 100 else 3))
    lcd.print_270(text=f"{heading:.0f}°", pos=(214, 92 + (indent * 10)), image=disp2_image,
                  font=lcd.font0_28pt, color="yellow")

    # Arrows to indicate rotation direction between current heading the peak rssi
    arrow_annotation(disp2_draw, shortest_angle, left_arrow_position=(224, 91 - 20 - 17),
                     right_arrow_position=(224, 154 + 20))


def handle_scan_mode(rssi_heading_history, heading, target_ssid, target_channel, oled_context: DisplayContextOLED, lcd,
                     disp0, disp1):
    """ Scan for rssi metric, connect if sufficient strength and button pressed. """
    global button0_short_press, button1_pressed, button2_pressed

    # Only short press (Button 0) or Button 2 can trigger connection, reset buttons after status noted
    connect_triggered = button0_short_press or button2_pressed
    button0_short_press = False
    button2_pressed = False

    rssi = None
    scan_timeout = 3
    is_connected = False
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
            print(f"\n* Connection Triggered ({rssi} dBm). Trying to connect/link...")
            if oled_context:
                oled_context.update_line3_oled("trying to connect...")
            if lcd and disp0 and disp1:
                display_0_metrics_lcd(lcd, disp0, rssi, download_count, connected=False, try_connect=True)

            if change_connection("up"):
                is_connected = True
                time.sleep(0.25)
                _, _, _, _, bssid, _ = query_wifi()

                if bssid:
                    print(f" SUCCESS: Connected to BSSID: {bssid} with SSID: {ssid}\n")
                else:
                    print(" SUCCESS: Connected to unknown BSSID? with SSID: {ssid}\n")

                # lists are mutatable
                rssi_heading_history[:] = [-99.0] * 360
                return is_connected, rssi, ssid
        else:
            print(f"\n* Connection ignored: Signal ({rssi} dBm) below threshold.")

    return is_connected, rssi, ssid


def handle_connected_mode(download_count, heading, target_ssid, url, destination_dir, oled_context,
                          lcd, disp0, disp1):
    """Get signal metrics, download file if sufficient strength and button pressed."""
    global button0_short_press, button1_pressed, button2_pressed

    is_connected = True

    # Only short press (Button 0) or Button 1 can trigger a download, reset buttons after status noted
    download_triggered = button0_short_press or button1_pressed
    button0_short_press = False
    button1_pressed = False

    rssi, quality, rx_rate, tx_rate, bssid, is_new_rssi = query_wifi()
    if rssi is None:
        # if no rssi check if connection dropped
        current_ssid = get_ssid()

        # Call connection dropped when HW switched networks or if middle of switching connections
        if current_ssid != target_ssid and current_ssid not in [None, "", "wlan0 essid unknown"]:
            is_connected = False
            return is_connected, None, None, None, None, download_count, None, False
        # allow temporary drop, check next scan
        current_ssid = target_ssid

    else:
        # confirm that RSSI seen and current ssid is the target ssid
        current_ssid = target_ssid

    if download_triggered:
        if rssi is not None and rssi >= RSSI_DOWNLOAD_THRESHOLD:
            print(f"\n* Download Triggered ({rssi} dBm). Executing Transfer...")
            if oled_context:
                oled_context.update_line3_oled("trying download...")
            if lcd and disp0 and disp1:
                display_0_trying_download_lcd(lcd, disp0, download_count)

            success, filename = download_file(url, destination_dir)
            if success:
                download_count += 1
                print(f" -> successfully downloaded {destination_dir}/{filename}")
        else:
            print(f"\n* Download aborted: Signal ({rssi} dBm) below threshold.")

    return is_connected, rssi, current_ssid, quality, rx_rate, download_count, bssid, is_new_rssi


def wifi_connected_thread_worker(metrics, lis3mdl, oled_context, lcd, disp_0, disp_1):
    """Background worker thread that runs exclusively when connected."""
    global download_count
    print("[Thread] Background connected worker loop started.")

    while USE_ASYNC_METRICS:
        current_heading = get_compass_heading(lis3mdl)
        with metrics_lock:
            active = metrics.is_connected

        if not active:
            time.sleep(0.01)  # 10 ms Throttle down resource usage when scanning
            continue

        # Get network results outside the critical lock section
        is_connected, rssi, ssid, quality, rx_rate, dowload_count, bssid, is_new_rssi = handle_connected_mode(
            download_count, current_heading, TARGET_SSID, URL_STRING, DESTINATION_STRING,
            oled_context, lcd, disp_0, disp_1
        )

        # Safely write metrics into the shared namespace
        with metrics_lock:
            download_count = dowload_count
            metrics.is_connected = is_connected
            metrics.heading = current_heading
            metrics.rssi = rssi
            metrics.quality = quality
            metrics.rx_rate = rx_rate
            metrics.bssid = bssid
            metrics.is_new_rssi = is_new_rssi
            update_rssi_heading_history(metrics)

            if not metrics.is_connected:
                print("[Thread] Connection dropped. Background loop backgrounding.")

        time.sleep(0.01)


def update_rssi_heading_history(metrics):
    if metrics.heading is not None:
        metrics.rssi_heading_history[int(metrics.heading) % 360] = metrics.rssi
    # # show circular rssi if no known heading
    # else:
    #     metrics.rssi_heading_history[:] = [rssi] * 360
    else:
        # TODO REMOVE this testing-only ELSE CLAUSE: which make Random index if no magnetometer
        if metrics.rssi is not None:
            metrics.rssi_heading_history = fake_rssi_history_fill(metrics.rssi,
                                                                  metrics.rssi_heading_history)


def print_metrics(connected, ssid, rssi, quality, rx_rate, heading, download_count):
    """Print metrics to Console"""
    if connected:
        print(
            f"** Connected {TARGET_SSID} (channel = {TARGET_CHANNEL}) RSSI: {f'{rssi} dBm' if rssi is not None else 'None'}")
        if rssi is not None:
            quality_string = quality_to_string(quality)
            print(f"Bars:    {rssi_to_string(rssi)}")
            print(f"Quality: {f'{quality:>3}%' if quality is not None else 'n/a'}  {quality_string}")
            print(f"RX Rate: {f'{rx_rate:.1f} Mb/s' if rx_rate is not None else 'n/a'}")

            if rssi >= RSSI_DOWNLOAD_THRESHOLD:
                print("-> download possible, trigger with button1")
            else:
                print("-> connected, weak signal")
        else:
            print("Quality: n/a")
            print("RX Rate: n/a")
            print("-> connected, but signal is lost")

    else:
        print(
            f"** Scanning {TARGET_SSID} (channel={TARGET_CHANNEL}) RSSI: {f'{rssi} dBm' if rssi is not None else 'None'}")
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
        disp_0, disp_1, disp_2 = create_lcd_display_canvases(splash_file_name="radiant-ether-098.jpg")

    print(f"\nScanning SSID = {TARGET_SSID}, channel = {TARGET_CHANNEL}")
    print(f"Fetch from: {URL_STRING} and then saved to: {DESTINATION_STRING}")
    print(f"Plots on Pi Zero are logged to: {LOG_DIRECTORY}\n")

    print("Display being used:")
    print(f"{lcd_detected=}")
    print(f"{oled_detected=}")

    scan_mode = True
    load_dotenv()

    metrics = types.SimpleNamespace(
        is_connected=False,
        rssi=None,
        quality=None,
        rx_rate=None,
        tx_rate=None,
        bssid=None,
        heading=0.0,
        rssi_heading_history=[-99.0] * 360,
        update_period=None
    )

    # Local variables
    ssid = None

    try:
        cadence_fill = False
        start_time = time.time()
        last_csv_write = time.time()
        pi_celsius = pico_temperature() or 0.0
        duration = 0.0
        temp_duration = 0.0
        metrics.heading = get_compass_heading(lis3mdl)

        # todo remove fake sweep initialization
        sweep_degree = 290

        loop_counter = 0
        while True:
            loop_counter += 1
            cadence_fill = not cadence_fill
            start_loop = time.time()

            # write CSV of heading, rssi strength for entire 360 degrees, every 61 seconds
            # TODO ADD BACK LOGGING CSV TO FLASH -  **************** LOGGING DISABLED *****************
            # if start_loop - last_csv_write > 61:
            #     write_history_to_csv(rssi_heading_history)
            #     last_csv_write = time.time()

            temp_duration += duration
            if temp_duration > 60.0:
                print(f"Updated Temperature (sys call) after): {temp_duration:.1f} sec")
                pi_celsius = pico_temperature()
                temp_duration = 0.0
                if pi_celsius and pi_celsius > 60.0:
                    print(f"Warning: ** High Temp: {pi_celsius:.1f}°C")

            # On long press, disconnect and revert to scanning, reset radar history
            if button0_long_press:
                button0_long_press = False
                if metrics.is_connected:
                    change_connection("down")
                    metrics.rssi_heading_history = [-99.0] * 360
                metrics.is_connected = False

            if not metrics.is_connected:
                # Scan mode - Update RSSI metric
                metrics.quality, metrics.rx_rate = None, None
                is_new_rssi = True
                metrics.is_connected, metrics.rssi, ssid = handle_scan_mode(metrics.rssi_heading_history,
                                                                            metrics.heading, TARGET_SSID,
                                                                            TARGET_CHANNEL, oled_context,
                                                                            lcd, disp_0, disp_1)
            else:
                # CONNECTED MODES - Synchronous & Asynchronous
                if not USE_ASYNC_METRICS:
                    # Synchronous Connected mode - Update full metrics, depends on iw or /net/proc/wireless probing
                    metrics.is_connected, metrics.rssi, ssid, metrics.quality, metrics.rx_rate, download_count, metrics.bssid, is_new_rssi = handle_connected_mode(
                        download_count, metrics.heading, TARGET_SSID, URL_STRING, DESTINATION_STRING, oled_context,
                        lcd, disp_0,
                        disp_1)
                else:
                    print("USE ASYNC_METRICS - ******* unimplemented CODE !!!!!!!!!!!!!")
                    break

            # Get current heading, then update RSSI strength at that heading in rssi_heading_history
            metrics.heading = get_compass_heading(lis3mdl)
            if is_new_rssi:
                update_rssi_heading_history(metrics)

            # todo remove fake sweeping
            if metrics.heading is None:
                metrics.heading, sweep_degree = fake_heading_sweep(sweep_degree)

            # Print metrics to console
            print_metrics(metrics.is_connected, ssid, metrics.rssi, metrics.quality, metrics.rx_rate, metrics.heading,
                          download_count)

            # Display metrics on OLED screen
            if oled_detected:
                clear_display_oled(oled_display, draw, image)
                display_metrics_oled(draw, font, metrics.rssi, ssid, metrics.rx_rate, metrics.heading, download_count,
                                     metrics.is_connected)
                display_radar_oled(draw, cadence_fill, metrics.heading or 0.0, metrics.rssi_heading_history,
                                   metrics.is_connected)
                oled_display.image(image)
                oled_display.show()

            # Display metrics on LCD screens
            if lcd_detected:
                peak_rssi, peak_degree, peak_cluster, has_valid_history = extract_radar_metrics(
                    metrics.rssi_heading_history)
                shortest_angle = rotation_to_peak(metrics.heading, peak_degree)

                display_0_metrics_lcd(lcd, disp_0, metrics.rssi, download_count, metrics.is_connected,
                                      try_connect=False)
                display_1_metrics_lcd(lcd, disp_1, metrics.rssi, metrics.heading, shortest_angle, metrics.is_connected)

                disp2_image = Image.new("RGB", (disp_2.width, disp_2.height), "black")
                disp2_draw = ImageDraw.Draw(disp2_image)

                display_radar_lcd(
                    disp2_draw, cadence_fill, metrics.heading, metrics.rssi_heading_history, metrics.is_connected,
                    peak_degree, peak_rssi,
                    peak_cluster
                )

                # Annotate radar with heading & peak arrows, seems unneeded enough visual cues with peak indicators
                # annotate_display_2_rotate_to_peak(disp2_image, disp2_draw, metrics.heading, shortest_angle)
                disp_2.ShowImage(disp2_image)

            # Print update frequency and period to console
            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time
            print(f"Pi Zero 2W temp: {pi_celsius:.1f}°C")
            print(f"Display Updates: {duration * 1000:>7.1f} msec, {1.0 / duration:.0f} Hz")
            if not metrics.is_connected or not USE_ASYNC_METRICS:
                metrics.update_period = duration
            print(f"Radar Updates:   {metrics.update_period * 1000:>7.1f} msec, {1.0 / metrics.update_period:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    except KeyboardInterrupt:
        print("\nEnded Tracking (^c).")

    finally:
        # remove shell-fi on exit
        if TARGET_SSID == "shell-fi":
            remove_ssid(TARGET_SSID)

        if lcd_detected:
            black_0 = Image.new("RGB", (disp_0.width, disp_0.height), "black")
            disp_0.ShowImage(black_0)
            black_1 = Image.new("RGB", (disp_1.width, disp_1.height), "black")
            disp_1.ShowImage(black_1)
            display_2_splash_lcd(disp_2, splash_image_file="radiant-ether-098.jpg")
            disp_0.module_exit()
            disp_1.module_exit()
            disp_2.module_exit()

        if oled_detected:
            clear_display_oled(oled_display, draw, image)


if __name__ == "__main__":
    main()
