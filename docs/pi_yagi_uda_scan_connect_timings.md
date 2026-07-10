Scan Rates:

PI ZERO 2 W TIMINGS (TODO)
=
LCD & USE_PROC_NET_WIRELESS=False in wifi_utils.py
 - Connected Mode,  ~ ?? ms  14-20 Hz  (USE_ASYNC_METRICS=True)
 - Connected Mode,  ~??? ms     3 Hz  (USE_ASYNC_METRICS=False)
 - Scan Mode,       ~??? ms     2 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

    Issues: with USE_PROC_NET_WIRELESS=True
    1. Memory reads occur regardless of updates
    2. >30% of reads show no updates.
       
Text & USE_PROC_NET_WIRELESS=True in wifi_utils.py
 - Connected Mode, actual ~ ?? ms 41 Hz  (at this rate, it won't return RX Rate (n/a in output))
 - Scan Mode,      actual ~??? ms  3 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

PI ZERO W TIMINGS
=
LCD & USE_PROC_NET_WIRELESS=False in wifi_utils.py
 - Connected Mode,  ~ 50-68 ms  14-20 Hz  (USE_ASYNC_METRICS=True)
 - Connected Mode,  ~300 ms     3 Hz  (USE_ASYNC_METRICS=False)
 - Scan Mode,       ~630 ms     2 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

    Issues: with USE_PROC_NET_WIRELESS=True
    1. Memory reads occur regardless of updates
    2. >30% of reads show no updates.


Text & USE_PROC_NET_WIRELESS=True in wifi_utils.py
 - Connected Mode, actual ~ 24 ms 41 Hz  (at this rate, it won't return RX Rate (n/a in output))
 - Scan Mode,      actual ~300 ms  3 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

Text & USE_PROC_NET_WIRELESS=False in wifi_utils.py
 - Connected Mode, actual ~ 50 ms 20 Hz
 - Scan Mode,      actual ~300 ms  3 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

 OLED & USE_PROC_NET_WIRELESS=False in wifi_utils.py -- FLASHES !!!
 - Connected Mode, actual ~200 ms  5 Hz  (at this rate, it won't return RX Rate (n/a in output))
 - Scan Mode,      actual ~461 ms  3 Hz
 - Out of range,   actual ~ ?? ms ?? Hz
 - temperature read every 60 sec since this is system call

TODO consider do not clear whole OLED screen, but black out values to be updated

If the targeted network is not connected, it uses a lighter weight Scan Mode which scans all available networks looking for the targeted network.
 - The OLED SSD display shows:
 - ssid <target-ssid>

If the targeted network is connected, it can download the data file.
 - The OLED SSD display shows:
 - SSID = <target-ssid>