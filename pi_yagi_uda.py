# pi_yagi_uda.py
"""
On Raspberry Pi Zero 2 W, the code repeatedly measures the RSSI, Link Quality,
and Tx Bit Rate of the currently targeted network on interface wlan0.
pyro

if the targeted network is connected it can download the data file.
* this is shown in the OLED SSD display as:
* "SSID = target-net"

If the targeted network is not connected, it uses a lighter weight probe which scans all available networks looking for the targeted network.
* this is shown in the OLED SSD display as:
* "ssid   target-net"
When connected to a Yagi-Uda Antenna and an IMU we can use this to locate the WiFi source.

It prints the results to std out and an OLED display.
It graphically shows the signal strength at a compass direction.
This is also shown graphically in a small radar screen graphic.
It gracefully handles total connection drops and resumes automatically on reconnect.

1. Starts in Probe Mode
   a. If signal ≥ RSSI_CONNECT_THRESHOLD, a short press triggers Connected Mode (nmcli up).
2. In Connection Mode
   a. If signal ≥ RSSI_DOWNLOAD_THRESHOLD, a short press starts download.
   b. A long press returns to Probe Mode (nmcli down)

short press >0.1 sec
long press >1.5 sec

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
 TODO must edit config.txt

    # on Mac edit microSD's config.txt
    # enable second i2c port (i2c0)
    # dtparam=i2c_vc=on
    # DO NOT load overlays for detected cameras (=1 is on)
    # camera_auto_detect=0

"""
import math
import time
import subprocess
from datetime import datetime

# Testing display had to use: import adafruit_ssd1306
import adafruit_ssd1305

import board
import busio
from PIL import Image, ImageDraw, ImageFont
from adafruit_bno08x import BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR
from adafruit_bno08x.i2c import BNO08X_I2C
from gpiozero import Button

# Network signal tracking dependencies
from pi_wifi_rssi_quality_txrate import get_ssid, probe_target_ssid, query_wifi, print_metrics

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
SSD_HEIGHT = 32  # TODO uncomment this when get ssd 1305 bonnet
#  SSD_HEIGHT = 64  # Set to 64 for SSD1309
TEXT_WIDTH_LIMIT = 96  # text on left 96px
CIRCLE_AREA_START_X = TEXT_WIDTH_LIMIT  # Graphic starts at 96px

# Globals
long_press = False
short_press = False
button_press_time = 0.0
download_count = 0

# Configure Button on GPIO 26 (Physical Pin 37) with a 2.0 second hold threshold
button0 = Button(26, pull_up=True, bounce_time=0.1, hold_time=1.0)


def on_button_pressed():
    global button_press_time
    button_press_time = time.time()  # Capture raw baseline time on down-stroke


def on_button_released():
    global short_press, long_press, button_press_time

    # Calculate press time
    if button_press_time > 0.0:
        duration = time.time() - button_press_time
    else:
        duration = 0.0  # Fallback safety case

    # Reset press time
    button_press_time = 0.0

    if duration >= button0.hold_time:
        long_press = True
        print(f"\n* ====== Long Press Detected ({duration:.4f}s). Reverting to Probe Mode.")
    else:
        short_press = True
        print(f"\n* ------ Short Press Detected ({duration:.4f}s).")


# Listen to both edges to manage our independent software timer cleanly
button0.when_pressed = on_button_pressed
button0.when_released = on_button_released
print("Button0 Listeners Active (GPIO 26) for Press and Release Edges.")


