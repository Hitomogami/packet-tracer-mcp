(function(){
var d=null;try{d=ipc.network().getDevice('pc2');}catch(e){}
var cp=null;
try{cp=d.getCommandPrompt();}catch(e1){}
if(!cp){try{reportResult('A: no cp');}catch(x){} return;}
var o='';
try{o=String(cp.getOutput());}catch(e2){o='EX:'+e2;}
try{reportResult('len='+o.length+'\nTAIL>>>'+o.substring(Math.max(0,o.length-700)));}catch(x){}
})();
