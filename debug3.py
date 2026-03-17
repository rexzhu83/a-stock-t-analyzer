import subprocess, sys

r = subprocess.run(["git", "cat-file", "-p", "e955728e0f0b005a27baf079d651559496f27489"], capture_output=True)
blob = r.stdout
text = blob.decode("utf-8", errors="replace")

# Find all problematic characters
problems = []
for i, c in enumerate(text[:500]):
    code = ord(c)
    if code > 127 and not (0x4E00 <= code <= 0x9FFF) and code != 0xFF0C and code != 0x3001 and code != 0xFF1A and code != 0x2014 and code != 0x2026 and code != 0x300A and code != 0x300B and code != 0xFF08 and code != 0xFF09 and code != 0x201C and code != 0x201D and code != 0xFF01 and code != 0x3002 and code != 0x0A and code != 0x0D and code != 0x09:
        if code > 0x2000:  # skip ASCII
            hx = blob[i:i+4].hex(" ")
            problems.append(f"pos={i} U+{code:04X} bytes=[{hx}] char=[{c}]")

for p in problems[:30]:
    print(p)

print(f"\nTotal problematic chars in first 500: {len(problems)}")

# Try to figure out the intended text
# Let's see what the ASCII parts look like
ascii_text = ""
for c in text[:500]:
    if 32 <= ord(c) <= 126 or ord(c) in (10, 13):
        ascii_text += c
    else:
        ascii_text += "?"
print(f"\nASCII view:\n{ascii_text[:400]}")
