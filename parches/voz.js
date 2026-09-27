/* ===== MÓDULO VOZ (26-09-2026) — lectura en voz alta de las narraciones =====
   Dueño: frente «voz». Prefijo vz-. Datos: D.audio (datos/censo/audio.json, esquema 4.6).
   Lee los capítulos narrativos (título, entradilla, títulos de sección y párrafos) y los relatos de
   personaje (nombre, entradilla y relato). Dos motores: (a) pista pregrabada servida desde D.audio.base
   (jsDelivr), solo si su «huella» (SHA-256 del texto canónico) coincide con el texto actual; (b) la voz
   del navegador (speechSynthesis, es-ES), párrafo a párrafo y frase a frase.
   Este fichero lo inserta build_local.py dentro de la IIFE de la plantilla: ve D, NARR, NR, NRP, PJ_BY,
   esc, $, $$, store, MOD y route. */

/*VZ-TEXTO-INICIO*/
/* Regla única de extracción del texto locutado. La misma regla vive en tmp/voz_narrativa/textos.py
   (Python) y tmp/voz_narrativa/comprobar_huellas.py comprueba que las dos dan la misma huella.
   - Capítulo: t, lede, y por cada sección h y cada p (en ese orden). Nada de claves, pull, callout,
     lista, figura, widget ni personajes.
   - Relato: nombre, lede, relato[] (en la investigación y la restringida, la bio del personaje).
   - Cada bloque: quitar etiquetas HTML, deshacer cinco entidades, colapsar espacios, recortar, NFC.
   - Texto canónico = bloques no vacíos unidos por «\n». Huella = SHA-256 hex del UTF-8. */
function vzLimpia(s){
  return String(s==null?'':s).replace(/<[^>]+>/g,' ').replace(/&nbsp;/g,' ').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/\s+/g,' ').trim().normalize('NFC');
}
function vzBloquesCapitulo(N){
  var b=[];if(!N)return b;
  if(N.t)b.push({k:'t',x:N.t});
  if(N.lede)b.push({k:'lede',x:N.lede});
  (N.secciones||[]).forEach(function(s,i){if(s&&s.h)b.push({k:'h',i:i,x:s.h});((s&&s.p)||[]).forEach(function(p,j){b.push({k:'p',i:i,j:j,x:p})})});
  return b.map(function(o){o.x=vzLimpia(o.x);return o}).filter(function(o){return o.x});
}
function vzBloquesRelato(nombre,lede,relato){
  var b=[];
  if(nombre)b.push({k:'nombre',x:nombre});
  if(lede)b.push({k:'lede',x:lede});
  (relato||[]).forEach(function(p,j){b.push({k:'p',j:j,x:p})});
  return b.map(function(o){o.x=vzLimpia(o.x);return o}).filter(function(o){return o.x});
}
function vzTextoCanonico(bloques){return bloques.map(function(b){return b.x}).join('\n')}
/*VZ-TEXTO-FIN*/

