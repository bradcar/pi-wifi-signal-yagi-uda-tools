# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

"""
Display compass heading data five times per second. Use calibration constants created by
hard_only_calibrate_lisemdl_test.py.

Explanation of why only hard-iron needed:
Compass headings (atan2) computes the differences of the angles of X- and Y-values.
The Soft-iron calibrations would make sure the vector lengths are calibrated, which doesn't affect the angle.

Typically, we see +/-5 degree reading change for stationary sensor
"""

import board
import time
from math import atan2, degrees
import adafruit_lis3mdl

# Hard-iron calibration offsets from high-speed calibration run
CALIBRATED_MAG_MIN = [-58.7548, -38.7898, -102.2800]
CALIBRATED_MAG_MAX = [44.9284, 63.4171, -4.4870]

# Create offsets based on calibration constants - true magnetic midpoint offset for X and Y
X_OFFSET = (CALIBRATED_MAG_MAX[0] + CALIBRATED_MAG_MIN[0]) / 2.0
Y_OFFSET = (CALIBRATED_MAG_MAX[1] + CALIBRATED_MAG_MIN[1]) / 2.0

# create scale factors to normalize the field to a 1.0 radius
X_SCALE = (CALIBRATED_MAG_MAX[0] - CALIBRATED_MAG_MIN[0]) / 2.0
Y_SCALE = (CALIBRATED_MAG_MAX[1] - CALIBRATED_MAG_MIN[1]) / 2.0


def vector_2_degrees(x, y):
    angle = degrees(atan2(y, x))
    if angle < 0:
        angle += 360
    return angle


def get_heading(mag_sensor):
    magnet_x, magnet_y, magnet_z = mag_sensor.magnetic

    # Apply pre-calculated scaling directly, stripping out map_range entirely
    cal_x = (magnet_x - X_OFFSET) / X_SCALE
    cal_y = (magnet_y - Y_OFFSET) / Y_SCALE

    return vector_2_degrees(cal_x, cal_y)


def main():
    # Initialize the specific hardware interface
    i2c1 = board.I2C()
    lis3mdl = adafruit_lis3mdl.LIS3MDL(i2c1)

    while True:
        print(f"heading: {get_heading(lis3mdl):.0f} degrees")
        time.sleep(0.2)


if __name__ == "__main__":
    main()