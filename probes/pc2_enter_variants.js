(function(){
var d=null;try{d=ipc.network().getDevice('pc2');}catch(e){}
var cp=null;
try{cp=d.getCommandPrompt();}catch(e1){}
if(!cp){try{reportResult('A: no cp');}catch(x){} return;}
try{reportResult('A: cp ok');}catch(x){}
var r1='!none';
try{r1=JSON.stringify(cp.enterCommand('ipconfig'));}catch(e2){r1='EX:'+e2;}
try{reportResult('B: one-arg ret='+r1);}catch(x){}
var o1='';
try{o1=String(cp.getOutput());}catch(e3){o1='EX:'+e3;}
try{reportResult('C: len='+o1.length+' tail='+JSON.stringify(o1.substring(Math.max(0,o1.length-200))));}catch(x){}
var r2='!none';
try{r2=JSON.stringify(cp.enterCommand('ipconfig','user'));}catch(e4){r2='EX:'+e4;}
try{reportResult('D: user-mode ret='+r2);}catch(x){}
var o2='';
try{o2=String(cp.getOutput());}catch(e5){o2='EX:'+e5;}
try{reportResult('E: len='+o2.length+' tail='+JSON.stringify(o2.substring(Math.max(0,o2.length-200))));}catch(x){}
})();
