(function(){
var d=null;try{d=ipc.network().getDevice('pc1');}catch(e){}
var cp=null;
try{cp=d.getCommandPrompt();}catch(e1){}
if(!cp){try{reportResult('A: no cp');}catch(x){} return;}
try{reportResult('A: cp ok');}catch(x){}
try{cp.enterCommand('ping 192.168.1.3');}catch(e3){try{reportResult('ping EX:'+e3);}catch(x){} return;}
try{reportResult('B: ping sent');}catch(x){}
var t0=(new Date()).getTime();
while((new Date()).getTime()-t0<15000){}
var o='';
try{o=String(cp.getOutput());}catch(e4){o='EX:'+e4;}
try{reportResult('C: len='+o.length+'\nTAIL>>>'+o.substring(Math.max(0,o.length-700)));}catch(x){}
})();
