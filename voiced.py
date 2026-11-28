"""Does a short piece of microphone sound carry a human voice? Used only to decide whether Ria should stop speaking.

A voice has a pitch: in the 180-3000 Hz band (where speech is clear and fan hum, rumble and thumps mostly are not) the wave
repeats 80 to 400 times a second. Hiss, knocks and rumble do not repeat like that. No model needed.
Other people talking, a TV or a song also have a voice: this cannot tell them from the customer.
"""
import numpy as np

RATE = 16000
WINDOW = 960                       # 60 ms: long enough for two periods of a low voice
LOW_HZ, HIGH_HZ = 180, 3000
LAG_MIN, LAG_MAX = RATE // 400, RATE // 80
PERIODIC = 0.45                    # how strongly the wave must repeat (1 = perfectly)
BAND_SHARE = 0.20                  # at least this part of the energy lies in the speech band


def score(window: np.ndarray) -> tuple:
    """(how strongly it repeats at a voice pitch, share of the energy in the speech band)."""
    x = np.asarray(window, dtype="float64")
    if x.size < LAG_MAX * 2:
        return 0.0, 0.0
    x = x - x.mean()
    spec = np.fft.rfft(x, 2048)
    freq = np.fft.rfftfreq(2048, 1 / RATE)
    total = float(np.sum(np.abs(spec) ** 2)) + 1e-12
    spec[(freq < LOW_HZ) | (freq > HIGH_HZ)] = 0
    share = float(np.sum(np.abs(spec) ** 2)) / total
    y = np.fft.irfft(spec, 2048)[: x.size]
    best = 0.0
    for lag in range(LAG_MIN, LAG_MAX + 1):
        a, b = y[:-lag], y[lag:]
        d = float(np.sqrt(np.dot(a, a) * np.dot(b, b)))
        if d > 1e-12:
            best = max(best, float(np.dot(a, b)) / d)
    return best, share


def is_voice(window: np.ndarray) -> bool:
    periodic, share = score(window)
    return periodic >= PERIODIC and share >= BAND_SHARE
