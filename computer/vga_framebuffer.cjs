// Actual v86 graphical VGA pixels; no DOM, browser, fonts or synthetic desktop.
const zlib = require('node:zlib'), crypto = require('node:crypto');
function crc32(bytes) { let crc=0xffffffff; for(const b of bytes){crc^=b;for(let n=0;n<8;n++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return(crc^0xffffffff)>>>0; }
function chunk(kind,data){const name=Buffer.from(kind),out=Buffer.alloc(data.length+12);out.writeUInt32BE(data.length,0);name.copy(out,4);data.copy(out,8);out.writeUInt32BE(crc32(Buffer.concat([name,data])),out.length-4);return out;}
function png(width,height,rgba){const header=Buffer.alloc(13);header.writeUInt32BE(width,0);header.writeUInt32BE(height,4);header[8]=8;header[9]=6;const rows=Buffer.alloc(height*(width*4+1));for(let y=0;y<height;y++)rgba.copy(rows,y*(width*4+1)+1,y*width*4,(y+1)*width*4);return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',zlib.deflateSync(rows,{level:1})),chunk('IEND',Buffer.alloc(0))]);}
function attachFramebuffer(adapter, getVga) {
 if(!adapter?.set_mode||!adapter?.set_size_graphical||!adapter?.update_buffer)return{capture:()=>({kind:"serial",available:false,reason:"v86 graphical adapter is unavailable"})};
 const session=crypto.randomUUID();
 let graphical=false,width=0,height=0,pixels=null,revision=0,lastHash='',lastPng=null;
 const mode=adapter.set_mode.bind(adapter),size=adapter.set_size_graphical.bind(adapter),update=adapter.update_buffer.bind(adapter);
 adapter.set_mode=function(active){graphical=!!active;mode(active);if(!graphical){pixels=null;lastHash='';lastPng=null;}};
 adapter.set_size_graphical=function(w,h,...args){size(w,h,...args);if(Number.isInteger(w)&&Number.isInteger(h)&&w>0&&h>0&&w*h<=1280*1024){width=w;height=h;pixels=Buffer.alloc(w*h*4);}else{width=height=0;pixels=null;}};
 adapter.update_buffer=function(layers){update(layers);if(!graphical||!pixels)return;
  for(const layer of layers){const data=layer.image_data;if(!data?.data||!data.width)continue;
   for(let row=0;row<layer.buffer_height;row++){
    const dy=layer.screen_y+row,sy=layer.buffer_y+row;if(dy<0||dy>=height||sy<0||sy>=data.height)continue;
    const dx=Math.max(0,layer.screen_x),skip=dx-layer.screen_x,sx=layer.buffer_x+skip,count=Math.min(layer.buffer_width-skip,width-dx,data.width-sx);if(count<=0||sx<0)continue;
    Buffer.from(data.data.buffer,data.data.byteOffset+(sy*data.width+sx)*4,count*4).copy(pixels,(dy*width+dx)*4);
   }
  }
 };
 return {capture(){const vga=getVga();if(!graphical||!pixels||!vga)return{kind:'serial',available:false,reason:'Guest has not entered a supported graphical VGA mode'};vga.screen_fill_buffer();const hash=crypto.createHash('sha256').update(pixels).digest('hex');if(hash!==lastHash){revision++;lastHash=hash;lastPng=png(width,height,pixels);}return{kind:'graphical',available:true,width,height,revision,frame_id:session+'-'+revision,png:lastPng};}};
}
module.exports={attachFramebuffer,png};
