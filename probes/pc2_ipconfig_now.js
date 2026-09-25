(function(){
var d=null;try{d=ipc.network().getDevice('pc2');}catch(e){}
if(!d){try{reportResult('A: NO DEVICE');}catch(x){} return;}
var cp=null;
try{cp=d.getCommandPrompt();}catch(e1){try{reportResult('cp EX:'+e1);}catch(x){} return;}
if(!cp){try{reportResult('A: no cp');}catch(x){} return;}
try{cp.enterCommand('ipconfig');}catch(e0){}
var t0=(new Date()).getTime();
while((new Date()).getTime()-t0<2000){}
var o='';
try{o=String(cp.getOutput());}catch(e2){o='EX:'+e2;}
var i=o.lastIndexOf('FastEthernet0 Connection');
try{reportResult('len='+o.length+'\nIPCONFIG>>>'+o.substring(Math.max(0,i-60)));}catch(x){}
})();
