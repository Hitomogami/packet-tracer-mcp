var aw=ipc.appWindow();
var out=[];
var r="";var ex="";
try{r=String(aw.fileSaveAsNoPrompt("D:/packet-tracer-mcp/1.pkt",true));}catch(e){ex=String(e);}
out.push("restore.ret="+(r||"(undefined)")+((ex)?" EX:"+ex:""));
var fn="";
try{fn=String(aw.getActiveFile().getSavedFilename());}catch(e){fn="EX:"+String(e);}
out.push("getSavedFilename.after="+fn);
__out=out.join("\n");