var VZ=(function(){
  var A=D.audio||{},PISTAS=A.pistas||{},BASE=String(A.base||'').replace(/\/+$/,'');
  /* Manifiesto vivo (27-09-2026). Las locuciones con la voz de Google (Gemini TTS) se generan y publican en el
     repositorio azabarte-laminas (voz/narrativa/audio.json, mismo esquema que D.audio) y se sirven por jsDelivr.
     Se consulta al cargar la página: una pista nueva o regenerada suena sin volver a desplegar la web.
     Para cada clave hay hasta dos candidatas (la embebida en D.audio y la del manifiesto vivo); al abrir se usa
     la que tenga la huella del texto actual. D.config.audioManifiesto permite otra URL, o '' para no consultarlo. */
  var VIVO_URL=(typeof CFG.audioManifiesto==='string')?CFG.audioManifiesto:'https://cdn.jsdelivr.net/gh/azabartefj5-cell/azabarte-laminas@main/voz/narrativa/audio.json';
  var VIVAS={};
  function conBase(p,b){if(!p||!p.src)return null;var q={};for(var k in p)q[k]=p[k];q.base=String(p.base||b||'').replace(/\/+$/,'');return q.base?q:null}
  function candidatas(clave){return [conBase(PISTAS[clave],BASE),VIVAS[clave]||null].filter(Boolean)}
  var vivoListo=(VIVO_URL&&window.fetch)?fetch(VIVO_URL,{cache:'no-cache'}).then(function(r){return r.ok?r.json():null}).then(function(m){
      if(!m||!m.pistas)return;var b=String(m.base||'').replace(/\/+$/,'');
      Object.keys(m.pistas).forEach(function(k){var q=conBase(m.pistas[k],b);if(q)VIVAS[k]=q});
      try{var p=pistaDeRuta(route());if(p&&(synth||candidatas(p.clave).length))ponBoton(p);pintaBoton()}catch(e){}
    }).catch(function(){}):Promise.resolve();
  function esperaVivo(ms){return Promise.race([vivoListo,new Promise(function(res){setTimeout(res,ms)})])}
  var synth=('speechSynthesis' in window&&'SpeechSynthesisUtterance' in window)?window.speechSynthesis:null;
  var VELS=[0.8,0.9,1,1.1,1.25,1.5];
  var CPS=15.5; /* caracteres por segundo de una locución en castellano a 1× (estimación para el «≈ N min») */
  var st={abierto:false,clave:null,titulo:'',tipo:'',bloques:[],els:[],cum:[],total:0,idx:0,motor:null,tocando:false,
          vel:+store.get('vz_vel',1)||1,seguir:store.get('vz_seguir',true)!==false,preparando:false,frac:0,ultimoGuardado:0};
  if(VELS.indexOf(st.vel)<0)st.vel=1;
  var ui=null;

  function qs(s,r){return (r||document).querySelector(s)}
  function qsa(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))}
  function mmss(s){s=Math.max(0,Math.round(s||0));var m=Math.floor(s/60),r=s%60;return m+':'+(r<10?'0':'')+r}
  function minutos(chars,vel){var m=Math.round(chars/CPS/(vel||1)/60);return m<1?'menos de un minuto':(m===1?'1 min':m+' min')}
  function velTxt(v){return String(v).replace('.',',')+'×'}

  /* ---------- pista según la ruta ---------- */
  function pistaDeRuta(r){
    if(NARR&&r.mode==='leer'&&r.a){
      var N=(NR.capitulos||{})[r.a];if(!N)return null;
      var b=vzBloquesCapitulo(N);if(b.length<2)return null;
      return {clave:'cap:'+r.a,titulo:N.t||r.a,tipo:'cap',bloques:b,boton:'Escuchar este capítulo'};
    }
    if(r.mode==='explorar'&&r.a==='personajes'&&r.b){
      var p=PJ_BY[r.b];if(!p)return null;
      var R=NARR?NRP(p.id):{};var conRelato=!!(NARR&&R.relato&&R.relato.length);
      var bio=p.bio||[];var lede=(NARR&&R.lede)||bio[0]||'';var cuerpo=conRelato?R.relato:bio.slice(1);
      var bl=vzBloquesRelato(p.nombre,lede,cuerpo);if(bl.length<3)return null;
      return {clave:(conRelato?'pj:':'bio:')+p.id,titulo:p.corto||p.nombre,tipo:'pj',bloques:bl,boton:'Escuchar su historia'};
    }
    return null;
  }
  /* Elementos de la página que corresponden a cada bloque: se emparejan por texto, en orden, para no
     depender del HTML exacto que pinten la plantilla u otros módulos. */
  function mapea(tipo,bloques,elsDados){
    if(elsDados)return elsDados;
    var sel=tipo==='cap'?'#article h1, #article h2, #article h3, #article p':(tipo==='pj'?'.pj-hero h1, .pj-hero .pj-lede, .pj-body p':null);
    if(!sel)return bloques.map(function(){return null});
    var cands=qsa(sel).filter(function(el){return !el.closest('.claves,.callout,.nr-cast,.nr-who,figure,nav,.toc,.margin,.vz-fila,.vz-player,.kin')});
    var k=0;return bloques.map(function(b){for(var i=k;i<cands.length;i++){if(vzLimpia(cands[i].textContent)===b.x){k=i+1;return cands[i]}}return null});
  }
  function huella(texto){
    if(!(window.crypto&&crypto.subtle&&window.TextEncoder))return Promise.resolve(null);
    return crypto.subtle.digest('SHA-256',new TextEncoder().encode(texto)).then(function(buf){return Array.prototype.map.call(new Uint8Array(buf),function(x){return ('0'+x.toString(16)).slice(-2)}).join('')}).catch(function(){return null});
  }

  /* ---------- posiciones recordadas ---------- */
  function posGuardada(clave){var m=store.get('vz_pos',{})||{};return m[clave]||null}
  function guardaPos(i,t,frac,fuerza){
    var ahora=Date.now();if(!fuerza&&ahora-st.ultimoGuardado<2500)return;st.ultimoGuardado=ahora;
    var m=store.get('vz_pos',{})||{};m[st.clave]={i:i,t:t||0,f:frac||0,cuando:ahora};
    var ks=Object.keys(m);if(ks.length>40){ks.sort(function(a,b){return (m[a].cuando||0)-(m[b].cuando||0)});ks.slice(0,ks.length-40).forEach(function(k){delete m[k]})}
    store.set('vz_pos',m);
  }
  function borraPos(clave){var m=store.get('vz_pos',{})||{};if(m[clave]){delete m[clave];store.set('vz_pos',m)}}

  /* ---------- voces del navegador ---------- */
  function vocesEs(){if(!synth)return [];return synth.getVoices().filter(function(v){return /^es([-_]|$)/i.test(v.lang||'')})}
  function puntua(v){
    var l=String(v.lang||'').replace('_','-').toLowerCase(),n=String(v.name||'').toLowerCase(),s=0;
    if(l==='es-es')s+=100;else if(l.slice(0,2)==='es')s+=40;else return -1;
    if(/natural|online|neural/.test(n))s+=30;
    if(/google/.test(n))s+=15;
    if(/premium|enhanced|mejorad/.test(n))s+=12;
    if(/spain|españa|castellano/.test(n))s+=5;
    if(/m[eé]xico|mexico|estados unidos|united states|latin/.test(n))s-=10;
    if(v.default)s+=1;
    return s;
  }
  function eligeVoz(){
    var vs=vocesEs();if(!vs.length)return null;
    var pref=store.get('vz_voz','');if(pref){var e=vs.filter(function(v){return v.voiceURI===pref||v.name===pref})[0];if(e)return e}
    vs.sort(function(a,b){return puntua(b)-puntua(a)});return vs[0];
  }
  function avisoVoz(v){
    if(!synth)return 'Este navegador no permite la lectura en voz alta.';
    if(!v){var todas=synth.getVoices();return todas.length?'Este dispositivo no tiene instalada ninguna voz en español; se leerá con la voz que haya, que pronunciará mal el castellano. En Windows y en el móvil se puede añadir una voz en español desde los ajustes de idioma.':'El navegador todavía no ha cargado sus voces. Pulse de nuevo dentro de un momento.'}
    var l=String(v.lang||'').replace('_','-').toLowerCase();
    if(l!=='es-es')return 'No hay voz de España en este dispositivo; se usa «'+v.name+'» ('+v.lang+'). En Windows y en el móvil se puede añadir una voz de español de España desde los ajustes de idioma.';
    return '';
  }

  /* ---------- motor (a): pista pregrabada ---------- */
  function motorAudio(pista,alFallar){
    var au=new Audio();au.preload='auto';au.src=pista.base+'/'+pista.src;
    var marcas=pista.marcas||[],dur=+pista.dur||0,vivo=true;
    au.playbackRate=st.vel;
    au.addEventListener('loadedmetadata',function(){if(isFinite(au.duration)&&au.duration>0)dur=au.duration;pinta()});
    au.addEventListener('timeupdate',function(){if(!vivo)return;var t=au.currentTime,i=0;for(var k=0;k<marcas.length;k++){if(marcas[k]<=t+0.05)i=k}
      if(i!==st.idx){st.idx=i;marca(i,true)}st.frac=dur?Math.min(1,t/dur):0;guardaPos(i,t,st.frac);pinta()});
    au.addEventListener('play',function(){st.tocando=true;pinta()});
    au.addEventListener('pause',function(){st.tocando=false;pinta();guardaPos(st.idx,au.currentTime,st.frac,true)});
    au.addEventListener('waiting',function(){estado('Cargando la grabación…')});
    au.addEventListener('ended',function(){fin()});
    au.addEventListener('error',function(){if(vivo){vivo=false;alFallar()}});
    return {tipo:'audio',_au:au,
      play:function(){var p=au.play();if(p&&p.catch)p.catch(function(e){if(vivo&&e&&e.name==='NotAllowedError'){st.tocando=false;nota('Pulse ▶ para empezar a escuchar la grabación.');pinta()}})},
      pause:function(){au.pause()},
      ir:function(i){i=Math.max(0,Math.min(marcas.length-1,i));au.currentTime=marcas[i]||0;st.idx=i;marca(i,true);pinta()},
      frac:function(f){if(dur){au.currentTime=f*dur}},
      vel:function(v){au.playbackRate=v},
      tiempo:function(){return {t:au.currentTime,dur:dur}},
      reanudar:function(p){if(!p)return;var t=(p.t&&(!dur||p.t<dur-2))?p.t:((p.i>0&&marcas[p.i])?marcas[p.i]:0);if(t>0){au.currentTime=t;st.idx=p.i||0}},
      destruir:function(){vivo=false;try{au.pause();au.removeAttribute('src');au.load()}catch(e){}}};
  }

  /* ---------- motor (b): voz del navegador ---------- */
  function trozos(t){
    /* frases de ≤ ~180 caracteres: Chrome corta las locuciones largas de sus voces en red */
    var frases=t.match(/[^.!?…]+[.!?…]+[»”"’)]*\s*|[^.!?…]+$/g)||[t];
    var out=[],acc='';
    frases.forEach(function(f){if(acc&&(acc+f).length>180){out.push(acc);acc=f}else acc+=f});
    if(acc.trim())out.push(acc);
    var res=[];
    out.forEach(function(s){if(s.length<=260){res.push(s);return}
      var cur='';s.replace(/([,;:])\s+/g,'$1\u0001').split('\u0001').forEach(function(x){if(cur&&(cur+' '+x).length>180){res.push(cur);cur=x}else cur=cur?cur+' '+x:x});if(cur)res.push(cur)});
    return res.map(function(s){return s.trim()}).filter(Boolean);
  }
  function motorVoz(){
    var gen=0,chunks=[],ci=0,offset=0,voz=null,vigia=null;
    var esChromium=/Chrome|Edg\//.test(navigator.userAgent)&&!/Android|iPhone|iPad|Mobile/.test(navigator.userAgent);
    function prepara(i){st.idx=i;var b=st.bloques[i];chunks=trozos(b.x);ci=0;offset=0}
    function habla(g){
      if(g!==gen)return;
      if(ci>=chunks.length){if(st.idx+1<st.bloques.length){prepara(st.idx+1);marca(st.idx,true);habla(g)}else fin();return}
      var u=new SpeechSynthesisUtterance(chunks[ci]);
      voz=eligeVoz();if(voz){u.voice=voz;u.lang=voz.lang||'es-ES'}else u.lang='es-ES';
      u.rate=st.vel;u.pitch=1;
      u.onstart=function(){if(g!==gen)return;st.tocando=true;pinta()};
      u.onboundary=function(e){if(g!==gen)return;progresoVoz(offset+(e.charIndex||0))};
      u.onend=function(){if(g!==gen)return;offset+=chunks[ci].length+1;ci++;progresoVoz(offset);guardaPos(st.idx,0,st.frac);habla(g)};
      u.onerror=function(e){if(g!==gen)return;var k=e&&e.error;if(k==='interrupted'||k==='canceled')return;
        if(k==='not-allowed'||k==='synthesis-failed'||k==='audio-busy'||k==='synthesis-unavailable'){nota('No se ha podido iniciar la voz del navegador ('+k+'). Pulse de nuevo «Reproducir».');pausa();return}
        ci++;habla(g)};
      try{synth.speak(u)}catch(err){nota('La voz del navegador ha fallado: '+(err&&err.message||err));pausa()}
    }
    function progresoVoz(chars){var b=st.bloques[st.idx];var dentro=Math.min(chars,b?b.x.length:0);st.frac=st.total?((st.cum[st.idx]||0)+dentro)/st.total:0;pinta()}
    function arranca(){
      gen++;var g=gen;
      var av=avisoVoz(eligeVoz());if(av)nota(av);
      if(synth.speaking||synth.pending){synth.cancel();setTimeout(function(){habla(g)},80)}else habla(g);
      st.tocando=true;pinta();
      if(esChromium&&!vigia)vigia=setInterval(function(){if(st.tocando&&synth.speaking&&!synth.paused){synth.pause();synth.resume()}},10000);
    }
    function pausa(){gen++;try{synth.cancel()}catch(e){}st.tocando=false;pinta();guardaPos(st.idx,0,st.frac,true)}
    prepara(0);
    return {tipo:'voz',
      play:function(){arranca()},
      pause:function(){pausa()},
      ir:function(i){i=Math.max(0,Math.min(st.bloques.length-1,i));var iba=st.tocando;gen++;try{synth.cancel()}catch(e){}prepara(i);marca(i,true);progresoVoz(0);if(iba)arranca();else{st.tocando=false;pinta()}},
      frac:function(f){var obj=Math.max(0,Math.min(st.total-1,Math.round(f*st.total)));var i=0;for(var k=0;k<st.cum.length;k++){if(st.cum[k]<=obj)i=k}this.ir(i)},
      vel:function(){if(st.tocando){gen++;try{synth.cancel()}catch(e){}arranca()}},
      tiempo:function(){return null},
      reanudar:function(p){if(p&&p.i>0&&p.i<st.bloques.length){prepara(p.i)}},
      destruir:function(){gen++;try{synth.cancel()}catch(e){}if(vigia){clearInterval(vigia);vigia=null}}};
  }

  /* ---------- reproductor ---------- */
  var ICO={play:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>',
           pause:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>',
           ant:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/></svg>',
           sig:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 6h2v12h-2zM6 18l8.5-6L6 6z"/></svg>',
           cerrar:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7l1.4-1.4 6.3 6.3 6.3-6.3z"/></svg>',
           auri:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a9 9 0 0 0-9 9v6a3 3 0 0 0 3 3h2v-8H5v-1a7 7 0 0 1 14 0v1h-3v8h2a3 3 0 0 0 3-3v-6a9 9 0 0 0-9-9z"/></svg>'};
  function creaUI(){
    if(ui)return ui;
    var d=document.createElement('div');d.id='vz-player';d.className='vz-player';d.setAttribute('role','region');d.setAttribute('aria-label','Lectura en voz alta');d.hidden=true;
    d.innerHTML='<div class="vz-cab"><span class="vz-titulo" id="vz-titulo"></span><span class="vz-estado" id="vz-estado" aria-live="polite"></span></div>'+
      '<input type="range" class="vz-rango" id="vz-rango" min="0" max="1000" value="0" step="1" aria-label="Posición en la lectura" aria-valuetext="">'+
      '<div class="vz-ctl">'+
        '<button type="button" class="vz-b" data-vz="ant" aria-label="Párrafo anterior" title="Párrafo anterior">'+ICO.ant+'</button>'+
        '<button type="button" class="vz-b vz-play" data-vz="play" aria-label="Reproducir" title="Reproducir">'+ICO.play+'</button>'+
        '<button type="button" class="vz-b" data-vz="sig" aria-label="Párrafo siguiente" title="Párrafo siguiente">'+ICO.sig+'</button>'+
        '<button type="button" class="vz-b vz-vel" data-vz="vel" aria-label="Velocidad de lectura" title="Velocidad de lectura">1×</button>'+
        '<button type="button" class="vz-b vz-seg" data-vz="seguir" aria-pressed="true" title="Desplazar la página con la lectura">Seguir</button>'+
        '<button type="button" class="vz-b vz-vozb" data-vz="voces" aria-expanded="false" aria-controls="vz-voces" title="Elegir la voz">Voz</button>'+
        '<button type="button" class="vz-b vz-cerrar" data-vz="cerrar" aria-label="Cerrar el reproductor" title="Cerrar">'+ICO.cerrar+'</button>'+
      '</div>'+
      '<div class="vz-nota" id="vz-nota" hidden></div>'+
      '<div class="vz-voces" id="vz-voces" hidden><label for="vz-sel">Voz del navegador</label><select id="vz-sel"></select><small id="vz-voces-nota"></small></div>';
    document.body.appendChild(d);
    d.addEventListener('keydown',function(e){
      if(e.key==='Escape'){cerrar();return}
      if(e.target&&e.target.tagName==='SELECT')return;
      if(e.key==='ArrowLeft'){e.preventDefault();anterior()}else if(e.key==='ArrowRight'){e.preventDefault();siguiente()}
    });
    var rango=qs('#vz-rango',d);
    rango.addEventListener('input',function(){if(st.motor)st.motor.frac(rango.value/1000)});
    qs('#vz-sel',d).addEventListener('change',function(e){store.set('vz_voz',e.target.value);if(st.motor&&st.motor.tipo==='voz'){nota(avisoVoz(eligeVoz()));if(st.tocando)st.motor.ir(st.idx)}});
    ui=d;return d;
  }
  function nota(t){var n=qs('#vz-nota');if(!n)return;n.hidden=!t;n.textContent=t||''}
  function estado(t){var e=qs('#vz-estado');if(e)e.textContent=t}
  function pinta(){
    if(!ui||!st.abierto)return;
    qs('#vz-titulo').textContent=st.titulo;
    var play=qs('[data-vz="play"]',ui);play.innerHTML=st.tocando?ICO.pause:ICO.play;play.setAttribute('aria-label',st.tocando?'Pausar':'Reproducir');play.title=st.tocando?'Pausar':'Reproducir';
    qs('[data-vz="vel"]',ui).textContent=velTxt(st.vel);qs('[data-vz="vel"]',ui).setAttribute('aria-label','Velocidad de lectura: '+velTxt(st.vel)+'. Pulse para cambiar');
    var seg=qs('[data-vz="seguir"]',ui);seg.setAttribute('aria-pressed',st.seguir?'true':'false');
    qs('[data-vz="voces"]',ui).hidden=!(st.motor&&st.motor.tipo==='voz');
    var r=qs('#vz-rango');r.value=Math.round(st.frac*1000);
    var n=st.bloques.length,i=Math.min(st.idx+1,n);
    var txt;
    if(st.preparando)txt='Preparando la lectura…';
    else if(st.motor&&st.motor.tipo==='audio'){var tm=st.motor.tiempo();txt=(tm&&tm.dur?mmss(tm.t)+' / '+mmss(tm.dur):'')+' · '+i+' de '+n+' · voz sintética (IA)'}
    else txt='Párrafo '+i+' de '+n+' · ≈ '+minutos(st.total-(st.cum[st.idx]||0),st.vel)+(st.motor&&st.motor.tipo==='voz'?' · voz del navegador':'');
    estado(txt);r.setAttribute('aria-valuetext','Párrafo '+i+' de '+n);
    pintaBoton();
  }
  function pintaBoton(){
    qsa('.vz-boton').forEach(function(b){
      var mio=st.abierto&&b.dataset.vzClave===st.clave;
      var base=b.dataset.vzTexto||'Escuchar';var chars=+b.dataset.vzChars||0;
      var p=posGuardada(b.dataset.vzClave);
      var label=mio?(st.tocando?'Pausar la lectura':'Continuar la lectura'):(p&&p.i>0?'Seguir escuchando':base);
      var html=ICO.auri+'<span>'+esc(label)+'</span>'+(mio?'':'<span class="vz-min">≈ '+esc(minutos(chars,1))+'</span>');
      if(b.innerHTML!==html)b.innerHTML=html;
      var pressed=mio&&st.tocando?'true':'false';if(b.getAttribute('aria-pressed')!==pressed)b.setAttribute('aria-pressed',pressed);
      var al=label+(mio?'':' (≈ '+minutos(chars,1)+' de audio)');if(b.getAttribute('aria-label')!==al)b.setAttribute('aria-label',al);
    });
  }
  function marca(i,desplaza){
    qsa('.vz-on').forEach(function(el){el.classList.remove('vz-on')});
    var el=st.els[i];if(!el)return;el.classList.add('vz-on');
    if(desplaza&&st.seguir&&st.tocando){var red=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      var rc=el.getBoundingClientRect(),alto=window.innerHeight;
      if(rc.top<80||rc.bottom>alto-160){try{el.scrollIntoView({block:'center',behavior:red?'auto':'smooth'})}catch(e){el.scrollIntoView()}}}
  }
  function llenaVoces(){
    var sel=qs('#vz-sel');if(!sel)return;var vs=vocesEs().sort(function(a,b){return puntua(b)-puntua(a)});var act=eligeVoz();
    sel.innerHTML=vs.map(function(v){return '<option value="'+esc(v.voiceURI)+'"'+(act&&v.voiceURI===act.voiceURI?' selected':'')+'>'+esc(v.name)+' · '+esc(v.lang)+'</option>'}).join('')||'<option value="">(sin voces en español)</option>';
    qs('#vz-voces-nota').textContent=vs.length?'Las voces con «Natural» u «Online» suenan mejor. Se prefiere el español de España (es-ES).':'';
  }

  function abrir(p,autoplay){
    if(st.abierto&&st.clave===p.clave){if(autoplay)alternar();return}
    if(st.abierto)cerrar(true);
    creaUI();
    st.abierto=true;st.clave=p.clave;st.titulo=p.titulo;st.tipo=p.tipo;st.bloques=p.bloques;st.idx=0;st.frac=0;st.tocando=false;st.preparando=true;
    st.els=mapea(p.tipo,p.bloques,p.els);
    st.cum=[];st.total=0;p.bloques.forEach(function(b){st.cum.push(st.total);st.total+=b.x.length+1});
    document.body.classList.add('vz-abierto');ui.hidden=false;nota('');qs('#vz-voces').hidden=true;
    pinta();
    var cands=candidatas(p.clave);
    var listo=function(motor){
      if(!st.abierto||st.clave!==p.clave)return;
      st.motor=motor;st.preparando=false;
      var pos=posGuardada(p.clave);if(pos&&pos.i>0&&pos.i<p.bloques.length){motor.reanudar(pos);st.idx=pos.i;st.frac=pos.f||0}
      marca(st.idx,false);pinta();
      if(motor.tipo==='voz'){llenaVoces();var av=avisoVoz(eligeVoz());if(av)nota(av)}
      if(autoplay)motor.play();
    };
    var conVoz=function(){if(synth){listo(motorVoz())}else{st.preparando=false;st.motor=null;nota('Este navegador no permite la lectura en voz alta y no hay grabación disponible para este texto.');pinta()}};
    if(cands.length||VIVO_URL){
      /* se espera al manifiesto vivo solo si aún no ha llegado (un momento como mucho) */
      Promise.all([huella(vzTextoCanonico(p.bloques)),esperaVivo(cands.length?1200:2500)]).then(function(res){
        var h=res[0];var pista=h?candidatas(p.clave).filter(function(c){return c.huella===h})[0]:null;
        if(pista){listo(motorAudio(pista,function(){
          /* la grabación no carga: seguimos con la voz del navegador desde el mismo párrafo */
          var i=st.idx;if(st.motor)st.motor.destruir();st.motor=null;
          if(synth){var m=motorVoz();st.motor=m;m.ir(i);nota('No se ha podido cargar la grabación; se sigue con la voz del navegador.');if(st.tocando)m.play()}
          else nota('No se ha podido cargar la grabación.');
          pinta()}))}
        else conVoz();
      });
    }else conVoz();
    if(synth&&synth.addEventListener&&!abrir._voces){abrir._voces=true;synth.addEventListener('voiceschanged',function(){if(st.abierto&&st.motor&&st.motor.tipo==='voz'){llenaVoces();nota(avisoVoz(eligeVoz()))}})}
  }
  function cerrar(silencio){
    if(!st.abierto)return;
    if(st.motor){if(st.tocando)guardaPos(st.idx,(st.motor.tiempo()||{}).t||0,st.frac,true);st.motor.destruir()}
    st.motor=null;st.tocando=false;st.abierto=false;var clave=st.clave;st.clave=null;
    qsa('.vz-on').forEach(function(el){el.classList.remove('vz-on')});
    var teniaFoco=ui&&ui.contains(document.activeElement);
    if(ui){ui.hidden=true}document.body.classList.remove('vz-abierto');
    if(!silencio){pintaBoton();if(teniaFoco){var b=qsa('.vz-boton').filter(function(x){return x.dataset.vzClave===clave})[0];if(b)b.focus()}}
    return clave;
  }
  function alternar(){if(!st.motor)return;if(st.tocando)st.motor.pause();else st.motor.play()}
  function anterior(){if(!st.motor)return;st.motor.ir(Math.max(0,st.idx-1))}
  function siguiente(){if(!st.motor)return;if(st.idx+1>=st.bloques.length){fin();return}st.motor.ir(st.idx+1)}
  function fin(){
    if(st.motor){if(st.tocando)st.motor.pause();if(st.motor.tipo==='voz')st.motor.ir(0)}
    st.tocando=false;st.idx=0;st.frac=1;borraPos(st.clave);
    qsa('.vz-on').forEach(function(el){el.classList.remove('vz-on')});pinta();estado('Lectura terminada');
  }
  function cambiaVel(){var i=VELS.indexOf(st.vel);st.vel=VELS[(i+1)%VELS.length];store.set('vz_vel',st.vel);if(st.motor)st.motor.vel(st.vel);pinta()}

  /* ---------- botón «Escuchar…» en la cabecera ---------- */
  function ponBoton(p){
    var host=null,anc=null;
    if(p.tipo==='cap'){var art=qs('#article');if(!art)return;host=qs('.nv-acciones',art);anc=qs('h1',art)}
    else if(p.tipo==='pj'){var hero=qs('.pj-hero');if(!hero)return;host=qs('.nv-acciones',hero)||qs('.nv-acciones');anc=qs('h1',hero)}
    if(!host){if(!anc)return;host=document.createElement('div');host.className='vz-fila';anc.insertAdjacentElement('afterend',host)}
    if(qs('.vz-boton',host))return;
    var b=document.createElement('button');b.type='button';b.className='vz-boton';b.setAttribute('aria-controls','vz-player');
    b.dataset.vzClave=p.clave;b.dataset.vzTexto=p.boton;b.dataset.vzChars=p.bloques.reduce(function(n,x){return n+x.x.length},0);
    host.appendChild(b);pintaBoton();
  }

  /* ---------- eventos ---------- */
  document.addEventListener('click',function(e){
    var t=e.target.closest?e.target.closest('.vz-boton,[data-vz]'):null;if(!t)return;
    if(t.classList.contains('vz-boton')){var p=pistaDeRuta(route());if(p&&p.clave===t.dataset.vzClave)abrir(p,true);return}
    var k=t.dataset.vz;
    if(k==='play')alternar();else if(k==='ant')anterior();else if(k==='sig')siguiente();else if(k==='vel')cambiaVel();
    else if(k==='seguir'){st.seguir=!st.seguir;store.set('vz_seguir',st.seguir);pinta();if(st.seguir)marca(st.idx,true)}
    else if(k==='voces'){var pan=qs('#vz-voces');pan.hidden=!pan.hidden;t.setAttribute('aria-expanded',pan.hidden?'false':'true');if(!pan.hidden){llenaVoces();qs('#vz-sel').focus()}}
    else if(k==='cerrar'){cerrar();}
  });
  window.addEventListener('pagehide',function(){if(synth){try{synth.cancel()}catch(e){}}});
  window.addEventListener('beforeunload',function(){if(synth){try{synth.cancel()}catch(e){}}});
  if(synth){try{synth.getVoices()}catch(e){}}

  MOD.trasRender(function(r){
    var p=pistaDeRuta(r);
    if(st.abierto&&(!p||p.clave!==st.clave))cerrar(true);
    if(!p)return;
    if(!synth&&!candidatas(p.clave).length)return;
    ponBoton(p);
    if(st.abierto&&p.clave===st.clave){st.els=mapea(p.tipo,st.bloques);marca(st.idx,false)}
  });

  return {abrir:abrir,cerrar:cerrar,pista:pistaDeRuta,estado:function(){return st}};
})();
window.VZ=VZ;
