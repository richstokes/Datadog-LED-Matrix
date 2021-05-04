#!/bin/bash
# Helper script to copy files in place on device and connect to terminal for debugging
set -e

killall screen || true
cp logo.bmp /Volumes/CIRCUITPY
cp metrics.json /Volumes/CIRCUITPY
cp code.py /Volumes/CIRCUITPY
screen $(ls -r /dev/tty.usbmodem* | xargs | grep -oE '[^ ]+$') 11500 # Tries to find the most likely serial device
