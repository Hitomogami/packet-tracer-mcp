(function(){
var d=null;try{d=ipc.network().getDevice('pc1');}catch(e){}
if(!d){try{reportResult('A: NO DEVICE');}catch(x){} return;}
var cp=null;
try{cp=d.getCommandPrompt();}catch(e1){try{reportResult('cp EX:'+e1);}catch(x){} return;}
if(!cp){try{reportResult('A: no cp');}catch(x){} return;}
var o='';
try{o=String(cp.getOutput());}catch(e2){o='EX:'+e2;}
try{reportResult('len='+o.length+'\nTAIL>>>'+o.substring(Math.max(0,o.length-700)));}catch(x){}
})();
