#!/usr/bin/env python3
"""
test_all_rings.py

Auto-detects Arduino serial, sets safe brightness, then tests each ring and pixel.
Designed for the Arduino firmware you uploaded (commands: PIX, SET, RANGE, BRIGHT, CLEAR).

Configure RING_LEDS to match your hardware.
"""

import serial, glob, time, sys

# ------------- CONFIG -------------
RING_LEDS = [7, 8, 12, 16]   # ring0 has 7 (index 0 = nucleus, 1..6 outer)
SAFE_BRIGHTNESS = 120        # 0..255 (reduce if power issues)
TEST_DELAY_PIXEL = 0.25      # seconds between lighting individual pixels
TEST_DELAY_RING = 1.0        # seconds after setting whole ring
# -----------------------------------

def find_port():
    candidates = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    if not candidates:
        raise RuntimeError("No serial device found. Plug in Arduino and try again.")
    # prefer ttyACM (Arduino UNO/Micro), otherwise first available
    for c in candidates:
        if 'ACM' in c:
            return c
    return candidates[0]

def open_serial(port):
    ser = serial.Serial(port, 115200, timeout=1)
    time.sleep(2)  # allow Arduino to reset
    return ser

def send(ser, cmd, echo=True):
    cmd = cmd.strip()
    ser.write((cmd + '\n').encode('ascii'))
    # read one response line (Arduino prints OK or errors)
    resp = ser.readline().decode('ascii').strip()
    if echo:
        print(f"> {cmd}   =>  '{resp}'")
    return resp

def set_brightness(ser, b):
    b = max(0, min(255, int(b)))
    return send(ser, f"BRIGHT {b}")

def clear_all(ser):
    return send(ser, "CLEAR")

def test_pixel_sequence(ser, ring_index):
    n = RING_LEDS[ring_index]
    print(f"\nTesting ring {ring_index} — {n} LEDs (lighting each pixel red one by one)...")
    for i in range(n):
        send(ser, f"PIX {ring_index} {i} 255 0 0")
        time.sleep(TEST_DELAY_PIXEL)
        send(ser, f"PIX {ring_index} {i} 0 0 0")  # turn it off after showing
    print(f"Done pixel sequence for ring {ring_index}.")

def test_whole_ring(ser, ring_index, r,g,b):
    print(f"\nSetting entire ring {ring_index} color ({r},{g},{b}) ...")
    # For ring0 we want to avoid nucleus when setting outer depending on intent.
    if ring_index == 0:
        outer_count = RING_LEDS[0] - 1
        if outer_count > 0:
            # set indices 1..outer_count
            send(ser, f"RANGE 0 1 {outer_count} {r} {g} {b}")
        else:
            print("Ring0 has no outer pixels to set.")
    else:
        send(ser, f"SET {ring_index} {r} {g} {b}")
    time.sleep(TEST_DELAY_RING)

def test_nucleus(ser):
    print("\nTesting nucleus (ring0 index 0)...")
    # light center red, then green, then off
    send(ser, "PIX 0 0 255 0 0")
    time.sleep(0.6)
    send(ser, "PIX 0 0 0 255 0")
    time.sleep(0.6)
    send(ser, "PIX 0 0 0 0 0")
    print("Nucleus test complete.")

def main():
    print("Auto-detecting Arduino serial port...")
    try:
        port = find_port()
    except RuntimeError as e:
        print("ERROR:", e)
        sys.exit(1)

    print("Using serial port:", port)
    ser = open_serial(port)
    try:
        # read any initial greeting
        intro = ser.readline().decode().strip()
        if intro:
            print("Arduino intro:", intro)
        # set safe brightness
        set_brightness(ser, SAFE_BRIGHTNESS)
        time.sleep(0.2)

        # clear everything first
        clear_all(ser)
        time.sleep(0.3)

        # test nucleus
        test_nucleus(ser)

        # iterate through each ring
        for ri in range(len(RING_LEDS)):
            print("\n" + "="*40)
            print(f"RING {ri} TESTS (LED count = {RING_LEDS[ri]})")
            print("="*40)
            # pixel-by-pixel
            test_pixel_sequence(ser, ri)

            # set whole ring to a visible color (green)
            test_whole_ring(ser, ri, 0, 200, 0)
            # pause to observe
            time.sleep(TEST_DELAY_RING)

            # set whole ring to a different color (blue)
            test_whole_ring(ser, ri, 0, 0, 200)
            time.sleep(TEST_DELAY_RING)

            # clear ring after test
            if ri == 0:
                # clear outer only, leave nucleus off too
                outer_count = RING_LEDS[0] - 1
                if outer_count > 0:
                    send(ser, f"RANGE 0 1 {outer_count} 0 0 0")
                send(ser, "PIX 0 0 0 0 0")
            else:
                send(ser, f"SET {ri} 0 0 0")

        # final sweep: set all rings to a soft color and then clear
        print("\nFinal: soft color on all rings for 1 second...")
        send(ser, "ALL 30 30 80")
        time.sleep(1.0)
        clear_all(ser)
        print("\nAll tests complete. Cleared all LEDs.")

    finally:
        ser.close()

if __name__ == "__main__":
    main()
