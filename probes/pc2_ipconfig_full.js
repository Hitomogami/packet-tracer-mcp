(function(){
var d=null;try{d=ipc.network().getDevice('pc2');}catch(e){}
var cp=null;
try{cp=d.getCommandPrompt();}catch(e1){}
if(!cp){try{reportResult('A: no cp');}catch(x){} return;}
try{reportResult('A: cp ok, dhcpFlag='+JSON.stringify(function(){try{return d.getDhcpFlag();}catch(e){return 'EX';}}()));}catch(x){}
try{cp.enterCommand('ipconfig');}catch(e2){}
try{reportResult('B: ipconfig sent');}catch(x){}
var o='';
try{o=String(cp.getOutput());}catch(e3){o='EX:'+e3;}
try{reportResult('C: len='+o.length+'\nFULL>>>'+o);}catch(x){}
})();
