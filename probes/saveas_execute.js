var aw=ipc.appWindow();
var out=[];
var r="";var ex="";
try{r=String(aw.fileSaveAsNoPrompt("D:/packet-tracer-mcp/1_saveas_test.pkt"));}catch(e){ex=String(e);}
out.push("fileSaveAsNoPrompt.ret="+(r||"(empty)")+((ex)?" EX:"+ex:""));
var f=null;
try{f=aw.getActiveFile();}catch(e){}
var fn="";
try{fn=String(f.getSavedFilename());}catch(e){fn="EX:"+String(e);}
out.push("getSavedFilename.after="+fn);
__out=out.join("\n");