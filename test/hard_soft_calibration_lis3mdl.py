# hard_soft_calibration_lis3mdl.py
"""
3D Combined Hard-Iron and Soft-Iron Calibration Tool for LIS3MDL,

To be used as electronic compasses, magnetometers need to be calibrated in their final device.
The calibration process corrects for local magnetic fields and field distortions due to nearby conductors and
ferrous materials.

Collects 3D magnetometer data points over a timed window (typically 30 seconds to 120 seconds), fits an ellipsoid,
and outputs copy-paste-able hard-iron offsets and a 3x3 soft-iron transformation matrix.
"""

import board
import json
import math
import os
import time
from datetime import datetime

import adafruit_lis3mdl
import matplotlib
import numpy as np

matplotlib.use("Agg")  # Non-interactive backend (works over SSH without GUI)
import matplotlib.pyplot as plt

# Initialize magnetometer sensor
i2c = board.I2C()
magnetometer = adafruit_lis3mdl.LIS3MDL(i2c)

PLOT_FILE_NAME = "calibration_plot"
CALIBRATION_FILE_NAME = "calibration_values"
PARAMETER_FILE_NAME = "calibration_parameters"


def create_output_directory(dir_name="calibration_output_files"):
    """Creates the calibration output directory if it does not exist and returns its path."""
    os.makedirs(dir_name, exist_ok=True)
    return dir_name


def collect_samples(runtime_seconds=60, sample_delay=0.05):
    """Collects (x, y, z) points and streams LOG_DATA formatted lines to console."""
    samples = []
    print(f"Collecting data for {runtime_seconds} seconds.")
    print("-> Rotate sensor in ALL 3D directions (spin 360°, flip upside down).")
    print("----------------------------------------------------------------")

    start_time = time.time()
    last_print = time.time()

    # Dynamic bounding box tracks extremes during calibration
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    while time.time() - start_time < runtime_seconds:
        x, y, z = magnetometer.magnetic
        if None not in (x, y, z):
            samples.append((x, y, z))

            # Update running min/max
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            min_z, max_z = min(min_z, z), max(max_z, z)

        elapsed = time.time() - start_time
        remaining = max(0.0, runtime_seconds - elapsed)

        # Print formatted log string twice per second
        if time.time() - last_print > 0.4 and samples:
            rx, ry, rz = samples[-1]

            # Normalize raw values onto a [-1.0, +1.0] unit span
            span_x = (max_x - min_x) if max_x != min_x else 1.0
            span_y = (max_y - min_y) if max_y != min_y else 1.0
            span_z = (max_z - min_z) if max_z != min_z else 1.0

            mx = 2.0 * (rx - min_x) / span_x - 1.0
            my = 2.0 * (ry - min_y) / span_y - 1.0
            mz = 2.0 * (rz - min_z) / span_z - 1.0

            print(
                f"{remaining:4.1f}s remain, Raw: ({rx:6.1f}, {ry:6.1f}, {rz:6.1f}) -> "
                f"Mapped: ({mx:+5.2f}, {my:+5.2f}, {mz:+5.2f})"
            )
            last_print = time.time()

        time.sleep(sample_delay)

    return samples


