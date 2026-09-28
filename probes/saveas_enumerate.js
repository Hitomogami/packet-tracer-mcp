var out=[];
var ik=[];
try{for(var k in ipc){ik.push(k+":"+typeof ipc[k]);}}catch(e){ik.push("ERR:"+e);}
out.push("ipc.keys="+ik.join("|"));
var aw=null;var awex="";
try{aw=ipc.appWindow();}catch(e){awex=String(e);}
if(!aw){out.push("appWindow=FAIL "+awex);}
else{
var ak=[];
try{for(var k2 in aw){ak.push(k2+":"+typeof aw[k2]);}}catch(e){ak.push("ERR:"+e);}
out.push("appWindow.keys="+ak.join("|"));
var mb=null;var mbex="";
try{mb=aw.getMenuBar();}catch(e){mbex=String(e);}
if(!mb){out.push("menuBar=FAIL "+mbex);}
else{
var mk=[];
try{for(var k3 in mb){mk.push(k3+":"+typeof mb[k3]);}}catch(e){mk.push("ERR:"+e);}
out.push("menuBar.keys="+mk.join("|"));
var mv=[];
try{var mc=mb.getMenuCount();mv.push("getMenuCount="+mc);}catch(e){mv.push("getMenuCount EX:"+e);}
try{var ma=mb.getMenus();mv.push("getMenus="+typeof ma+" len="+((ma&&ma.length!==undefined)?ma.length:"?"));}catch(e){mv.push("getMenus EX:"+e);}
out.push("menuBar.probe="+mv.join(" | "));
}
var nk=[];
try{for(var k4 in aw.getWorkspaceCount){nk.push("getWorkspaceCount:"+typeof aw.getWorkspaceCount);}}catch(e){}
out.push("misc.getWorkspaceCount="+(typeof aw.getWorkspaceCount));
}
var nw=null;var nwex="";
try{nw=ipc.network();}catch(e){nwex=String(e);}
if(!nw){out.push("network=FAIL "+nwex);}
else{
var nwk=[];
try{for(var k5 in nw){nwk.push(k5+":"+typeof nw[k5]);}}catch(e){nwk.push("ERR:"+e);}
out.push("network.keys="+nwk.join("|"));
}
__out=out.join("\n");