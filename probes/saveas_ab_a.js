var aw=ipc.appWindow();
var r="";var ex="";
try{r=String(aw.fileSaveAsNoPrompt("D:/packet-tracer-mcp/tmp_saveA.pkt",true));}catch(e){ex=String(e);}
__out="saveA.ret="+(r||"(undefined)")+((ex)?" EX:"+ex:"");