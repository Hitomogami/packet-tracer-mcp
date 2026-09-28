var aw=ipc.appWindow();
var out=[];
var P="D:/packet-tracer-mcp/1_saveas_test.pkt";
function t(label,fn){var r="";var ex="";try{r=String(fn());}catch(e){ex=String(e);}out.push(label+" => "+(r||"(empty)")+((ex)?" EX:"+ex:""));}
t("NP(title,path)",function(){return aw.fileSaveAsNoPrompt("Save As",P);});
t("NP(path,filter)",function(){return aw.fileSaveAsNoPrompt(P,"Packet Tracer Files (*.pkt)");});
t("NP(path,num0)",function(){return aw.fileSaveAsNoPrompt(P,0);});
t("NP(num0,path)",function(){return aw.fileSaveAsNoPrompt(0,P);});
t("NP(path,bool)",function(){return aw.fileSaveAsNoPrompt(P,true);});
t("NP(path,empty)",function(){return aw.fileSaveAsNoPrompt(P,"");});
var fn="";
try{fn=String(aw.getActiveFile().getSavedFilename());}catch(e){fn="EX:"+String(e);}
out.push("getSavedFilename.after="+fn);
__out=out.join("\n");