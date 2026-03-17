import subprocess, sys

r = subprocess.run(["git", "cat-file", "-p", "e955728e0f0b005a27baf079d651559496f27489"], capture_output=True)
blob = r.stdout

# The file starts with correct ASCII: <div align="center">
# Then at byte 34 we should have Chinese chars but they're corrupted
# Let's check: is the ENTIRE file corrupted or just Chinese parts?

# Write the raw bytes to a file for inspection
with open("raw_readme.bin", "wb") as f:
    f.write(blob[:200])

# Let's try: what if the file was written as GBK but read as UTF-8?
# GBK encoding of "股" = 0xB9C9
# If those bytes are interpreted as UTF-8: 0xB9 is not a valid UTF-8 start byte
# So that doesn't work either

# What if the file was double-encoded? (UTF-8 bytes treated as latin1/cp1252 then re-encoded to UTF-8)
# "股" = UTF-8: E8 82 A1
# If E8 82 A1 is interpreted as Latin1: è  ‚  ¡
# Then those chars encoded to UTF-8: C3 A8 C2 82 C2 A1
# That would be 6 bytes instead of 3

# Check: is blob[34] the start of a multi-byte UTF-8 sequence?
byte34 = blob[34]
byte35 = blob[35]
byte36 = blob[36]
print(f"Byte 34: 0x{byte34:02x} = {bin(byte34)}")
print(f"Byte 35: 0x{byte35:02x}")
print(f"Byte 36: 0x{byte36:02x}")

# UTF-8: E9 = 1110 1001 -> 3-byte sequence, expecting 10xxxxxx 10xxxxxx
# So E9 A6 83 = U+2983 or U+??? 
val = ((byte34 & 0x0F) << 12) | ((byte35 & 0x3F) << 6) | (byte36 & 0x3F)
print(f"As UTF-8 3-byte: U+{val:04X}")

# What should it be? "🇨" = U+1F1E8 = 4-byte UTF-8: F0 9F 87 A8
# "股" = U+80A1 = 3-byte UTF-8: E8 82 A1
# "做" = U+505A = 3-byte UTF-8: E5 81 9A
# "T" = U+0054

# So at position 34 we expect something like "A股做T"
# E8 82 A1 = 股
# A8 82 A1... wait, we have E9 A6 83
# U+2983 = "⟃" (mathematical symbol) - that's not right

# Let me try: what if the bytes are GBK?
# GBK uses 2 bytes: first byte 0x81-0xFE, second 0x40-0xFE
# E9 A6 in GBK = ? Let's check
try:
    gbk_text = blob[34:40].decode("gbk")
    print(f"As GBK: {gbk_text}")
except:
    print("Not valid GBK")

# The title should be "# 🇨🇳 A股做T智能分析工具"
# Let's just check: "智能分析工具" in UTF-8
expected = "智能分析工具"
print(f"\nExpected UTF-8 for '智能分析工具': {expected.encode('utf-8').hex(' ')}")
print(f"Actual bytes 42-60: {blob[42:60].hex(' ')}")

# Conclusion: the file content is corrupted at the source level
# We need to completely rewrite it
print("\n=== CONCLUSION: File content is corrupted, needs complete rewrite ===")

# Count corrupted chars
text = blob.decode("utf-8", errors="replace")
bad = sum(1 for c in text if ord(c) > 0x4DFF and not (0x4E00 <= ord(c) <= 0x9FFF))
total_cjk = sum(1 for c in text if 0x4E00 <= ord(c) <= 0x9FFF)
print(f"Bad chars: {bad}, Valid CJK: {total_cjk}")
