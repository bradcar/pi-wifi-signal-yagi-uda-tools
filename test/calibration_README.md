# 3D Combined Hard-Iron and Soft-Iron Calibration for LIS3MDL

A Python utility for creating calibration from  3D magnetometer data collected from Adafruit LIS3MDL sensors via CircuitPython (adafruit-circuitpython-lis3mdl). 
It corrects for local magnetic field distortions by fitting an ellipsoid to raw 3D data points and transforming them into a normalized unit sphere.

Magnetometers sensors planced in cases or devides experience two main types of magnetic distortion:
1. Hard-Iron Distortion: Caused by permanent magnets, magnetized metals, batteries, or static fields near the sensor. 
This shifts the sphere's origin by a fixed offset [bx, by, bz] 

2. Soft-Iron Distortion: Caused by nearby ferromagnetic materials that distort the local magnetic field based on orientation. 
This distorts the sphere into an ellipsoid along its principal axes.

This script measures raw microtesla (μT) readings over a timed window. 
During this time the user should rotate sensor in aLL 3D directions so it points to as to as many points in the full sphere.
The device should be figrure-eighted in ever direction and even flip upside down.

It then fits a bounding ellipsoid to sphere, and computes:
1. Min/Max Bounding Vectors (HARD_IRON_CALIBRATED_MAG_MIN / HARD_IRON_CALIBRATED_MAG_MAX) to center the dataset.
2. A 3×3 Soft-Iron Transformation Matrix (SOFT_IRON_MATRIX) accounting for cross-axis coupling and axis scaling.

To fit the hard-iron offset vector, the hard-iron distortion shifts the center of the sphere away from the origin (0,0,0). 
The offset vector b is estimated by calculating the midpoint of the extreme coordinate boundaries collected during sensor rotation.
Then this offset vector is subtracted from each data points to shift the dataset center to the origin.

1. **Hard-Iron Shift Vector ($\mathbf{b}$):**
   $$b_x = \frac{x_{\max} + x_{\min}}{2}, \quad b_y = \frac{y_{\max} + y_{\min}}{2}, \quad b_z = \frac{z_{\max} + z_{\min}}{2}$$


Soft-iron effects scale the response along each axis, stretching the sphere into an ellipsoid with semi-axis radii (rx, ry, rz).
When soft-iron distortion tilts or rotates the ellipsoid's principal axes relative to the coordinate frame, cross-axis coupling occurs.
The script estimates off-diagonal entries using normalized sample covariances of the centered points.
Combining diagonal axis scaling and off-diagonal cross-coupling terms yields the symmetric 3×3 soft-iron transformation matrix Msoft

2. **Soft-Iron Scale Factors ($s_x, s_y, s_z$):**
   $$r_x = \frac{x_{\max} - x_{\min}}{2}, \quad r_{\text{avg}} = \frac{r_x + r_y + r_z}{3}, \quad s_x = \frac{r_{\text{avg}}}{r_x}$$

3. **Soft-Iron Cross-Axis Terms ($M_{ij}$):**
   $$M_{xy} = -\frac{\text{Cov}(X, Y)}{\sigma_X \sigma_Y} = -\frac{\sum (x_i - b_x)(y_i - b_y)}{\sqrt{\sum (x_i - b_x)^2 \sum (y_i - b_y)^2}}$$

Finally:
$$\mathbf{x}_{\text{calibrated}} = \mathbf{M}_{\text{soft}} (\mathbf{x}_{\text{raw}} - \mathbf{b})$$


## Hardware & Software Requirements
* Adafruit CircuitPython / Blinka (adafruit-blinka)
* Adafruit LIS3MDL Library (adafruit-circuitpython-lis3mdl)
* Matplotlib (matplotlib)

## Installation

pip install adafruit-blinka adafruit-circuitpython-lis3mdl matplotlib

## Usage Instructions and the Execute the Script
Mount the Sensor: Ensure the LIS3MDL is installed in its final enclosure or mounting frame to account for nearby metal and electronics.

python hard_soft_calibration_lis3mdl.py
Rotate in 3D Space: During the sampling window (default 120 seconds), rotate the sensor smoothly through all spatial orientations:


## Generated Output Files
All output files are automatically created inside the ./calibration_output_files/ directory.
Each file is stamped with a timestamp suffix (YYYYMMDD_HHMMSS):


