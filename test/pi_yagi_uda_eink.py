# pi_yagi_uda.py
"""
E-INK REFRESH IS TOO SLOW FOR THIS PROJECT > 3 Seconds!

WiFi Signal Monitor (Pi Zero): ABox-PDX
SSID:    ABox-PDX
RSSI:    -25 dBm  4 bars
Link Q:  70/70    Hi Quality
Tx Rate: 72.2 Mb/s
-> download possible (download 3).?)
Sweep Vector Angle: 40.0° --> Mock RSSI: -73.3 dBm
Compass Heading: 304° (Magnetic North = 0°)
Updates: 3059.5 msec, 0 Hz  <========================================
Clock: 2026-06-01 19:14:21


On Raspberry Pi Zero 2 W, the code repeatedly measures the RSSI, Link Quality,
and Tx Bit Rate of the currently targeted network on interface wlan0.

if the targeted network is connected it can download the data file.
* this is shown in the display as:
* "SSID = target-net"

If the targeted network is not connected, it uses a lighter weight probe which scans all available networks looking for the targeted network.
* this is shown in the display as:
* "ssid   target-net"
When connected to a Yagi-Uda Antenna and an IMU we can use this to locate the WiFi source.

It prints the results to std out and an E-ink display.
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

Data is shown on Adafruit 2.13" SSD1680 E-ink display (250x122 Landscape via Pillow rotation) and printed to std out.
Left side for text matrix metrics readout.
Right side for scaled antenna tracking radar visual scope.

 Pi Zero 2 W must be modified to attach an external antenna like a Yagi Uda.
 directions: https://www.youtube.com/watch?v=6R8xhSzpJTU&t=166s
  Note: I've heard Uda was the inventor and Yagi was the promoter.

 The Pi Zero 2 W is running Debian Trixie base. 64-bit
  - with no desktop environment
  - 555.1 MB download, Released: 2026-04-21
  - uname -a
Linux pi-zero 6.12.75+rpt-rpi-v8 #1 SMP PREEMPT Debian 1:6.12.75-1+rpt1 (2026-03-11) aarch64 GNU/Linux

Requirements:
 Must edit config.txt to enable i2c_vc, etc.
"""
import math
import time
import subprocess
from datetime import datetime

import digitalio
from adafruit_epd.ssd1680 import Adafruit_SSD1680

# for Monochrom E-ink 0 is black and 255 is white,  SSD1306 Monochrome is 0 for black and 1 for white
FILL_WHITE = 255

import board
import busio
from PIL import Image, ImageDraw, ImageFont
from adafruit_bno08x import BNO_REPORT_GEOMAGNETIC_ROTATION_VECTOR
from adafruit_bno08x.i2c import BNO08X_I2C
from gpiozero import Button

# Network signal tracking dependencies
from pi_wifi_rssi_quality_txrate import get_ssid, probe_target_ssid, query_wifi, print_metrics

# Import the mock test environment
from cardiod_test_data_generator import measured_signal_strength, MOCK_SIGNAL_ARRAY

# Target SSID
TARGET_SSID = "ABox-PDX"

# Network Signal Lock Thresholds
RSSI_CONNECT_THRESHOLD = -75  # Minimum signal to allow a hardware connection
RSSI_DOWNLOAD_THRESHOLD = -70  # Minimum signal to execute data payload transfer

# Radar lines Boundary
RSSI_STRONG_BOUND = -45
RSSI_WEAK_BOUND = -80

# Native Hardware Configuration Mappings for 2.13" E-ink (Portrait State)
EPD_WIDTH = 122
EPD_HEIGHT = 250

# Virtual dimensions for Landscape mapping
VIRTUAL_WIDTH = 250
VIRTUAL_HEIGHT = 122

# Globals
long_press = False
short_press = False
button_press_time = 0.0
download_count = 0

# SSD1306: Configure Button on GPIO 26 (Physical Pin 37) with a 2.0 second hold threshold
# E-ink: "Up" Button: actually GPIO 6 NOT GPIO 5
# E-ink: "Down" Button: actually GPIO 5 NOT GPIO 6
button0 = Button(5, pull_up=True, bounce_time=0.1, hold_time=1.0)


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
    # Set I2C primary on Pi Zero 2 W
    i2c1 = busio.I2C(board.SCL, board.SDA, frequency=400000)

    # Set I2C0 secondary on Pi Zero 2 W
    i2c0 = None
    try:
        i2c0 = busio.I2C(board.SCL0, board.SDA0, frequency=400000)
    except Exception as e:
        i2c0 = None
        print(f"i2c0 (secondary) not available: {e}")

    ssd_detected, bno_detected = scan_i2c_bus(i2c1, i2c0)
    return i2c1, i2c0, ssd_detected, bno_detected


