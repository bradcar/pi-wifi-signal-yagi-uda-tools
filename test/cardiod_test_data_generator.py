# cardiod_test_data_generator.py
"""
Creates a mock antenna cardiod shape of RSSI signal at full 360 degrees.
"""
import math

# Initialize a global lookup array where index = degree heading (0-359)
MOCK_SIGNAL_ARRAY = [-99.0] * 360


def setup_mock_environment():
    """
    Populates the lookup array with a  cardiod mock signal profile.
    - Peak strength of -20 dBm at due South (180 degrees).
    - Smoothly falls off to -80 dBm across most of the environment.
    - Drops to a hard dead-zone (-99 dBm) in only one direction (due North / 0 degrees).
    """
    target_heading = 180  # Access point direction (South)
    peak_strength = -50.0  # Maximum signal strength
    floor_strength = -80.0  # Standard background fall-off limit
    dead_zone_heading = 0  # Only direction with absolute silence (-99 dBm)

    # Calculate the total span of dBm loss from peak to floor (e.g., 60 dBm drop)
    total_drop = abs(floor_strength - peak_strength)

    for degree in range(360):
        # Calculate distance from the transmitter (180°)
        # angle_diff ranges from 0 (at 180°) to 180 (at 0°)
        angle_diff = min(abs(degree - target_heading), 360 - abs(degree - target_heading))

        # Map the distance to a smooth drop *downward* from -20 dBm
        fall_off_factor = angle_diff / 180.0
        calculated_signal = peak_strength - (fall_off_factor * total_drop)

        # create sharp dead-zone at exactly one direction (due North / 0 degrees)
        if abs(degree - dead_zone_heading) <= 1:
            MOCK_SIGNAL_ARRAY[degree] = -99.0
        else:
            MOCK_SIGNAL_ARRAY[degree] = round(calculated_signal, 1)


# Initialize the array values on script load
setup_mock_environment()


def measured_signal_strength(current_heading: float):
    """
    Simulates checking the network signal strength at a specific physical heading.

    :param current_heading: The live compass angle provided by the IMU sensor.
    :return: tuple (heading, strength)
             heading: normalized integer degree (0-359)
             strength: float dBm value mapped from the profile array
    """
    if current_heading is None:
        return 0, -99.0

    heading_idx = int(round(current_heading)) % 360
    strength = MOCK_SIGNAL_ARRAY[heading_idx]

    return heading_idx, strength


def main():
    print("Create cardiod Antenna Strength pattern for testing...\n")
    print("Signal strength at sample directions:")
    print("-" * 45)

    # Test sample directions to confirm the new asymmetrical profile
    test_angles = [180, 135, 90, 45, 5, 0, 355]
    for test_angle in test_angles:
        heading, strength = measured_signal_strength(test_angle)
        print(f"Heading: {heading:>3}°  --> Simulated RSSI: {strength:>6.1f} dBm")


if __name__ == "__main__":
    main()