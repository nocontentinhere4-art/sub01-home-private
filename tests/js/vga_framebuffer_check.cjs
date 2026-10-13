const assert=require('node:assert/strict'),zlib=require('node:zlib');
const {attachFramebuffer}=require('../../computer/vga_framebuffer.cjs');
const adapter={set_mode(){},set_size_graphical(){},update_buffer(){}};
const rgba=new Uint8ClampedArray([255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255]);
let fill=()=>{};const c=attachFramebuffer(adapter,()=>({screen_fill_buffer(){fill();}}));
assert.equal(c.capture().available,false);
adapter.set_mode(true);adapter.set_size_graphical(2,2);
fill=()=>adapter.update_buffer([{image_data:{data:rgba,width:2,height:2},screen_x:0,screen_y:0,buffer_x:0,buffer_y:0,buffer_width:2,buffer_height:2}]);
const frame=c.capture();assert.equal(frame.kind,'graphical');assert.equal(frame.revision,1);assert.equal(c.capture().revision,1);
let offset=8,compressed=[];while(offset<frame.png.length){const n=frame.png.readUInt32BE(offset),kind=frame.png.toString('ascii',offset+4,offset+8);if(kind==='IDAT')compressed.push(frame.png.subarray(offset+8,offset+8+n));offset+=n+12;}
assert.deepEqual(zlib.inflateSync(Buffer.concat(compressed)),Buffer.from([0,...rgba.slice(0,8),0,...rgba.slice(8)]));
rgba[0]=128;assert.equal(c.capture().revision,2);
adapter.set_mode(false);assert.equal(c.capture().available,false);
adapter.set_mode(true);adapter.set_size_graphical(99999,99999);assert.equal(c.capture().available,false);
console.log('PASS: untouched VGA RGBA pixels, actual PNG scanlines, stable frame revision, serial-mode gate and bounded allocation.');
