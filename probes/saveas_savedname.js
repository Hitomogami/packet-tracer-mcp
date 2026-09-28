var aw=ipc.appWindow();
var out=[];
var f=null;var ex="";
try{f=aw.getActiveFile();}catch(e){ex=String(e);}
if(!f){out.push("getActiveFile=FAIL "+ex);}
else{
var fn="";var fnex="";
try{fn=f.getSavedFilename();}catch(e){fnex=String(e);}
out.push("getSavedFilename="+(fn||("(empty/"+fnex+")")));
var af="";var afex="";
try{af=f.isActivityFile();}catch(e){afex=String(e);}
out.push("isActivityFile="+af+((afex)?" EX:"+afex:""));
}
__out=out.join("\n");