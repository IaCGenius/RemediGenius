'use strict';
(() => {
 const panel=el('div',undefined,'panel');panel.id='hermes-agent';
 const status=el('p','Checking cloud Hermes…');
 const select=el('select');select.id='hermes-assessment';select.multiple=true;select.size=4;
 const question=el('textarea');question.id='hermes-question';question.rows=3;
 question.value='Investigate the selected evidence. Explain what matters, apply relevant reviewed knowledge and scoped variations, identify gaps, and prepare actionable verification and rollback steps. Cite record IDs.';
 const plan=el('div'), runs=el('div');runs.id='hermes-runs';
 let followup=null;
 panel.append(el('h2','Investigate with Hermes'),status,el('p','The cloud agent receives only your selected snapshot and applicable knowledge. It can read that snapshot and explain it; it cannot change your cloud resources.'),select,question,
 action('Review investigation scope',async()=>{
   if(!select.value)throw new Error('Select collected evidence or an assessment first.');
   const p=await api('hermes/prepare',{record_ids:[...select.selectedOptions].map(o=>o.value),question:question.value,followup_job:followup});
   plan.replaceChildren(el('h3','Review before sending'),el('p',p.provider+' · '+p.model),el('p',p.disclosure),el('p',p.file_count+' snapshot files. Includes applicable knowledge and cited sources.'),
     action('Read exact snapshot',async()=>{const r=await api('records/'+p.id);show('Model disclosure snapshot',r,'These are the exact files and question prepared for this run.');}),
     action('Consent and start Hermes',async()=>{await api('hermes/start',{preparation_id:p.id,consent:true});plan.replaceChildren(el('p','Investigation started. You can leave this page; completed results are saved to your workspace.'));await update();}));
 }),plan,runs);
 $('workspace').insertBefore(panel,$('annotations'));
 function invalidate(){plan.replaceChildren();}select.onchange=()=>{followup=null;invalidate();};question.oninput=invalidate;
 async function update(){
   const d=await api('hermes');
   panel.hidden=!d.runtime.enabled;
   if(!d.runtime.enabled)return;
   status.textContent=(d.runtime.ready?'Ready':'Unavailable')+' · '+(d.runtime.provider||'Provider not configured')+' · '+(d.runtime.model||'Model not configured')+'. '+d.runtime.notice;
   runs.replaceChildren();
   for(const r of d.runs){const card=el('article',undefined,'panel');card.append(badge('ai_interpretation'),el('h3','Hermes · '+r.state),el('p',r.notice||''));
     if(['queued','running','cancelling'].includes(r.state))card.append(action('Cancel investigation',async()=>{await api('hermes/runs/'+r.job_id+'/cancel',{});await update();}));
     if(r.text){card.append(el('p','Unreviewed AI interpretation · citation check: '+r.citation_check),el('pre',r.text));card.append(action('Review run receipt',()=>show('Hermes investigation receipt',r,'Matching citations do not prove each claim. Review before acting.')));}
     if(r.state==='completed')card.append(action('Ask a follow-up',async()=>{const p=await api('records/'+r.preparation_id);for(const o of select.options)o.selected=p.body.selected_records.includes(o.value);followup=r.job_id;question.value='';question.placeholder='Ask your follow-up about this evidence…';plan.replaceChildren(el('p','The prior AI answer will be included as unreviewed context. Review the new scope before sending.'));question.focus();panel.scrollIntoView();}));
     if(r.error)card.append(el('p',r.error));runs.append(card);
   }
 }
 const old=refresh;refresh=async function(){await old();const prior=new Set([...select.selectedOptions].map(o=>o.value));select.replaceChildren();for(const r of [...state.assessments,...state.evidence]){const o=el('option',(r.kind||'evidence')+' · '+r.body.adapter+' · '+r.body.observed_at);o.value=r.id;select.append(o);}for(const o of select.options)o.selected=prior.has(o.value);if(!prior.size&&select.options.length)select.options[0].selected=true;await update();};
 setInterval(()=>{if(token)update().catch(()=>{status.textContent='Connection lost. Reconnect to inspect the saved investigation state.';});},3000);
})();