def scan_i2c_bus(i2c_primary, i2c_secondary):
    print("I2C device Scan...")
    bno_detected = None
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
                elif address == 0x4B or address == 0x4A:
                    print(" -> likely BNO086 IMU")
                    bno_detected = address
                else:
                    print(f" -> unknown device {hex(address)}")
    except RuntimeError as e:
        print(f"I2C Hardware Error: {e}")

        # Check Secondary I2C0 bus
    if i2c_secondary is None:
        print("\nSkipping I2C0 scan: Secondary bus not available.")
    else:
        devices0 = i2c_secondary.scan()
        if not devices0:
            print("Error: No I2C0 devices detected (secondary). Check your wiring")
        else:
            print(f"\nFound I2C0 (secondary) {len(devices0)} device(s):")
            for address in devices0:
                print(f" I2C0 Device: Hex: {hex(address)} ({address})")
                if address == 0x3C:
                    print(" -> likely SSD1305 OLED display")
                    ssd_detected = True
                elif address == 0x4B or address == 0x4A:
                    print(" -> likely BNO086 IMU")
                    bno_detected = address
                else:
                    print(f" -> unknown device {hex(address)}")

    print("\n")
    return ssd_detected, bno_detected


def init_i2c():
    # Set I2C 1M is max for SSD1305 display, i2c1 is primary on Pi Zero 2 W
    i2c1 = busio.I2C(board.SCL, board.SDA, frequency=400000)

    # Set I2C 400K is standard mode ofr  for SSD1305 display, i2c0 is secondary on Pi Zero 2 W
    # note: must have 4.7k to 10k ohm pullups for sda and sck on 400K
    # SDA pin 27
    # SCL pin 28
    # must edit config.txt
    # # enable second i2c port (i2c0)
    # dtparam=i2c_vc=on
    # # BRAD: DO NOT load overlays for detected cameras (=1 is on)
    # camera_auto_detect=0
    # https://www.youtube.com/watch?v=FUAiELC76aw
    i2c0 = None
    try:
        i2c0 = busio.I2C(board.SCL0, board.SDA0, frequency=400000)
    except Exception as e:
        i2c0 = None
        print(f"i2c0 (secondary) not available: {e}")

    ssd_detected, bno_detected = scan_i2c_bus(i2c1, i2c0)
    return i2c1, i2c0, ssd_detected, bno_detected


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
    # font = ImageFont.load_default()
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


def display_metrics_ssd(draw, font, rssi, ssid: str, tx_rate, heading: float, download_count, connected: bool = True):
    left_indent = 0
    direction_str = get_compass_8pt_string(heading) if heading is not None else ""
    heading_str = f"{heading:>3.0f}°" if heading is not None else "???°"

    # No target signal, target is out of range
    if rssi is None:
        line1 = f"target: {TARGET_SSID}"
        line2 = "out of range... "
        line3 = f"{heading_str} {direction_str:<2} scanning"

    # Signal lock (Either probing OR fully connected)
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

    # Write text to OLED buffer canvas
    draw.text((left_indent, 0), line1, font=font, fill=1)
    draw.text((left_indent, 10), line2, font=font, fill=1)
    draw.text((left_indent, 20), line3, font=font, fill=1)


