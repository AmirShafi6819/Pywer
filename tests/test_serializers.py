import unittest
import uuid
from pywer.util.serializer import ByteReader, ByteWriter


class TestSerializers(unittest.TestCase):
    def test_u8_and_bool(self):
        w = ByteWriter()
        w.write_u8(42)
        w.write_bool(True)
        w.write_bool(False)
        data = w.get()

        r = ByteReader(data)
        self.assertEqual(r.read_u8(), 42)
        self.assertTrue(r.read_bool())
        self.assertFalse(r.read_bool())
        self.assertEqual(r.left(), 0)

    def test_varuint(self):
        w = ByteWriter()
        values = [0, 1, 127, 128, 255, 300, 16384, 2097151, 2147483647]
        for v in values:
            w.write_varuint32(v)

        r = ByteReader(w.get())
        for v in values:
            self.assertEqual(r.read_varuint32(), v)
        self.assertEqual(r.left(), 0)

    def test_varint_zigzag(self):
        w = ByteWriter()
        values = [0, -1, 1, -2, 2, -2147483648, 2147483647]
        for v in values:
            w.write_varint32(v)

        r = ByteReader(w.get())
        for v in values:
            self.assertEqual(r.read_varint32(), v)
        self.assertEqual(r.left(), 0)

    def test_u16_u24_u32_u64(self):
        w = ByteWriter()
        w.write_u16_le(0x1234)
        w.write_u16_be(0x1234)
        w.write_u24_le(0x123456)
        w.write_u32_le(0x12345678)
        w.write_u32_be(0x12345678)
        w.write_u64_le(0x0102030405060708)
        w.write_u64_be(0x0102030405060708)

        r = ByteReader(w.get())
        self.assertEqual(r.read_u16_le(), 0x1234)
        self.assertEqual(r.read_u16_be(), 0x1234)
        self.assertEqual(r.read_u24_le(), 0x123456)
        self.assertEqual(r.read_u32_le(), 0x12345678)
        self.assertEqual(r.read_u32_be(), 0x12345678)
        self.assertEqual(r.read_u64_le(), 0x0102030405060708)
        self.assertEqual(r.read_u64_be(), 0x0102030405060708)
        self.assertEqual(r.left(), 0)

    def test_string_and_uuid(self):
        w = ByteWriter()
        test_str = "Minecraft Bedrock §ePywer"
        test_uuid = uuid.uuid4()
        w.write_string(test_str)
        w.write_uuid(test_uuid)

        r = ByteReader(w.get())
        self.assertEqual(r.read_string(), test_str)
        self.assertEqual(r.read_uuid(), test_uuid)
        self.assertEqual(r.left(), 0)


if __name__ == "__main__":
    unittest.main()
