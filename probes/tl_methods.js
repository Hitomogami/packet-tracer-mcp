var d=null;try{d=ipc.network().getDevice('switchC');}catch(e){}
if(!d){__out='NO DEVICE';}else{
var tl=null;var ex='';
try{tl=d.getIpcTerminalLine();}catch(e2){ex='EX:'+e2;}
if(!tl){__out='NO TL '+ex;}else{
var ks=[];for(var k in tl){ks.push(k);}
__out='keys='+ks.join('|')
+'\nh_getOutput='+(typeof tl.getOutput)
+' h_getMode='+(typeof tl.getMode)
+' h_getPrompt='+(typeof tl.getPrompt)
+' h_getCurrentHistory='+(typeof tl.getCurrentHistory)
+' h_getUserHistory='+(typeof tl.getUserHistory)
+' h_getConfigHistory='+(typeof tl.getConfigHistory)
+' h_getCommandInput='+(typeof tl.getCommandInput)
+' h_flush='+(typeof tl.flush)
+' h_registerEvent='+(typeof tl.registerEvent);}}
