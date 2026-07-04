# radar_math_utils.py
import numpy as np


def calculate_peak_bounds(degrees) -> tuple[float, float, float]:
    """
    Calculates the indestructible circular vector mean and the true
    start (first_deg) and end (last_deg) boundaries using circular gap detection.
    """
    if len(degrees) == 0:
        return 0.0, 0.0, 0.0

    radians = np.deg2rad(degrees)

    # Calculate the angular mean
    sum_sin = np.sum(np.sin(radians))
    sum_cos = np.sum(np.cos(radians))
    mean_peak_degree = float(np.degrees(np.arctan2(sum_sin, sum_cos)) % 360)

    # Find the arc boundaries by locating the largest angular gap
    sorted_deg = np.sort(np.unique(degrees))
    if len(sorted_deg) == 1:
        first_deg = float(sorted_deg[0])
        last_deg = float(sorted_deg[0])
    else:
        gaps = np.diff(sorted_deg)
        wrap_gap = (sorted_deg[0] - sorted_deg[-1]) % 360
        all_gaps = np.append(gaps, wrap_gap)
        max_gap_idx = np.argmax(all_gaps)

        if max_gap_idx == len(all_gaps) - 1:
            first_deg = float(sorted_deg[0])
            last_deg = float(sorted_deg[-1])
        else:
            first_deg = float(sorted_deg[max_gap_idx + 1])
            last_deg = float(sorted_deg[max_gap_idx])

    return mean_peak_degree, first_deg, last_deg


def rotation_to_align_peak(compass, peak_rssi_angle):
    cw_flag = False
    ccw_flag = False
    if compass is not None and peak_rssi_angle is not None:
        diff = peak_rssi_angle - compass
        shortest_angle = (diff + 180) % 360 - 180
        if shortest_angle < 0:
            cw_flag = True
        elif shortest_angle > 0:
            ccw_flag = True
        else:
            pass
        return cw_flag, ccw_flag, shortest_angle
    else:
        return cw_flag, ccw_flag, 0
