"""Bounded Annex-B all-IDR capture units for the existing latest-frame channel.

No network, process launch or privacy decision occurs here. Every emitted unit
contains AUD/SPS/PPS and IDR slices, so dropping previous units is safe.
"""
import re

MAX_ACCESS_UNIT = 2 * 1024 * 1024
_START = re.compile(b'\x00\x00(?:\x00)?\x01')
_PREFIX = b'\x00\x00\x00\x01'


def capture_command(fps, width):
    if fps not in (8,15,24,30,60) or width not in (960,1280):
        raise ValueError('Supported bounded capture dimensions/rate required')
    return ['ffmpeg','-nostdin','-loglevel','error','-f','x11grab',
            '-draw_mouse','0','-framerate',str(fps),'-video_size','1280x720','-i',':99.0',
            '-vf',f'scale={width}:{width*9//16},format=yuv420p',
            '-filter_threads','1','-threads','1','-c:v','h264_nvenc',
            '-preset','p1','-tune','ull','-profile:v','high','-level:v','3.2',
            '-rc','cbr','-b:v','12M','-maxrate','12M','-bufsize','2M',
            '-g','1','-bf','0','-rc-lookahead','0','-zerolatency','1',
            '-aud','1','-bsf:v','dump_extra=freq=keyframe','-f','h264','pipe:1']


class AnnexBAccessUnits:
    """Incremental NAL/AUD splitter; independently repeat cached parameter sets.

    FFmpeg/NVENC normally repeats SPS/PPS on IDRs. Repeating the latest actual
    encoder sets here also covers an encoder that sends them only initially.
    Predictive slices, missing AUD/parameter sets, and oversized data fail closed.
    """
    def __init__(self, limit=MAX_ACCESS_UNIT):
        if type(limit)is not int or not 64<=limit<=MAX_ACCESS_UNIT:
            raise ValueError('Bounded access-unit limit required')
        self.limit=limit;self.buffer=bytearray();self.parts=[]
        self.parts_bytes=0;self.sps=None;self.pps=None

    def _finish_unit(self):
        if not self.parts:return None
        parts=self.parts;self.parts=[];self.parts_bytes=0
        types=[part[0]&31 for part in parts]
        if 5 not in types:return None
        if types[0]!=9 or self.sps is None or self.pps is None:
            raise ValueError('Independent IDR requires AUD/SPS/PPS')
        ordered=[parts[0],self.sps,self.pps]+[p for p in parts[1:] if p[0]&31 not in (7,8)]
        data=b''.join(_PREFIX+p for p in ordered)
        if len(data)>self.limit:raise ValueError('Access-unit bound exceeded')
        return data

    def _nal(self, nal):
        if not nal:return []
        if nal[0]&128:raise ValueError('Forbidden H264 NAL bit')
        kind=nal[0]&31
        if kind in (1,2,3,4):raise ValueError('Predictive H264 slice refused; all-IDR required')
        if kind not in (5,6,7,8,9,12):raise ValueError('Unsupported capture NAL type')
        if kind in (7,8):
            if len(nal)>65536:raise ValueError('Parameter-set bound exceeded')
            if kind==7:self.sps=nal
            else:self.pps=nal
        out=[]
        if kind==9:
            finished=self._finish_unit()
            if finished is not None:out.append(finished)
        if not self.parts and kind!=9:
            # Accept encoder parameter sets before the first explicit AUD.
            if kind in (7,8):return out
            raise ValueError('Capture NAL before AUD')
        self.parts.append(nal);self.parts_bytes+=len(nal)+4
        if self.parts_bytes>self.limit:raise ValueError('Access-unit bound exceeded')
        return out

    def feed(self, chunk):
        if not isinstance(chunk,(bytes,bytearray)):raise TypeError('Binary encoder data required')
        self.buffer.extend(chunk)
        if len(self.buffer)+self.parts_bytes>2*self.limit:raise ValueError('Capture buffer bound exceeded')
        matches=list(_START.finditer(self.buffer));out=[]
        if not matches:
            if len(self.buffer)>self.limit:raise ValueError('NAL/start-code bound exceeded')
            return out
        if any(self.buffer[:matches[0].start()]):raise ValueError('Non Annex-B prefix refused')
        for index in range(len(matches)-1):
            out.extend(self._nal(bytes(self.buffer[matches[index].end():matches[index+1].start()])))
        self.buffer=self.buffer[matches[-1].start():]
        return out

    def finish(self):
        out=[];matches=list(_START.finditer(self.buffer))
        if matches:
            if len(matches)!=1 or any(self.buffer[:matches[0].start()]):raise ValueError('Incomplete Annex-B stream')
            out.extend(self._nal(bytes(self.buffer[matches[0].end():])))
        elif self.buffer:raise ValueError('Incomplete Annex-B stream')
        self.buffer.clear();last=self._finish_unit()
        if last is not None:out.append(last)
        return out
