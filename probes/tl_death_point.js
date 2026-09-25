(function(){
var d=null;try{d=ipc.network().getDevice('switchC');}catch(e){}
if(!d){try{reportResult('NO DEVICE');}catch(x){} return;}
var c='';var t='';
try{c=String(d.getCommandLine().getOutput());}catch(e2){try{reportResult('clEX:'+e2);}catch(x){} return;}
try{t=String(d.getIpcTerminalLine().getOutput());}catch(e3){try{reportResult('tlEX:'+e3);}catch(x){} return;}
// Step-by-step reports: each line is sent BEFORE the next risky op, so a
// hard abort shows exactly which content dereference killed the execution.
try{reportResult('A tl_len='+t.length);}catch(x){}
try{reportResult('B typeof='+typeof(t)+' str='+JSON.stringify(t instanceof String));}catch(x){}
try{var ch=t.charCodeAt(0);reportResult('C c0='+ch);}catch(x){}
try{reportResult('D alive-after-C');}catch(x){}
try{var sub=t.substring(0,3);reportResult('E sublen='+sub.length+' sub0='+sub.charCodeAt(0));}catch(x){}
try{reportResult('F alive-after-E');}catch(x){}
try{var hist=null;try{hist=t.getCurrentHistory;}catch(x){}
reportResult('G has_getCurrentHistory='+(typeof t.getCurrentHistory)+' has_getUserHistory='+(typeof t.getUserHistory)+' has_getCommandInput='+(typeof t.getCommandInput));}catch(x){}
})();
