var d=null;try{d=ipc.network().getDevice('switchC');}catch(e){}
if(!d){__out='NO DEVICE';}else{
var c='';var t='?';var clEx='';
try{c=String(d.getCommandLine().getOutput());}catch(e2){clEx=e2;}
try{t=String(d.getIpcTerminalLine().getOutput());}catch(e3){t='TLEXC:'+e3;}
__out='cl_len='+c.length+' tl_len='+t.length+' clEx='+clEx;}