def fit_ellipsoid_and_compute_matrices(samples):
    """Computes 3D Hard-Iron Offsets and 3x3 Soft-Iron Matrix from collected points."""
    n = len(samples)
    if n < 50:
        raise ValueError("Not enough samples collected for reliable calibration.")

    xs = [p[0] for p in samples]
    ys = [p[1] for p in samples]
    zs = [p[2] for p in samples]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)

    hard_iron_x = (max_x + min_x) / 2.0
    hard_iron_y = (max_y + min_y) / 2.0
    hard_iron_z = (max_z + min_z) / 2.0

    centered = [
        (p[0] - hard_iron_x, p[1] - hard_iron_y, p[2] - hard_iron_z)
        for p in samples
    ]

    rad_x = (max_x - min_x) / 2.0
    rad_y = (max_y - min_y) / 2.0
    rad_z = (max_z - min_z) / 2.0
    avg_radius = (rad_x + rad_y + rad_z) / 3.0

    scale_x = avg_radius / rad_x if rad_x != 0 else 1.0
    scale_y = avg_radius / rad_y if rad_y != 0 else 1.0
    scale_z = avg_radius / rad_z if rad_z != 0 else 1.0

    var_x = sum(c[0] ** 2 for c in centered) / n
    var_y = sum(c[1] ** 2 for c in centered) / n
    var_z = sum(c[2] ** 2 for c in centered) / n

    cov_xy = sum(c[0] * c[1] for c in centered) / n
    cov_xz = sum(c[0] * c[2] for c in centered) / n
    cov_yz = sum(c[1] * c[2] for c in centered) / n

    soft_xy = (-cov_xy / math.sqrt(var_x * var_y) if (var_x * var_y) > 0 else 0.0)
    soft_xz = (-cov_xz / math.sqrt(var_x * var_z) if (var_x * var_z) > 0 else 0.0)
    soft_yz = (-cov_yz / math.sqrt(var_y * var_z) if (var_y * var_z) > 0 else 0.0)

    soft_iron_matrix = [
        [round(scale_x, 4), round(soft_xy, 4), round(soft_xz, 4)],
        [round(soft_xy, 4), round(scale_y, 4), round(soft_yz, 4)],
        [round(soft_xz, 4), round(soft_yz, 4), round(scale_z, 4)],
    ]

    hard_iron_offsets = [
        round(hard_iron_x, 4),
        round(hard_iron_y, 4),
        round(hard_iron_z, 4),
    ]
    min_vals = [round(min_x, 4), round(min_y, 4), round(min_z, 4)]
    max_vals = [round(max_x, 4), round(max_y, 4), round(max_z, 4)]

    return hard_iron_offsets, soft_iron_matrix, min_vals, max_vals


def save_calibration_data(raw_samples, mag_min, mag_max, filename):
    """Saves raw_samples, mag_min, and mag_max into a JSON calibration file."""
    data = {
        "raw_samples": raw_samples,
        "mag_min": mag_min,
        "mag_max": mag_max,
    }
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)
    print(f"Saved calibration data to {filename}")


def load_calibration_data(filename):
    """Loads raw_samples, mag_min, and mag_max from a JSON calibration file."""
    with open(filename, "r") as f:
        data = json.load(f)
    print(f"Loaded calibration data from {filename}")
    return data["raw_samples"], data["mag_min"], data["mag_max"]


