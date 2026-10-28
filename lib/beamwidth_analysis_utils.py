#
"""
beamwidth_analysis_utils.py

Beamwidth Analysis utilities for Antenna Pattern Analysis Library using NumPy.
Designed for analysis 360-degree RSSI sweeps (1° increments) on Pi Zero 2W with Yagi-Uda directional antenna.

Functions:
    smooth_signal_history_gaussian()
        Circular Gaussian smoothing with circular gap interpolation.

    calculate_beam_statistics()
        Calculates RSSI dynamic range, circular standard deviation, excess kurtosis, and a heuristic lobe-validity flag.

    calculate_half_power_bandwidth()
        Calculates the -3 dB half-power beamwidth (HPBW), including sub-degree interpolation of both cutoff headings.

    ADDED PRINT FUNCTION TO TEST CODE ON MANY CSVS - Doesn't seem like this code adds much value
    def batch_analyze_saved_csv_files(log_directory_path, sigma, window_length):

Important:
    - Input arrays must contain exactly 360 samples.
    - Index 0 corresponds to heading 0 degrees.
    - Values <= -120.0 dBm are treated as missing/uninitialized.
    - NaN and infinite values are treated as missing.
    - Interpolated values are not considered measured observations.
    - The "snr" result key is retained for compatibility, but it represents RSSI dynamic range, not a true noise-based SNR.
    - The lobe-validity flag is heuristic and must be validated against measured antenna patterns before operational use.

TODOs
*
"""

_EXPECTED_SAMPLE_COUNT = 360
_MISSING_RSSI_THRESHOLD = -120.0
_MINIMUM_VALID_SAMPLES = 10
_MINIMUM_WINDOW_LENGTH = 3
_MAXIMUM_WINDOW_LENGTH = 359


def _prepare_signal_history(signal_history):
    """
    Validate and copy a 360-sample RSSI history.

    Returns:
        signal_array: float array, shape (360)
        valid_mask: True for finite, initialized RSSI samples

    Raises:
        ValueError: If the input is not a one-dimensional array of exactly 360 samples.
    """
    signal_array = np.asarray(signal_history, dtype=float)
    if signal_array.ndim != 1 or signal_array.size != _EXPECTED_SAMPLE_COUNT:
        raise ValueError(f"signal_history must be a 1D array of exactly {_EXPECTED_SAMPLE_COUNT} samples")

    signal_array = signal_array.copy()
    valid_mask = np.isfinite(signal_array) & (signal_array > _MISSING_RSSI_THRESHOLD)
    return signal_array, valid_mask


def _circular_interpolate_missing(signal_array, valid_mask):
    """
    Fill missing samples by linear interpolation around a 360-degree circle.
    This function does not modify the input array.

    If fewer than two valid samples exist, no meaningful interpolation can be performed. In that case, a copy of the input is returned.
    """
    interpolated_array = signal_array.copy()
    valid_indices = np.flatnonzero(valid_mask)
    if valid_indices.size < 2:
        return interpolated_array

    missing_indices = np.flatnonzero(~valid_mask)
    if missing_indices.size == 0:
        return interpolated_array

    # Circular interpolation treating 359° and 0° as adjacent points
    interpolated_array[missing_indices] = np.interp(
        missing_indices, valid_indices, signal_array[valid_indices], period=float(_EXPECTED_SAMPLE_COUNT)
    )
    return interpolated_array


def _validate_smoothing_parameters(window_length, sigma):
    """ Validate Gaussian smoothing parameters and return an odd window length no larger than 359 samples."""
    if isinstance(window_length, (bool, np.bool_)) or not isinstance(window_length, (int, np.integer)):
        raise ValueError("window_length must be an integer")
    if window_length < _MINIMUM_WINDOW_LENGTH:
        raise ValueError(f"window_length must be at least {_MINIMUM_WINDOW_LENGTH}")

    sigma = float(sigma)
    if not np.isfinite(sigma) or sigma <= 0.0:
        raise ValueError("sigma must be a finite positive number")

    if window_length % 2 == 0:
        window_length += 1
    return min(window_length, _MAXIMUM_WINDOW_LENGTH), sigma


