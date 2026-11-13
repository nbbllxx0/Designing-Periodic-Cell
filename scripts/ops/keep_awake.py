"""Hold a Windows idle-sleep block (SetThreadExecutionState, per process; no power setting is changed) while a given
process is alive. Used for the multi-day E4 run, which outlives any interactive session.

    keep_awake.py <pid>
"""
import ctypes
import subprocess
import sys
import time

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


def alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


if __name__ == "__main__":
    pid = int(sys.argv[1])
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    try:
        while alive(pid):
            time.sleep(60)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
