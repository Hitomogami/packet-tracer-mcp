var d=null;try{d=ipc.network().getDevice('pc2');}catch(e){}
if(!d){__out='NO DEVICE';}else{
var cp=null;
try{cp=d.getCommandPrompt();}catch(e2){__out='getCommandPrompt EX:'+e2;}
if(!cp){__out='getCommandPrompt returned null/undefined';}else{
var ks=[];for(var k in cp){ks.push(k);}
__out='keys='+ks.join('|')
+'\ntypeof enterCommand='+(typeof cp.enterCommand)
+' typeof getOutput='+(typeof cp.getOutput)
+' typeof getMode='+(typeof cp.getMode)
+' typeof getPrompt='+(typeof cp.getPrompt)
+' typeof println='+(typeof cp.println);}}
