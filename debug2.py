import subprocess

r = subprocess.run(["git", "cat-file", "-p", "e955728e0f0b005a27baf079d651559496f27489"], capture_output=True)
blob = r.stdout

# Check what's at the position of the first Chinese char (byte 34)
print(f"Bytes 34-40: {blob[34:40].hex(' ')}")

# What we expect for "股" (U+80A1) in UTF-8
expected = "股".encode("utf-8")
print(f"Expected UTF-8 for 股: {expected.hex(' ')}")

# What we have
print(f"Actual bytes at that position: {blob[34:37].hex(' ')}")

# Decode as GBK
try:
    text = blob.decode("gbk", errors="replace")
    print(f"\nGBK decode first 200 chars:")
    print(text[:200])
except Exception as e:
    print(f"GBK failed: {e}")

# Decode as UTF-8
try:
    text = blob.decode("utf-8", errors="replace")
    print(f"\nUTF-8 decode first 200 chars:")
    print(text[:200])
except Exception as e:
    print(f"UTF-8 failed: {e}")

# Check if file on disk is different from blob
with open("README.md", "rb") as f:
    disk = f.read()

print(f"\nDisk == Blob: {disk == blob}")
print(f"Disk size: {len(disk)}, Blob size: {len(blob)}")

if disk != blob:
    for i in range(min(len(disk), len(blob))):
        if disk[i] != blob[i]:
            print(f"First diff at byte {i}: disk=0x{disk[i]:02x} blob=0x{blob[i]:02x}")
            print(f"Disk context: {disk[max(0,i-3):i+5].hex(' ')}")
            print(f"Blob context: {blob[max(0,i-3):i+5].hex(' ')}")
            break
