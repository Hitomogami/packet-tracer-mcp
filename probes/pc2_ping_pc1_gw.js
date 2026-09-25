(function(){
var d=null;try{d=ipc.network().getDevice('pc2');}catch(e){}
if(!d){try{reportResult('A: NO DEVICE');}catch(x){} return;}
var cp=null;
try{cp=d.getCommandPrompt();}catch(e1){try{reportResult('cp EX:'+e1);}catch(x){} return;}
if(!cp){try{reportResult('A: no cp');}catch(x){} return;}
try{cp.enterCommand('ipconfig');}catch(e0){}
try{cp.enterCommand('ping 192.168.1.2');}catch(e3){try{reportResult('ping EX:'+e3);}catch(x){} return;}
var t0=(new Date()).getTime();
while((new Date()).getTime()-t0<15000){}
var o='';
try{o=String(cp.getOutput());}catch(e4){o='EX:'+e4;}
try{reportResult('len='+o.length+'\nTAIL>>>'+o.substring(Math.max(0,o.length-1400)));}catch(x){}
})();
