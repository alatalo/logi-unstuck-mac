#!/usr/bin/env python3
import ctypes
import os
import signal
import sys
import time

HIToolbox = ctypes.CDLL(
    "/System/Library/Frameworks/Carbon.framework/Frameworks/HIToolbox.framework/HIToolbox"
)

HIToolbox.EnableSecureEventInput.restype = None
HIToolbox.DisableSecureEventInput.restype = None
HIToolbox.IsSecureEventInputEnabled.restype = ctypes.c_bool

running = True


def stop(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

print(f"PID: {os.getpid()}")
print("Enabling Secure Input...")
HIToolbox.EnableSecureEventInput()

print(f"Secure Input enabled: {HIToolbox.IsSecureEventInputEnabled()}")
print("Leave this running, then test your Logi Unstuck script in another terminal.")
print("Press Ctrl-C here to cleanly disable Secure Input.")

try:
    while running:
        time.sleep(1)
finally:
    print("\nDisabling Secure Input...")
    HIToolbox.DisableSecureEventInput()
    print(f"Secure Input enabled: {HIToolbox.IsSecureEventInputEnabled()}")
