var d=null;try{d=ipc.network().getDevice('switchC');}catch(e){}
if(!d){__out='NO DEVICE';}else{
function scan(label,t){var r=[label];
var n=-1;try{n=t.getTelnetClientCount();}catch(e){r.push('cntEX:'+e);}
r.push('telnetCount='+n);
for(var i=0;i<n&&i<4;i++){
(function(){
var c=null;try{c=t.getTelnetClientAt(i);}catch(e){r.push('at'+i+' EX:'+e);return;}
if(!c){r.push('at'+i+' =null');return;}
var ks=[];for(var k in c){ks.push(k);}
var s='at'+i+' ['+ks.join('|')+']';
if(typeof c.getOutput==='function'){try{var o=String(c.getOutput());s+=' len='+o.length+' tail='+JSON.stringify(o.substring(Math.max(0,o.length-200)));}catch(e){s+=' outEX:'+e;}}
r.push(s);
})();}
return r.join('\n');}
var out=[];
try{out.push(scan('IPC-TL',d.getIpcTerminalLine()));}catch(e){out.push('ipcEX:'+e);}
try{out.push(scan('GUI-CL',d.getCommandLine()));}catch(e){out.push('clEX:'+e);}
try{out.push(scan('CONSOLE-PORT-TL',d.getConsole().getTerminalLine()));}catch(e){out.push('cpEX:'+e);}
__out=out.join('\n\n');}
