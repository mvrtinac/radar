/* Lógica compartida del catálogo (datos, filtros, pestañas, tiendas).
   Cada propuesta de diseño define window.RADAR = { card(item, h), panelClass? } antes de cargar este archivo
   y usa los mismos id en su HTML. */
(function () {
  const CFG = window.RADAR || {};
  const COLORS = {"Negro":"#1a1a1a","Blanco/Crema":"#f3efe6","Gris":"#9a9ca1","Azul":"#2f5fa8","Rojo/Burdeo":"#8e2333","Rosado":"#e89ab5","Verde":"#5d7a3e","Café/Beige":"#8a6a4a","Amarillo":"#e7c43c","Naranjo":"#e3792f","Morado":"#7a4fa0","Camuflado":"#6b6b47"};
  const SIZE_ORDER = ["XS","S","M","L","XL","XXL","XXXL","Única"];
  const LABELS = {brand:"Marca",cat:"Tipo",size:"Talla",color:"Color"};
  const PAGE = CFG.page || 48, NEW_DAYS = 14;
  const fmt = n => "$" + Math.round(n).toLocaleString("es-CL");
  const int = n => n.toLocaleString("es-CL");
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const normTxt = s => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const $ = id => document.getElementById(id);
  const X = '<svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 2l6 6M8 2L2 8" stroke="currentColor" stroke-width="1.5"/></svg>';

  let DATA = {items:[],stores:[]}, STORES = {}, shown = PAGE, openKey = null;
  const state = {q:"",tab:"all",stock:true,brand:new Set(),cat:new Set(),size:new Set(),color:new Set(),pMin:null,pMax:null,sort:"rel"};
  const isNew = i => i.published && (Date.now() - new Date(i.published).getTime()) < NEW_DAYS * 864e5;
  const onSale = i => i.compare_at > i.price;
  const disc = i => onSale(i) ? Math.round((1 - i.price / i.compare_at) * 100) : 0;
  const KEY = "radar-" + (CFG.id || "p");
  const okUrl = u => typeof u === "string" && /^https:\/\//i.test(u);
  try{["radar-f1","radar-f2","radar-f3"].forEach(k=>localStorage.removeItem(k))}catch(e){}

  function save(){try{localStorage.setItem(KEY,JSON.stringify({...state,brand:[...state.brand],cat:[...state.cat],size:[...state.size],color:[...state.color]}))}catch(e){}}
  function load(){try{const s=JSON.parse(localStorage.getItem(KEY)||"null");if(s)Object.assign(state,s,{brand:new Set(s.brand),cat:new Set(s.cat),size:new Set(s.size),color:new Set(s.color)})}catch(e){}}

  function matches(i, skip){
    if(state.tab==="sale"&&!onSale(i))return false;
    if(state.tab==="new"&&!isNew(i))return false;
    if(state.stock&&!i.available)return false;
    if(skip!=="brand"&&state.brand.size&&!state.brand.has(i.brand))return false;
    if(skip!=="cat"&&state.cat.size&&!state.cat.has(i.cat))return false;
    if(skip!=="color"&&state.color.size&&!i.colors.some(c=>state.color.has(c)))return false;
    if(skip!=="size"&&state.size.size&&!i.sizes.some(s=>state.size.has(s)))return false;
    if(state.pMin!=null&&i.price<state.pMin)return false;
    if(state.pMax!=null&&i.price>state.pMax)return false;
    if(state.q){const w=normTxt(state.q).split(/\s+/).filter(Boolean);if(!w.every(x=>i.search.includes(x)))return false}
    return true;
  }
  const valsOf = (i,k) => k==="brand"?[i.brand]:k==="cat"?[i.cat]:k==="size"?i.sizes:i.colors;
  function counts(key){const m=new Map();DATA.items.forEach(i=>{if(matches(i,key))valsOf(i,key).forEach(v=>m.set(v,(m.get(v)||0)+1))});return m}
  function allValues(key){
    const s=new Set();DATA.items.forEach(i=>valsOf(i,key).forEach(v=>s.add(v)));let v=[...s];
    if(key==="size")v.sort((a,b)=>{const x=SIZE_ORDER.indexOf(a),y=SIZE_ORDER.indexOf(b);if(x>-1&&y>-1)return x-y;if(x>-1)return -1;if(y>-1)return 1;return a.localeCompare(b,"es",{numeric:true})});
    else if(key==="color")v=Object.keys(COLORS).filter(c=>s.has(c));
    else v.sort((a,b)=>a.localeCompare(b,"es"));
    return v;
  }

  function panelHTML(key){
    const foot=`<div class="pfoot"><button class="plink quiet" type="button" data-clear>Quitar</button><button class="plink" type="button" data-close>Listo</button></div>`;
    if(key==="price")return `<div class="prow"><input type="number" id="pMin" placeholder="Mínimo" min="0" step="1000" inputmode="numeric" value="${Number.isFinite(state.pMin)?state.pMin:""}" aria-label="Precio mínimo"><input type="number" id="pMax" placeholder="Máximo" min="0" step="1000" inputmode="numeric" value="${Number.isFinite(state.pMax)?state.pMax:""}" aria-label="Precio máximo"></div>
      <div class="presets"><button type="button" data-p="0-20000">Hasta $20.000</button><button type="button" data-p="20000-40000">$20.000 a $40.000</button><button type="button" data-p="40000-60000">$40.000 a $60.000</button><button type="button" data-p="60000-">Más de $60.000</button></div>${foot}`;
    const c=counts(key), vals=allValues(key);
    if(key==="size")return `<div class="sizes-grid">${vals.map(v=>`<label><input type="checkbox" value="${esc(v)}" ${state.size.has(v)?"checked":""}>${esc(v)}</label>`).join("")}</div>${foot}`;
    const opts=vals.map(v=>{const n=c.get(v)||0;const sw=key==="color"?`<span class="sw" style="background:${COLORS[v]}"></span>`:"";
      return `<label class="opt${n?"":" zero"}" data-v="${esc(normTxt(v))}"><input type="checkbox" value="${esc(v)}" ${state[key].has(v)?"checked":""}>${sw}<span>${esc(v)}</span><span class="c">${int(n)}</span></label>`}).join("");
    const find=key==="brand"?`<input type="search" placeholder="Buscar entre ${vals.length} marcas" data-find aria-label="Buscar marca">`:"";
    return `${find}<div class="opts">${opts}</div>${foot}`;
  }
  function closePanel(){document.querySelectorAll(".panel").forEach(p=>p.remove());document.querySelectorAll(".dd .ctl").forEach(b=>b.setAttribute("aria-expanded","false"));openKey=null}
  function openPanel(dd){
    const key=dd.dataset.key, was=openKey===key; closePanel(); if(was)return;
    openKey=key; dd.querySelector(".ctl").setAttribute("aria-expanded","true");
    const p=document.createElement("div");p.className="panel";p.innerHTML=panelHTML(key);dd.appendChild(p);
    p.addEventListener("click",e=>e.stopPropagation());
    p.querySelectorAll("input[type=checkbox]").forEach(cb=>cb.onchange=()=>{cb.checked?state[key].add(cb.value):state[key].delete(cb.value);update()});
    const f=p.querySelector("[data-find]");if(f){f.focus();f.oninput=()=>{const t=normTxt(f.value);p.querySelectorAll(".opt").forEach(l=>l.hidden=!l.dataset.v.includes(t))}}
    if(key==="price"){
      const num=v=>v===""?null:Number(v);
      $("pMin").oninput=()=>{state.pMin=num($("pMin").value);update()};
      $("pMax").oninput=()=>{state.pMax=num($("pMax").value);update()};
      p.querySelectorAll("[data-p]").forEach(b=>b.onclick=()=>{const[a,z]=b.dataset.p.split("-");state.pMin=a?+a:null;state.pMax=z?+z:null;$("pMin").value=state.pMin??"";$("pMax").value=state.pMax??"";update()});
    }
    p.querySelector("[data-clear]").onclick=()=>{clearKey(key);closePanel();update()};
    p.querySelector("[data-close]").onclick=closePanel;
  }
  function clearKey(k){if(k==="price"){state.pMin=null;state.pMax=null}else state[k].clear()}

  function renderActive(){
    const pills=[];
    ["brand","cat","size","color"].forEach(k=>state[k].forEach(v=>pills.push(`<button class="chip" type="button" data-k="${k}" data-v="${esc(v)}"><span>${LABELS[k]}</span>${esc(v)} ${X}</button>`)));
    if(state.pMin!=null||state.pMax!=null)pills.push(`<button class="chip" type="button" data-k="price"><span>Precio</span>${state.pMin!=null?fmt(state.pMin):"$0"} a ${state.pMax!=null?fmt(state.pMax):"sin tope"} ${X}</button>`);
    if(pills.length>1)pills.push(`<button class="plink quiet" type="button" id="clearAll">Quitar todos</button>`);
    $("active").innerHTML=pills.join("");
    $("active").querySelectorAll(".chip").forEach(b=>b.onclick=()=>{const k=b.dataset.k;k==="price"?clearKey("price"):state[k].delete(b.dataset.v);update()});
    $("clearAll")?.addEventListener("click",()=>{["brand","cat","size","color","price"].forEach(clearKey);update()});
    document.querySelectorAll(".dd").forEach(dd=>{const k=dd.dataset.key,n=dd.querySelector(".n");if(n)n.textContent=k==="price"?((state.pMin!=null||state.pMax!=null)?"1":""):(state[k].size||"")});
    $("tStock").classList.toggle("on",state.stock);$("tStock").setAttribute("aria-pressed",state.stock);
    document.querySelectorAll("[data-tab]").forEach(t=>t.setAttribute("aria-selected",t.dataset.tab===state.tab));
  }

  const H = {fmt,int,esc,isNew,onSale,disc,store:b=>STORES[b]||{}};
  function picHTML(i){
    return i.image?`<img src="${esc(i.image)}" alt="${esc(i.title)}" loading="lazy" decoding="async" >`:`<span class="ph">Sin foto</span>`;
  }
  H.pic = picHTML;
  H.sizes = i => i.sizes.length ? i.sizes.map(s=>`<span>${esc(s)}</span>`).join("") : `<span class="none">Sin tallas disponibles</span>`;

  function sorted(list){
    const d=i=>onSale(i)?1-i.price/i.compare_at:0;
    if(state.sort==="asc")return list.sort((a,b)=>a.price-b.price);
    if(state.sort==="desc")return list.sort((a,b)=>b.price-a.price);
    if(state.sort==="disc")return list.sort((a,b)=>d(b)-d(a));
    return list.sort((a,b)=>(b.published||"").localeCompare(a.published||""));
  }
  function update(resetPage=true){
    if(resetPage)shown=PAGE;
    const base=t=>{const keep=state.tab;state.tab=t;const n=DATA.items.filter(i=>matches(i)).length;state.tab=keep;return n};
    ["all","sale","new"].forEach(t=>{const el=$("c-"+t);if(el)el.textContent=int(base(t))});
    const list=sorted(DATA.items.filter(i=>matches(i)));
    $("grid").innerHTML=list.length?list.slice(0,shown).map((i,k)=>CFG.card(i,H,k)).join(""):`<div class="empty">Ninguna prenda calza con estos filtros. Quita alguno para ver más.</div>`;
    $("more").hidden=list.length<=shown;
    $("more").textContent=`Ver más prendas (${int(Math.min(shown,list.length))} de ${int(list.length)})`;
    $("count").textContent=`${int(list.length)} prenda${list.length===1?"":"s"}`;
    renderActive();
    if(openKey&&["brand","cat","color"].includes(openKey)){const c=counts(openKey);document.querySelectorAll(".panel .opt").forEach(l=>{const v=l.querySelector("input").value,n=c.get(v)||0;l.querySelector(".c").textContent=int(n);l.classList.toggle("zero",!n)})}
    save();
  }
  function renderStores(){
    const rows=DATA.stores.map(s=>{const its=DATA.items.filter(i=>i.brand===s.brand);return{...s,n:its.length,stock:its.filter(i=>i.available).length,sale:its.filter(onSale).length}}).sort((a,b)=>b.n-a.n||a.brand.localeCompare(b.brand,"es"));
    const empty=rows.filter(r=>!r.n).length;
    $("stores-sub").textContent=`${rows.length} marcas, ordenadas por cantidad de prendas.`+(empty?` ${empty===1?"Una tienda no tiene":empty+" tiendas no tienen"} prendas publicadas hoy.`:"");
    const z=n=>n?int(n):`<span class="zero">0</span>`;
    $("stores-table").querySelector("tbody").innerHTML=rows.map(r=>`<tr>
      <td class="name"><button type="button" data-brand="${esc(r.brand)}">${esc(r.brand)}</button></td>
      <td class="r">${z(r.n)}</td><td class="r opt-col">${z(r.stock)}</td><td class="r">${z(r.sale)}</td>
      <td><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.url.replace(/^https?:\/\/(www\.)?/,""))}</a></td>
      <td class="opt-col">${r.instagram?`<a href="${esc(r.instagram)}" target="_blank" rel="noopener noreferrer">@${esc(r.instagram.replace(/\/$/,"").split("/").pop())}</a>`:`<span class="dash">—</span>`}</td></tr>`).join("");
    $("stores-table").querySelectorAll("[data-brand]").forEach(b=>b.onclick=()=>{state.brand=new Set([b.dataset.brand]);state.tab="all";location.hash="";update();route()});
  }
  function route(){
    const v=location.hash==="#tiendas"?"stores":"catalog";
    $("v-catalog").hidden=v!=="catalog";$("v-stores").hidden=v!=="stores";
    document.querySelectorAll("[data-view]").forEach(a=>{if(a.dataset.view===v)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current")});
    window.scrollTo(0,0);
  }
  function skeleton(){$("grid").innerHTML=Array.from({length:8},()=>`<div class="card skel" aria-hidden="true"><div class="pic"></div></div>`).join("")}

  function wire(){
    document.querySelectorAll(".dd").forEach(dd=>dd.querySelector(".ctl").addEventListener("click",e=>{e.stopPropagation();openPanel(dd)}));
    document.addEventListener("click",closePanel);
    document.addEventListener("keydown",e=>{if(e.key==="Escape")closePanel()});
    document.querySelectorAll("[data-tab]").forEach(t=>t.onclick=()=>{state.tab=t.dataset.tab;update()});
    $("q").oninput=()=>{state.q=$("q").value;update()};
    $("tStock").onclick=()=>{state.stock=!state.stock;update()};
    $("sort").onchange=()=>{state.sort=$("sort").value;update()};
    $("more").onclick=()=>{shown+=PAGE;update(false)};
    window.addEventListener("hashchange",route);
    document.addEventListener("error",e=>{const t=e.target;if(t.tagName==="IMG"&&t.closest(".pic"))t.replaceWith(Object.assign(document.createElement("span"),{className:"ph",textContent:"Foto no disponible"}))},true);
    window.addEventListener("scroll",()=>document.body.classList.toggle("scrolled",scrollY>4),{passive:true});
  }
  function loadData(){
    skeleton();
    fetch((CFG.data||"../data.json")+"?v="+Date.now()).then(r=>{if(!r.ok)throw new Error(r.status);return r.json()}).then(d=>{
      (d.items||[]).forEach(i=>{if(!okUrl(i.url))i.url="#";if(i.image&&!okUrl(i.image))i.image=null});
      (d.stores||[]).forEach(s=>{if(!okUrl(s.url))s.url="#";if(s.instagram&&!okUrl(s.instagram))s.instagram=null});
      DATA=d;STORES={};(d.stores||[]).forEach(s=>STORES[s.brand]=s);
      const items=d.items,brands=new Set(items.map(i=>i.brand)).size,sale=items.filter(i=>onSale(i)&&i.available).length,fresh=items.filter(isNew).length;
      const stats={items:items.length,brands,sale,fresh,updated:d.updated};
      if(CFG.finding)CFG.finding(stats,H);
      else $("finding").innerHTML=`<b>${int(items.length)}</b> prendas de <b>${brands}</b> marcas chilenas. <b>${int(sale)}</b> en oferta con stock`+(fresh?` y <b>${int(fresh)}</b> publicadas en los últimos ${NEW_DAYS} días.`:".");
      document.querySelectorAll("[data-stamp]").forEach(el=>el.textContent=`Actualizado ${d.updated}`);
      if(CFG.ticker)CFG.ticker(d,H);
      $("sort").value=state.sort;
      update();renderStores();route();
    }).catch(()=>{
      $("finding").textContent="No se pudo cargar el catálogo.";
      $("grid").innerHTML=`<div class="empty">No se pudo cargar el catálogo. <button class="plink" type="button" id="retry">Reintentar</button></div>`;
      $("retry").onclick=loadData;
    });
  }
  load();wire();$("q").value=state.q;route();loadData();
})();
