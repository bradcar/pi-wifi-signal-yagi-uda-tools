"""
SPDX-FileCopyrightText: 2024 Liz Clark for Adafruit Industries
SPDX-License-Identifier: MIT

Magnetometer Hard-Iron calibration tool, sufficient for compass heading.
Optimized for 60 seconds at 20Hz sampling to thoroughly calibrate magnetometer.
If a full hard & soft iron calibration is needed, please look at: hard_soft_calibration_lis3mdl.py

Explanation of why only hard-iron needed:
Compass headings (atan2) computes the differences of the angles of X- and Y-values.
The Soft-iron calibrations would make sure the vector lengths are calibrated, which doesn't affect the angle.

Changed from LIz orig progam for a full 30 sec, also fixed the the division by zero issue,

Sample output (which provides copy-paste constants for Python codes).

CALIBRATED_MAG_MIN = [-58.7548, -38.7898, -102.2800]
CALIBRATED_MAG_MAX = [44.9284, 63.4171, -4.4870]

CALIBRATED_MAG_MIN = [-61.7656, -49.6492, -88.6144]
CALIBRATED_MAG_MAX = [44.8699, 79.8305, 26.3666]


last 4 sec and output:
 4.0s remain, Raw: (  +6.3,  +37.2,  -96.4) -> Mapped: (+0.27, +0.45, -0.86)
 3.6s remain, Raw: (  -5.2,  -12.1,  -93.8) -> Mapped: (+0.05, -0.52, -0.81)
 3.2s remain, Raw: ( -19.0,  -25.8,  -26.2) -> Mapped: (-0.21, -0.79, +0.53)
 2.8s remain, Raw: ( -24.2,  +35.4,  -11.0) -> Mapped: (-0.30, +0.42, +0.84)
 2.3s remain, Raw: ( -19.0,  +40.0,  -95.2) -> Mapped: (-0.21, +0.51, -0.84)
 1.9s remain, Raw: ( -22.2,  -15.4,  -88.6) -> Mapped: (-0.27, -0.58, -0.71)
 1.5s remain, Raw: (  -6.2,  +33.2,  -98.9) -> Mapped: (+0.04, +0.37, -0.91)
 1.1s remain, Raw: ( +29.9,  +20.8,  -22.9) -> Mapped: (+0.72, +0.13, +0.60)
 0.7s remain, Raw: ( +27.0,  -17.4,  -69.6) -> Mapped: (+0.66, -0.62, -0.33)
 0.3s remain, Raw: ( +16.1,  +14.1,  -95.7) -> Mapped: (+0.46, +0.00, -0.85)

================================================================
Calibration Complete!
Copy and paste these Constant declarations into your main Python code:
CALIBRATED_MAG_MIN = [-60.9909, -36.7729, -103.2885]
CALIBRATED_MAG_MAX = [44.7091, 64.9810, -2.6747]
"""
import time
import board
import adafruit_lis3mdl

i2c1 = board.I2C()
magnetometer = adafruit_lis3mdl.LIS3MDL(i2c1)

# Initialize array boundaries
MAG_MIN = [1000, 1000, 1000]
MAG_MAX = [-1000, -1000, -1000]


def map_range(x, in_min, in_max, out_min, out_max):
    """
    Maps a number from one range to another with a division by zero safeguard.
    """
    if in_max == in_min:
        return (out_max + out_min) / 2.0

    mapped = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
    if out_min <= out_max:
        return max(min(mapped, out_max), out_min)

    return min(max(mapped, out_max), out_min)


def calibrate_mag(runtime_seconds=60):
    """
    Calibrates the magnetometer by sampling at 20Hz (0.05s intervals)
    for a long window to allow complete physical rotation.
    """
    print(f"Calibration window active for {runtime_seconds} seconds.")
    print("-> Pick up the magnetometer and smoothly rotate it in 3D space.")
    print("-> Make sure to flip it completely upside down and spin it 360°.")
    print("----------------------------------------------------------------")

    start_time = time.time()
    last_print_time = time.time()

    # Initial values using the first hardware reading
    x, y, z = magnetometer.magnetic
    mag_vals = [x, y, z]
    for i in range(3):
        MAG_MIN[i] = mag_vals[i]
        MAG_MAX[i] = mag_vals[i]

    # Main acquisition loop
    while time.time() - start_time < runtime_seconds:
        x, y, z = magnetometer.magnetic
        mag_vals = [x, y, z]

        # Dynamically stretch the min/max envelope bounds
        for i in range(3):
            MAG_MIN[i] = min(MAG_MIN[i], mag_vals[i])
            MAG_MAX[i] = max(MAG_MAX[i], mag_vals[i])

        # Track time elapsed
        elapsed = time.time() - start_time
        remaining = max(0.0, runtime_seconds - elapsed)

        # Output current calibration updates every 0.4 seconds to keep terminal legible
        if time.time() - last_print_time > 0.4:
            cal_x = map_range(x, MAG_MIN[0], MAG_MAX[0], -1, 1)
            cal_y = map_range(y, MAG_MIN[1], MAG_MAX[1], -1, 1)
            cal_z = map_range(z, MAG_MIN[2], MAG_MAX[2], -1, 1)

            print(
                f"{remaining:4.1f}s remain, Raw: ({x:+6.1f}, {y:+6.1f}, {z:+6.1f}) -> Mapped: ({cal_x:+.2f}, {cal_y:+.2f}, {cal_z:+.2f})")
            last_print_time = time.time()

        # 50ms delay = 20 samples per second high-density tracking
        time.sleep(0.05)

    return MAG_MIN, MAG_MAX


print("Preparing magnetometer calibration. Get ready to move the magnetometer...")
time.sleep(3)
print("Starting magnetometer calibration...\n")

FINAL_MIN, FINAL_MAX = calibrate_mag(runtime_seconds=60)

print("\n================================================================")
print("Calibration Complete!")
print("Copy and paste these Constant declarations into your main Python code:")
print(f"CALIBRATED_MAG_MIN = [{FINAL_MIN[0]:.4f}, {FINAL_MIN[1]:.4f}, {FINAL_MIN[2]:.4f}]")
print(f"CALIBRATED_MAG_MAX = [{FINAL_MAX[0]:.4f}, {FINAL_MAX[1]:.4f}, {FINAL_MAX[2]:.4f}]")
