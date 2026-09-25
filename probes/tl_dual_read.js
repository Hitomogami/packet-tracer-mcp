var d=null;try{d=ipc.network().getDevice('switchC');}catch(e){}
if(!d){__out='NO DEVICE';}else{
var c='';
try{c=String(d.getCommandLine().getOutput());}catch(e2){}
function spin(ms){var t0=(new Date()).getTime();while((new Date()).getTime()-t0<ms){}}
var t1='';var t2='';var t3='';
try{t1=String(d.getIpcTerminalLine().getOutput());}catch(e3){t1='EX1:'+e3;}
spin(2000);
try{t2=String(d.getIpcTerminalLine().getOutput());}catch(e4){t2='EX2:'+e4;}
spin(2000);
try{t3=String(d.getIpcTerminalLine().getOutput());}catch(e5){t3='EX3:'+e5;}
__out='cl_len='+c.length
+'\nL1='+t1.length+' L2='+t2.length+' L3='+t3.length
+'\nT1>>>'+t1+'\nT2>>>'+t2+'\nT3>>>'+t3;}
