var d=null;try{d=ipc.network().getDevice('pc2');}catch(e){}
if(!d){__out='NO DEVICE';}else{
var ks=[];for(var k in d){ks.push(k);}
var probes=['enterCommand','skipBoot','getCommandLine','getIpcTerminalLine','getConsole','isDesktopAvailable','getUserDesktopAppCount','getUserDesktopAppAt','getUserDesktopAppById','addUserDesktopApp','runCodeInProject','getProcess','getUserEntryAt','isUserExist'];
var t=[];
for(var i=0;i<probes.length;i++){
var v;try{v=typeof d[probes[i]];}catch(e){v='EXC';}
if(v!=='undefined')t.push(probes[i]+'='+v);}
__out='keys='+ks.join('|')+'\nNON-UNDEF: '+t.join(' ');}
