#!/usr/bin/python3
import time
from gpiozero import Button

# Configure Button on GPIO 26 (Physical Pin 37)
# hold_time=1.0 matches your updated configuration threshold
button0 = Button(26, pull_up=True, bounce_time=0.1, hold_time=1.0)

# Global tracking flags
long_press = False
short_press = False
button_press_time = 0.0  # Tracks the precise unix epoch down-stroke timestamp

# INTERRUPT BACKGROUND HANDLERS
def on_button_pressed():
    """Fires instantly on the falling edge when the button is pushed down."""
    global button_press_time
    button_press_time = time.time()  # Capture baseline system time


def on_button_released():
    """Fires on the rising edge when the finger leaves the button."""
    global short_press, long_press, button_press_time

    # Compute duration of button press
    if button_press_time > 0.0:
        duration = time.time() - button_press_time
    else:
        duration = 0.0  # Fallback safety case

    # Reset timestamp for next hardware event
    button_press_time = 0.0

    # determine if long or short press
    if duration >= button0.hold_time:
        long_press = True
        print(f"\n ====== Long Press Detected ({duration:.4f}s).")
    else:
        short_press = True
        print(f"\n ------ Short Press Detected ({duration:.4f}s).")


# Register background event listeners
button0.when_pressed = on_button_pressed
button0.when_released = on_button_released


# MAIN APPLICATION LOOP
def main():
    global short_press, long_press

    print("      GPIO 26 Standalone Button Press Test Loop         ")
    print("========================================================")
    print(f"Hold Time Threshold: {button0.hold_time}s | Bounce Window:0.1s")
    print("Monitoring events... Press Ctrl+C to terminate script.\n")

    try:
        while True:
            if long_press:
                print(f"  -> MAIN LOOP STATUS: Reverting to Probe Mode (Long Press Handled)")

                # Reset flags synchronously inside the loop processing block
                long_press = False
                short_press = False

            elif short_press:
                print(f"  ->Executing full metrics (Short Press Handled)")

                # Reset single action flag synchronously
                short_press = False

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nExiting button test script cleanly.")


if __name__ == "__main__":
    main()