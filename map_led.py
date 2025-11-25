#!/usr/bin/env python3
"""
map_leds_visual.py

Interactive LED index → physical-label mapper for 4 NeoPixel rings controlled
by the Arduino serial controller (commands: PIX, SET, RANGE, BRIGHT, CLEAR).

Saves mapping to led_mapping.json and prints ASCII visual maps for each ring.

Edit RING_LEDS if your ring counts differ.
"""
import serial, glob, time, json, math, sys, os

# --------- CONFIG (edit if needed) ----------
RING_LEDS = [7, 8, 12, 16]   # ring0 has 7 (index 0 = nucleus, 1..6 outer)
SAFE_BRIGHTNESS = 110
PIX_ON_COLOR = (200, 0, 0)   # red when lighting an index for identification
PIX_OFF_COLOR = (0, 0, 0)
TEST_DELAY_AFTER_LIGHT = 0.05
OUTPUT_FILE = "led_mapping.json"
REFERENCE_PHOTO = "/mnt/data/6CB81642-8FC4-4FC2-A525-46DE60AFC80E.jpeg"
# --------------------------------------------

def find_port():
    cands = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    if not cands:
        raise RuntimeError("No serial device found. Plug in Arduino and try again.")
    # prefer ttyACM
    for c in cands:
        if 'ACM' in c:
            return c
    return cands[0]

def open_serial(port):
    ser = serial.Serial(port, 115200, timeout=1)
    time.sleep(2)  # allow Arduino auto-reset
    return ser

def send(ser, cmd, echo=False):
    ser.write((cmd.strip() + '\n').encode('ascii'))
    resp = ser.readline().decode('ascii').strip()
    if echo:
        print(f"> {cmd} => '{resp}'")
    return resp

def set_brightness(ser, b):
    return send(ser, f"BRIGHT {int(b)}")

def clear_all(ser):
    return send(ser, "CLEAR")

def pix(ser, ring, idx, r,g,b):
    return send(ser, f"PIX {ring} {idx} {r} {g} {b}")

def print_title(s):
    print("\n" + "="*len(s))
    print(s)
    print("="*len(s))

# ASCII-drawing helper: map indices to positions on a grid approximating a circle
def draw_ring_ascii(labels, ring_index, ring_count):
    """
    labels: list of strings length = ring_count
    returns printable string of ASCII map
    """
    # grid size depends on ring_count
    size = 11  # default grid size (odd)
    cx = cy = size//2
    grid = [["   " for _ in range(size)] for __ in range(size)]

    # place center for smallest ring (if ring_count small and we want center)
    if ring_count <= 7:
        center_label = labels[0] if len(labels) > 0 else ""
        grid[cy][cx] = center_label.center(3)[:3]

        # outer positions are labels[1..]
        outer = labels[1:]
        n = len(outer)
        radius = 4
        for i, lab in enumerate(outer):
            ang = -math.pi/2 + (2*math.pi*i)/n   # start at top
            x = cx + int(round(radius * math.cos(ang)))
            y = cy + int(round(radius * math.sin(ang)))
            grid[y][x] = f"{i+1:>2}" if not lab else lab[:3].center(3)
    else:
        # no center special
        n = ring_count
        radius = 4
        for i, lab in enumerate(labels):
            ang = -math.pi/2 + (2*math.pi*i)/n
            x = cx + int(round(radius * math.cos(ang)))
            y = cy + int(round(radius * math.sin(ang)))
            # display index:label (short)
            idx_label = f"{i:>2}"
            grid[y][x] = lab[:3].center(3) if lab else idx_label.center(3)

    # Build string lines
    lines = []
    for row in grid:
        lines.append("".join(cell if cell else "   " for cell in row))
    return "\n".join(lines)

def interactive_map():
    print_title("LED Index → Physical Label Mapper")
    print("Reference photo (open separately if helpful):", REFERENCE_PHOTO)
    print("This tool will light each LED index and ask you to type a short label")
    print("Examples of labels: center, top, pos1, 1, 12oc, N, E, LED3")
    print("Press Enter to skip labeling a particular LED (it will remain unlabeled).")
    print()

    port = find_port()
    print("Using serial port:", port)
    ser = open_serial(port)
    try:
        # initial greeting read
        intro = ser.readline().decode().strip()
        if intro:
            print("Arduino intro:", intro)
        # safety: set brightness and clear
        set_brightness(ser, SAFE_BRIGHTNESS)
        time.sleep(0.1)
        clear_all(ser)
        time.sleep(0.1)

        mapping = {}
        for r in range(len(RING_LEDS)):
            n = RING_LEDS[r]
            print_title(f"Ring {r} — {n} LEDs")
            labels = [""] * n
            for i in range(n):
                # light this pixel (special-case ring0: namespace)
                # light red
                pix(ser, r, i, PIX_ON_COLOR[0], PIX_ON_COLOR[1], PIX_ON_COLOR[2])
                time.sleep(TEST_DELAY_AFTER_LIGHT)
                prompt = f"Label for ring {r} index {i} (visible LED lit) : "
                lab = input(prompt).strip()
                if lab == "":
                    print("Skipped — leaving label empty.")
                labels[i] = lab
                # turn off this pixel immediately (to reduce power draw)
                pix(ser, r, i, PIX_OFF_COLOR[0], PIX_OFF_COLOR[1], PIX_OFF_COLOR[2])
                time.sleep(0.03)
            mapping[str(r)] = labels
            # brief whole-ring confirmation: set a dim color then clear
            send_resp = set_brightness(ser, SAFE_BRIGHTNESS)
            time.sleep(0.05)
            print(f"Captured labels for ring {r}: {labels}")
            print()

        # Print ASCII maps
        print_title("ASCII VISUAL MAPS")
        for r in range(len(RING_LEDS)):
            labels = mapping[str(r)]
            print_title(f"Ring {r} (indices 0..{RING_LEDS[r]-1})")
            ascii_map = draw_ring_ascii(labels, r, RING_LEDS[r])
            print(ascii_map)
            print()  # blank line

        # Save mapping to file
        with open(OUTPUT_FILE, "w") as f:
            json.dump({
                "ring_leds": RING_LEDS,
                "mapping": mapping,
                "reference_photo": REFERENCE_PHOTO
            }, f, indent=2)
        print("Saved mapping to", OUTPUT_FILE)
        print("You can edit the JSON file if you want to tweak labels.")
    finally:
        try:
            clear_all(ser)
        except Exception:
            pass
        ser.close()

if __name__ == "__main__":
    try:
        interactive_map()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        sys.exit(0)