* Parameters 
* * calibration_parameters_TIMESTAMP.py -	Python code snippet containing calibration arrays ready for copy-pasting.
* Calibration Raw Data
* * calibration_values_TIMESTAMP.json	- Raw (x,y,z) sample points and min/max vector limits stored as JSON.
* 3D Plot of uncalibrated points and calibration sphere
* * calibration_plot_TIMESTAMP.png - Side-by-side 3D scatter plots showing raw ellipsoid vs. normalized sphere.

Note: The script users Matplotlib's Agg backend, allowing high-resolution 3D plot generation over headless SSH sessions without requiring a display server.

## Integration Example
Copy the generated parameters from calibration_parameters_TIMESTAMP.py directly into your sensor sampling loop.
### Python
```
import adafruit_lis3mdl
import board

i2c = board.I2C()
sensor = adafruit_lis3mdl.LIS3MDL(i2c)

# Copy and paste these declarations into the code that uses the LIS3MDL:
# Hard-iron: Calibration constants from hard_only_calibrate_lis3mdl_test.py:
HARD_IRON_MIN = [-42.1234, -18.5432, -65.4321]
HARD_IRON_MAX = [38.5678, 55.4321, 12.3456]

# Soft-iron: Calibration constants from hard_soft_calibrate_lis3mdl_test.py:
SOFT_IRON_MATRIX = [
    [1.025, -0.012, 0.005],
    [-0.012, 0.985, 0.018],
    [0.005, 0.018, 1.012],
]


def get_calibrated_magnetometer():
    rx, ry, rz = sensor.magnetic

    # Normalize onto a [-1.0, +1.0] unit span using min/max bounds
    span_x = HARD_IRON_MAX[0] - HARD_IRON_MIN[0]
    span_y = HARD_IRON_MAX[1] - HARD_IRON_MIN[1]
    span_z = HARD_IRON_MAX[2] - HARD_IRON_MIN[2]

    mx = 2.0 * (rx - HARD_IRON_MIN[0]) / span_x - 1.0
    my = 2.0 * (ry - HARD_IRON_MIN[1]) / span_y - 1.0
    mz = 2.0 * (rz - HARD_IRON_MIN[2]) / span_z - 1.0

    # Apply Soft-Iron Matrix transformation
    cx = (SOFT_IRON_MATRIX[0][0] * mx + SOFT_IRON_MATRIX[0][1] * my + SOFT_IRON_MATRIX[0][2] * mz)
    cy = (SOFT_IRON_MATRIX[1][0] * mx + SOFT_IRON_MATRIX[1][1] * my + SOFT_IRON_MATRIX[1][2] * mz)
    cz = (SOFT_IRON_MATRIX[2][0] * mx + SOFT_IRON_MATRIX[2][1] * my + SOFT_IRON_MATRIX[2][2] * mz)

    return cx, cy, cz
```

## Output
```
#================================================================
#Calibration Complete!
# Copy and paste these declarations into the code that uses the LIS3MDL:

# Hard-iron: Calibration constants from hard_only_calibrate_lis3mdl_test.py:
HARD_IRON_CALIBRATED_MAG_MIN = [-92.0199, 1.5639, -93.0868]
HARD_IRON_CALIBRATED_MAG_MAX = [7.9070, 101.2716, 7.2347]

# Soft-iron: Calibration constants from hard_soft_calibrate_lis3mdl_test.py:
SOFT_IRON_MATRIX = [
    [1.001, 0.070, -0.176],
    [0.070, 1.003, 0.118],
    [-0.176, 0.118, 0.997]
]

Saved calibration parameters to calibration_output_files/calibration_parameters_20261007_180712.py
Saved calibration data to calibration_output_files/calibration_values_20261007_180712.json

=== Calibration Quality Metrics ===
Mean Absolute Percentage Error (MAPE) : 3.13%
Normalized RMSE (NRMSE)               : 0.0392
Semi-Axes Ratio (c/a)                 : 0.6279 (Target: 1.0000)
Oblateness / Flattening (f)           : 0.3721 (Target: 0.0000)
Fractional Anisotropy (FA)            : 0.4367 (Target: 0.0000)

Loaded calibration data from calibration_output_files/calibration_values_20261007_180712.json

Create subplot for BEFORE: Raw Magnetometer Data
Create subplot for AFTER: Normalized Calibrated Sphere

Saved calibration plot to calibration_output_files/calibration_plot_20261007_180712.png

Process finished with exit code 0
```