def smooth_signal_history_gaussian(signal_history, window_length=15, sigma=3.0):
    """
        Smooth a 360-degree RSSI history using a circular Gaussian kernel.
        Missing samples (<= -120 dBm, NaN, or infinite values) are interpolated circularly before smoothing.
        The original input is not modified.

        Note:
            Gaussian smoothing can reduce narrow peaks and change measured beamwidth.

        Args:
            signal_history: One-dimensional array containing 360 RSSI samples.
            window_length: Gaussian kernel length; even values are increased to the next odd value. Maximum length is 359.
            sigma: Gaussian standard deviation in sample units.

        Returns:
            A float NumPy array of length 360.

            If all samples are missing, the returned array preserves those missing values.
            If fewer than two samples are valid, the original signal values are returned without smoothing.

        Raises:
            ValueError: For invalid array dimensions, array length, or smoothing parameters.
        """
    signal_array, valid_mask = _prepare_signal_history(signal_history)
    window_length, sigma = _validate_smoothing_parameters(window_length, sigma)

    if np.count_nonzero(valid_mask) < 2:
        return signal_array

    filled_signal = _circular_interpolate_missing(signal_array, valid_mask)
    half_window = window_length // 2
    x_indices = np.arange(-half_window, half_window + 1, dtype=float)

    gaussian_kernel = np.exp(-0.5 * (x_indices / sigma) ** 2)
    kernel_sum = gaussian_kernel.sum()
    if not np.isfinite(kernel_sum) or kernel_sum <= 0.0:
        raise ValueError("Gaussian kernel normalization failed")
    gaussian_kernel /= kernel_sum

    # Pad both ends circularly so convolution handles the 360-degree boundary smoothly
    padded_signal = np.concatenate((filled_signal[-half_window:], filled_signal, filled_signal[:half_window]))
    return np.convolve(padded_signal, gaussian_kernel, mode="valid")


def calculate_beam_statistics(signal_history):
    """
        Calculate descriptive statistics for a 360-degree RSSI pattern.

        Returns:
            dict containing:
                snr:
                    Compatibility key. This is peak-to-minimum RSSI dynamic range in dB, NOT a true noise-based SNR.

                rssi_dynamic_range_db:
                    Peak-to-minimum RSSI range in dB.

                circular_std:
                    Power-weighted circular standard deviation in degrees.

                excess_kurtosis:
                    Fisher excess kurtosis of the valid RSSI samples.

                is_valid_lobe:
                    Heuristic quality flag. It is not proof that the antenna pattern contains one clean main lobe.

                valid_sample_count:
                    Number of measured, initialized samples.

        Fewer than 10 valid samples produces a false validity flag and zero-valued descriptive statistics.

        Raises:
            ValueError: If signal_history is not exactly 360 samples.
        """
    signal_array, valid_mask = _prepare_signal_history(signal_history)
    valid_values = signal_array[valid_mask]
    valid_count = valid_values.size

    if valid_count < _MINIMUM_VALID_SAMPLES:
        return {
            "snr": 0.0,
            "rssi_dynamic_range_db": 0.0,
            "circular_std": 0.0,
            "excess_kurtosis": 0.0,
            "is_valid_lobe": False,
            "valid_sample_count": valid_count,
        }

    peak_rssi = valid_values.max()
    floor_rssi = valid_values.min()
    dynamic_range = peak_rssi - floor_rssi

    mean_value = valid_values.mean()
    centered = valid_values - mean_value
    variance = (centered ** 2).mean()

    if variance <= 0.0 or not np.isfinite(variance):
        kurtosis = 0.0
    else:
        kurtosis = (centered ** 4).mean() / (variance ** 2) - 3.0

    weights = 10.0 ** ((valid_values - peak_rssi) / 10.0)
    weight_sum = weights.sum()

    if weight_sum <= 0.0 or not np.isfinite(weight_sum):
        circular_std = float("nan")
    else:
        weights /= weight_sum
        angles = np.radians(np.flatnonzero(valid_mask).astype(float))
        mean_cos = (weights * np.cos(angles)).sum()
        mean_sin = (weights * np.sin(angles)).sum()
        resultant = np.hypot(mean_cos, mean_sin)
        clamped = min(max(resultant, 1e-10), 1.0)

        # Power-weighted circular standard deviation in degrees
        circular_std = np.degrees(np.sqrt(-2.0 * np.log(clamped)))

    is_valid = (dynamic_range >= 10.0) and (kurtosis > -0.5)

    return {
        "snr": float(dynamic_range),
        "rssi_dynamic_range_db": float(dynamic_range),
        "circular_std": float(circular_std),
        "excess_kurtosis": float(kurtosis),
        "is_valid_lobe": bool(is_valid),
        "valid_sample_count": int(valid_count),
    }


