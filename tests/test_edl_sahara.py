"""Self-check for Sahara packet framing (run: python tests/test_edl_sahara.py)."""
import struct, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.hardware import edl_detector as e


class FakeSerial:
    """Scripted device: records writes, replays queued reads."""
    def __init__(self, replies): self.tx, self.rx, self.timeout = [], bytearray(b"".join(replies)), 1
    is_open = True
    in_waiting = 0
    def write(self, d): self.tx.append(bytes(d)); return len(d)
    def flush(self): pass
    def read(self, n): out, self.rx = bytes(self.rx[:n]), self.rx[n:]; return out
    def close(self): pass


def proto(replies):
    p = e.SaharaProtocol("FAKE"); p._serial = FakeSerial(replies); return p


# HELLO_RESPONSE is 48 bytes with length field 0x30
p = proto([]); p.send_hello_response(2, 1, e.SAHARA_MODE_COMMAND)
assert len(p._serial.tx[0]) == 48 and struct.unpack("<I", p._serial.tx[0][4:8])[0] == 48

# CMD_READY accepted; END_IMAGE_TRANSFER refusal raises PermissionError
proto([struct.pack("<2I", e.SAHARA_CMD_READY_ID, 8)]).wait_command_ready()
try:
    proto([struct.pack("<4I", e.SAHARA_END_TRANSFER_ID, 16, 13, 1)]).wait_command_ready()
    assert False
except PermissionError as exc:
    assert "image_id=13" in str(exc) and "status=1" in str(exc)

# CMD_EXEC: 16-byte EXEC_RESP then payload
p = proto([struct.pack("<4I", e.SAHARA_CMD_EXEC_RESP_ID, 16, 1, 4), b"\x99\x95\xac\x9d"])
assert p.execute_command(e.SAHARA_EXEC_CMD_SERIAL_NUM) == b"\x99\x95\xac\x9d"

# stale END_IMAGE_TRANSFER in place of HELLO -> ConnectionError naming the state
try:
    proto([struct.pack("<4I", e.SAHARA_END_TRANSFER_ID, 16, 13, 1)]).wait_for_hello(); assert False
except ConnectionError as exc:
    assert "error state" in str(exc)

print("ok")

# image transfer: READ_DATA x2, END_IMAGE_TRANSFER ok, DONE_RESP
import tempfile
img = bytes(range(256)) * 8
with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".elf") as f: f.write(img); path = f.name
p = proto([struct.pack("<5I", e.SAHARA_READ_DATA_ID, 20, 13, 0, 1024),
           struct.pack("<2I3Q", e.SAHARA_READ_DATA64_ID, 32, 13, 1024, 1024),
           struct.pack("<4I", e.SAHARA_END_TRANSFER_ID, 16, 13, 0),
           struct.pack("<3I", e.SAHARA_DONE_RESP_ID, 12, 0)])
p.upload_image(path)
assert p._serial.tx[0] == img[:1024] and p._serial.tx[1] == img[1024:] and p._serial.tx[2][:4] == b"\x05\0\0\0"
try:
    proto([struct.pack("<4I", e.SAHARA_END_TRANSFER_ID, 16, 13, 37)]).upload_image(path); assert False
except PermissionError as exc: assert "status=37" in str(exc) and "signature" in str(exc)
os.unlink(path)
print("image transfer ok")
