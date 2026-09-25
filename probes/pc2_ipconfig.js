(function(){
var d=null;try{d=ipc.network().getDevice('pc2');}catch(e){}
if(!d){try{reportResult('A: NO DEVICE');}catch(x){} return;}
var cp=null;
try{cp=d.getCommandPrompt();}catch(e1){try{reportResult('A EX:'+e1);}catch(x){} return;}
if(!cp){try{reportResult('A: null cp');}catch(x){} return;}
try{reportResult('A: cp ok');}catch(x){}
var m='?';
try{m=String(cp.getMode());}catch(e2){m='EX:'+e2;}
try{reportResult('B: mode='+m);}catch(x){}
var o0='';
try{o0=String(cp.getOutput());}catch(e3){o0='EX:'+e3;}
try{reportResult('C: outlen_before='+o0.length+' tail='+JSON.stringify(o0.substring(Math.max(0,o0.length-120))));}catch(x){}
var r='!none';
try{r=JSON.stringify(cp.enterCommand('ipconfig',''));}catch(e4){r='EX:'+e4;}
try{reportResult('D: ipconfig ret='+r);}catch(x){}
var o1='';
try{o1=String(cp.getOutput());}catch(e5){o1='EX:'+e5;}
try{reportResult('E: outlen_after='+o1.length+'\nOUT>>>'+o1.substring(Math.max(0,o1.length-600)));}catch(x){}
})();
