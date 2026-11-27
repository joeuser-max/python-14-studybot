"""Streamlit Components V2 雙向拖放七日課表（不依賴 FullCalendar）。"""
import json
import streamlit as st

HTML = """
<div class="wb">
  <aside class="deck"><header><strong>待排任務</strong><small class="count"></small></header>
    <small>拖曳至右側空格，卡片右側把手可橫向調整 1–4 節。也可點卡片後再點目標格。</small>
    <section class="cards"></section>
    <button class="autofill">一鍵填滿剩餘任務</button>
    <small>只有按下此鍵才會安排其餘任務；手動安排不受影響。</small>
  </aside>
  <main class="board"><header><strong>未來七日 · 16 節</strong><small>T+0 至 T+6，沒有過去日期</small></header>
    <div class="matrix"></div>
    <footer>紅：固定課程　黃：外部行事曆（點擊編輯）　藍：已排任務（× 移回待排）</footer>
  </main>
</div>
"""

CSS = """
*{box-sizing:border-box} .wb{width:100%;display:grid;grid-template-columns:225px minmax(0,1fr);
gap:12px;font-family:inherit;color:#24334a}
.deck,.board{border:1px solid #d8e0eb;border-radius:10px;background:#fff;padding:9px;min-width:0}
.deck header,.board header{display:flex;justify-content:space-between;gap:6px;align-items:center;font-size:14px;margin-bottom:8px}
.deck small,.board small,.board footer{font-size:10px;color:#63758e;line-height:1.5;display:block}
.cards{margin-top:10px;min-height:50px;display:flex;flex-direction:column;gap:7px}
.card{background:#e8f0ff;border:1px solid #99b6f7;border-radius:7px;min-height:49px;
font-size:10px;color:#17458e;padding:6px;cursor:grab;max-width:100%;
display:flex;align-items:center;justify-content:space-between;gap:4px;overflow:hidden}
.card.selected{outline:2px solid #3166cc}
.card .info{overflow:hidden;white-space:nowrap;min-width:0}
.card .title{font-weight:bold;overflow:hidden;text-overflow:ellipsis}
.card .grip{min-width:10px;height:27px;cursor:ew-resize;touch-action:none;
border-left:2px dashed #577fca;border-right:2px dashed #577fca}
.autofill{width:100%;background:#265ec7;color:white;border:0;border-radius:7px;
padding:9px;margin:10px 0 4px;font-size:12px;font-weight:bold;cursor:pointer}
.matrix{display:grid;grid-template-columns:52px repeat(7,minmax(0,1fr));
grid-template-rows:37px repeat(16,32px);border-top:1px solid #dbe1e9;
border-left:1px solid #dbe1e9;position:relative}
.matrix>div{min-width:0;border-right:1px solid #dbe1e9;border-bottom:1px solid #dbe1e9}
.hdr{background:#f1f5fa;text-align:center;font-weight:700;font-size:10px;
display:flex;align-items:center;justify-content:center;flex-direction:column}
.hdr.today{background:#dae8ff;color:#1b51a8}
.period{background:#f7f9fc;display:flex;align-items:center;justify-content:center;
gap:4px;font-size:10px}
.period b{font-size:12px}
.cell{background:#fff;cursor:copy}
.cell.past{background:#eff1f4;cursor:not-allowed}
.cell.over{background:#d6e8ff}
.event{position:relative;z-index:3;border-radius:4px;margin:1px;padding:3px;
font-size:10px;line-height:1.2;overflow:hidden;word-break:break-word;
border-left:3px solid;min-height:0}
.event.course{background:#ffe1e7;color:#8a2740;border-color:#c94352;pointer-events:none}
.event.external{background:#fff1d4;color:#7a5219;border-color:#c88a21;cursor:pointer}
.event.study{background:#dce8ff;color:#19489e;border-color:#3166cc;cursor:grab}
.event button{background:none;border:0;color:inherit;float:right;padding:0 2px;cursor:pointer}
.board footer{margin-top:8px}
@media(max-width:900px){.wb{grid-template-columns:165px minmax(0,1fr);gap:5px}
.deck,.board{padding:5px}.matrix{grid-template-columns:40px repeat(7,minmax(0,1fr))}
.event{font-size:9px}} @media(max-width:700px){.wb{display:block}.deck{margin-bottom:10px}
.cards{flex-direction:row;flex-wrap:wrap}.board{overflow-x:auto}.matrix{min-width:650px}}
"""

