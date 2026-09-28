var aw=ipc.appWindow();
var r="";var ex="";
try{r=String(aw.fileSaveAsNoPrompt("D:/packet-tracer-mcp/tmp_saveB.pkt",true));}catch(e){ex=String(e);}
__out="saveB.ret="+(r||"(undefined)")+((ex)?" EX:"+ex:"");