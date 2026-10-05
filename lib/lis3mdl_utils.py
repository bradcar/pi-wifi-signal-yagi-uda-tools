# lis3mdl_utils.py
import math
import adafruit_lis3mdl
from lis3mdl_calibration_parameters import X_OFFSET, Y_OFFSET, Z_OFFSET, SOFT_IRON_MATRIX, LOCAL_MAGNETIC_DECLINATION


def init_lis3mdl(i2c):
    """
    Initialize LIS3MDL
    Args:
        i2c: bus

    Returns:
        sensor: LIS3MDL sensor or None
    """
    try:
        sensor = adafruit_lis3mdl.LIS3MDL(i2c)
        print("Successful LIS3MDL Magnetometer Init\n")
        return sensor
    except Exception as e:
        print(f"WARNING: LIS3MDL Init Failed: {e}\n")
        return None


def get_compass_8pt_string(heading: float):
    """
    Args:
        heading: compass heading

    Returns:
        string: 2-letter acronym for compass heading (N, NW, NE, E, SE, SW, NW, NE, SE, SW)
    """
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


def get_compass_heading(sensor, magnetic_declination: float = LOCAL_MAGNETIC_DECLINATION):
    """
    Gets a calibrated compass heading from the X-Y magnetometer axes.
    For compass angles only need hard-iron offsets.

    Assumes:
      - Sensor is kept level relative to the ground.
      - X_OFFSET and Y_OFFSET accurately represent the hard-iron center.
      - +Y axis points toward the front of the device (North at 0°).

    Args:
        sensor: LIS3MDL sensor instance or None
        magnetic_declination: Magnetic declination angle in degrees (defaults to MAG_DECL parameter)
    Returns
        float: compass heading in degrees
    """
    if sensor is None:
        return None

    try:
        raw_reading = sensor.magnetic
        if raw_reading is None or None in raw_reading:
            return None

        mag_x, mag_y, _ = raw_reading

        # Apply hard-iron offset correction
        cal_x = mag_x - X_OFFSET
        cal_y = mag_y - Y_OFFSET

        # Calculate magnetic heading angle (North = +Y = 0°, East = +X = 90°)
        heading_deg = math.degrees(math.atan2(cal_x, cal_y))

        # Apply magnetic declination
        if mag_decl is not None:
            heading_deg += magnetic_declination

        # Normalize  to 0.0 <= heading < 360.0, clean up negative floating-point artifacts (-0.0 -> 0.0)
        heading = heading_deg % 360.0
        if heading < 0:
            heading += 360.0

        return heading

    except (ValueError, TypeError, OSError) as e:
        print(f"Magnetometer Read Error: {e}")
        return None


def get_compass_heading_hard_soft_corrections(sensor, magnetic_declination: float = LOCAL_MAGNETIC_DECLINATION):
    """
    Calculates geographic heading using 3D hard-iron offsets, a 3x3 soft-iron matrix,
    and local magnetic declination.

    Assumes:
      - Sensor is kept level relative to the ground.
      - +Y axis points toward the front of the device.

    Args:
        sensor: LIS3MDL sensor instance or None
        magnetic_declination: Magnetic declination angle in degrees (defaults to MAG_DECL parameter)

    Returns:
        float: Geographic heading in degrees [0, 360), or None on error
    """
    if sensor is None:
        return None

    try:
        mag_x, mag_y, mag_z = sensor.magnetic
        if None in (mag_x, mag_y, mag_z):
            return None

        # Apply 3D Hard-iron offsets
        hi_cal = [
            mag_x - X_OFFSET,
            mag_y - Y_OFFSET,
            mag_z - Z_OFFSET
        ]

        # Apply 3x3 Soft-iron matrix
        cal_data = [0.0, 0.0, 0.0]
        for i in range(3):
            cal_data[i] = (
                    (SOFT_IRON_MATRIX[i][0] * hi_cal[0]) +
                    (SOFT_IRON_MATRIX[i][1] * hi_cal[1]) +
                    (SOFT_IRON_MATRIX[i][2] * hi_cal[2])
            )

        # Calculate heading angle (matching original implementation: -1 * atan2(X, Y))
        heading = -1.0 * math.degrees(math.atan2(cal_data[0], cal_data[1]))

        # Apply magnetic declination
        if magnetic_declination is not None:
            heading += magnetic_declination

        # Normalize  to 0.0 <= heading < 360.0, clean up negative floating-point artifacts (-0.0 -> 0.0)
        heading = heading % 360.0
        if heading < 0:
            heading += 360.0

        return heading

    except (ValueError, TypeError, OSError) as e:
        print(f"Magnetometer Read Error: {e}")
        return None
