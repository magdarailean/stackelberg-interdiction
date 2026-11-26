const MISSIONS=[
 {title:"CALIBRATION",brief:"Set a baseline plan. Compare your allocation with automated methods.",budget:4,train:4},
 {title:"INFORMATION COVERAGE",brief:"Optimize the plan with more training scenarios, then evaluate it on independent scenarios.",budget:3,train:8},
 {title:"LIMITED RESOURCES",brief:"The checkpoint-hour budget changes. Every strategy follows the same operational limit.",budget:5,train:12},
 {title:"NETWORK SHIFT",brief:"Compare nominal testing with a test where network connectivity has changed.",budget:4,train:8},
 {title:"FINAL EVALUATION",brief:"Complete the campaign and compare the combined performance of your chosen plans.",budget:6,train:12}
];
const COORDS=[[23.9,48.0],[25.7,47.6],[27.0,46.8],[28.0,47.9],[29.2,46.9],[30.0,46.0]];
const CITIES=[["Bucharest",26.10,44.43,-13,22,"end"],["Iasi",27.59,47.16,-10,-12,"end"],["Chisinau",28.86,47.05,10,-12,"start"],["Galati",28.05,45.43,-10,20,"end"],["Odesa",30.73,46.47,12,17,"start"]];
const STORE="frontier-command-web-campaign-v2";
const S={sites:[],chosen:new Set(),schedule:null,mission:0,budget:4,result:null,history:{},baseSeed:42,busy:false,timer:null};
const $=s=>document.querySelector(s),site=id=>S.sites.find(x=>x.id===id),clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
const svg=(tag,attrs={},text="")=>{const n=document.createElementNS("http://www.w3.org/2000/svg",tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;return n};
function xy(lon,lat){return[(lon-17.4)*1400/18.2,(50.6-lat)*988/8.9]}
function current(){return MISSIONS[S.mission]||null}
function save(){try{localStorage.setItem(STORE,JSON.stringify({mission:S.mission,history:S.history,chosen:[...S.chosen],schedule:S.schedule,budget:S.budget,baseSeed:S.baseSeed,result:S.result}))}catch{}}
function load(){try{const d=JSON.parse(localStorage.getItem(STORE)||"{}");S.mission=clamp(+d.mission||0,0,MISSIONS.length);S.history=d.history||{};S.chosen=new Set(d.chosen||[]);S.schedule=Array.isArray(d.schedule)?d.schedule:null;S.budget=+d.budget||0;S.baseSeed=+d.baseSeed||42;S.result=d.result||null}catch{}}
function fmt(n){return Number(n||0).toLocaleString("en-US",{minimumFractionDigits:1,maximumFractionDigits:1})}
function toast(msg){const t=$("#toast");t.textContent=msg;t.classList.add("show");clearTimeout(S.timer);S.timer=setTimeout(()=>t.classList.remove("show"),2400)}
function renderMap(){
 const layer=$("#map-layers");layer.replaceChildren();
 const cityLayer=svg("g",{class:"cities"});
 for(const item of CITIES){const n=item[0],[x,y]=xy(item[1],item[2]),dx=item[3],dy=item[4],anchor=item[5];cityLayer.append(svg("circle",{cx:x,cy:y,r:5,class:"city-dot"}),svg("circle",{cx:x,cy:y,r:10,class:"city-halo","pointer-events":"none"}),svg("text",{x:x+dx,y:y+dy,"text-anchor":anchor,class:"city-label"},n))}
 layer.append(cityLayer);
 const sites=svg("g",{class:"site-layer"});
 S.sites.forEach((s,i)=>{const pos=xy(...COORDS[i%COORDS.length]),x=pos[0],y=pos[1],on=S.chosen.has(s.id),g=svg("g",{class:"site"+(on?" selected":""),"data-site-id":s.id,tabindex:"0",role:"button","aria-pressed":String(on),"aria-label":"Fictional candidate site "+(i+1)+", cost "+s.hours+" hrs"});
 g.append(svg("circle",{cx:x,cy:y,r:27,class:"site-hit"}),svg("circle",{cx:x,cy:y,r:on?17:15,class:"site-pin"}),svg("text",{x:x,y:y+4,class:"site-number"},String(s.number||i+1)),svg("text",{x:x+19,y:y+24,class:"site-hours"},s.hours+" h"));sites.append(g)});
 layer.append(sites);$("#candidate-count").textContent=S.sites.length+" CANDIDATE SITES";
}
function used(){return S.schedule?S.schedule.length:[...S.chosen].reduce((sum,id)=>sum+(site(id)?.hours||0),0)}
function renderChosen(){
 const box=$("#selected-list"),items=S.sites.filter(s=>S.chosen.has(s.id)),h=used();
 $("#selection-count").textContent=h+" / "+S.budget+" HRS";$("#top-budget").innerHTML=String(S.budget).padStart(2,"0")+" <small>HRS</small>";
 $("#budget-value").textContent=S.budget;$("#budget-input").value=S.budget;$("#budget-slider").value=S.budget;
 $("#budget-input").max=current()?.budget||12;$("#budget-slider").max=current()?.budget||12;$("#budget-max-label").textContent=(current()?.budget||12)+" hrs";
 const pct=(current()?.budget||12)?S.budget/(current()?.budget||12)*100:0;$("#budget-slider").style.background="linear-gradient(to right,#c89b4b "+pct+"%,#46515a "+pct+"%)";
 box.replaceChildren();
 if(!items.length){const empty=document.createElement("div");empty.className="empty-order";empty.innerHTML="<span>＋</span><span>No sites assigned. Select a gold marker on the map.</span>";box.append(empty)}
 items.forEach(s=>{const row=document.createElement("div");row.className="site-order";const count=S.schedule?S.schedule.filter(x=>x[1]===s.id).length:s.hours;row.innerHTML="<span><b>CANDIDATE SITE "+String(s.number).padStart(2,"0")+"</b><small>"+(S.schedule?"MILP hourly schedule":"Manual assignment · 1 slot")+"</small></span><strong>"+count+" SLOT"+(count===1?"":"S")+"</strong><button type='button' aria-label='Remove site'>×</button>";row.querySelector("button").onclick=()=>toggle(s.id);box.append(row)});
}
function setBudget(value){S.schedule=null;S.budget=clamp(parseInt(value||"0",10),0,current()?.budget||12);[...S.chosen].sort((a,b)=>(site(b)?.hours||0)-(site(a)?.hours||0)).forEach(id=>{if(used()>S.budget)S.chosen.delete(id)});$("#selection-warning").textContent="";renderMap();renderChosen();save()}
function toggle(id){S.schedule=null;if(S.chosen.has(id))S.chosen.delete(id);else{const s=site(id);if(!s)return;if(used()+s.hours>S.budget){$("#selection-warning").textContent="The plan exceeds this turn's checkpoint-hour budget.";toast("Not enough budget for this site.");return}S.chosen.add(id)}$("#selection-warning").textContent="";renderMap();renderChosen();save()}
function renderCampaign(){
 const m=current(),done=S.mission>=MISSIONS.length;
 $("#turn-label").textContent=done?"CAMPAIGN COMPLETE":"TURN "+String(S.mission+1).padStart(2,"0")+" / 05";
 $("#campaign-steps").replaceChildren(...MISSIONS.map((x,i)=>{const e=document.createElement("span");e.className="campaign-step"+(i<S.mission?" complete":i===S.mission&&!done?" active":"");e.title="Turn "+(i+1)+": "+x.title;return e}));
 if(done){
  $("#mission-title").textContent="Campaign complete.";$("#mission-brief").textContent="Review the record, then start a new campaign for another replication.";
  $("#turn-heading").textContent="FINAL RECORD";$("#phase-badge").textContent="FINAL";$("#briefing-text").textContent="Saved results are stored in this browser.";
  $("#run-button").disabled=true;$("#continue-button").textContent="NEW CAMPAIGN";$("#continue-button").hidden=false;$("#continue-button").onclick=newCampaign
 }else{
  const titles=["Secure the corridor.","Improve information coverage.","Work with limited resources.","Adapt to the network shift.","Complete the evaluation."];
  $("#mission-title").textContent=titles[S.mission];$("#mission-brief").textContent=m.brief;
  $("#turn-heading").textContent="TURN "+String(S.mission+1).padStart(2,"0")+" · "+m.title;$("#phase-badge").textContent="PHASE "+String(S.mission+1).padStart(2,"0");
  $("#briefing-text").textContent=m.brief;$("#run-button").disabled=false;$("#continue-button").onclick=advance
 }
 $("#budget-input").max=m?.budget||12;$("#budget-slider").max=m?.budget||12;$("#train-input").value=m?.train||12;
 $("#report-turn").textContent=done?"FINAL RECORD":"TURN "+String(S.mission+1).padStart(2,"0");
 renderDossier();if(S.result){renderResults(S.result)}else $("#results-section").hidden=true
}
function renderDossier(){const n=Object.keys(S.history).length;$("#dossier-count").textContent=n+" / 5 TURNS";$("#dossier-fill").style.width=(n/5*100)+"%";const vals=Object.values(S.history).map(x=>Number(x.ratio)||0);$("#dossier-summary").textContent=vals.length?"Average campaign reduction: "+fmt(vals.reduce((a,b)=>a+b,0)/vals.length)+"%":"Average test reduction: —"}
function renderResults(data){
 const normal=data.splits.nominal_test.policies;
 $("#metric-normal").textContent=fmt(normal.manual.mean_delivered);$("#metric-reduction").textContent=fmt(normal.manual.mean_reduction);
 $("#metric-hours").textContent=fmt(normal.manual.mean_checkpoint_hours)+" / "+data.budget;
 $("#solver-status").textContent="MILP "+data.solver.status.toUpperCase()+" · "+fmt(data.solver.seconds)+" SEC";
 const splits=[["train","TRAINING"],["nominal_test","NOMINAL TEST"],["shifted_test","SHIFTED TEST"]];
 $("#results-body").innerHTML=splits.map(([key,label])=>{const q=data.splits[key],p=q.policies;return"<tr><td>"+label+"<small>"+q.scenario_count+" scenarios</small></td><td class='you'><strong>"+fmt(p.manual.mean_delivered)+"</strong><small>reduction "+fmt(p.manual.mean_reduction)+"</small></td><td><strong>"+fmt(p.greedy.mean_delivered)+"</strong></td><td><strong>"+fmt(p.milp.mean_delivered)+"</strong></td><td><strong>"+fmt(p.centrality.mean_delivered)+"</strong></td><td><strong>"+fmt(p.random.mean_delivered)+"</strong></td><td><strong>"+fmt(p.none.mean_delivered)+"</strong></td><td><strong>"+(p.oracle?fmt(p.oracle.mean_delivered):"—")+"</strong><small>unattainable benchmark</small></td></tr>"}).join("");
 $("#results-section").hidden=false;
 const completed=S.history[String(S.mission)]!==undefined;$("#continue-button").hidden=!completed;
 $("#continue-button").textContent=S.mission===MISSIONS.length-1?"END CAMPAIGN →":"CONTINUE CAMPAIGN →";
}
function showResults(data){S.result=data;const p=data.splits.nominal_test.policies,n=p.none.mean_delivered,ratio=n>0?100*p.manual.mean_reduction/n:0;
 S.history[String(S.mission)]={ratio,manual:p.manual.mean_delivered,greedy:p.greedy.mean_delivered,milp:p.milp.mean_delivered,shifted:data.splits.shifted_test.policies.manual.mean_delivered};
 save();renderResults(data);renderDossier()
}
async function run(){
 if(S.busy||!current())return;S.busy=true;const b=$("#run-button"),st=$("#run-status");b.disabled=true;b.querySelector("span").textContent="CALCULATING…";st.className="status";st.textContent="Evaluating the plan on training scenarios and independent test scenarios…";
 const payload={selected_ids:[...S.chosen],schedule:S.schedule,budget:S.budget,seed:(parseInt($("#seed-input").value,10)||42)+S.mission*997,train_count:+$("#train-input").value,test_count:+$("#test-input").value,time_limit:+$("#time-input").value};
 try{const r=await fetch("/api/simulate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}),d=await r.json();if(!r.ok)throw Error(d.error||"Simulation failed.");showResults(d);st.className="status success";st.textContent="Plan calculated. Reduced flow represents avoided modeled delivery, not an interception.";$("#results-section").scrollIntoView({behavior:"smooth",block:"start"})}
 catch(e){st.className="status error";st.textContent=e.message;toast(e.message)}
 finally{S.busy=false;b.disabled=false;b.querySelector("span").textContent="RECALCULATE PLAN"}
}
function advance(){if(!S.result)return;if(S.mission>=MISSIONS.length-1){S.mission=MISSIONS.length;S.chosen.clear();S.schedule=null;S.result=null}
 else{S.mission++;S.budget=current().budget;S.chosen.clear();S.result=null}
 save();renderCampaign();renderMap();renderChosen();window.scrollTo({top:0,behavior:"smooth"})
}
function newCampaign(){if(!confirm("Start a new campaign? This campaign record will be erased from this browser."))return;localStorage.removeItem(STORE);S.mission=0;S.history={};S.chosen.clear();S.schedule=null;S.result=null;S.baseSeed=42;S.budget=MISSIONS[0].budget;$("#seed-input").value=42;renderCampaign();renderMap();renderChosen();$("#run-status").textContent="New campaign. Choose candidate sites on the map."}
function initEvents(){
 $("#network-map").addEventListener("click",e=>{const g=e.target.closest("[data-site-id]");if(g)toggle(g.dataset.siteId)});
 $("#network-map").addEventListener("keydown",e=>{const g=e.target.closest("[data-site-id]");if(g&&(e.key==="Enter"||e.key===" ")){e.preventDefault();toggle(g.dataset.siteId)}});
 $("#budget-slider").addEventListener("input",e=>setBudget(e.target.value));$("#budget-input").addEventListener("change",e=>setBudget(e.target.value));
 $("#run-button").onclick=run;$("#reset-button").onclick=()=>{S.chosen.clear();S.schedule=null;renderMap();renderChosen();save();$("#selection-warning").textContent="";$("#run-status").textContent="Plan cleared."};
 $("#apply-milp").onclick=()=>{if(!S.result)return;S.schedule=S.result.milp_plan;S.chosen=new Set(S.result.milp_site_ids);renderMap();renderChosen();$("#run-status").textContent="The MILP hourly schedule has been loaded. Run it to record it in the campaign.";save()};
 $("#continue-button").onclick=advance;$("#new-campaign").onclick=newCampaign
}
async function init(){
 load();S.budget=current()?.budget||S.budget||4;initEvents();renderCampaign();
 try{const r=await fetch("/api/config"),d=await r.json();if(!r.ok)throw Error(d.error||"The simulator is not responding.");S.sites=d.sites;S.budget=current()?.budget||d.budget;S.chosen=new Set([...S.chosen].filter(id=>S.sites.some(s=>s.id===id)));if(S.schedule&&!S.schedule.every(x=>Array.isArray(x)&&S.sites.some(s=>s.id===x[1])))S.schedule=null;if(used()>S.budget){S.schedule=null;S.chosen.clear()}renderCampaign();renderMap();renderChosen();$("#run-status").className="status success";$("#run-status").textContent="Simulator connected · hourly scenarios with synthetic flows."}
 catch(e){$("#run-status").className="status error";$("#run-status").textContent="Could not connect to the simulator: "+e.message}
}
init();
