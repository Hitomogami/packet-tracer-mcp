var d=null;try{d=ipc.network().getDevice('switchC');}catch(e){}
if(!d){__out='NO DEVICE';}else{
var c='';var t='';var steps=[];
try{c=String(d.getCommandLine().getOutput());}catch(e2){steps.push('clEX:'+e2);}
try{t=String(d.getIpcTerminalLine().getOutput());}catch(e3){steps.push('tlEX:'+e3);}
// content-liveness ladder: each step is individually fatal if the char
// data is dangling — report which step we reached via charCodes-style
// safe digits only (no content characters ever enter __out).
var s='reached:';
try{s+='len('+t.length+')';}catch(e4){steps.push('lenEX:'+e4);__out=s+' | '+steps.join('|');}
if(steps.length===0){
try{var ch=t.charCodeAt(0);s+=' c0('+ch+')';}catch(e5){steps.push('ccEX:'+e5);}
}
if(steps.length===0){
try{var sub=t.substring(0,3);s+=' sub('+sub.length+')';}catch(e6){steps.push('subEX:'+e6);}
}
if(steps.length===0){
try{var cat='x'+t;s+=' catlen('+cat.length+')';}catch(e7){steps.push('catEX:'+e7);}
}
__out=s+' | '+steps.join('|');
}
