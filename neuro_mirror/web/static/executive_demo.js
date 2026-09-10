(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const panel = $("executive-panel");
  const canvas = $("executive-canvas");
  const sample = $("executive-sample");
  const trailLayer = $("executive-trail");
  const analysisPanel = $("executive-analysis");
  if (!panel || !canvas || !sample || !trailLayer || !analysisPanel) return;

  const ctx = canvas.getContext("2d");
  const state = { mode: "house_copy", strokes: [[]], hover: null, trail: [] };
  const trailItems = [
    ["1", 12, 18], ["А", 34, 72], ["2", 52, 24], ["Б", 76, 62], ["3", 88, 17],
    ["В", 68, 88], ["4", 43, 48], ["Г", 18, 86], ["5", 8, 48], ["Д", 91, 48],
  ];

  function open(mode) {
    state.mode = mode;
    panel.dataset.mode = mode;
    reset();
    $("main-menu")?.setAttribute("hidden", "");
    panel.removeAttribute("hidden");
    document.body.style.overflow = "hidden";
    $("executive-title").textContent = mode === "trail" ? "Последовательность" : mode === "house_recall" ? "Дом по памяти" : "Копирование дома";
    $("executive-instruction").textContent = mode === "trail"
      ? "Соедините элементы, чередуя цифры и буквы: 1 — А — 2 — Б — 3 — В — 4 — Г — 5 — Д."
      : mode === "house_recall" ? "Нарисуйте дом по памяти. Образец не показывается." : "Повторите дом по образцу в поле справа.";
    sample.toggleAttribute("hidden", mode !== "house_copy");
    trailLayer.toggleAttribute("hidden", mode !== "trail");
    $("executive-new-line").toggleAttribute("hidden", mode === "trail");
    $("executive-undo").toggleAttribute("hidden", mode === "trail");
    $("executive-done").querySelector("span").textContent = mode === "trail" ? "Готово" : "Проверить";
    analysisPanel.setAttribute("hidden", "");
    buildTrail();
    draw();
  }

  function close() {
    panel.setAttribute("hidden", "");
    document.body.style.overflow = "";
    $("main-menu")?.removeAttribute("hidden");
  }

  function reset() { state.strokes = [[]]; state.hover = null; state.trail = []; analysisPanel.setAttribute("hidden", ""); buildTrail(); draw(); }

  function pointFromMouse(event) {
    const rect = canvas.getBoundingClientRect();
    return { x: clamp((event.clientX-rect.left)/rect.width), y: clamp((event.clientY-rect.top)/rect.height) };
  }

  function clamp(value) { return Math.max(0, Math.min(1, value)); }

  function draw() {
    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.lineWidth=4; ctx.strokeStyle="#17202a"; ctx.lineJoin="round"; ctx.lineCap="round";
    const paths = state.mode === "trail" ? [state.trail.map((index) => ({x:trailItems[index][1]/100,y:trailItems[index][2]/100}))] : state.strokes;
    for (const stroke of paths) {
      if (!stroke.length) continue;
      ctx.beginPath(); ctx.moveTo(stroke[0].x*canvas.width,stroke[0].y*canvas.height);
      for (const point of stroke.slice(1)) ctx.lineTo(point.x*canvas.width,point.y*canvas.height);
      ctx.stroke();
    }
    const stroke=state.strokes.at(-1);
    if (state.mode !== "trail" && stroke?.length && state.hover) {
      const last=stroke.at(-1); ctx.save(); ctx.setLineDash([9,7]); ctx.beginPath();
      ctx.moveTo(last.x*canvas.width,last.y*canvas.height); ctx.lineTo(state.hover.x*canvas.width,state.hover.y*canvas.height); ctx.stroke(); ctx.restore();
    }
  }

  function buildTrail() {
    trailLayer.innerHTML="";
    if (state.mode !== "trail") return;
    trailItems.forEach(([label,x,y],index) => {
      const button=document.createElement("button"); button.type="button"; button.textContent=label;
      button.style.left=`${x}%`; button.style.top=`${y}%`; button.classList.toggle("selected",state.trail.includes(index));
      button.addEventListener("click",()=>{ state.trail.push(index); button.classList.add("selected"); draw(); });
      trailLayer.appendChild(button);
    });
    for (const [text,x,y] of [["Начало",12,8],["Конец",91,56]]) {
      const label=document.createElement("span"); label.className="executive-trail-label"; label.textContent=text; label.style.left=`${x}%`; label.style.top=`${y}%`; trailLayer.appendChild(label);
    }
  }

  function houseLines() {
    return state.strokes.filter((stroke)=>stroke.length===2).map((stroke)=>({
      x1:stroke[0].x, y1:stroke[0].y, x2:stroke[1].x, y2:stroke[1].y,
    }));
  }

  async function analyzeHouse() {
    const lines=houseLines();
    analysisPanel.removeAttribute("hidden");
    analysisPanel.textContent="Проверяю структуру…";
    try {
      const response=await fetch("/api/demo/executive/house-analysis",{
        method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({lines}),
      });
      if(!response.ok) throw new Error(`HTTP ${response.status}`);
      renderAnalysis(await response.json());
    } catch(error) {
      analysisPanel.textContent=`Не удалось проверить рисунок: ${error.message || error}`;
    }
  }

  function renderAnalysis(result) {
    const labels={body:"Корпус",roof:"Крыша и контакт с корпусом",chimney:"Труба и контакт с крышей",
      annex:"Пристройка справа и контакт",window:"Окно внутри корпуса",window_cross:"Перекладины окна"};
    const relation={roof:"touches_body",chimney:"touches_roof",annex:"left_edge_touches_body",
      window:"inside_body",window_cross:"found"};
    const title=document.createElement("h3"); title.textContent="Структура рисунка";
    const list=document.createElement("ul"); list.className="executive-analysis-list";
    for(const key of Object.keys(labels)) {
      const feature=result.features?.[key] || {};
      const requiredRelation=relation[key];
      const ok=Boolean(feature.found && (!requiredRelation || requiredRelation==="found" || feature[requiredRelation]));
      const row=document.createElement("li"); row.className="executive-analysis-row";
      const name=document.createElement("span"); name.textContent=labels[key];
      const status=document.createElement("strong"); status.className=ok?"executive-analysis-ok":"executive-analysis-missing";
      status.textContent=ok?"найдено":"не найдено"; row.append(name,status); list.appendChild(row);
    }
    const counts=document.createElement("p"); counts.className="executive-analysis-note";
    counts.textContent=`Линий: ${result.counts?.accepted_lines || 0}. Прямоугольников: ${result.counts?.rectangles || 0}. Треугольников: ${result.counts?.triangles || 0}.`;
    const note=document.createElement("p"); note.className="executive-analysis-note"; note.textContent=result.notes || "";
    analysisPanel.replaceChildren(title,list,counts,note);
  }

  document.querySelectorAll("[data-executive-demo]").forEach((button) => button.addEventListener("click",()=>open(button.dataset.executiveDemo)));
  canvas.addEventListener("click",(event)=>{
    if(state.mode === "trail") return;
    const stroke=state.strokes.at(-1);
    stroke.push(pointFromMouse(event));
    if(stroke.length === 2) state.strokes.push([]);
    state.hover=null;
    draw();
  });
  canvas.addEventListener("mousemove",(event)=>{ if(state.mode === "trail") return; state.hover=pointFromMouse(event); draw(); });
  canvas.addEventListener("mouseleave",()=>{ state.hover=null; draw(); });
  $("executive-new-line").addEventListener("click",()=>{ if(state.strokes.at(-1).length === 1) state.strokes.pop(); if(!state.strokes.length || state.strokes.at(-1).length) state.strokes.push([]); state.hover=null; draw(); });
  $("executive-undo").addEventListener("click",()=>{ let stroke=state.strokes.at(-1); if(!stroke.length && state.strokes.length>1) { state.strokes.pop(); stroke=state.strokes.at(-1); } stroke.pop(); if(stroke.length === 2) state.strokes.push([]); draw(); });
  $("executive-clear").addEventListener("click",reset);
  $("executive-done").addEventListener("click",()=>state.mode==="trail"?close():analyzeHouse());
  $("executive-close").addEventListener("click",close);
  new ResizeObserver(() => {
    const rect=canvas.getBoundingClientRect();
    const ratio=Math.min(window.devicePixelRatio || 1, 2);
    const width=Math.max(1,Math.round(rect.width*ratio)), height=Math.max(1,Math.round(rect.height*ratio));
    if(canvas.width !== width || canvas.height !== height) { canvas.width=width; canvas.height=height; draw(); }
  }).observe(canvas);
})();
