var d=null;try{d=ipc.network().getDevice('switchC');}catch(e){}
if(!d){__out='NO DEVICE';}else{
var cp=null;try{cp=d.getConsole();}catch(e2){__out='getConsole EX:'+e2;}
if(!cp){__out='NO CONSOLE PORT';}else{
var t=null;try{t=cp.getTerminalLine();}catch(e3){__out='getTerminalLine EX:'+e3;}
if(!t){__out='NO TERMINAL LINE';}else{
var ks=[];for(var k in t){ks.push(k);}
var info='keys='+ks.join('|')
+'\nmode='+(function(){try{return String(t.getMode());}catch(e){return 'EX:'+e;}})()
+'\nprompt='+(function(){try{return JSON.stringify(String(t.getPrompt()));}catch(e){return 'EX:'+e;}})();
if(typeof t.getOutput==='function'){
var o='';try{o=String(t.getOutput());}catch(e4){o='OUTEX:'+e4;}
info+='\noutlen='+o.length+'\nTAIL>>>\n'+o.substring(Math.max(0,o.length-1200));
}else{info+='\ngetOutput='+(typeof t.getOutput);}
__out=info;}}}
