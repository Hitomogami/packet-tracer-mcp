var d=null;try{d=ipc.network().getDevice('switchC');}catch(e){}
if(!d){__out='NO DEVICE';}else{
var c='';var t='';
try{c=String(d.getCommandLine().getOutput());}catch(e2){}
try{t=String(d.getIpcTerminalLine().getOutput());}catch(e3){}
var s='';
for(var i=0;i<t.length;i++){s+=t.charCodeAt(i)+',';}
__out='cl_len='+c.length+' tl_len='+t.length+' CODES:'+s;}
