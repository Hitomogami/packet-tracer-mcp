var d=null;try{d=ipc.network().getDevice('switchC');}catch(e){}
if(!d){__out='NO DEVICE';}else{
function dump(label,fn){var o=null;try{o=fn();}catch(e){return label+' EX:'+e;}
if(!o)return label+' = null';
var ks=[];for(var k in o){ks.push(k);}
var extra='';
try{if(typeof o.getOutput==='function'){var s=String(o.getOutput());extra=' outlen='+s.length+' tail='+JSON.stringify(s.substring(Math.max(0,s.length-150)));}}catch(e){extra+=' outEX:'+e;}
return label+' ['+ks.join('|')+']'+extra;}
var r=[];
r.push(dump('getConsole',function(){return d.getConsole();}));
r.push(dump('getLine',function(){return d.getLine();}));
r.push(dump('getVtyLine',function(){return d.getVtyLine();}));
r.push(dump('tl.getCommandInput',function(){return d.getIpcTerminalLine().getCommandInput();}));
__out=r.join('\n\n');}
