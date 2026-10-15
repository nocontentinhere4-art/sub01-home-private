"""Read-only contact sidecar from actual generated SOMA output with BVH timing."""
import argparse
import ast
import hashlib
import json
import re
import zipfile
from pathlib import Path

def extract(source, bvh):
    raw = source.read_bytes()
    text = bvh.read_text()
    count = int(re.search(r'Frames:\s*(\d+)', text)[1])
    frame_time = float(re.search(r'Frame Time:\s*([\d.eE-]+)', text)[1])
    fps = round(1/frame_time)
    assert 1 <= fps <= 120 and abs(1/frame_time-fps) < .001
    with zipfile.ZipFile(source) as archive:
        data = archive.read('foot_contacts.npy')
    assert data[:6] == bytes([147])+b'NUMPY'
    prefix = 10 if data[6] == 1 else 12
    size = int.from_bytes(data[8:prefix], 'little')
    header = ast.literal_eval(data[prefix:prefix+size].decode())
    assert header['descr'] == '|b1' and not header['fortran_order']
    assert tuple(header['shape']) == (count, 6)
    values = data[prefix+size:]
    assert len(values) == count*6 and all(v in (0, 1) for v in values)
    return {
        'schema': 'sub01.source-soma-foot-contacts.v1',
        'soma_sha256': hashlib.sha256(raw).hexdigest(),
        'bvh_sha256': hashlib.sha256(bvh.read_bytes()).hexdigest(),
        'fps': fps,
        'fps_proof': f'Actual BVH Frame Time={frame_time}; caller must also verify model output timing',
        'frame_count': count,
        'duration_samples_s': count/fps,
        'last_sample_time_s': (count-1)/fps,
        'joint_order': ['LeftFoot', 'LeftToeBase', 'LeftToeEnd', 'RightFoot', 'RightToeBase', 'RightToeEnd'],
        'contacts': [[bool(v) for v in values[i*6:(i+1)*6]] for i in range(count)],
    }

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('bvh', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = extract(args.source, args.bvh)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'contacts'}))
