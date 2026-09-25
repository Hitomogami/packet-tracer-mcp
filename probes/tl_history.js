var d=null;try{d=ipc.network().getDevice('switchC');}catch(e){}
if(!d){__out='NO DEVICE';}else{
var tl=null;try{tl=d.getIpcTerminalLine();}catch(e2){}
if(!tl){__out='NO TL';}else{
function cap(v,n){if(v===undefined)return 'undef';if(v===null)return 'null';
var s=JSON.stringify(v);if(s===undefined)return 'unstringifiable';
if(s.length>n)s=s.substring(0,n)+'...('+s.length+' total)';return s;}
var uh='?',ch='?',chh='?';
try{uh=cap(tl.getUserHistory(),800);}catch(e3){uh='EX:'+e3;}
try{ch=cap(tl.getCurrentHistory(),800);}catch(e4){ch='EX:'+e4;}
try{chh=cap(tl.getConfigHistory(),800);}catch(e5){chh='EX:'+e5;}
__out='getUserHistory='+uh+'\ngetCurrentHistory='+ch+'\ngetConfigHistory='+chh;}}
