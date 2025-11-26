#!/usr/bin/env python3
"""
electron_atom_full.py

FEATURES:
- Nucleus always RED with soft pulsing effect
- Only required shells activate
- Smooth electron orbit per shell
- Per-shell colors:
    K → cyan
    L → blue
    M → green
    N → magenta
- Trailing glow (fade tail)
- Power-safe brightness ramp
"""

import serial, glob, time, math

# ---------------- Hardware ----------------
RING_LEDS = [7, 8, 12, 16]     # ring0 nucleus=0, rest outer LEDs
SAFE_BRIGHTNESS = 180

# ---------------- Atomic Presets ----------------
ATOM_PRESETS = {
    "H": 1, "He": 2, "Li": 3, "Be": 4, "B":5, "C":6, "N":7, "O":8, "F":9, "Ne":10,
    "Na":11,"Mg":12,"Al":13,"Si":14,"P":15,"S":16,"Cl":17,"Ar":18
}

# Chemical shell distribution (correct up to Ar)
SHELL_CAPS = [2, 8, 8, 18]

# Per-shell electron colors
SHELL_COLORS = {
    0: (0,255,255),   # K → cyan
    1: (0,120,255),   # L → blue
    2: (0,255,80),    # M → green
    3: (200,0,200)    # N → magenta
}

# Tail fade color
TAIL_FADE = (20, 20, 20)


# ---------------- Serial Helpers ----------------

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

def nucleus_on(ser, intensity=255):
    """Red nucleus with soft pulsing"""
    send(ser, f"PIX 0 0 {intensity} 0 0")

def shell_clear(ser, ring):
    if ring == 0:
        send(ser, "RANGE 0 1 6 0 0 0")
    else:
        send(ser, f"SET {ring} 0 0 0")


# ---------------- Atom Logic ----------------

def distribute_electrons(total):
    remaining = total
    dist = []
    for cap in SHELL_CAPS:
        take = min(cap, remaining)
        dist.append(take)
        remaining -= take
    return dist


def compute_positions(ring_idx, count):
    total = RING_LEDS[ring_idx]

    if ring_idx == 0:
        available = total - 1
        indices = [1 + i for i in range(available)]
    else:
        available = total
        indices = list(range(total))

    if count == 0:
        return []
    if count > available:
        count = available

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

    # fill missing if rounding created less
    i = 0
    while len(unique) < count:
        cand = indices[i % available]
        if cand not in seen:
            unique.append(cand)
            seen.add(cand)
        i += 1

    return unique[:count]


# ---------------- Orbit Animation ----------------

def orbit(ser, electrons):
    clear_all(ser)
    send(ser, f"BRIGHT {SAFE_BRIGHTNESS}")

    # nucleus initial pulse
    nucleus_on(ser, 255)

    shell_dist = distribute_electrons(electrons)
    print("Shell distribution:", shell_dist)

    # precompute electron local states per ring
    local_states = []
    for ring_idx, ecount in enumerate(shell_dist):
        if ecount == 0:
            local_states.append([])
            continue

        ring_leds = (RING_LEDS[ring_idx]-1) if ring_idx==0 else RING_LEDS[ring_idx]
        use = min(ecount, ring_leds)

        start_positions = [
            int(round((i * ring_leds)/use)) % ring_leds
            for i in range(use)
        ]
        local_states.append(start_positions)

    # main animation loop
    SPEED = 0.12
    pulse_phase = 0

    try:
        while True:
            # nucleus pulsing
            pulse_phase += 0.15
            nuc_intensity = int(150 + 80 * math.sin(pulse_phase))
            nucleus_on(ser, nuc_intensity)

            # clear previous electrons (soft fade)
            for ring_idx in range(4):
                shell_clear(ser, ring_idx)

            # draw electrons
            for ring_idx, locals in enumerate(local_states):
                ring_len = (RING_LEDS[ring_idx]-1) if ring_idx==0 else RING_LEDS[ring_idx]
                if ring_len == 0:
                    continue

                shell_color = SHELL_COLORS[ring_idx]

                for p_index in range(len(locals)):
                    # move electron
                    locals[p_index] = (locals[p_index] + 1) % ring_len

                    # actual LED index
                    if ring_idx == 0:
                        actual = 1 + locals[p_index]
                    else:
                        actual = locals[p_index]

                    # main electron
                    send(ser,
                        f"PIX {ring_idx} {actual} {shell_color[0]} {shell_color[1]} {shell_color[2]}")

                    # tail pixel (fade)
                    tail_pos = (locals[p_index] - 1) % ring_len
                    if ring_idx == 0:
                        tail_actual = 1 + tail_pos
                    else:
                        tail_actual = tail_pos

                    send(ser,
                        f"PIX {ring_idx} {tail_actual} {TAIL_FADE[0]} {TAIL_FADE[1]} {TAIL_FADE[2]}")

            time.sleep(SPEED)

    except KeyboardInterrupt:
        clear_all(ser)
        nucleus_on(ser, 255)
        print("\nStopped.")


# ---------------- CLI ----------------

def main():
    ser = open_serial()
    print("Arduino:", ser.readline().decode().strip())

    print("\nAtoms available:")
    print(", ".join(ATOM_PRESETS.keys()))
    print("Type element symbol (e.g., C) or number of electrons (e.g., 6):")

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