def _find_half_power_crossing(processed_signal, measured_mask, peak_idx, threshold, direction):
    """
        Find the first -3 dB crossing in one direction from the peak.

        Args:
            processed_signal_array: Smoothed or raw RSSI samples.
            measured_valid_mask: True only for original measured samples.
            peak_idx: Index of the selected peak.
            threshold_rssi: Peak RSSI minus 3 dB.
            direction: +1 for clockwise, -1 for counterclockwise.

        Returns:
            A float heading in [0, 360), or None if a crossing cannot be established from adjacent measured samples.

        Missing samples terminate the search.
        The function does not treat interpolated values as proof of a measured threshold crossing.
        """
    for offset in range(1, 180):
        current_idx = (peak_idx + direction * offset) % _EXPECTED_SAMPLE_COUNT
        previous_idx = (peak_idx + direction * (offset - 1)) % _EXPECTED_SAMPLE_COUNT

        # Guard: both bracketing samples must be genuinely measured (not interpolated gaps)
        if not measured_mask[previous_idx] or not measured_mask[current_idx]:
            return None

        prev_val = processed_signal[previous_idx]
        curr_val = processed_signal[current_idx]

        if curr_val <= threshold:
            denominator = curr_val - prev_val
            frac = 0.0 if denominator == 0.0 else (threshold - prev_val) / denominator
            frac = np.clip(frac, 0.0, 1.0)

            # Linear interpolation for sub-degree crossing precision
            return float((previous_idx + direction * frac) % _EXPECTED_SAMPLE_COUNT)
    return None


def calculate_half_power_bandwidth(signal_history, use_smoothing=True, window_length=15, sigma=3.0):
    """
        Calculate half-power beamwidth (HPBW) for a 360-degree RSSI sweep.

        The threshold is peak RSSI minus 3 dB. The peak is selected from the original measured samples, even when smoothing is enabled.

        Both cutoff crossings must be found, and each crossing must be bracketed by adjacent valid measured samples.
        Missing data cannot be treated as a measured threshold crossing.

        Args:
            signal_history: One-dimensional array containing 360 samples.
            use_smoothing: Apply circular Gaussian smoothing before finding the peak and cutoff crossings.
            window_length: Gaussian kernel length when smoothing is enabled.
            sigma: Gaussian standard deviation in sample units.

        Returns:
            (peak_degree,
                beamwidth_degrees,
                (left_cutoff_degree, right_cutoff_degree),
                beam_statistics)

            peak_degree:
                Peak heading in degrees, or None if insufficient data.

            beamwidth_degrees:
                Angular width between the left and right -3 dB crossings, measured clockwise across the main-lobe interval,
                or None if either crossing cannot be established.

            (left_cutoff_degree, right_cutoff_degree):
                Sub-degree crossing headings in [0, 360), or (None, None) when a reliable pair cannot be established.

            beam_statistics:
                Dictionary returned by calculate_beam_statistics().

        Raises:
            ValueError: If signal_history is not exactly 360 samples.
            ValueError: If smoothing parameters are invalid when smoothingis enabled.
        """
    signal_array, measured_mask = _prepare_signal_history(signal_history)
    beam_stats = calculate_beam_statistics(signal_array)

    if np.count_nonzero(measured_mask) < _MINIMUM_VALID_SAMPLES:
        return None, None, (None, None), beam_stats

    processed = smooth_signal_history_gaussian(signal_array, window_length,
                                               sigma) if use_smoothing else signal_array.copy()

    valid_indices = np.flatnonzero(measured_mask)
    peak_candidates = processed[valid_indices]
    if not np.all(np.isfinite(peak_candidates)):
        return None, None, (None, None), beam_stats

    # Restrict peak selection to measured samples to avoid selecting synthetic gaps
    peak_idx = int(valid_indices[peak_candidates.argmax()])
    threshold = processed[peak_idx] - 3.0

    right_crossing = _find_half_power_crossing(processed, measured_mask, peak_idx, threshold, direction=1)
    left_crossing = _find_half_power_crossing(processed, measured_mask, peak_idx, threshold, direction=-1)

    if left_crossing is None or right_crossing is None:
        return float(peak_idx), None, (None, None), beam_stats

    # Compute clockwise span handling 360° circular wrap-around
    beamwidth = (right_crossing - left_crossing) % float(_EXPECTED_SAMPLE_COUNT)
    return float(peak_idx), float(beamwidth), (float(left_crossing), float(right_crossing)), beam_stats


