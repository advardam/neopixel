#!/usr/bin/env python3
"""
electron_atom_clean.py

Clean atom model:
- Nucleus always RED (ring0 index 0)
- Only required shells light up
- Only electrons glow (matched count)
- Electrons move smoothly (orbit)
- Ring0 outer positions = indices 1..6
- Works with your existing Arduino controller
"""

import serial, glob, time, math

# ---------------- Hardware ----------------
RING_LEDS = [7, 8, 12, 16]     # (ring0 nucleus=0, outer=6 LEDs)
SAFE_BRIGHTNESS = 150

# ---------------- Atomic Presets ----------------
ATOM_PRESETS = {
    "H": 1, "He": 2, "Li": 3, "Be": 4, "B":5, "C":6, "N":7, "O":8, "F":9, "Ne":10,
    "Na":11,"Mg":12,"Al":13,"Si":14,"P":15,"S":16,"Cl":17,"Ar":18
}

# chemical shell distribution (correct for elements up to Ar)
SHELL_CAPS = [2,8,8,18]

# -----------------------------------------
def find_port():
    c = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    if not c:
        raise RuntimeError("Arduino not detected.")
    return c[0]

def open_serial():
    port = find_port()
    ser = serial.Serial(port, 115200, timeout=1)
    time.sleep(2)
    return ser

def send(ser, cmd):
    ser.write((cmd+'\n').encode())
    return ser.readline().decode().strip()

def clear_all(ser):
    send(ser, "CLEAR")

def nucleus_on(ser):
    send(ser, "PIX 0 0 255 0 0")  # ALWAYS RED

def shell_clear(ser, ring):
    if ring == 0:
        send(ser, "RANGE 0 1 6 0 0 0")
    else:
        send(ser, f"SET {ring} 0 0 0")

# -----------------------------------------
def distribute_electrons(total):
    # inner to outer fill
    remaining = total
    dist = []
    for cap in SHELL_CAPS:
        take = min(cap, remaining)
        dist.append(take)
        remaining -= take
    return dist   # always length 4

def compute_positions(ring_idx, count):
    """Spread electrons evenly on the ring."""
    total = RING_LEDS[ring_idx]

    if ring_idx == 0:
        # ring0: skip nucleus, use 1..6
        available = total - 1
        indices = [1 + i for i in range(available)]
    else:
        available = total
        indices = list(range(total))

    count = min(count, available)
    if count == 0:
        return []

    step = available / count
    positions = []
    for k in range(count):
        pos = int(round(k * step)) % available
        positions.append(indices[pos])

    # remove duplicates
    unique = []
    seen = set()
    for x in positions:
        if x not in seen:
            unique.append(x)
            seen.add(x)

    # fill missing if rounding caused issues
    i = 0
    while len(unique) < count:
        cand = indices[i % available]
        if cand not in seen:
            unique.append(cand)
            seen.add(cand)
        i += 1

    return unique[:count]

# -----------------------------------------
def orbit(ser, electrons):
    clear_all(ser)
    send(ser, f"BRIGHT {SAFE_BRIGHTNESS}")
    nucleus_on(ser)

    shell_dist = distribute_electrons(electrons)
    print("Shell distribution:", shell_dist)

    # Precompute local motion states
    local_states = []
    for shell_idx, ecount in enumerate(shell_dist):
        if ecount == 0:
            local_states.append([])
            continue

        ring_leds = (RING_LEDS[shell_idx]-1) if shell_idx==0 else RING_LEDS[shell_idx]
        use = min(ecount, ring_leds)

        # local positions around ring
        start_positions = [
            int(round((i * ring_leds)/use)) % ring_leds
            for i in range(use)
        ]
        local_states.append(start_positions)

    # Run animation
    SPEED = 0.12
    runtime = 99999   # keeps running until Ctrl+C

    try:
        while True:
            # clear previous electrons
            for ring_idx in range(4):
                shell_clear(ser, ring_idx)

            # redraw with new positions
            for ring_idx, locals in enumerate(local_states):

                ring_len = (RING_LEDS[ring_idx]-1) if ring_idx==0 else RING_LEDS[ring_idx]
                if ring_len == 0:
                    continue

                for i in range(len(locals)):
                    locals[i] = (locals[i] + 1) % ring_len

                    if ring_idx == 0:
                        actual = 1 + locals[i]
                    else:
                        actual = locals[i]

                    send(ser,
                         f"PIX {ring_idx} {actual} 0 255 255")  # cyan electrons

            time.sleep(SPEED)
    except KeyboardInterrupt:
        clear_all(ser)
        nucleus_on(ser)
        print("\nStopped.")


# -----------------------------------------
def main():
    ser = open_serial()
    print("Arduino:", ser.readline().decode().strip())

    print("\nAtoms available:")
    print(", ".join(ATOM_PRESETS.keys()))
    print("Type symbol (e.g. C) or number of electrons (e.g. 6):")

    while True:
        choice = input("\nEnter atom or electron count: ").strip()

        if choice == "":
            continue

        if choice in ATOM_PRESETS:
            electrons = ATOM_PRESETS[choice]
        else:
            try:
                electrons = int(choice)
            except:
                print("Invalid input")
                continue

        print(f"Loading atom with {electrons} electrons...")
        orbit(ser, electrons)

if __name__ == "__main__":
    main()
