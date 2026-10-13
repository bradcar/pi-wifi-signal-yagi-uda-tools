
#================================================================
#Calibration Complete!
# Copy and paste these declarations into the code that uses the LIS3MDL:

# Hard-iron: Calibration constants from hard_only_calibrate_lis3mdl_test.py:
HARD_IRON_CALIBRATED_MAG_MIN = [-92.0199, 1.5639, -93.0868]
HARD_IRON_CALIBRATED_MAG_MAX = [7.9070, 101.2716, 7.2347]

# Soft-iron: Calibration constants from hard_soft_calibrate_lis3mdl_test.py:
SOFT_IRON_MATRIX = [
    [1.007, 0.043, -0.004],
    [0.043, 1.015, 0.002],
    [-0.004, 0.002, 1.011]
]