"""
batch_analyze_radar_csvs.py

Scans the radar log directory for saved 360-degree RSSI CSV files,
computes beam statistics and half-power beamwidth (HPBW) using Gaussian smoothing,
prints out analytical metrics, and generates before/after polar plots.
"""

from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt


def batch_analyze_saved_csv_files(log_directory_path, sigma, window_length):
    log_directory = Path(log_directory_path)
    if not log_directory.exists():
        print(f"Error: Log directory '{log_directory}' does not exist.")
        return

    csv_file_list = list(log_directory.glob("*.csv"))
    if not csv_file_list:
        print(f"No CSV files found in '{log_directory}'.")
        return

    print(f"Found {len(csv_file_list)} radar CSV file(s) to process.\n")
    print("=" * 70)

    for csv_file_path in csv_file_list:
        print(f"Analyzing file: {csv_file_path.name}")

        try:
            # Load CSV data created by np.savetxt (expects degree,rssi with header)
            loaded_data = np.loadtxt(csv_file_path, delimiter=",", skiprows=1)
            degrees_array = loaded_data[:, 0]
            rssi_history_array = loaded_data[:, 1]
        except Exception as error_message:
            print(f" -> Error reading {csv_file_path.name}: {error_message}\n")
            continue

        # 1. Compute Raw Statistics
        raw_beam_statistics = calculate_beam_statistics(rssi_history_array)

        # 2. Run HPBW and Smoothed Analysis
        peak_heading_degree, half_power_beamwidth_degrees, (left_cutoff_degree,
                                                            right_cutoff_degree), _ = calculate_half_power_bandwidth(
            rssi_history_array,
            use_smoothing=True,
            window_length=window_length,
            sigma=sigma
        )

        # 3. Compute Smoothed Statistics for comparison
        smoothed_rssi_array = smooth_signal_history_gaussian(
            rssi_history_array,
            window_length=window_length,
            sigma=sigma
        )
        smoothed_beam_statistics = calculate_beam_statistics(smoothed_rssi_array)

        # 4. Clean Print Layout
        print(f"   Raw Signal Statistics")
        print(f"   - Valid Sample Count   : {raw_beam_statistics['valid_sample_count']} / 360 samples")
        print(f"   - RSSI Dynamic Range   : {raw_beam_statistics['rssi_dynamic_range_db']:.0f} dB")
        print(f"   - Circular Std Dev     : {raw_beam_statistics['circular_std']:.0f}°")
        print(f"   - Excess Kurtosis      : {raw_beam_statistics['excess_kurtosis']:.2f}")
        print(f"   - Heuristic Valid Lobe : {raw_beam_statistics['is_valid_lobe']}")

        print(f"\n   Smoothed Analysis (sigma={sigma}, window_length={window_length})")
        print(f"   - Smoothed Dynamic Range: {smoothed_beam_statistics['rssi_dynamic_range_db']:.0f} dB")
        print(f"   - Smoothed Kurtosis     : {smoothed_beam_statistics['excess_kurtosis']:.2f}")
        if half_power_beamwidth_degrees is not None:
            print(f"   - Peak Heading          : {peak_heading_degree:.0f}°")
            print(f"   - Half-Power Beamwidth  : {half_power_beamwidth_degrees:.0f}°")
            print(f"   -3 dB Cutoff Crossings  : Left @ {left_cutoff_degree:.0f}°, Right @ {right_cutoff_degree:.0f}°")
        else:
            print(f"   - Peak Heading          : {peak_heading_degree if peak_heading_degree is not None else 'N/A'}°")
            print(f"   - Half-Power Beamwidth  : Unresolved (Main lobe too wide or cut off)")
        print("-" * 70)

        # Generate Before & After (Raw vs. Smoothed) Polar Plot
        smoothed_rssi_array = smooth_signal_history_gaussian(
            rssi_history_array,
            window_length=window_length,
            sigma=sigma
        )

        angles_in_radians = np.radians(degrees_array)

        # Mask uninitialized noise floor values (-120.0 dBm) so they don't drag down the center plot line
        raw_plot_values = np.where(rssi_history_array <= -120.0, np.nan, rssi_history_array)
        smoothed_plot_values = np.where(smoothed_rssi_array <= -120.0, np.nan, smoothed_rssi_array)

        figure, polar_axis = plt.subplots(subplot_kw={'projection': 'polar'}, figsize=(8, 8))

        # Plot Raw RSSI
        polar_axis.plot(
            angles_in_radians,
            raw_plot_values,
            label='Raw RSSI measurements',
            color='darkorange',
            alpha=0.6,
            linewidth=1.5
        )

        label_string = f"Smoothed RSSI (sigma={sigma}, window={window_length})"

        # Plot Smoothed RSSI
        polar_axis.plot(
            angles_in_radians,
            smoothed_plot_values,
            label=label_string,
            color='cyan',
            linewidth=2.5
        )

        # --- DRAW BEAMWIDTH & PEAK INDICATOR LINES ---
        min_radial_limit = polar_axis.get_rmin()
        max_radial_limit = polar_axis.get_rmax()

        # 1. Solid Red Line for Peak Heading
        if peak_heading_degree is not None:
            peak_rad = np.radians(peak_heading_degree)
            polar_axis.plot(
                [peak_rad, peak_rad],
                [min_radial_limit, max_radial_limit],
                color='red',
                linestyle='-',
                linewidth=2.0,
                label=f'Peak ({peak_heading_degree:.0f}°)'
            )

        # 2. Dotted Red Lines for Left and Right -3dB Cutoff Degrees
        if left_cutoff_degree is not None and right_cutoff_degree is not None:
            left_rad = np.radians(left_cutoff_degree)
            right_rad = np.radians(right_cutoff_degree)

            polar_axis.plot(
                [left_rad, left_rad],
                [min_radial_limit, max_radial_limit],
                color='red',
                linestyle=':',
                linewidth=1.5,
                label='-3dB Cutoffs'
            )
            polar_axis.plot(
                [right_rad, right_rad],
                [min_radial_limit, max_radial_limit],
                color='red',
                linestyle=':',
                linewidth=1.5
            )
        # ---------------------------------------------

        # Configure polar plot orientation (North 0° at top, clockwise sweep)
        polar_axis.set_theta_zero_location('N')
        polar_axis.set_theta_direction(-1)

        tick_angles_degrees = np.arange(0, 360, 15)
        polar_axis.set_thetagrids(tick_angles_degrees)

        plot_title = f"Wi_Fi RSSI Measured by Yagi Uda (peak at {peak_heading_degree if peak_heading_degree is not None else 'N/A'}°)\n{csv_file_path.stem}"
        polar_axis.set_title(plot_title, va='bottom', fontsize=11, color='black')
        polar_axis.legend(loc='upper right', bbox_to_anchor=(1.3, 0.03))

        # Style for dark background telemetry aesthetic
        polar_axis.tick_params(colors='gray', labelsize=9)
        polar_axis.grid(True, color='gray', alpha=0.4, linestyle='--')

        comparison_plot_path = csv_file_path.with_name(f"{csv_file_path.stem}_comparison.png")

        figure.savefig(comparison_plot_path, dpi=150, bbox_inches='tight')
        plt.close(figure)

        print(f" -> Saved comparison plot to: {comparison_plot_path.name}\n")


if __name__ == "__main__":
    # Point to existing log directory where CSVs are saved
    TARGET_LOG_DIRECTORY = "./"
    batch_analyze_saved_csv_files(TARGET_LOG_DIRECTORY, sigma=1.5, window_length=9)
