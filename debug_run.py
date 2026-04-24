import subprocess
import sys
import time
import threading

# Run test_deepgram.py first to isolate the issue
print("=" * 60)
print("TESTING DEEPGRAM CONNECTION")
print("=" * 60)

proc = subprocess.Popen(
    [sys.executable, "test_deepgram.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    cwd="c:\\Users\\SAI\\Desktop\\Projects\\Interview Helper"
)

for line in proc.stdout:
    print(line.rstrip())
    
proc.wait()
print("\n" + "=" * 60)
print("DEEPGRAM TEST COMPLETE")
print("=" * 60)
