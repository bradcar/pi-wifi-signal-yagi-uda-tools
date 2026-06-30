# pi_zero_utils.py
"""
General purpose Pi Zero functions
"""
import signal
from contextlib import contextmanager


def pico_temperature():
    """ Reads system temperature as substitute for Pico ADC(4) """
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            celsius = float(f.read()) / 1000.0
        return celsius
    except Exception:
        return None


@contextmanager
def timeout(seconds, error_message="Timed out"):
    def signal_handler(signum, frame):
        raise TimeoutError(f"{error_message}")

    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