def init_e_ink_display():
    """Initializes the E-ink display using SPI and creates the canvas."""
    spi = busio.SPI(board.SCK, board.MOSI)

    ecs = digitalio.DigitalInOut(board.CE0)  # Chip Select
    dc = digitalio.DigitalInOut(board.D22)  # Data/Command Control
    rst = digitalio.DigitalInOut(board.D27)  # Hardware Reset
    busy = digitalio.DigitalInOut(board.D17)  # Hardware Busy Line

    # Initialize display with native hardware parameters (Portrait shape)
    display = Adafruit_SSD1680(
        width=EPD_WIDTH,
        height=EPD_HEIGHT,
        spi=spi,
        cs_pin=ecs,
        dc_pin=dc,
        sramcs_pin=None,
        rst_pin=rst,
        busy_pin=busy
    )
    display.rotation = 0

    # Clear screen initially
    display.fill(0)
    display.display()

    # Initialize image as a virtual landscape workspace canvas directly.
    image = Image.new("L", (VIRTUAL_WIDTH, VIRTUAL_HEIGHT))
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.load_default(size=18)
    except IOError:
        font = ImageFont.load_default()
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
    left_indent = 2
    direction_str = get_compass_8pt_string(heading) if heading is not None else ""
    heading_str = f"{heading:>3.0f}°" if heading is not None else "???°"

    if rssi is None:
        line1 = f"target: {TARGET_SSID}"
        line2 = "out of range... "
        line3 = f"{heading_str} {direction_str:<2} scanning"
    else:
        if connected:
            line1 = f"SSID = {ssid}"
            rate_str = f"{tx_rate:.0f} mb/s" if tx_rate is not None else "linked"
            line2 = f"{rssi} dbm  {rate_str}"
            line3 = f"{heading_str} {direction_str:<2} ..dload {download_count}?" if rssi >= RSSI_DOWNLOAD_THRESHOLD else f"{heading_str} {direction_str:<2}"
        else:
            line1 = f"ssid   {ssid}"
            line2 = f"{rssi} dbm ...probing"
            line3 = f"{heading_str} {direction_str:<2} .connect?" if rssi >= RSSI_CONNECT_THRESHOLD else f"{heading_str} {direction_str:<2} weak"

    draw.text((left_indent, 15), line1, font=font, fill=FILL_WHITE)
    draw.text((left_indent, 45), line2, font=font, fill=FILL_WHITE)
    draw.text((left_indent, 75), line3, font=font, fill=FILL_WHITE)


def display_radar_ssd(draw, current_sweep_angle: float, cadence_fill, heading: float = 0.0):
    # FIX: Recalculate boundaries to expand text area
    center_x = 200
    center_y = 61
    max_radius = 45

    if heading is None:
        heading = 0.0

    # FIX: Outer rectangle box converted into a tall layout framework (Left: 153, Right: 247)
    draw.rectangle((153, 5, 247, 117), fill=FILL_WHITE)
    draw.ellipse((center_x - max_radius, center_y - max_radius, center_x + max_radius, center_y + max_radius),
                 outline=0, fill=0)

    # Shifted heartbeat indicator safely inside the new framing profile
    draw.rectangle((158, 10, 168, 20), fill=0)
    draw.rectangle((160, 12, 166, 18), fill=int(cadence_fill))

    north_rad = math.radians(0.0 - heading - 90.0)
    south_rad = math.radians(180.0 - heading - 90.0)
    west_rad = math.radians(270.0 - heading - 90.0)
    east_rad = math.radians(90.0 - heading - 90.0)

    nx = int(center_x + max_radius * math.cos(north_rad))
    ny = int(center_y + max_radius * math.sin(north_rad))
    draw.line((center_x, center_y, nx, ny), fill=FILL_WHITE)

    for r in range(0, max_radius + 1, 4):
        sx = int(center_x + r * math.cos(south_rad))
        sy = int(center_y + r * math.sin(south_rad))
        draw.point((sx, sy), fill=FILL_WHITE)

        wx = int(center_x + r * math.cos(west_rad))
        wy = int(center_y + r * math.sin(west_rad))
        draw.point((wx, wy), fill=FILL_WHITE)

        ex = int(center_x + r * math.cos(east_rad))
        ey = int(center_y + r * math.sin(east_rad))
        draw.point((ex, ey), fill=FILL_WHITE)

    polygon_points = []

    for angle in range(0, 360, 5):
        saved_rssi = MOCK_SIGNAL_ARRAY[angle]

        if saved_rssi > RSSI_STRONG_BOUND:
            saved_rssi = RSSI_STRONG_BOUND
        elif saved_rssi < RSSI_WEAK_BOUND:
            saved_rssi = RSSI_WEAK_BOUND

        proportion = (saved_rssi - RSSI_WEAK_BOUND) / (RSSI_STRONG_BOUND - RSSI_WEAK_BOUND)
        line_length = max_radius * proportion

        angle_rad = math.radians(angle - heading - 90.0)

        target_x = int(center_x + line_length * math.cos(angle_rad))
        target_y = int(center_y + line_length * math.sin(angle_rad))

        polygon_points.append((target_x, target_y))

    if len(polygon_points) >= 3:
        draw.polygon(polygon_points, fill=FILL_WHITE, outline=1)

    draw.point((center_x, center_y - 1), fill=0)
    draw.point((center_x, center_y + 1), fill=0)
    draw.point((center_x - 1, center_y), fill=0)
    draw.point((center_x + 1, center_y), fill=0)
    draw.point((center_x, center_y), fill=0)


