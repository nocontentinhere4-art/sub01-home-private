import struct
import unittest
from derive_reverse_upright_getup import reverse_rows

class ReverseDerivedTest(unittest.TestCase):
    def test_interleaved_protected_data_and_exact_endpoints(self):
        raw=b'HEAD'+struct.pack('<2f',1,99)+struct.pack('<2f',2,98)+struct.pack('<2f',3,97)+b'TAIL';out=reverse_rows(raw,4,8,3,4)
        self.assertEqual(out[:4],b'HEAD');self.assertEqual(out[-4:],b'TAIL');self.assertEqual(struct.unpack_from('<f',out,4)[0],3);self.assertEqual(struct.unpack_from('<f',out,20)[0],1)
        for offset in (8,16,24):self.assertEqual(raw[offset:offset+4],out[offset:offset+4])
        self.assertEqual(reverse_rows(out,4,8,3,4),raw)

if __name__=='__main__':unittest.main()
