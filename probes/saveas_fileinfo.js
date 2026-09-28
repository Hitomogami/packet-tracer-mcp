var aw=ipc.appWindow();
var out=[];
function trycall(label,fn){var r="";try{var v=fn();r=String(v);}catch(e){r="EX:"+String(e);}out.push(label+"="+r);}
trycall("getActiveFile",function(){return aw.getActiveFile();});
trycall("getDefaultFileSaveLocation",function(){return aw.getDefaultFileSaveLocation();});
trycall("getUserFolder",function(){return aw.getUserFolder();});
trycall("getBasePath",function(){return aw.getBasePath();});
trycall("getTempFileLocation",function(){return aw.getTempFileLocation();});
trycall("getVersion",function(){return aw.getVersion();});
trycall("getListOfFilesSaved",function(){return aw.getListOfFilesSaved();});
trycall("isActivityWizardOpen",function(){return aw.isActivityWizardOpen();});
__out=out.join("\n");