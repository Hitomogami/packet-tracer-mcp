var aw=ipc.appWindow();
var out=[];
var f=null;var ex="";
try{f=aw.getActiveFile();}catch(e){ex=String(e);}
if(!f){out.push("getActiveFile=FAIL "+ex);}
else{
var ks=[];
try{for(var k in f){ks.push(k+":"+typeof f[k]);}}catch(e){ks.push("ERR:"+e);}
out.push("activeFile.keys="+ks.join("|"));
var vs=[];
try{for(var k2 in f){var v="";try{v=String(f[k2]);}catch(e2){v="EX";}vs.push(k2+"="+v);}}catch(e){vs.push("ERR:"+e);}
out.push("activeFile.values="+vs.join(" | "));
}
__out=out.join("\n");