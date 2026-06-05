# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

"""
Display compass heading data five times per second
see +/-2 degree for stationary sensor
"""

import board
import time
from math import atan2, degrees
import adafruit_lis3mdl

i2c1 = board.I2C()
lis3mdl = adafruit_lis3mdl.LIS3MDL(i2c1)


def vector_2_degrees(x, y):
    angle = degrees(atan2(y, x))
    if angle < 0:
        angle += 360
    return angle


def get_heading(mag_sensor):
    magnet_x, magnet_y, magnet_z = mag_sensor.magnetic
    return vector_2_degrees(magnet_x, magnet_y)


while True:
    print(f"heading: {get_heading(lis3mdl):.0f} degrees")
    time.sleep(0.2)