def main():
    global short_press, long_press, download_count

    print("Starting Pi Zero 2 W Signal & Antenna Tracking...\n")
    i2c1, i2c0, ssd_detected, bno_detected = init_i2c()
    bno_sensor = None
    if bno_detected:
        bno_sensor = init_bno086(i2c0, address=bno_detected)

    display, draw, font, image = init_e_ink_display()

    sweep_angle = 0.0
    mock_heading_tracker = 0.0

    ssid, rssi, quality, tx_rate = None, None, None, None
    connected_mode = False

    try:
        start_time = time.time()
        cadence_fill = False
        while True:
            cadence_fill = not cadence_fill
            current_loop_time = time.time()

            if long_press:
                if connected_mode:
                    try:
                        print("\nLong_press: disconnecting")
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
                    rssi, quality, tx_rate = query_wifi()
                    ssid = current_ssid

                    if rssi is not None and rssi >= RSSI_DOWNLOAD_THRESHOLD:
                        if short_press:
                            print(f"\n* Button pressed ({rssi} dBm). Downloading {download_count}...")
                            download_count += 1
                            print(f"TODO Add Download code !!!\n")
                else:
                    connected_mode = False
                    tx_rate = None
                    quality = None
            else:
                tx_rate = None
                quality = None

                rssi = probe_target_ssid(interface="wlan0", target_ssid=TARGET_SSID)
                ssid = TARGET_SSID if rssi is not None else None

                if rssi is not None and rssi >= RSSI_CONNECT_THRESHOLD:
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

            if heading is None:
                heading = mock_heading_tracker

            _, mock_rssi = measured_signal_strength(sweep_angle)

            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time

            if connected_mode:
                print_metrics(quality, rssi, ssid, tx_rate)
                if rssi >= RSSI_DOWNLOAD_THRESHOLD:
                    print(f"-> download possible (download {download_count}).?)")
                else:
                    print("-> connected, but signal too weak for download")
            else:
                print(f"**Probing ssid: {TARGET_SSID} un-connected")
                if rssi is not None and rssi >= RSSI_CONNECT_THRESHOLD:
                    print("-> connection possible (connect?)")

            print(f"Sweep Vector Angle: {sweep_angle}° --> Mock RSSI: {mock_rssi} dBm")
            if heading is not None:
                print(f"Compass Heading: {heading:.0f}° (Magnetic North = 0°)")
            else:
                print("Compass Heading: n/a")

            print(f"Updates: {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            # --- RENDER BLOCK ---
            # Clear canvas (250x122)
            draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=0)

            # display text metrics and radar disply
            display_metrics_ssd(draw, font, rssi, ssid, tx_rate, heading, download_count, connected=connected_mode)
            display_radar_ssd(draw, sweep_angle, cadence_fill, heading=heading)

            # rotate to landscape matrix 270 degrees.
            hardware_aligned_image = image.rotate(270, expand=True)

            # Give rotated portrait buffer directly to the unrotated driver
            display.image(hardware_aligned_image)

            # TRY THIS: Pass partial update flags if supported by the driver backend
            try:
                display.display(partial_refresh=True)
            except TypeError:
                # If the wrapper doesn't take the argument, use the direct hardware command
                #print("&&&& partial refresh didn't work &&&&&")
                display.display()
            # --------------------------------------------------------

            sweep_angle = (sweep_angle + 5) % 360
            mock_heading_tracker = (mock_heading_tracker + 2.0) % 360

            if connected_mode:
                time.sleep(0.1)
            elif rssi is not None:
                time.sleep(0.05)
            else:
                time.sleep(0.5)

    except KeyboardInterrupt:
        # Clear canvas
        draw.rectangle((0, 0, VIRTUAL_WIDTH, VIRTUAL_HEIGHT), fill=0)
        hardware_aligned_image = image.rotate(270, expand=True)
        display.image(hardware_aligned_image)
        display.display()
        print("\nEnded Tracking (^c).")


if __name__ == "__main__":
    main()