def plot_calibration(calibration_file, plot_filename):
    # Reads samples and min/max bounds directly from the saved calibration file
    samples, mag_min, mag_max = load_calibration_data(calibration_file)

    # Generates 3D before/after calibration plot and saves it to a file.
    rx = [p[0] for p in samples]
    ry = [p[1] for p in samples]
    rz = [p[2] for p in samples]

    # Map raw samples to unit sphere (-1.0 to +1.0) using min/max bounds
    span_x = mag_max[0] - mag_min[0] if mag_max[0] != mag_min[0] else 1.0
    span_y = mag_max[1] - mag_min[1] if mag_max[1] != mag_min[1] else 1.0
    span_z = mag_max[2] - mag_min[2] if mag_max[2] != mag_min[2] else 1.0

    mx = [2.0 * (x - mag_min[0]) / span_x - 1.0 for x in rx]
    my = [2.0 * (y - mag_min[1]) / span_y - 1.0 for y in ry]
    mz = [2.0 * (z - mag_min[2]) / span_z - 1.0 for z in rz]

    fig = plt.figure(figsize=(12, 5))
    fig.suptitle("Magnetometer Calibration Results", fontsize=14, fontweight="bold")

    # Create subplot for Raw Ellipsoid
    ax1 = fig.add_subplot(121, projection="3d")
    ax1.scatter(rx, ry, rz, c=rz, cmap="coolwarm", s=15, alpha=0.8)
    print("\nCreate subplot for BEFORE: Raw Magnetometer Data")
    ax1.set_title("BEFORE: Raw Magnetometer Data")

    # Force equal aspect ratio on raw plot so distortion is visually obvious
    span_rx = max(rx) - min(rx)
    span_ry = max(ry) - min(ry)
    span_rz = max(rz) - min(rz)
    max_range = max(span_rx, span_ry, span_rz) / 2.0

    # Individual midpoints preserve local coordinate shifts
    mid_x = (max(rx) + min(rx)) / 2.0
    mid_y = (max(ry) + min(ry)) / 2.0
    mid_z = (max(rz) + min(rz)) / 2.0

    ax1.set_xlim(mid_x - max_range, mid_x + max_range)
    ax1.set_ylim(mid_y - max_range, mid_y + max_range)
    ax1.set_zlim(mid_z - max_range, mid_z + max_range)
    ax1.set_box_aspect([1, 1, 1])

    ax1.set_xlabel("X (µT)")
    ax1.set_ylabel("Y (µT)")
    ax1.set_zlabel("Z (µT)")

    # Create subplot for Calibrated Sphere
    ax2 = fig.add_subplot(122, projection="3d")
    ax2.scatter(mx, my, mz, c=mz, cmap="viridis", s=15, alpha=0.8)
    print("Create subplot for AFTER: Normalized Calibrated Sphere")
    ax2.set_title("AFTER: Normalized Calibrated Sphere")
    ax2.set_xlim(-1.1, 1.1)
    ax2.set_ylim(-1.1, 1.1)
    ax2.set_zlim(-1.1, 1.1)
    ax2.set_box_aspect([1, 1, 1])

    plt.tight_layout()
    plt.savefig(plot_filename, dpi=150)
    print(f"\nSaved calibration plot to {plot_filename}")
    plt.close(fig)


def print_and_save_parameters(mag_min, mag_max, matrix, filepath):
    """Formats calibration parameters, prints them to the console, and writes them to a file."""
    output_lines = [
        "\n#================================================================",
        "#Calibration Complete!",
        "# Copy and paste these declarations into the code that uses the LIS3MDL:\n",
        "# Hard-iron: Calibration constants from hard_only_calibrate_lis3mdl_test.py:",
        f"HARD_IRON_CALIBRATED_MAG_MIN = [{mag_min[0]:.4f}, {mag_min[1]:.4f}, {mag_min[2]:.4f}]",
        f"HARD_IRON_CALIBRATED_MAG_MAX = [{mag_max[0]:.4f}, {mag_max[1]:.4f}, {mag_max[2]:.4f}]\n",
        "# Soft-iron: Calibration constants from hard_soft_calibrate_lis3mdl_test.py:",
        "SOFT_IRON_MATRIX = [",
        f"    [{matrix[0][0]:.3f}, {matrix[0][1]:.3f}, {matrix[0][2]:.3f}],",
        f"    [{matrix[1][0]:.3f}, {matrix[1][1]:.3f}, {matrix[1][2]:.3f}],",
        f"    [{matrix[2][0]:.3f}, {matrix[2][1]:.3f}, {matrix[2][2]:.3f}]",
        "]",
    ]

    formatted_text = "\n".join(output_lines)

    # Print to console
    print(formatted_text)

    # Save to parameter text file
    with open(filepath, "w") as f:
        f.write(formatted_text + "\n")

    print(f"\nSaved calibration parameters to {filepath}")


