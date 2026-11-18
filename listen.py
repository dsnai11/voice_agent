"""Hands-free listening: detects when the caller starts and stops speaking (no keyboard).

The agent is half-duplex: it listens only while it is not speaking, so its own voice is not
picked up. Use headphones, or keep speaker volume moderate, to avoid echo from the speakers.
"""
import numpy as np
import sounddevice as sd

RATE = 16000
BLOCK = 480                      # 30 ms
BLOCK_S = BLOCK / RATE


def rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0


class Segmenter:
    """Feed 30 ms blocks; returns a finished utterance (float32 array) or None."""

    def __init__(self, threshold: float, end_silence_s: float = 1.0, min_speech_s: float = 0.4,
                 max_speech_s: float = 20.0, preroll_s: float = 0.3, start_blocks: int = 3):
        self.thr = threshold
        self.end_blocks = int(end_silence_s / BLOCK_S)
        self.min_blocks = int(min_speech_s / BLOCK_S)
        self.max_blocks = int(max_speech_s / BLOCK_S)
        self.preroll = int(preroll_s / BLOCK_S)
        self.start_blocks = start_blocks
        self.reset()

    def reset(self):
        self.pre = []            # recent blocks before speech starts
        self.buf = []            # blocks of the current utterance
        self.loud_run = 0
        self.quiet_run = 0
        self.lead = 0
        self.speaking = False

    def feed(self, block: np.ndarray):
        loud = rms(block) > self.thr
        if not self.speaking:
            self.pre.append(block)
            self.pre = self.pre[-self.preroll - self.start_blocks:]
            self.loud_run = self.loud_run + 1 if loud else 0
            if self.loud_run >= self.start_blocks:
                self.speaking, self.buf, self.quiet_run = True, list(self.pre), 0
                self.lead = len(self.buf) - self.start_blocks   # blocks before the speech itself
            return None
        self.buf.append(block)
        self.quiet_run = 0 if loud else self.quiet_run + 1
        if self.quiet_run >= self.end_blocks or len(self.buf) >= self.max_blocks:
            speech_blocks = len(self.buf) - self.quiet_run - self.lead
            audio = np.concatenate(self.buf)
            self.reset()
            return audio if speech_blocks >= self.min_blocks else None   # ignore clicks / coughs
        return None


def calibrate(seconds: float = 1.0) -> float:
    """Measure room noise (stay quiet) and return a speech threshold above it."""
    n = int(seconds / BLOCK_S)
    with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK) as stream:
        levels = [rms(stream.read(BLOCK)[0][:, 0]) for _ in range(n)]
    noise = float(np.median(levels))
    return max(0.012, noise * 4.0)


def listen_for_utterance(threshold: float, idle_timeout_s: float = 30.0, **seg_kwargs):
    """Block until the caller finishes a sentence. Returns audio, or None if nobody spoke in time."""
    seg = Segmenter(threshold, **seg_kwargs)
    idle_blocks = 0
    with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK) as stream:
        while idle_blocks * BLOCK_S < idle_timeout_s:
            audio = seg.feed(stream.read(BLOCK)[0][:, 0])
            if audio is not None:
                return audio
            idle_blocks = 0 if seg.speaking else idle_blocks + 1   # the timer only runs while silent
    return None
