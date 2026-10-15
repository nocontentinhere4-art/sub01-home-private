"""Explicit captured-window derivative with a short C1 endpoint bridge."""
import copy,math,struct
from fp_arms_clip_tracks import rows


def derive(doc,binary,start_key=105,end_key=210,bridge_intervals=12,bridge_seconds=.4):
    if not 0<start_key<end_key or bridge_intervals<2 or bridge_seconds<=0:raise ValueError('Invalid explicit keyboard window/bridge')
    out=copy.deepcopy(doc);data=bytearray(binary);animation=out['animations'][0];original=doc['animations'][0]
    def unpack(ai):
        width={'SCALAR':1,'VEC3':3,'VEC4':4}[doc['accessors'][ai]['type']];return [struct.unpack('<'+'f'*width,r)for r in rows(doc,binary,ai)]
    def append(values,kind):
        while len(data)%4:data.append(0)
        start=len(data)
        for value in values:data.extend(struct.pack('<'+'f'*len(value),*value))
        out['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(data)-start});a={'bufferView':len(out['bufferViews'])-1,'componentType':5126,'type':kind,'count':len(values)}
        if kind=='SCALAR':a.update(min=[values[0][0]],max=[values[-1][0]])
        out['accessors'].append(a);return len(out['accessors'])-1
    time=[v[0]for v in unpack(original['samplers'][0]['input'])]
    if end_key>=len(time)or start_key==0 or end_key==len(time)-1:raise ValueError('Endpoint velocity neighbors required')
    written_times=[v-time[start_key]for v in time[start_key:end_key+1]];capture_duration=written_times[-1];written_times +=[capture_duration+bridge_seconds*i/bridge_intervals for i in range(1,bridge_intervals+1)];ti=append([(v,)for v in written_times],'SCALAR');used=set();channels=[]
    for ch in animation['channels']:
        si=ch['sampler']
        if si in used:continue
        used.add(si);sampler=animation['samplers'][si];old=original['samplers'][si];kind=doc['accessors'][old['output']]['type'];values=unpack(old['output']);path=ch['target']['path'];a=list(values[end_key]);b=list(values[start_key]);prev=list(values[end_key-1]);after=list(values[start_key+1]);rotation=path=='rotation'
        if rotation:
            if sum(x*y for x,y in zip(a,prev))<0:prev=[-x for x in prev]
            if sum(x*y for x,y in zip(b,after))<0:after=[-x for x in after]
            if sum(x*y for x,y in zip(a,b))<0:b=[-x for x in b];after=[-x for x in after]
        da=[(x-y)/(time[end_key]-time[end_key-1])for x,y in zip(a,prev)];db=[(x-y)/(time[start_key+1]-time[start_key])for x,y in zip(after,b)];bridge=[]
        for i in range(1,bridge_intervals+1):
            if i==bridge_intervals:value=values[start_key]
            else:
                u=i/bridge_intervals;h00=2*u**3-3*u**2+1;h10=u**3-2*u**2+u;h01=-2*u**3+3*u**2;h11=u**3-u**2;value=[h00*x+h10*bridge_seconds*dx+h01*y+h11*bridge_seconds*dy for x,dx,y,dy in zip(a,da,b,db)]
                if rotation:
                    length=math.sqrt(sum(x*x for x in value))
                    if length<.5:raise ValueError('Quaternion bridge singular')
                    value=[x/length for x in value]
            bridge.append(value)
        fresh=values[start_key:end_key+1]+bridge;sampler['input']=ti;sampler['output']=append(fresh,kind)
        assert rows(out,data,sampler['output'])[:end_key-start_key+1]==rows(doc,binary,old['output'])[start_key:end_key+1]
        assert rows(out,data,sampler['output'])[-1]==rows(doc,binary,old['output'])[start_key]
        channels.append({'name':doc['nodes'][ch['target']['node']]['name'],'path':path})
    out['buffers'][0]['byteLength']=len(data);animation['name']='SUB01_FirstPersonKeyboard_LoopCandidate';animation['extras']={'derived':True,'captured_source_keys':[start_key,end_key],'bridge_seconds':bridge_seconds,'source_ready':False,'native_ready':False}
    return out,bytes(data),{'schema':'sub01.fp-keyboard-loop-derivation.v1','captured_key_range':[start_key,end_key],'captured_time_range_s':[time[start_key],time[end_key]],'captured_keys_exact_rows':end_key-start_key+1,'captured_duration_s':capture_duration,'bridge_intervals':bridge_intervals,'bridge_seconds':bridge_seconds,'total_keys':len(written_times),'duration_s':written_times[-1],'original_prefix_unchanged':bytes(data[:len(binary)])==binary,'captured_track_rows_exact':True,'last_rows_equal_first_exact':True,'bridge_tracks':channels,'bridge_method':'Normalized quaternion/component cubic Hermite using captured endpoint velocities; explicit derived bridge, not untouched capture','source_ready':False,'native_ready':False}


def add_midpoint_keys(doc,binary):
    """Retain every original float32 row, add its exact glTF interpolation midpoint."""
    from math import acos,sin,sqrt
    out=copy.deepcopy(doc);data=bytearray(binary);animation=out['animations'][0];samplers=doc['animations'][0]['samplers'];written=set()
    def append(values,kind):
        while len(data)%4:data.append(0)
        start=len(data)
        for value in values:data.extend(struct.pack('<'+'f'*len(value),*value))
        out['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(data)-start});a={'bufferView':len(out['bufferViews'])-1,'componentType':5126,'type':kind,'count':len(values)}
        if kind=='SCALAR':a.update(min=[values[0][0]],max=[values[-1][0]])
        out['accessors'].append(a);return len(out['accessors'])-1
    for ch in animation['channels']:
        si=ch['sampler']
        if si in written:continue
        written.add(si);old=samplers[si];time=[struct.unpack('<f',v)[0]for v in rows(doc,binary,old['input'])];kind=doc['accessors'][old['output']]['type'];width={'SCALAR':1,'VEC3':3,'VEC4':4}[kind];values=[struct.unpack('<'+'f'*width,v)for v in rows(doc,binary,old['output'])];times=[];fresh=[]
        for i in range(len(time)-1):
            a=values[i];b=values[i+1];times.extend([(time[i],),((time[i]+time[i+1])/2,)]);fresh.append(a)
            if ch['target']['path']=='rotation':
                an=sqrt(sum(v*v for v in a));bn=sqrt(sum(v*v for v in b));aa=[v/an for v in a];bb=[v/bn for v in b];dot=sum(x*y for x,y in zip(aa,bb))
                if dot<0:bb=[-v for v in bb];dot=-dot
                angle=acos(min(1.,dot))
                mid=[x+y for x,y in zip(aa,bb)]if angle<1e-5 else[(sin(angle/2)*x+sin(angle/2)*y)/sin(angle)for x,y in zip(aa,bb)];norm=sqrt(sum(v*v for v in mid));mid=[v/norm for v in mid]
            else:mid=[(x+y)/2 for x,y in zip(a,b)]
            fresh.append(mid)
        times.append((time[-1],));fresh.append(values[-1]);animation['samplers'][si]['input']=append(times,'SCALAR');animation['samplers'][si]['output']=append(fresh,kind);assert rows(out,data,animation['samplers'][si]['output'])[::2]==rows(doc,binary,old['output'])
    out['buffers'][0]['byteLength']=len(data);return out,bytes(data)
