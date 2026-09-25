(function(){
var d=null;try{d=ipc.network().getDevice('pc2');}catch(e){}
var cp=null;
try{cp=d.getCommandPrompt();}catch(e1){}
if(!cp){try{reportResult('A: no cp');}catch(x){} return;}
var o0='';
try{o0=String(cp.getOutput());}catch(e2){o0='';}
try{reportResult('A: base_len='+o0.length);}catch(x){}
try{cp.enterCommand('ping 192.168.0.3');}catch(e3){try{reportResult('ping EX:'+e3);}catch(x){} return;}
try{reportResult('B: ping sent');}catch(x){}
var t0=(new Date()).getTime();
while((new Date()).getTime()-t0<8000){}
try{reportResult('C: spun 8s');}catch(x){}
var o='';
try{o=String(cp.getOutput());}catch(e4){o='EX:'+e4;}
try{reportResult('D: len='+o.length+'\nTAIL>>>'+o.substring(Math.max(0,o.length-900)));}catch(x){}
})();
