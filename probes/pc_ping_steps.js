(function(){
var d=null;
try{d=ipc.network().getDevice('pc2');}catch(e){}
if(!d){try{reportResult('A: NO DEVICE');}catch(x){} return;}
try{reportResult('A: device ok');}catch(x){}
try{d.skipBoot();}catch(e1){}
try{reportResult('B: skipBoot done');}catch(x){}
var en='ok';
try{d.enterCommand('enable','enable');}catch(e2){en='EX:'+e2;}
try{reportResult('C: enable-switch done, en='+en);}catch(x){}
var p='!none';
try{p=JSON.stringify(d.enterCommand('ping 192.168.0.3',''));}catch(e3){p='EX:'+e3;}
try{reportResult('D: ping ret='+p);}catch(x){}
try{reportResult('E: alive');}catch(x){}
})();
