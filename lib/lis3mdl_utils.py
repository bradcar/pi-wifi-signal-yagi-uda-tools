# lis3mdl_utils.py
import math
import adafruit_lis3mdl
from lis3mdl_calibration_parameters import X_OFFSET, X_SCALE, Y_OFFSET, Y_SCALE

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


def get_compass_heading(sensor):
    """
    Gets a calibrated compass heading from the X-Y magnetometer axes.
    For compass angles only need hard-iron offsets.
    Args:
        sensor: LIS3MDL sensor or None
    Returns
        float: compass heading in degrees
    """
    if sensor is None:
        return None
    try:
        mag_x, mag_y, mag_z = sensor.magnetic

        if None in (mag_x, mag_y, mag_z):
            return None

        # APPLY HARD-IRON SPATIAL CALIBRATION
        # Shift data cluster centers to 0.0 and scale to a perfect 1.0 radius sphere
        cal_x = (mag_x - X_OFFSET) / X_SCALE
        cal_y = (mag_y - Y_OFFSET) / Y_SCALE

        # use calibrated vectors into the arc-tangent calculator, notice only hard-iron calibration needed due to atan2
        heading_rad = math.atan2(cal_y, cal_x)
        heading_deg = math.degrees(heading_rad)

        # Normalize to 0-360°
        heading = (heading_deg + 360.0) % 360.0
        return heading
    except (ValueError, TypeError, OSError) as e:
        print(f"Magnetometer Read Error: {e}")
        return None
