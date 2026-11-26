"""Local voice recorder with an on-screen script (teleprompter). Everything stays on this PC.
python voice_kit/recorder.py   then open http://localhost:3910
Recordings are saved as WAV files in D:\\Voice Agent Model\\voice_recordings\\ (line_01.wav, line_02.wav ...)."""
import http.server
import json
import os
import re
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("REC_DIR", r"D:\Voice Agent Model\voice_recordings")
PORT = int(os.environ.get("REC_PORT", "3910"))
os.makedirs(OUT, exist_ok=True)


def script_lines():
    with open(os.path.join(HERE, "recording_lines.json"), encoding="utf-8") as f:
        return json.load(f)


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype == "application/json" else ""))
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/":
            with open(os.path.join(HERE, "recorder.html"), encoding="utf-8") as f:
                return self._send(200, f.read(), "text/html")
        if self.path == "/lines":
            done = {re.sub(r"\.wav$", "", n) for n in os.listdir(OUT) if n.endswith(".wav")}
            return self._send(200, json.dumps({"lines": script_lines(), "done": sorted(done)}, ensure_ascii=False))
        m = re.fullmatch(r"/audio/(line_\d+)\.wav", self.path)
        if m and os.path.exists(os.path.join(OUT, m.group(1) + ".wav")):
            with open(os.path.join(OUT, m.group(1) + ".wav"), "rb") as f:
                return self._send(200, f.read(), "audio/wav")
        self._send(404, "{}")

    def do_POST(self):
        m = re.fullmatch(r"/save/(line_\d+)", self.path)
        if not m:
            return self._send(404, "{}")
        n = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(n)
        if data[:4] != b"RIFF":
            return self._send(400, '{"error":"not a wav"}')
        with open(os.path.join(OUT, m.group(1) + ".wav"), "wb") as f:
            f.write(data)
        self._send(200, '{"ok":true}')


if __name__ == "__main__":
    print(f"Recorder: http://localhost:{PORT}   (saving to {OUT})", flush=True)
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
