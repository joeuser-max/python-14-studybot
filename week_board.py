"""Streamlit Components V2 雙向拖放七日課表（不依賴 FullCalendar）。"""
import json
import streamlit as st

HTML = """
<div class="wb">
  <aside class="deck"><header><strong>待排任務</strong><small class="count"></small></header>
    <small>卡片右側可伸縮，每次 30 分鐘；拖到時間格或先點卡片再點時段。已排方塊底部可直接拉長／縮短。</small>
    <section class="cards"></section>
    <button class="autofill">一鍵安排剩餘任務</button>
    <div class="preference-controls">
      <button class="pref-clear" type="button">清除全部綠色偏好</button>
      <button class="pref-cancel" type="button">保留偏好，暫不排程</button>
    </div>
    <small class="pref-hint">點一鍵安排後，在空白格點選或拖曳畫綠，再確認排入。</small>
  </aside>
  <main class="board"><header><strong>未來七日 · 16 節</strong><small>T+0 至 T+6，沒有過去日期</small></header>
    <div class="matrix"></div>
    <footer>紅：固定課程　黃：外部活動　藍：一般任務　紫：AI 筆記任務　綠：偏好時段（不是硬限制）</footer>
    <div class="board-alert" role="alert" aria-live="polite"></div>
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
.card.ai{background:#efe3ff;border-color:#aa86dd;color:#592b8a}
.card.ai.selected{outline-color:#8356c4}
.card .info{overflow:hidden;white-space:nowrap;min-width:0}
.card .title{font-weight:bold;overflow:hidden;text-overflow:ellipsis}
.card .grip{min-width:10px;height:27px;cursor:ew-resize;touch-action:none;
border-left:2px dashed #577fca;border-right:2px dashed #577fca}
.autofill{width:100%;background:#265ec7;color:white;border:0;border-radius:7px;
padding:9px;margin:10px 0 4px;font-size:12px;font-weight:bold;cursor:pointer}
.preference-controls{display:flex;flex-direction:column;gap:4px}
.pref-clear,.pref-cancel{border:1px solid #8da2b8;border-radius:5px;padding:6px;
background:#fff;color:#31455e;cursor:pointer;font-size:11px;display:none}
.pref-hint{display:block;margin-top:4px}
.matrix{display:grid;grid-template-columns:52px repeat(7,minmax(0,1fr));
grid-template-rows:37px repeat(32,20px);border-top:1px solid #dbe1e9;
border-left:1px solid #dbe1e9;position:relative}
.matrix>div{min-width:0;border-right:1px solid #dbe1e9;border-bottom:1px solid #dbe1e9}
.hdr{background:#f1f5fa;text-align:center;font-weight:700;font-size:10px;
display:flex;align-items:center;justify-content:center;flex-direction:column}
.hdr.today{background:#dae8ff;color:#1b51a8}
.period{background:#f7f9fc;display:flex;align-items:center;justify-content:center;
gap:4px;font-size:10px}
.period b{font-size:12px}
.cell{background:#fff;cursor:copy;touch-action:pan-y}
.cell.preferred{background:#b9e4ce;box-shadow:inset 0 0 0 1px #23845b}
.cell.paintable{cursor:crosshair}
.cell.past{background:#eff1f4;cursor:not-allowed}
.cell.over{background:#d6e8ff}
.cell.over-conflict{background:#ffcdd2!important;box-shadow:inset 0 0 0 2px #c94352}
.cell.busy{cursor:not-allowed}
.board-alert{margin-top:6px;color:#a12635;font-size:12px;font-weight:600;min-height:0}
.event.study.ai{background:#ead9fc;color:#542a83;border-color:#8356c4}
.event .resize-handle{position:absolute;z-index:8;left:25%;right:25%;bottom:0;
height:7px;border-radius:5px;background:rgba(45,77,126,.38);cursor:ns-resize;touch-action:none}
.event.study.ai .resize-handle{background:#8356c4}
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
  let dragged=null, selected=null, handledDrop=false;
  const errorBox=root.querySelector(".board-alert");
  errorBox.textContent=data.error||"";
  const showError=(message)=>{errorBox.textContent=message;errorBox.scrollIntoView({block:"nearest"});};
  const minutesLabel=(min)=>min%60===0?(min/60)+" 節":min+" 分鐘";
  const preferenceMode=Boolean(data.preference_mode);
  const preferenceSet=new Set((data.preferences||[]).map(p=>p.date+"|"+p.period));
  let painting=false,paintDesired=true,paintMap=new Map();
  const send=(v)=>setTriggerValue("action",JSON.stringify({...v,nonce:Date.now()+"-"+Math.random()}));
  const cell=(cls,txt)=>{const el=document.createElement("div");el.className=cls;el.textContent=String(txt||"");return el;};
  const pos=(el,col,row,span=1)=>{el.style.gridColumn=String(col);el.style.gridRow=row+" / span "+span;matrix.append(el);};
  root.querySelector(".count").textContent=tasks.length+" 項";
  const fillButton=root.querySelector(".autofill");
  fillButton.textContent=preferenceMode?"確認偏好並一鍵安排":"一鍵安排：標記綠色偏好";
  fillButton.onclick=()=>send({type:preferenceMode?"fill":"pref_begin"});
  const clearButton=root.querySelector(".pref-clear");
  const cancelButton=root.querySelector(".pref-cancel");
  clearButton.style.display=preferenceMode?"block":"none";
  cancelButton.style.display=preferenceMode?"block":"none";
  clearButton.onclick=()=>send({type:"pref_clear"});
  cancelButton.onclick=()=>send({type:"pref_cancel"});
  root.querySelector(".pref-hint").textContent=preferenceMode
    ?"點選／拖曳空格標綠，再確認安排；其他空檔仍可後備使用。"
    :"只有準備一鍵安排時才進入畫筆；偏好會保留直到你修改或清除。";
  if(tasks.length===0)deck.append(cell("empty","目前沒有待排任務"));
  tasks.forEach(t=>{
    let minutes=Number(t.minutes)||Number(t.blocks||1)*60;
    let blocks=Math.ceil(minutes/60);
    const card=cell("card"+(t.is_ai?" ai":""),"");
    card.style.width=Math.min(100,24+minutes/60*19)+"%";
    const info=cell("info",""),title=cell("title",t.title),subtitle=cell("subtitle","");
    const update=()=>{blocks=Math.ceil(minutes/60);
      subtitle.textContent=t.subject+"｜"+minutesLabel(minutes)+"｜期限 "+(t.deadline_at||t.deadline);
      card.style.width=Math.min(100,24+minutes/60*19)+"%";};
    update();info.append(title,subtitle);
    const grip=cell("grip","");grip.title="橫向拖曳改變長度";
    card.append(info,grip);
    card.draggable=true;
    card.ondragstart=(evt)=>{dragged={task_id:t.task_id,blocks,minutes};handledDrop=false;
      evt.dataTransfer.setData("text/plain",t.task_id);
      evt.dataTransfer.setData("application/x-classpulse-blocks",String(blocks));
      evt.dataTransfer.setData("application/x-classpulse-minutes",String(minutes));
      evt.dataTransfer.effectAllowed="move";};
    card.ondragend=(evt)=>{
      // Some browsers do not dispatch drop on a nested CSS grid after a
      // component refresh. When releasing over an eligible cell, use dragend.
      if(!handledDrop){
        const under=document.elementFromPoint(evt.clientX,evt.clientY);
        const target=under&&under.closest(".cell");
        if(target&&!target.classList.contains("past")&&target.dataset.date&&target.dataset.period)
          send({type:"drop",task_id:t.task_id,date:target.dataset.date,
                period:target.dataset.period,blocks,duration_minutes:minutes});
      }
      dragged=null;
    };
    card.onclick=(evt)=>{if(evt.target===grip)return;selected={task_id:t.task_id,blocks,minutes};
      deck.querySelectorAll(".card").forEach(x=>x.classList.remove("selected"));card.classList.add("selected");};
    grip.onpointerdown=(evt)=>{
      evt.stopPropagation();evt.preventDefault();const x=evt.clientX,old=minutes;
      grip.setPointerCapture(evt.pointerId);
      grip.onpointermove=(move)=>{minutes=Math.max(30,Math.min(240,old+Math.round((move.clientX-x)/18)*30));update();};
      grip.onpointerup=()=>{grip.onpointermove=null;grip.onpointerup=null;
        if(selected&&selected.task_id===t.task_id){selected.blocks=blocks;selected.minutes=minutes;}
        if(old!==minutes)send({type:"resize",task_id:t.task_id,blocks,minutes});};
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
    pos(cell("period",p.label+"  "+String(p.hour).padStart(2,"0")+":00"),1,k*2+2,2);
    days.forEach((d,i)=>{
     for(const half of [0,1]){
      const period=half?p.label+"+":p.label;
      const stamp=d.date+"T"+String(p.hour).padStart(2,"0")+":"+(half?"30":"00");
      const past=stamp<=data.now_iso.slice(0,16);
      const key=d.date+"|"+p.label;
      const c=cell("cell"+(past?" past":"")+
        (preferenceSet.has(key)?" preferred":"")+
        (preferenceMode&&!past?" paintable":""),"");
      c.title=d.date+" "+String(p.hour).padStart(2,"0")+":"+(half?"30":"00");
      c.dataset.date=d.date;c.dataset.period=period;
      c.ondragover=(e)=>{if(!past&&!preferenceMode){e.preventDefault();
        c.classList.add("over");}};
      c.ondragleave=()=>c.classList.remove("over");
      c.ondrop=(e)=>{e.preventDefault();c.classList.remove("over");
        if(past||preferenceMode)return;
        const transferred=e.dataTransfer.getData("text/plain");
        const transferBlocks=Number(e.dataTransfer.getData("application/x-classpulse-blocks"));
        const transferMinutes=Number(e.dataTransfer.getData("application/x-classpulse-minutes"));
        const actualTask=transferred || (dragged&&dragged.task_id);
        const actualMinutes=(transferMinutes>=30&&transferMinutes<=240)
          ?transferMinutes:(dragged&&dragged.minutes)||Math.max(1,transferBlocks)*60;
        if(actualTask){handledDrop=true;
          send({type:"drop",task_id:actualTask,date:d.date,period,
                blocks:Math.ceil(actualMinutes/60),duration_minutes:actualMinutes});}
      };
      c.onclick=()=>{if(!past&&!preferenceMode&&selected)send({type:"drop",
        task_id:selected.task_id,date:d.date,period,blocks:selected.blocks,
        duration_minutes:selected.minutes});};
      if(preferenceMode&&!past){
        c.onpointerdown=(e)=>{
          if(e.button!==0&&e.pointerType!=="touch")return;
          e.preventDefault();painting=true;paintMap=new Map();
          paintDesired=!preferenceSet.has(key);
          paintMap.set(key,{date:d.date,period:p.label});
          c.classList.toggle("preferred",paintDesired);
        };
      }
      pos(c,i+2,k*2+2+half);
     }
    });
  });
  if(preferenceMode){
    root.onpointermove=(e)=>{
      if(!painting)return;
      const target=document.elementFromPoint(e.clientX,e.clientY);
      const c=target&&target.closest(".cell.paintable");
      if(!c||!root.contains(c))return;
      const label=c.dataset.period.replace("+","");
      const key=c.dataset.date+"|"+label;
      paintMap.set(key,{date:c.dataset.date,period:label});
      c.classList.toggle("preferred",paintDesired);
    };
    root.onpointerup=()=>{
      if(!painting)return;
      painting=false;
      if(paintMap.size)send({type:"pref_paint",cells:[...paintMap.values()],enabled:paintDesired});
      paintMap=new Map();
    };
    root.onpointercancel=()=>{painting=false;paintMap=new Map();};
  }
  const event=(day,startHour,endHour,text,kind,meta={})=>{
    const idx=days.findIndex(d=>d.date===day);if(idx<0)return;
    const from=Math.max(8,Math.min(24,startHour)),to=Math.max(8,Math.min(24,endHour));
    if(to<=from)return;
    const el=cell("event "+kind+(meta.is_ai?" ai":""),text);el.title=text;
    if(kind==="study"){
      const btn=document.createElement("button");btn.textContent="×";btn.title="移回待排";btn.type="button";
      btn.onclick=(e)=>{e.stopPropagation();send({type:"unplace",task_id:meta.task_id});};
      el.prepend(btn);el.draggable=true;
      const handle=cell("resize-handle","");
      handle.title="直接拖動方塊底邊調整 30 分鐘";
      el.append(handle);
      handle.onpointerdown=(e)=>{
        e.stopPropagation();e.preventDefault();const y=e.clientY;
        const old=Number(meta.minutes)||Number(meta.blocks||1)*60;
        handle.setPointerCapture(e.pointerId);
        handle.onpointermove=(p)=>{
          const minutes=Math.max(30,Math.min(240,old+Math.round((p.clientY-y)/20)*30));
          el.style.gridRow=(Math.round((from-8)*2)+2)+" / span "+Math.max(1,minutes/30);
        };
        handle.onpointerup=(p)=>{
          const minutes=Math.max(30,Math.min(240,old+Math.round((p.clientY-y)/20)*30));
          handle.onpointermove=null;handle.onpointerup=null;
          if(minutes!==old)send({type:"resize_scheduled",task_id:meta.task_id,minutes});
        };
      };
      el.ondragstart=(e)=>{
        const minutes=Number(meta.minutes)||Number(meta.blocks||1)*60;
        dragged={task_id:meta.task_id,blocks:Math.ceil(minutes/60),minutes};
        e.dataTransfer.setData("text/plain",meta.task_id);
        e.dataTransfer.setData("application/x-classpulse-blocks",String(Math.ceil(minutes/60)));
        e.dataTransfer.setData("application/x-classpulse-minutes",String(minutes));
        e.dataTransfer.effectAllowed="move";};
    }
    if(kind==="external"){el.title="點擊編輯，變更前會再次確認";el.onclick=()=>send({type:"external_edit",id:meta.id});}
    if(kind==="study"||kind==="external"){
      el.ondragover=(e)=>{e.preventDefault();e.dataTransfer.dropEffect="none";};
      el.ondrop=(e)=>{e.preventDefault();e.stopPropagation();
        showError("此時間已被「"+text+"」占用，不能直接覆蓋；原有任務與行程保持不變。");
      };
    }
    pos(el,idx+2,Math.round((from-8)*2)+2,Math.round((to-from)*2));
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
  (data.scheduled||[]).forEach(s=>event(s.day,s.hour,Math.min(24,s.hour+(Number(s.minutes)||60)/60),
    s.title+" · "+s.subject+"（"+(s.source==="manual"?"手排":"自動")+"）","study",s));
}
"""

BOARD = st.components.v2.component("classpulse_rolling_week",html=HTML,css=CSS,js=JS)


def render_week_board(payload: dict) -> dict | None:
    result = BOARD(data=payload,key="classpulse_week_board",on_action_change=lambda: None)
    value = result.action
    return json.loads(value) if value else None
