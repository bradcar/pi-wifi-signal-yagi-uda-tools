"""
For advanced computation using standard desktop Python
(with pyserial), you can log raw data to CSV and use the MotionCal tool
or the Adafruit SensorLab Python notebooks to calculate a full \(3 \times 3\) soft-iron matrix.
If you are just using raw Python on Linux, you may need the Adafruit CircuitPython LIS3MDL Library.
"""
import time
import board
import adafruit_lis3mdl
import math

i2c = board.I2C()
sensor = adafruit_lis3mdl.LIS3MDL(i2c)

# ----------------------------------------------------
# REPLACE THESE WITH YOUR RECORDED MIN/MAX VALUES
# ----------------------------------------------------
min_val = {'x': -45.5, 'y': -32.0, 'z': -50.2}
max_val = {'x': 55.3, 'y': 48.6, 'z': 42.1}
# ----------------------------------------------------

# Calculate Hard Iron offsets (midpoints)
offset_x = (max_val['x'] + min_val['x']) / 2.0
offset_y = (max_val['y'] + min_val['y']) / 2.0
offset_z = (max_val['z'] + min_val['z']) / 2.0

# Calculate Average scale (to normalize the sphere)
avg_delta_x = (max_val['x'] - min_val['x']) / 2.0
avg_delta_y = (max_val['y'] - min_val['y']) / 2.0
avg_delta_z = (max_val['z'] - min_val['z']) / 2.0
avg_radius = (avg_delta_x + avg_delta_y + avg_delta_z) / 3.0

scale_x = avg_radius / avg_delta_x
scale_y = avg_radius / avg_delta_y
scale_z = avg_radius / avg_delta_z

print("Calibration loaded. Applying corrections...")

while True:
    raw_x, raw_y, raw_z = sensor.magnetic

    # Apply hard and soft iron calibration
    cal_x = (raw_x - offset_x) * scale_x
    cal_y = (raw_y - offset_y) * scale_y
    cal_z = (raw_z - offset_z) * scale_z

    print(f"Calibrated: X:{cal_x:6.2f} Y:{cal_y:6.2f} Z:{cal_z:6.2f} uT")
    time.sleep(0.5)
