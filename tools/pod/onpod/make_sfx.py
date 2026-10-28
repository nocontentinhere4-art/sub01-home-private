#!/usr/bin/env python3
"""The chat sound effects (owner 10-28: !airhorn, !rimshot ...), synthesized with ffmpeg (no sampled audio, no rights
question): 48 kHz stereo s16 WAV, at most 3 s, 10 ms fades, peaks normalized to PEAK_DB (Kimi feat2: conservative, so
they never mask his voice). Usage: make_sfx.py <out-dir>   (the agent plays <streamer-dir>/sfx/<name>.wav)."""
import subprocess
import sys
from pathlib import Path

PEAK_DB = -16.0
PI = "PI"


def tone(f, wave="sq"):
    """A crude oscillator for aevalsrc: square-ish (sq), saw-ish (saw) or sine."""
    if wave == "sq":
        return f"(sgn(sin(2*{PI}*{f}*t))*0.6+sin(2*{PI}*{f}*t)*0.4)"
    if wave == "saw":
        return f"(2*(t*{f}-floor(t*{f}+0.5)))"
    return f"sin(2*{PI}*{f}*t)"


def gate(a, b):
    return f"between(t,{a},{b})"


SOUNDS = {
    # three blasts of a Bb major chord
    "airhorn": (2.2, f"({gate(0, 0.22)}+{gate(0.32, 0.54)}+{gate(0.66, 2.1)})*({tone(466)}+{tone(587)}+0.7*{tone(698)})/3",
                "lowpass=f=3500,highpass=f=200"),
    # a snare roll that swells, then a crash
    "drumroll": (3.0, f"if(lt(t,2.5),(0.2+0.8*t/2.5)*(0.5+0.5*sin(2*{PI}*28*t))*(random(0)*2-1),"
                      f"exp(-(t-2.5)*6)*(random(0)*2-1))", "bandpass=f=2500:width_type=o:w=2"),
    # ba-dum-tss
    "rimshot": (1.6, f"{gate(0, 0.2)}*exp(-t*18)*{tone(180, 'sine')}+{gate(0.22, 0.45)}*exp(-(t-0.22)*18)*{tone(120, 'sine')}"
                     f"+{gate(0.5, 1.6)}*exp(-(t-0.5)*4)*(random(0)*2-1)*0.7", "highpass=f=60"),
    # wah wah wah waaah
    "sad": (2.8, f"({gate(0, 0.45)}*{tone(293.7, 'saw')}+{gate(0.5, 0.95)}*{tone(277.2, 'saw')}"
                 f"+{gate(1.0, 1.45)}*{tone(261.6, 'saw')}+{gate(1.5, 2.8)}*(2*((t*(246.9+6*sin(2*{PI}*5*t)))"
                 f"-floor(t*(246.9+6*sin(2*{PI}*5*t))+0.5))))", "lowpass=f=1400"),
    # a low hit with a falling pitch
    "boom": (2.0, f"exp(-t*2.2)*sin(2*{PI}*(30+60*exp(-t*3))*t)+0.3*exp(-t*5)*(random(0)*2-1)", "lowpass=f=400"),
    # many claps: noise with a fast random envelope
    "applause": (3.0, f"(0.6+0.4*sin(2*{PI}*0.7*t))*(random(0)*2-1)*(0.5+0.5*gt(random(1),0.55))*if(gt(t,2.4),(3-t)/0.6,1)",
                 "bandpass=f=1800:width_type=o:w=2.5"),
    # crickets: high chirps in pairs
    "crickets": (3.0, f"sin(2*{PI}*4600*t)*(0.5+0.5*sin(2*{PI}*32*t))*(between(mod(t,0.9),0,0.18)+between(mod(t,0.9),0.25,0.43))*0.6",
                 "highpass=f=2000"),
    # a short fanfare: arpeggio and a chord
    "win": (2.6, f"{gate(0, 0.14)}*{tone(523.3)}+{gate(0.15, 0.29)}*{tone(659.3)}+{gate(0.3, 0.44)}*{tone(784)}"
                 f"+{gate(0.45, 2.6)}*({tone(1046.5)}+{tone(659.3)}+{tone(784)})/3*exp(-(t-0.45)*0.8)", "lowpass=f=4000"),
}


def peak_db(path):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    line = next(l for l in out.splitlines() if "max_volume" in l)
    return float(line.split("max_volume:")[1].split("dB")[0])


def make(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (seconds, expr, filt) in SOUNDS.items():
        raw = out_dir / f".{name}.raw.wav"
        fade = f"afade=t=in:d=0.01,afade=t=out:st={seconds - 0.05:.2f}:d=0.05"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"aevalsrc='{expr}':s=48000:d={seconds}", "-af", f"{filt},{fade}", "-ac", "2", "-ar", "48000",
                        "-c:a", "pcm_s16le", str(raw)], check=True)
        gain = PEAK_DB - peak_db(raw)
        final = out_dir / f"{name}.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-af", f"volume={gain:.2f}dB",
                        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(final)], check=True)
        raw.unlink()
        print(f"{name}: {seconds:.1f} s, peak {peak_db(final):.1f} dBFS")


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "sfx")