def display_radar_ssd(draw, cadence_fill, heading: float, signal_history):
    """
    Draw a white box with a black radar circle in it.
    Add white directional orientation lines for North, East, South, and West.
    Calculates a solid white polygon tracking signal strength vs compass directions.
    """
    # Circle coordinates centering in the 32x32 right panel
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

    # Draw cadence box outline and cadence indicator to visually toggle with cadence_fill flag
    draw.rectangle((97, 26, 101, 30), fill=0)
    draw.rectangle((98, 27, 100, 29), fill=int(cadence_fill))

    # Draw the four cardinal compass North in white solid, other 3 in dashed lines
    # Dynamic crosshairs rotate based on heading relative to fixed screen space
    north_rad = math.radians(0.0 - heading - 90.0)
    south_rad = math.radians(180.0 - heading - 90.0)
    west_rad = math.radians(270.0 - heading - 90.0)
    east_rad = math.radians(90.0 - heading - 90.0)

    # Solid North Crosshair rotated with Antenna Angle
    nx = int(center_x + max_radius * math.cos(north_rad))
    ny = int(center_y + max_radius * math.sin(north_rad))
    draw.line((center_x, center_y, nx, ny), fill=1)  # North

    # Dashed Crosshairs rotated with Antenna Angle
    for r in range(0, max_radius + 1, 2):
        # South dashed line
        # draw.line((center_x, center_y + max_radius, center_x, center_y), fill=1)  # South
        sx = int(center_x + r * math.cos(south_rad))
        sy = int(center_y + r * math.sin(south_rad))
        draw.point((sx, sy), fill=1)  # South (from center going down)

        # West dashed line
        # draw.line((center_x - max_radius, center_y, center_x, center_y), fill=1)  # West
        wx = int(center_x + r * math.cos(west_rad))
        wy = int(center_y + r * math.sin(west_rad))
        draw.point((wx, wy), fill=1)  # West (from center going left)

        # East dashed line
        # draw.line((center_x + max_radius, center_y, center_x, center_y), fill=1)  # East
        ex = int(center_x + r * math.cos(east_rad))
        ey = int(center_y + r * math.sin(east_rad))
        draw.point((ex, ey), fill=1)  # East (from center going right)

    # Array for "antenna strength" polygon vertex points
    polygon_points = []

    # Loop through all 72 (every 5 degrees) to find the "antenna strength" boundary points
    for angle in range(0, 360, 5):

        # ADDED: 5-degree moving window to pull the max peak strength (angle +/- 2 degrees)
        window_values = []
        for offset in range(-2, 3):
            neighbor_index = (angle + offset) % 360
            window_values.append(signal_history[neighbor_index])

        # Use maximum signal strength found inside 5-degree slice
        saved_rssi = max(window_values)

        # Anything lower than or equal to your tracking floor is clipped to the floor
        if saved_rssi < RSSI_WEAK_BOUND:
            saved_rssi = RSSI_WEAK_BOUND
        elif saved_rssi > RSSI_STRONG_BOUND:
            saved_rssi = RSSI_STRONG_BOUND

        # Calculate proportional line length based on clamped values
        # If saved_rssi == RSSI_WEAK_BOUND (-80), proportion becomes exactly 0.0
        # If saved_rssi == RSSI_STRONG_BOUND (-45), proportion becomes exactly 1.0
        proportion = (saved_rssi - RSSI_WEAK_BOUND) / (RSSI_STRONG_BOUND - RSSI_WEAK_BOUND)
        line_length = max_radius * proportion

        # Shift geometry relative to current compass heading so layout updates dynamically
        angle_rad = math.radians(angle - heading - 90.0)

        # Compute polygon vertex coordinates
        target_x = int(center_x + line_length * math.cos(angle_rad))
        target_y = int(center_y + line_length * math.sin(angle_rad))

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
    global short_press, long_press, download_count

    print("Starting Pi Zero 2 W Signal & Antenna Tracking...\n")
    probe_mode = True
    connected_mode = False

    i2c1, i2c0, ssd_detected, bno_detected = init_i2c()
    bno_sensor = None
    if bno_detected:
        bno_sensor = init_bno086(i2c0, address=bno_detected)
    if ssd_detected:
        display, draw, font, image = init_ssd_display(i2c1)

    # signal history array tracking all 360 discrete headings
    signal_history = [-99.0] * 360

    ssid, rssi, quality, tx_rate = None, None, None, None
    connected_mode = False  # Track state: False = Probing, True = Hard Connection Lock

    try:
        start_time = time.time()
        cadence_fill = False
        while True:
            cadence_fill = not cadence_fill
            current_loop_time = time.time()

            # On long_press revert to Probe Mode
            if long_press:
                if connected_mode:
                    try:
                        print("\nLong_press: disconnecting")
                        # Set OS interface link to down
                        subprocess.run(["sudo", "nmcli", "connection", "down", TARGET_SSID], timeout=5)
                    except Exception as e:
                        print(f"Disconnect failed: {e}")

                connected_mode = False
                tx_rate = None
                quality = None
                long_press = False
                short_press = False

            if connected_mode:
                current_ssid = get_ssid()
                if current_ssid == TARGET_SSID:
                    # Connected Mode - Extract full metrics
                    rssi, quality, tx_rate = query_wifi()
                    ssid = current_ssid

                    # If signal above download threshold, test button state
                    if rssi is not None and rssi >= RSSI_DOWNLOAD_THRESHOLD:
                        # Cleanly captures the flag set by the trailing edge release handler
                        if short_press:
                            print(f"\n* Button pressed ({rssi} dBm). Downloading {download_count}...")
                            download_count += 1

                            # TODO Add download code
                            print(f"TODO Add Download code !!!\n")
                else:
                    # Connection broken. Return to Probe Mode
                    connected_mode = False
                    tx_rate = None
                    quality = None
            else:
                # Probe Mode - Scan for remote target, only rssi measured
                tx_rate = None
                quality = None

                # scan unconnected signals
                rssi = probe_target_ssid(interface="wlan0", target_ssid=TARGET_SSID)
                ssid = TARGET_SSID if rssi is not None else None

                # If signal hits the connection threshold, evaluate button input
                if rssi is not None and rssi >= RSSI_CONNECT_THRESHOLD:
                    # Cleanly captures the flag set by the trailing edge release handler
                    if short_press:
                        print(f"\n* Button pressed ({rssi} dBm). Connecting...")
                        try:
                            subprocess.run(["sudo", "nmcli", "connection", "up", TARGET_SSID], timeout=8)
                            connected_mode = True
                        except Exception as e:
                            print(f"Connection command failed: {e}")
                            connected_mode = False

            short_press = False

            heading = get_compass_heading(bno_sensor)

            # Convert current float heading to integer and save live signal strength telemetry
            if rssi is not None and heading is not None:
                current_index = int(heading) % 360
                signal_history[current_index] = rssi

            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time

            # Print Metrics to Standard Out
            if connected_mode:
                print_metrics(quality, rssi, ssid, tx_rate)
                if rssi >= RSSI_DOWNLOAD_THRESHOLD:
                    print("-> download possible (download {download_count}).}?)")
                else:
                    print("-> connected, but signal too weak for download")
            else:
                print(f"**Probing ssid: {TARGET_SSID} un-connected")
                if rssi is not None and rssi >= RSSI_CONNECT_THRESHOLD:
                    print("-> connection possible (connect?)")

            live_rssi_str = f"{rssi} dBm" if rssi is not None else "Out of Range"
            heading_print_str = f"{heading:.1f}°" if heading is not None else "0.0° (No IMU)"
            print(f"Antenna Vector Angle: {heading_print_str} --> Current RSSI: {live_rssi_str}")
            if heading is not None:
                print(f"Compass Heading: {heading:.0f}° (Magnetic North = 0°)")
            else:
                print("Compass Heading: n/a")

            print(f"Updates: {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            # OLED SSD Display, Left side is text stats, right side is radar graphic
            if ssd_detected:
                draw.rectangle((0, 0, SSD_WIDTH, SSD_HEIGHT), fill=0)  # clear canvas

                # Keep original raw heading (None -> "???°") for text layout
                display_metrics_ssd(draw, font, rssi, ssid, tx_rate, heading, download_count, connected=connected_mode)

                # Fallback to 0.0 strictly for geometric rotation math if the sensor is offline
                render_heading = heading if heading is not None else 0.0
                display_radar_ssd(draw, cadence_fill, render_heading, signal_history)

                display.image(image)
                display.show()

            # Dynamic sleep, sleep longer when WiFi out of range
            if connected_mode:
                time.sleep(0.05)  # Connected Mode
            elif rssi is not None:
                time.sleep(0.01)  # Probe Mode
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