JS = r"""
export default function(component) {
  const {data,parentElement,setTriggerValue}=component;
  const root=parentElement.querySelector(".wb");
  const matrix=root.querySelector(".matrix");
  const deck=root.querySelector(".cards");
  // 元件在 Streamlit 重新執行時可能重用同一個 shadow DOM。
  // 每次繪製前清空舊格與卡片，避免行事曆格子越刷越多。
  matrix.replaceChildren();
  deck.replaceChildren();
  const days=data.days||[], periods=data.periods||[], tasks=data.tasks||[];
  let dragged=null, selected=null;
  const send=(v)=>setTriggerValue("action",JSON.stringify({...v,nonce:Date.now()+"-"+Math.random()}));
  const cell=(cls,txt)=>{const el=document.createElement("div");el.className=cls;el.textContent=String(txt||"");return el;};
  const pos=(el,col,row,span=1)=>{el.style.gridColumn=String(col);el.style.gridRow=row+" / span "+span;matrix.append(el);};
  root.querySelector(".count").textContent=tasks.length+" 項";
  root.querySelector(".autofill").onclick=()=>send({type:"fill"});
  if(tasks.length===0)deck.append(cell("empty","目前沒有待排任務"));
  tasks.forEach(t=>{
    let blocks=Number(t.blocks)||1;
    const card=cell("card","");
    card.style.width=Math.min(100,24+blocks*19)+"%";
    const info=cell("info",""),title=cell("title",t.title),subtitle=cell("subtitle","");
    const update=()=>{subtitle.textContent=t.subject+"｜"+blocks+" 節｜期限 "+t.deadline;
      card.style.width=Math.min(100,24+blocks*19)+"%";};
    update();info.append(title,subtitle);
    const grip=cell("grip","");grip.title="橫向拖曳改變長度";
    card.append(info,grip);
    card.draggable=true;
    card.ondragstart=(evt)=>{dragged={task_id:t.task_id,blocks};
      evt.dataTransfer.setData("text/plain",t.task_id);};
    card.onclick=(evt)=>{if(evt.target===grip)return;selected={task_id:t.task_id,blocks};
      deck.querySelectorAll(".card").forEach(x=>x.classList.remove("selected"));card.classList.add("selected");};
    grip.onpointerdown=(evt)=>{
      evt.stopPropagation();evt.preventDefault();const x=evt.clientX,old=blocks;
      grip.setPointerCapture(evt.pointerId);
      grip.onpointermove=(move)=>{blocks=Math.max(1,Math.min(4,old+Math.round((move.clientX-x)/35)));update();};
      grip.onpointerup=()=>{grip.onpointermove=null;grip.onpointerup=null;
        if(selected&&selected.task_id===t.task_id)selected.blocks=blocks;
        if(old!==blocks)send({type:"resize",task_id:t.task_id,blocks});};
    };
    deck.append(card);
  });
  pos(cell("hdr","節次"),1,1);
  days.forEach((d,i)=>{
    const h=cell("hdr"+(d.date===data.today?" today":""),d.label);
    h.append(cell("",""+d.day_number));
    pos(h,i+2,1);
  });
  periods.forEach((p,k)=>{
    pos(cell("period",p.label+"  "+String(p.hour).padStart(2,"0")+":00"),1,k+2);
    days.forEach((d,i)=>{
      const past=(d.date+"T"+String(p.hour).padStart(2,"0")+":00")<=data.now_iso.slice(0,16);
      const c=cell("cell"+(past?" past":""),"");
      c.title=d.date+" "+p.time;
      c.ondragover=(e)=>{if(!past){e.preventDefault();c.classList.add("over");}};
      c.ondragleave=()=>c.classList.remove("over");
      c.ondrop=(e)=>{e.preventDefault();c.classList.remove("over");
        if(!past&&dragged)send({type:"drop",task_id:dragged.task_id,date:d.date,period:p.label,blocks:dragged.blocks});};
      c.onclick=()=>{if(!past&&selected)send({type:"drop",task_id:selected.task_id,date:d.date,period:p.label,blocks:selected.blocks});};
      pos(c,i+2,k+2);
    });
  });
  const event=(day,startHour,endHour,text,kind,meta={})=>{
    const idx=days.findIndex(d=>d.date===day);if(idx<0)return;
    const from=Math.max(8,Math.min(24,startHour)),to=Math.max(8,Math.min(24,endHour));
    if(to<=from)return;
    const el=cell("event "+kind,text);el.title=text;
    if(kind==="study"){
      const btn=document.createElement("button");btn.textContent="×";btn.title="移回待排";btn.type="button";
      btn.onclick=(e)=>{e.stopPropagation();send({type:"unplace",task_id:meta.task_id});};
      el.prepend(btn);el.draggable=true;el.ondragstart=(e)=>{
        dragged={task_id:meta.task_id,blocks:meta.blocks||1};e.dataTransfer.setData("text/plain",meta.task_id);};
    }
    if(kind==="external"){el.title="點擊編輯，變更前會再次確認";el.onclick=()=>send({type:"external_edit",id:meta.id});}
    pos(el,idx+2,from-8+2,to-from);
  };
  (data.courses||[]).forEach(c=>{
    days.forEach(d=>{
      const weekday=(new Date(d.date+"T12:00:00").getDay()+6)%7+1;
      if(weekday!==Number(c.weekday))return;
      const start=Number(c.start.slice(0,2)),end=Math.ceil(Number(c.end.slice(0,2))+Number(c.end.slice(3,5))/60);
      event(d.date,start,end,c.title,"course");
    });
  });
  (data.external||[]).forEach(e=>{
    const first=String(e.start).slice(0,10),last=String(e.end).slice(0,10);
    days.forEach(d=>{
      if(d.date<first||d.date>last)return;
      const begin=d.date===first?Number(e.start.slice(11,13)):8;
      const finish=d.date===last?Math.ceil(Number(e.end.slice(11,13))+Number(e.end.slice(14,16))/60):24;
      event(d.date,begin,finish,e.title,"external",e);
    });
  });
  (data.scheduled||[]).forEach(s=>event(s.day,s.hour,Math.min(24,s.hour+Number(s.blocks||1)),
    s.title+" · "+s.subject+"（"+(s.source==="manual"?"手排":"自動")+"）","study",s));
}
"""

BOARD = st.components.v2.component("classpulse_rolling_week",html=HTML,css=CSS,js=JS)


def render_week_board(payload: dict) -> dict | None:
    result = BOARD(data=payload,key="classpulse_week_board",on_action_change=lambda: None)
    value = result.action
    return json.loads(value) if value else None