def evaluate_calibration_quality(calibrated_samples, target_radius=1.0):
    """Calculates radial error, RMSE, oblateness (flattening), and fractional anisotropy.

    :param calibrated_samples: Nx3 array or list of (x, y, z) transformed
    points.
    :param target_radius: Expected magnitude (1.0 for unit sphere).
    """
    pts = np.array(calibrated_samples)

    # Calculate Magnitudes (Radii) for each sample point
    radii = np.linalg.norm(pts, axis=1)

    # Goodness Metrics (Radial Residuals)
    mape = np.mean(np.abs(radii - target_radius) / target_radius) * 100.0
    rmse = np.sqrt(np.mean((radii - target_radius) ** 2))
    nrmse = rmse / target_radius

    # Shape / Oblateness Metrics via Principal Covariance Eigenvalues
    cov_matrix = np.cov(pts.T)
    eigenvalues = np.sort(np.linalg.eigvalsh(cov_matrix))[::-1]  # Sort descending

    a, b, c = np.sqrt(np.maximum(eigenvalues, 1e-12))

    flattening = (a - c) / a if a > 0 else 0.0

    mean_lambda = np.mean(eigenvalues)
    fa = np.sqrt(1.5) * (
            np.sqrt(np.sum((eigenvalues - mean_lambda) ** 2))
            / np.sqrt(np.sum(eigenvalues ** 2))
    )

    print("\n=== Calibration Quality Metrics ===")
    print(f"Mean Absolute Percentage Error (MAPE) : {mape:.2f}%")
    print(f"Normalized RMSE (NRMSE)               : {nrmse:.4f}")
    print(f"Semi-Axes Ratio (c/a)                 : {c / a:.4f} (Target: 1.0000)")
    print(f"Oblateness / Flattening (f)           : {flattening:.4f} (Target: 0.0000)")
    print(f"Fractional Anisotropy (FA)            : {fa:.4f} (Target: 0.0000)\n")

    return {
        "mape": mape,
        "nrmse": nrmse,
        "flattening": flattening,
        "fa": fa,
    }


def main():
    print("Preparing calibration. Get ready to rotate the sensor in 3D...(sleep for 3 seconds)")
    time.sleep(5)

    # Collect samples and fit data, recommend 120 seconds collection_seconds
    collection_seconds = 120
    raw_samples = collect_samples(runtime_seconds=collection_seconds)
    offsets, matrix, mag_min, mag_max = fit_ellipsoid_and_compute_matrices(raw_samples)

    # Create output directory and timestamp for output files
    output_dir = create_output_directory()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\nSaving calibration data in directory ./{output_dir}, files will append {timestamp} string")

    # Print Results Formatted for Direct Copy-Paste
    param_file = os.path.join(output_dir, f"{PARAMETER_FILE_NAME}_{timestamp}.py")
    print_and_save_parameters(mag_min, mag_max, matrix, param_file)

    # Save calibration data to file
    calibration_file = os.path.join(output_dir, f"{CALIBRATION_FILE_NAME}_{timestamp}.json")
    save_calibration_data(raw_samples, mag_min, mag_max, calibration_file)

    # Compute target average radius in uT from raw bounding limits
    target_r = ((mag_max[0] - mag_min[0])
                + (mag_max[1] - mag_min[1])
                + (mag_max[2] - mag_min[2])
                ) / 6.0

    # Apply hard/soft-iron matrix AND normalize down to unit sphere (R = 1.0)
    calibrated_samples = []
    for rx, ry, rz in raw_samples:
        cx = rx - offsets[0]
        cy = ry - offsets[1]
        cz = rz - offsets[2]
        mx = matrix[0][0] * cx + matrix[0][1] * cy + matrix[0][2] * cz
        my = matrix[1][0] * cx + matrix[1][1] * cy + matrix[1][2] * cz
        mz = matrix[2][0] * cx + matrix[2][1] * cy + matrix[2][2] * cz

        # Divide by target_r so point magnitudes evaluate cleanly around 1.0
        calibrated_samples.append((mx / target_r, my / target_r, mz / target_r))

    # Evaluate Calibration Quality
    evaluate_calibration_quality(calibrated_samples, target_radius=1.0)

    # Plot using the stored calibration file
    plot_file = os.path.join(output_dir, f"{PLOT_FILE_NAME}_{timestamp}.png")
    plot_calibration(calibration_file, plot_file)


if __name__ == "__main__":
    main()
