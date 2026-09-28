var aw=ipc.appWindow();
var fn="";
try{fn=String(aw.getActiveFile().getSavedFilename());}catch(e){fn="EX:"+String(e);}
__out="getSavedFilename.now="+fn;