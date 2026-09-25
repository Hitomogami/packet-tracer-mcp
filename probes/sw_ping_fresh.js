(function(){
var d=null;try{d=ipc.network().getDevice('switchC');}catch(e){}
if(!d){try{reportResult('NO DEVICE');}catch(x){} return;}
try{d.skipBoot();}catch(e1){}
try{d.enterCommand('enable','enable');}catch(e2){}
var ret='!none';
try{ret=JSON.stringify(d.enterCommand('ping 192.168.0.3',''));}catch(e3){ret='EXC:'+e3;}
try{reportResult('PING_RET='+ret);}catch(x){}
})();
