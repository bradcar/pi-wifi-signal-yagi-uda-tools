"""
dowload_file_utils.py


"""
import os
import urllib.request
import urllib.error
from urllib.parse import urlparse


def download_file(url_string, destination_directory="/home/pi/downloads", timeout=5):
    """
    Downloads log file directly from the Pi Pico AP.
    Saves it using the Pico's dynamic versioned filename and validates file size.

    5 second timeout
    """
    # Expand user shortcuts ('~/')
    destination_directory = os.path.expanduser(destination_directory)

    # Ensure destination directory exists
    try:
        os.makedirs(destination_directory, exist_ok=True)
    except PermissionError:
        print(f"download_file ERROR: Permission denied creating directory: '{destination_directory}'")
        return False, None
    except OSError as e:
        print(f"download_file ERROR: Unable to create directory '{destination_directory}': {e}")
        return False, None

    # Verify write permissions before opening connection
    if not os.access(destination_directory, os.W_OK):
        print(f"download_file ERROR: Directory exists but is not writable: '{destination_directory}'")
        return False, None

    print(f"download_file: Download from {url_string}, timeout = {timeout} secs")

    local_filename = None
    try:
        with urllib.request.urlopen(url_string, timeout=timeout) as response:
            if response.status == 200:

                # Get dynamic Content-Disposition filename
                filename = None
                content_disposition = response.headers.get("Content-Disposition")

                if content_disposition and "filename=" in content_disposition:
                    try:
                        # Strips out quotes and pulls: flight_log.zip or flight_log (1).zip
                        filename = content_disposition.split("filename=")[1].strip('"\'')
                    except IndexError:
                        filename = None

                # Fallbacks if header parsing error
                if not filename:
                    parsed_url = urlparse(url_string)
                    filename = os.path.basename(parsed_url.path)
                if not filename or filename == "download":
                    filename = "unknown_name_log.zip"

                local_filename = os.path.join(destination_directory, filename)

                # Track expected size vs. received size
                expected_size = response.headers.get("Content-Length")
                if expected_size:
                    expected_size = int(expected_size)
                    print(f"download_file: Expected File Size: {expected_size} bytes")

                total_bytes_received = 0
                download_complete = False

                # Chunked stream write with cleanup protection
                try:
                    with open(local_filename, 'wb') as local_file:
                        while True:
                            chunk = response.read(4096)
                            if not chunk:
                                break
                            local_file.write(chunk)
                            total_bytes_received += len(chunk)
                    download_complete = True
                finally:
                    # Remove incomplete file if an exception aborted write before loop finished
                    if not download_complete and local_filename and os.path.exists(local_filename):
                        os.remove(local_filename)

                # Catch signal loss drop-offs mid-stream
                if expected_size and total_bytes_received != expected_size:
                    print(
                        f"download_file: TRANSFER ERROR: Corrupted download. Received {total_bytes_received}/{expected_size} bytes.")
                    # Clean up the broken partial file so it doesn't clutter filesystem
                    if os.path.exists(local_filename):
                        os.remove(local_filename)
                    return False, filename

                print(f"download_file SUCCESS: File saved as {local_filename} ({total_bytes_received} bytes)")
                return True, filename
            else:
                print(f"download_file FAILED: Server responded with HTTP Status {response.status}")
                return False, None

    except urllib.error.URLError as e:
        print(f"download_file: NETWORK ERROR: Could not reach download webpage: {e.reason}\n")
        return False, None
    except PermissionError:
        print(f"download_file ERROR: Permission denied writing file to '{local_filename}'\n")
        return False, None
    except Exception as e:
        print(f"download_file: ERROR during transfer: {e}\n")
        return False, None