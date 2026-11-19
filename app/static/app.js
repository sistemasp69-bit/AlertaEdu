'use strict';
let STUDENTS=[];let editing=null;
const $=id=>document.getElementById(id);
const escapeHTML=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const format=n=>Number(n).toFixed(1);
let CURRENT_USER=null;
let CSRF_TOKEN='';
const api=async(url,options={})=>{
  const method=(options.method||'GET').toUpperCase();
  const headers={'Content-Type':'application/json',...(options.headers||{})};
  if (!['GET','HEAD','OPTIONS'].includes(method)) headers['x-csrf-token']=CSRF_TOKEN;
  const r=await fetch(url,{...options,credentials:'same-origin',headers});
  let d=await r.json().catch(()=>({}));
  if(r.status===401){window.location.assign('/login');throw Error('Sesión caducada. Inicia sesión de nuevo.')}
  if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:`Error HTTP ${r.status}`);
  return d;
};
const badge=r=>`<span class="risk ${['Alto','Medio','Bajo'].includes(r)?r:'Sin'}">${escapeHTML(r)}</span>`;
function showPage(page){document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id===page));document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.page===page));const active=document.querySelector(`.nav[data-page="${page}"]`);$('breadcrumb').textContent=active?.textContent.trim()||page;window.scrollTo(0,0)}
document.querySelectorAll('.nav').forEach(x=>x.addEventListener('click',()=>showPage(x.dataset.page)));
document.querySelectorAll('[data-go]').forEach(x=>x.addEventListener('click',()=>showPage(x.dataset.go)));
function row(s,short=false){const first=`<td><strong>${escapeHTML(s.nombre)}</strong><br>${escapeHTML(s.id)}</td><td>${escapeHTML(s.carrera)}</td>`;return `<tr>${first}${short?`<td>${format(s.promedio)}</td><td>${badge(s.riesgo)}</td><td>${escapeHTML(s.estado)}</td>`:`<td>${s.semestre}°</td><td>${format(s.promedio)}</td><td>${format(s.asistencia)}%</td><td>${s.reprobadas}</td><td>${badge(s.riesgo)}</td><td>${escapeHTML(s.estado)}</td><td><button class="mini-btn" data-detail="${escapeHTML(s.id)}">Detalles</button>${CURRENT_USER?.role==='Administrador'?`<button class="mini-btn" data-edit="${escapeHTML(s.id)}">Editar</button><button class="mini-btn danger" data-delete="${escapeHTML(s.id)}">Eliminar</button>`:''}</td>`}</tr>`}
function render(){let high=STUDENTS.filter(s=>s.riesgo==='Alto').length,med=STUDENTS.filter(s=>s.riesgo==='Medio').length,low=STUDENTS.filter(s=>s.riesgo==='Bajo').length,total=STUDENTS.length;$('total').textContent=total;$('high').textContent=high;$('medium').textContent=med;$('followup').textContent=STUDENTS.filter(s=>s.estado==='En seguimiento').length;$('donut-total').textContent=total; $('leg-high').textContent=high;$('leg-medium').textContent=med;$('leg-low').textContent=low;const pct=n=>total?100*n/total:0;$('donut').style.background=`conic-gradient(#ed6780 0 ${pct(high)}%,#efb955 ${pct(high)}% ${pct(high+med)}%,#49b6a0 ${pct(high+med)}% ${pct(high+med+low)}%,#dfe5f1 ${pct(high+med+low)}% 100%)`;$('dash-table').innerHTML=STUDENTS.filter(s=>['Alto','Medio'].includes(s.riesgo)).map(s=>row(s,true)).join('')||'<tr><td colspan="5" class="no-data">No hay estudiantes prioritarios.</td></tr>';renderStudents();renderAlerts()}
function renderStudents(){const q=$('search').value.toLowerCase().trim(),r=$('risk-filter').value;const a=STUDENTS.filter(s=>(!r||s.riesgo===r)&&[s.id,s.nombre,s.carrera].some(x=>x.toLowerCase().includes(q)));$('students-table').innerHTML=a.map(s=>row(s)).join('')||'<tr><td colspan="9" class="no-data">No se encontraron estudiantes.</td></tr>';$('student-count').textContent=`Mostrando ${a.length} de ${STUDENTS.length} estudiantes · Registros en Supabase PostgreSQL`;document.querySelectorAll('[data-detail]').forEach(b=>b.onclick=()=>showStudent(b.dataset.detail));document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>openEditor(b.dataset.edit));document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>deleteStudent(b.dataset.delete))}
async function refresh(){try{const d=await api('/api/students');STUDENTS=d.items;render()}catch(err){$('total').textContent='Error';$('student-count').textContent=`No se pudo consultar la API: ${err.message}`}}
function openEditor(id=null){editing=id;const s=STUDENTS.find(x=>x.id===id);$('editor-title').textContent=s?'Editar estudiante':'Registrar estudiante';const f=$('student-form');f.reset();for(const k of ['id','nombre','carrera','semestre','promedio','asistencia'])f.elements[k].value=s?.[k]??'';f.elements.id.readOnly=!!s;f.elements.materias.value=(s?.materias||[]).map(m=>`${m.nombre} | ${m.nota}`).join('\n');$('editor-message').textContent='';$('student-editor').hidden=false;$('student-detail').hidden=true;$('student-editor').scrollIntoView({behavior:'smooth',block:'start'})}
$('new-student').onclick=()=>openEditor();$('cancel-editor').onclick=()=>{$('student-editor').hidden=true;editing=null};
function parseSubjects(text){return text.split(/\r?\n/).map(x=>x.trim()).filter(Boolean).map(line=>{const parts=line.split('|').map(x=>x.trim());if(parts.length!==2||!parts[0]||!parts[1])throw Error('Escribe las materias como "Nombre | Nota", una por línea.');const nota=Number(parts[1].replace(',','.'));if(!Number.isFinite(nota)||nota<0||nota>10)throw Error('Cada nota debe estar entre 0 y 10.');return {nombre:parts[0],nota}})}
$('student-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;try{const s={id:f.elements.id.value.trim(),nombre:f.elements.nombre.value.trim(),carrera:f.elements.carrera.value.trim(),semestre:Number(f.elements.semestre.value),promedio:Number(f.elements.promedio.value),asistencia:Number(f.elements.asistencia.value),materias:parseSubjects(f.elements.materias.value)};if(s.materias.some(m=>m.nota>=7))throw Error('Revisa las materias: una materia reprobada debe tener nota inferior a 7/10 (ajusta este criterio si corresponde a otra universidad).');await api(editing?`/api/students/${encodeURIComponent(editing)}`:'/api/students',{method:editing?'PUT':'POST',body:JSON.stringify(s)});$('student-editor').hidden=true;editing=null;await refresh();await showStudent(s.id)}catch(err){$('editor-message').textContent=err.message}};
async function deleteStudent(id){if(!confirm(`¿Eliminar a ${id} y sus intervenciones registradas?`))return;try{await api(`/api/students/${encodeURIComponent(id)}`,{method:'DELETE'});$('student-detail').hidden=true;await refresh()}catch(err){alert(err.message)}}
async function showStudent(id){try{const s=await api(`/api/students/${encodeURIComponent(id)}`);const data=await api(`/api/students/${encodeURIComponent(id)}/followups`);const evaluations=await api(`/api/students/${encodeURIComponent(id)}/evaluations`);$('student-editor').hidden=true;const subjects=s.materias.length?`<ul class="subject-list">${s.materias.map(m=>`<li>${escapeHTML(m.nombre)} — <strong>${format(m.nota)}/10</strong></li>`).join('')}</ul>`:'<p class="muted">Este estudiante no registra materias reprobadas.</p>';$('student-detail').innerHTML=`<div class="panel-head"><div><h2>Ficha académica · ${escapeHTML(s.nombre)}</h2><p>${escapeHTML(s.id)} · ${escapeHTML(s.carrera)}</p></div><button class="secondary" id="close-detail">Cerrar</button></div><div class="detail-meta"><span>Semestre: <b>${s.semestre}</b></span><span>Promedio: <b>${format(s.promedio)}/10</b></span><span>Asistencia: <b>${format(s.asistencia)}%</b></span><span>${badge(s.riesgo)}</span></div><h2>Materias reprobadas (${s.reprobadas})</h2>${subjects}<h2>Evaluaciones académicas guardadas (${evaluations.count})</h2>${evaluations.items.length?evaluations.items.map(x=>`<div class="note-entry"><strong>${escapeHTML(x.nivel)} · ${x.puntos}/${x.max_puntos} puntos</strong><p>Promedio: ${format(x.promedio)}/10 · Asistencia: ${format(x.asistencia)}% · Materias reprobadas: ${x.reprobadas}</p><small>${escapeHTML(x.fecha.slice(0,16).replace('T',' '))} UTC · Reglas orientativas, no IA</small></div>`).join(''):'<p class="muted">Sin evaluaciones guardadas.</p>'}<div class="inline-actions"><button class="secondary" id="evaluate-from-profile" type="button">Evaluar este estudiante</button></div><h2>Registrar intervención</h2><form id="followup-form" class="followup-grid"><select name="estado"><option ${s.estado==='Pendiente'?'selected':''}>Pendiente</option><option ${s.estado==='En seguimiento'?'selected':''}>En seguimiento</option><option ${s.estado==='Atendido'?'selected':''}>Atendido</option></select><input name="responsable" required placeholder="Responsable / tutor" maxlength="100"><textarea name="nota" required placeholder="Observación y acuerdos de seguimiento" maxlength="1000"></textarea><button class="primary" type="submit">Guardar seguimiento</button></form><p class="inline-note" id="followup-message" role="status"></p><h2>Historial de intervenciones</h2>${data.items.length?data.items.map(x=>`<div class="note-entry"><strong>${escapeHTML(x.responsable)}</strong><p>${escapeHTML(x.nota)}</p><small>${escapeHTML(x.fecha.slice(0,16).replace('T',' '))} UTC · ${escapeHTML(x.tipo)}</small></div>`).join(''):'<p class="muted">Sin intervenciones registradas.</p>'}`;$('student-detail').hidden=false;$('close-detail').onclick=()=>$('student-detail').hidden=true;$('evaluate-from-profile').onclick=()=>openEvaluation(s);$('followup-form').onsubmit=async e=>{e.preventDefault();const f=e.target;try{await api(`/api/students/${encodeURIComponent(id)}/followups`,{method:'POST',body:JSON.stringify({estado:f.elements.estado.value,responsable:f.elements.responsable.value.trim(),nota:f.elements.nota.value.trim()})});await refresh();await showStudent(id)}catch(err){$('followup-message').textContent=err.message}};$('student-detail').scrollIntoView({behavior:'smooth',block:'start'})}catch(err){alert(err.message)}}
function renderAlerts(){const a=STUDENTS.filter(s=>['Alto','Medio'].includes(s.riesgo));$('alert-list').innerHTML=a.map(s=>`<div class="alert-card"><div><strong>${escapeHTML(s.nombre)}</strong> · ${escapeHTML(s.id)} ${badge(s.riesgo)}<p>${escapeHTML(s.carrera)} · ${s.reprobadas} materia(s) reprobada(s) · ${format(s.asistencia)}% asistencia</p><p>Estado: ${escapeHTML(s.estado)}</p></div><button class="secondary" data-alert="${escapeHTML(s.id)}">Abrir seguimiento</button></div>`).join('')||'<p class="no-data">No hay alertas prioritarias.</p>';document.querySelectorAll('[data-alert]').forEach(b=>b.onclick=()=>{showPage('students');showStudent(b.dataset.alert)})}
$('search').oninput=renderStudents;$('risk-filter').onchange=renderStudents;
function exportCSV(){const cols=['id','nombre','carrera','semestre','promedio','asistencia','reprobadas','materias','riesgo','estado'];const rows=STUDENTS.map(s=>[s.id,s.nombre,s.carrera,s.semestre,s.promedio,s.asistencia,s.reprobadas,s.materias.map(m=>m.nombre+' ('+m.nota+')').join(' / '),s.riesgo,s.estado]);const contents='\ufeff'+[cols,...rows].map(a=>a.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(';')).join('\r\n');const url=URL.createObjectURL(new Blob([contents],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='alertaedu_estudiantes_prueba.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
$('export-students').onclick=exportCSV;$('export-report').onclick=exportCSV;
function openEvaluation(s){
    showPage('prediction');
    const fields=[...$('prediction-form').querySelectorAll('input')];
    fields[0].value=s.id;
    fields[1].value=s.promedio;
    fields[2].value=s.asistencia;
    fields[3].value=s.reprobadas;
    $('scenario-result').textContent='Datos precargados de la ficha. Al evaluar se guardará un registro nuevo en el historial.';
}
$('prediction-form').onsubmit=async e=>{
    e.preventDefault();
    const fields=[...e.target.querySelectorAll('input')];
    const sid=fields[0].value.trim();
    const payload={promedio:Number(fields[1].value),asistencia:Number(fields[2].value),reprobadas:Number(fields[3].value)};
    $('prediction-message').textContent='Evaluación con reglas académicas; no es una predicción de IA.';
    try{
        if(!sid)throw Error('Ingresa el código académico.');
        const d=await api(`/api/students/${encodeURIComponent(sid)}/evaluations`,{method:'POST',body:JSON.stringify(payload)});
        $('scenario-result').innerHTML=`<strong>Resultado guardado: ${escapeHTML(d.nivel_orientativo)}</strong><p>Puntuación: ${d.puntos}/${d.max_puntos} · Registro #${d.id}. Guardado en Supabase PostgreSQL el ${escapeHTML(d.fecha.slice(0,16).replace('T',' '))} UTC.</p><p>Este nivel es orientativo, NO una probabilidad ni una predicción de IA.</p><button type="button" class="secondary" id="view-saved-evaluation">Ver ficha e historial →</button>`;
        $('view-saved-evaluation').onclick=async()=>{showPage('students');await refresh();await showStudent(sid)};
        await refresh();
    }catch(err){$('scenario-result').textContent='No se guardó la evaluación: '+err.message}
};
$('check-status').onclick=async()=>{try{$('status-json').textContent=JSON.stringify(await api('/api/health'),null,2)}catch(err){$('status-json').textContent='API no disponible: '+err.message}};
// Se inicia refresh() después de confirmar la sesión.


// Importación Excel/CSV: previsualización y guardado transaccional en Supabase PostgreSQL.
let importFile = null;
let importPreviewApproved = false;
const importPicker = $('import-file');
const importConfirm = $('import-confirm');
function importFeedback(message, error=false) {
  const el = $('import-result');
  el.textContent = message;
  el.classList.toggle('import-error', error);
}
function resetImportPreview() {
  importFile = null;
  importPreviewApproved = false;
  importConfirm.disabled = true;
  $('import-validation').hidden = true;
}
importPicker.addEventListener('change', () => {
  resetImportPreview();
  const file = importPicker.files?.[0];
  importFeedback(file ? `Seleccionado: ${file.name}. Pulsa «Revisar archivo».` : 'Selecciona un archivo.');
});
async function sendImport(endpoint, file) {
  const form = new FormData();
  form.append('file', file, file.name);
  const response = await fetch(endpoint, {method:'POST', body:form,credentials:'same-origin',headers:{'x-csrf-token':CSRF_TOKEN}});
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (response.status === 401) {location.assign('/login');throw new Error('Inicia sesión de nuevo')};
  if (!response.ok) {
    const message = typeof data.detail === 'string' ? data.detail : `Error HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}
$('import-preview').onclick = async () => {
  resetImportPreview();
  const file = importPicker.files?.[0];
  if (!file) { importFeedback('Selecciona primero el Excel o CSV.', true); return; }
  $('import-preview').disabled = true;
  importFeedback('Revisando las columnas y validando estudiantes...');
  try {
    const result = await sendImport('/api/import/preview', file);
    importFile = file;
    $('import-validation').hidden = false;
    $('import-summary').innerHTML =
      `<span><b>${result.total}</b> filas</span><span><b>${result.nuevos}</b> nuevos</span><span><b>${result.existentes}</b> ya existen</span><span><b>${result.invalidos}</b> inválidos</span><span><b>${result.evaluacion_prevista?.Alto??0}</b> riesgo alto</span><span><b>${result.evaluacion_prevista?.Medio??0}</b> riesgo medio</span><span><b>${result.evaluacion_prevista?.Bajo??0}</b> riesgo bajo</span>`;
    const errors = result.errores || [];
    $('import-errors').innerHTML = errors.length ?
      `<div class="import-errors"><strong>Corrige el archivo antes de importar:</strong><ul>${errors.map(e=>`<li>Fila ${e.fila}: ${escapeHTML(e.error)}</li>`).join('')}</ul></div>` : '';
    $('import-table').innerHTML = (result.vista_previa || []).map(s=>
      `<tr><td>${s.fila}</td><td>${escapeHTML(s.codigo)}</td><td>${escapeHTML(s.nombre)}</td><td>${escapeHTML(s.carrera)}</td><td>${s.promedio}</td><td>${s.asistencia}%</td><td>${s.materias}</td><td>${badge(s.riesgo_orientativo)} · ${s.puntos}/9</td><td>${s.existente?'Ya existe':'Nuevo'}</td></tr>`
    ).join('') || '<tr><td colspan="9">No hay filas válidas</td></tr>';
    importPreviewApproved = Boolean(result.puede_importar);
    importConfirm.disabled = !importPreviewApproved;
    importFeedback(importPreviewApproved
      ? 'Vista previa lista. Al confirmar se guardarán los estudiantes y sus niveles de riesgo orientativos en Supabase PostgreSQL.'
      : 'La importación está bloqueada hasta corregir los errores del archivo.', !importPreviewApproved);
  } catch(err) {
    resetImportPreview();
    importFeedback(`No se pudo revisar el archivo: ${err.message}`, true);
  } finally { $('import-preview').disabled = false; }
};
importConfirm.onclick = async () => {
  if (!importPreviewApproved || !importFile) return;
  importConfirm.disabled = true;
  importFeedback('Guardando estudiantes y calculando riesgos orientativos en Supabase PostgreSQL...');
  try {
    const mode = $('import-duplicates').value;
    const result = await sendImport(`/api/import/students?on_duplicate=${encodeURIComponent(mode)}`, importFile);
    importFeedback(`Guardado: ${result.creados} nuevos, ${result.actualizados} actualizados, ${result.omitidos} omitidos. Evaluados automáticamente: ${result.evaluados_automaticamente} (Alto: ${result.por_nivel.Alto}, Medio: ${result.por_nivel.Medio}, Bajo: ${result.por_nivel.Bajo}). Clasificación orientativa por reglas, no IA.`);
    $('import-validation').hidden = true;
    importPreviewApproved = false;
    importFile = null;
    importPicker.value = '';
    await refresh();
    $('students-table').scrollIntoView({behavior:'smooth', block:'nearest'});
  } catch(err) {
    importFeedback(`No se guardó nada: ${err.message}`, true);
    importConfirm.disabled = false;
  }
};

// Los estudiantes importados antes de esta actualización también pueden evaluarse sin duplicar importaciones.
$('auto-evaluate-pending').onclick = async () => {
  const button=$('auto-evaluate-pending'), output=$('auto-evaluation-result');
  button.disabled=true;
  output.textContent='Calculando y guardando los riesgos pendientes...';
  try {
    const result=await api('/api/evaluations/auto',{method:'POST'});
    output.textContent=`Evaluados y guardados: ${result.evaluados}. Alto: ${result.por_nivel.Alto}; Medio: ${result.por_nivel.Medio}; Bajo: ${result.por_nivel.Bajo}. Clasificación por reglas, no IA.`;
    await refresh();
  } catch(err) {
    output.textContent='No se pudo guardar la evaluación: '+err.message;
  } finally {button.disabled=false;}
};



// Autenticación y administración de cuentas (el backend valida los permisos).
async function loadUsers(){
  if(CURRENT_USER?.role!=='Administrador')return;
  const data=await api('/api/users');
  $('users-table').innerHTML=data.items.map(u=>`<tr><td>${escapeHTML(u.username)}</td><td>${escapeHTML(u.role)}</td><td>${u.active?'Activa':'Desactivada'}</td></tr>`).join('')||'<tr><td colspan="3">Sin usuarios</td></tr>';
}
$('create-user-form').onsubmit=async e=>{
  e.preventDefault();const form=e.target,msg=$('create-user-message');msg.textContent='';
  try{const payload={username:form.elements.username.value.trim(),password:form.elements.password.value,role:form.elements.role.value};
      await api('/api/users',{method:'POST',body:JSON.stringify(payload)});
      msg.textContent='Cuenta creada. Comparte las credenciales por un canal seguro.';form.reset();await loadUsers();
  }catch(err){msg.textContent=err.message}
};
$('change-password-form').onsubmit=async e=>{
  e.preventDefault();const form=e.target,msg=$('password-message');msg.textContent='';
  try{await api('/api/auth/change-password',{method:'POST',body:JSON.stringify({current_password:form.elements.current_password.value,new_password:form.elements.new_password.value})});
      msg.textContent='Contraseña actualizada. Volviendo al inicio de sesión...';form.reset();location.assign('/login');
  }catch(err){msg.textContent=err.message}
};
$('logout').onclick=async()=>{try{await api('/api/auth/logout',{method:'POST'})}finally{location.assign('/login')}};
$('users-nav').addEventListener('click',()=>{loadUsers().catch(err=>$('users-table').textContent=err.message)});
async function initializeAuth(){
  try{
    CURRENT_USER=await api('/api/auth/me');
    CSRF_TOKEN=CURRENT_USER.csrf_token;
    $('user-role').textContent=CURRENT_USER.role;
    $('user-name').textContent=CURRENT_USER.username;
    $('user-avatar').textContent=CURRENT_USER.username.slice(0,2).toUpperCase();
    $('account-identity').textContent=`${CURRENT_USER.username} · ${CURRENT_USER.role}`;
    $('users-nav').hidden=CURRENT_USER.role!=='Administrador';
    const admin=CURRENT_USER.role==='Administrador';
    const canEvaluate=admin||CURRENT_USER.role==='Tutor';
    $('new-student').hidden=!admin;
    $('excel-importer').hidden=!admin;
    $('auto-evaluate-pending').disabled=!canEvaluate;
    // La creación/importación/edición se autoriza también del lado de FastAPI.
    if(!canEvaluate){document.querySelectorAll('.nav[data-page="prediction"]').forEach(el=>el.hidden=true)}
    await refresh();
  }catch(err){if(!location.pathname.includes('/login'))location.assign('/login')}
}
initializeAuth();


// RF-04: predicción ML separada de la clasificación por reglas.
async function refreshModelStatus(){
  const statusEl = $('ml-status'), btn = $('ml-predict-btn');
  if(!statusEl || !btn) return;
  try {
    const estado = await api('/api/ia/estado');
    btn.disabled = !estado.disponible;
    statusEl.textContent = estado.disponible
      ? `Modelo ${estado.version} activo. F1: ${estado.metricas.f1_desercion}; Recall: ${estado.metricas.recall_desercion}. Estimaciones sujetas a validación académica.`
      : `IA aún no disponible: ${estado.detalle} La clasificación automática por reglas sigue funcionando.`;
  } catch(err) {
    btn.disabled = true;statusEl.textContent='No se pudo consultar el estado del modelo: '+err.message;
  }
}
$('ml-predict-btn').onclick = async ()=>{
  const sid=$('prediction-form').querySelector('input').value.trim();
  const out=$('ml-prediction-result');
  if(!sid){out.textContent='Ingresa primero un código académico existente.';return;}
  out.textContent='Calculando predicción con modelo ML...';
  try {
    const p=await api('/api/ia/predecir/'+encodeURIComponent(sid),{method:'POST'});
    out.textContent=`IA guardada para ${sid}: ${(p.probabilidad_desercion*100).toFixed(1)}% (índice ${p.probabilidad_desercion.toFixed(4)}), nivel ${p.nivel_ia}, modelo ${p.modelo_version}. Estimación, no certeza.`;
  } catch(err) {out.textContent='No se generó predicción ML: '+err.message;}
};
refreshModelStatus();

// [RF04-UCI-LAB-BEGIN]
// Panel experimental: no crea ni modifica fichas académicas en Supabase PostgreSQL.
(async function initUCILaboratory(){
  const msg=$('uci-lab-status'), btn=$('uci-lab-predict'), input=$('uci-test-case'), result=$('uci-lab-result');
  if(!msg || !btn || !input || !result) return;
  try {
    const state=await api('/api/ia/uci/estado');
    if(!state.disponible){msg.textContent='No disponible: '+state.detalle;return;}
    btn.disabled=false;
    input.max=String(state.casos_evaluacion);
    const m=state.metricas;
    msg.textContent=`Modelo experimental disponible · ${state.casos_evaluacion} casos reservados · F1 ${(100*m.f1_dropout).toFixed(1)}% · Recall ${(100*m.recall_dropout).toFixed(1)}%. No se aplica a los expedientes de AlertaEdu.`;
  } catch(err) { msg.textContent='No se pudo cargar el laboratorio: '+err.message; }
  btn.onclick=async()=>{
    const caso=Number(input.value);
    if(!Number.isInteger(caso) || caso<1 || caso>Number(input.max)){result.textContent=`Ingresa un caso del 1 al ${input.max}.`;return;}
    btn.disabled=true;result.textContent='Calculando la probabilidad con Random Forest...';
    try{
      const r=await api('/api/ia/uci/predecir',{method:'POST',body:JSON.stringify({caso})});
      result.innerHTML=`<strong>Caso histórico #${r.caso}</strong><p>Probabilidad experimental de abandono: <b>${(100*r.probabilidad_desercion).toFixed(1)}%</b> (índice ${r.probabilidad_desercion.toFixed(4)})</p><p>Predicción del modelo: <b>${escapeHTML(r.prediccion)}</b> · Resultado histórico: <b>${escapeHTML(r.resultado_historico)}</b></p><p>${r.coincide?'Coincidió con el resultado histórico.':'No coincidió con el resultado histórico.'}</p><small>${escapeHTML(r.advertencia)}</small>`;
    }catch(err){result.textContent='No se pudo predecir: '+err.message;}
    finally{btn.disabled=false;}
  };
})();
// [RF04-UCI-LAB-END]


// [RF05-RF08-BEGIN]
async function loadRiskSettings(){
  const form=$('risk-settings-form');if(!form || CURRENT_USER?.role!=='Administrador')return;
  try{
    const s=await api('/api/risk/settings');
    for(const key of ['medium_points','high_points','notify_points'])form.elements[key].value=s[key];
    $('risk-settings-message').textContent='Umbrales actuales cargados de Supabase PostgreSQL. Sin reclasificación retroactiva.';
  }catch(err){$('risk-settings-message').textContent='No se pudo cargar la configuración: '+err.message;}
}
$('risk-settings-form')?.addEventListener('submit',async e=>{
  e.preventDefault();const f=e.currentTarget,out=$('risk-settings-message');
  const payload={medium_points:Number(f.elements.medium_points.value),high_points:Number(f.elements.high_points.value),notify_points:Number(f.elements.notify_points.value)};
  try{
    await api('/api/risk/settings',{method:'PUT',body:JSON.stringify(payload)});
    out.textContent='Guardado. Los umbrales se aplicarán a evaluaciones nuevas; no se ha modificado ninguna ficha histórica.';
  }catch(err){out.textContent='No se guardó: '+err.message;}
});
async function loadAutoAlerts(){
  const panel=$('rf-auto-alert-panel');if(!panel || !CURRENT_USER)return;
  if(!['Administrador','Tutor'].includes(CURRENT_USER.role)){panel.hidden=true;return;}
  panel.hidden=false;
  try{
    const d=await api('/api/alerts?estado='+encodeURIComponent($('auto-alert-filter').value)+'&limit=100');
    const counts=d.resumen||{};
    $('auto-alert-summary').textContent=`Avisos totales: ${Object.values(counts).reduce((a,b)=>a+b,0)} · Nuevos: ${counts.Nueva||0} · En seguimiento: ${counts['En seguimiento']||0} · Cerrados: ${counts.Cerrada||0}. Mostrando ${d.items.length} de ${d.total} según el filtro.`;
    $('auto-alert-records').innerHTML=d.items.map(a=>{
      const states=['Nueva','En seguimiento','Cerrada'];
      return `<div class="rf-alert-entry"><div class="rf-alert-info"><strong>${escapeHTML(a.nombre)} · ${escapeHTML(a.student_id)}</strong> ${badge(a.new_level)}
      <p>${escapeHTML(a.reason)} · Antes ${escapeHTML(a.old_level)} (${a.previous_points}/9), después ${escapeHTML(a.new_level)} (${a.new_points}/9)</p><small>${escapeHTML(a.created_at.slice(0,16).replace('T',' '))} UTC · Notificación interna por reglas, no IA</small></div>
      <div class="rf-alert-actions"><label>Estado<select data-rf-alert-state="${a.id}">${states.map(s=>`<option ${s===a.estado?'selected':''}>${s}</option>`).join('')}</select></label>
      <label>Usuario tutor o administrador<input data-rf-alert-owner="${a.id}" maxlength="40" value="${escapeHTML(a.responsable)}" placeholder="Ej. tutor01"></label>
      <button class="secondary" data-rf-alert-save="${a.id}">Guardar</button>
      <button class="secondary" data-rf-alert-history="${a.id}">Historial</button></div><div class="rf-alert-event" id="rf-alert-event-${a.id}"></div></div>`;
    }).join('')||'<p class="no-data">Todavía no hay avisos nuevos para este filtro. Se generarán cuando el riesgo empeore en una evaluación posterior.</p>';
    document.querySelectorAll('[data-rf-alert-save]').forEach(btn=>btn.onclick=async()=>{
      const id=btn.dataset.rfAlertSave, out=$('rf-alert-event-'+id);
      try{
        const estado=document.querySelector(`[data-rf-alert-state="${id}"]`).value;
        const responsable=document.querySelector(`[data-rf-alert-owner="${id}"]`).value.trim();
        await api('/api/alerts/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify({estado,responsable})});
        await loadAutoAlerts();
      }catch(err){out.textContent='No se guardó: '+err.message;}
    });
    document.querySelectorAll('[data-rf-alert-history]').forEach(btn=>btn.onclick=async()=>{
      const id=btn.dataset.rfAlertHistory, out=$('rf-alert-event-'+id);
      try{const d=await api('/api/alerts/'+encodeURIComponent(id)+'/history');
        out.textContent=d.items.map(e=>`${e.created_at.slice(0,16)} UTC · ${e.actor} · ${e.action}: ${e.detail}`).join(' | ')||'Sin eventos';
      }catch(err){out.textContent=err.message;}
    });
  }catch(err){$('auto-alert-summary').textContent='No se pudieron consultar las alertas: '+err.message;}
}
document.querySelector('.nav[data-page="alerts"]')?.addEventListener('click',loadAutoAlerts);
$('refresh-auto-alerts')?.addEventListener('click',loadAutoAlerts);
$('auto-alert-filter')?.addEventListener('change',loadAutoAlerts);
$('users-nav')?.addEventListener('click',loadRiskSettings);
// [RF05-RF08-END]


// [RF06-RF07-BEGIN]
(function initExplainabilityAndVersions(){
  const explainBtn=$('rf06-explain'), explainOut=$('rf06-result');
  const historyBtn=$('rf07-versions'), historyOut=$('rf07-result');
  const input=$('uci-test-case');
  if(!explainBtn || !historyBtn || !input) return;
  explainBtn.addEventListener('click', async ()=>{
    const caso=Number(input.value);
    if(!Number.isInteger(caso) || caso<1 || caso>Number(input.max || 100000)){
      explainOut.textContent='Indica un caso UCI válido antes de explicar.';return;
    }
    explainBtn.disabled=true;explainOut.textContent='Calculando valores SHAP del caso histórico...';
    try{
      const r=await api('/api/ia/uci/explicar?caso='+encodeURIComponent(caso));
      const rows=r.factores.map(f=>{
        const pct=Math.abs(Number(f.aporte)*100).toFixed(2);
        return `<li><b>${escapeHTML(f.nombre)}</b>: ${f.direccion==='aumenta'?'Aumenta':f.direccion==='reduce'?'Reduce':'Neutro'} ${pct} puntos porcentuales · valor ${Number(f.valor).toFixed(2)}</li>`;
      }).join('');
      explainOut.innerHTML=`<strong>Explicación del caso #${r.caso}</strong><p>Predicción experimental ${(100*r.probabilidad_desercion).toFixed(1)}% · Referencia SHAP ${(100*r.valor_base).toFixed(1)}%</p><ul>${rows}</ul><small>${escapeHTML(r.advertencia)}</small>`;
    }catch(err){explainOut.textContent='No se pudo explicar: '+err.message;}
    finally{explainBtn.disabled=false;}
  });
  historyBtn.addEventListener('click',async ()=>{
    historyBtn.disabled=true;historyOut.textContent='Consultando versiones experimentales...';
    try{
      const data=await api('/api/ia/uci/versiones');
      if(!data.items.length){historyOut.textContent='Aún no hay versiones. Ejecuta python REENTRENAR_RF07.py desde la carpeta AlertaEdu.';return;}
      historyOut.innerHTML='<strong>Versiones almacenadas: '+data.total_mostrado+'</strong><ul>'+data.items.map(v=>
        `<li><b>${escapeHTML(v.version)}</b> · F1 ${(100*v.f1_dropout).toFixed(1)}% · Recall ${(100*v.recall_dropout).toFixed(1)}% · ${escapeHTML(v.estado)}</li>`
      ).join('')+'</ul><small>Solo laboratorio UCI, no despliegue institucional.</small>';
    }catch(err){historyOut.textContent='No se pudo consultar el historial: '+err.message;}
    finally{historyBtn.disabled=false;}
  });
})();
// [RF06-RF07-END]

// [RF10-RF13-BEGIN]
(function initExtraReports(){
  const value=id=>document.getElementById(id);
  const title=(s)=>escapeHTML(s??'');
  async function effect(){
    const out=value('rf10-output');if(!out)return;
    if(!['Administrador','Tutor'].includes(CURRENT_USER?.role)){
      out.textContent='Consulta individual disponible solo para Administrador y Tutor.';return;}
    out.textContent='Consultando seguimiento...';
    try{
      const result=await api('/api/seguimiento/rf10/efectividad?limit=100');
      const r=result.resumen_mostrado;
      let msg=`<p>Intervenciones: ${result.total_intervenciones}. Mostradas: ${result.mostradas}. Mejoró: ${r.mejoro}; Empeoró: ${r.empeoro}; Sin cambio: ${r.sin_cambio}; Sin comparación: ${r.sin_comparacion}.</p>`;
      if(result.items.length){
        msg+='<div class="rf-scroller"><table><thead><tr><th>Estudiante</th><th>Seguimiento</th><th>Antes</th><th>Después</th><th>Cambio</th></tr></thead><tbody>'+
        result.items.slice(0,100).map(i=>`<tr><td>${title(i.nombre)}<br>${title(i.codigo)}</td><td>${title(i.tipo)}<br>${title(i.fecha_intervencion.slice(0,10))}</td><td>${i.antes?`${title(i.antes.nivel)} (${i.antes.puntos}/9)`:'Sin medición'}</td><td>${i.despues?`${title(i.despues.nivel)} (${i.despues.puntos}/9)`:'Sin medición'}</td><td>${title(i.resultado)}${i.otras_intervenciones_antes_de_evaluacion?' · otras intervenciones':''}</td></tr>`).join('')+'</tbody></table></div>';
      }
      out.innerHTML=msg+'<p class="muted">'+title(result.aviso)+'</p>';
    }catch(err){out.textContent='No se pudo consultar: '+err.message;}
  }
  async function segments(){
    const out=value('rf11-output');if(!out)return;
    out.textContent='Consultando segmentos...';
    try{
      const data=await api('/api/seguimiento/rf11/segmentos');
      out.innerHTML=`<p>Estudiantes: ${data.total_estudiantes}. Sin tasas históricas de retención verificables.</p><div class="rf-scroller"><table><thead><tr><th>Carrera</th><th>Total</th><th>Alto</th><th>Medio</th><th>Bajo</th><th>Sin evaluar</th></tr></thead><tbody>`+
      data.por_carrera.map(i=>`<tr><td>${title(i.carrera)}</td><td>${i.total}</td><td>${i.alto}</td><td>${i.medio}</td><td>${i.bajo}</td><td>${i.sin_evaluar}</td></tr>`).join('')+
      '</tbody></table></div><p class="muted">'+title(data.aviso)+'</p>';
    }catch(err){out.textContent='No se pudo consultar: '+err.message;}
  }
  function query(){
    const form=value('rf12-form');const params=new URLSearchParams();
    if(!form)return params;
    new FormData(form).forEach((v,k)=>{const s=String(v).trim();if(s)params.set(k,s);});
    return params;
  }
  async function filters(){
    const out=value('rf12-output');if(!out)return;
    if(!['Administrador','Tutor'].includes(CURRENT_USER?.role)){
      out.textContent='Los listados identificables requieren Administrador o Tutor.';return;}
    out.textContent='Filtrando en Supabase PostgreSQL...';
    try{
      const params=query();params.set('limit','100');
      const data=await api('/api/seguimiento/rf12/busqueda?'+params.toString());
      out.innerHTML=`<p>Coincidencias: ${data.total}. Mostrando ${data.items.length}; máximo 100 por vista. Los archivos exportados incluyen todos los resultados hasta 20.000.</p>`+
       '<div class="rf-scroller"><table><thead><tr><th>Código</th><th>Estudiante</th><th>Carrera</th><th>Sem.</th><th>Promedio</th><th>Asistencia</th><th>Riesgo</th><th>Estado</th></tr></thead><tbody>'+
       data.items.map(s=>`<tr><td>${title(s.id)}</td><td>${title(s.nombre)}</td><td>${title(s.carrera)}</td><td>${s.semestre}</td><td>${Number(s.promedio).toFixed(1)}</td><td>${Number(s.asistencia).toFixed(1)}%</td><td>${title(s.riesgo)}</td><td>${title(s.estado)}</td></tr>`).join('')+'</tbody></table></div>';
    }catch(err){out.textContent='No se pudo filtrar: '+err.message;}
  }
  value('rf10-refresh')?.addEventListener('click',effect);
  value('rf11-refresh')?.addEventListener('click',segments);
  value('rf12-form')?.addEventListener('submit',e=>{e.preventDefault();filters();});
  ['csv','xlsx','pdf'].forEach(format=>value('rf13-'+format)?.addEventListener('click',async()=>{
    const out=value('rf12-output'), btn=value('rf13-'+format);
    if(!['Administrador','Tutor'].includes(CURRENT_USER?.role)){
      out.textContent='Sin permisos para exportar expedientes individuales.';return;}
    const p=query();p.set('formato',format);btn.disabled=true;
    try{
      const r=await fetch('/api/seguimiento/rf13/exportar?'+p.toString(),{credentials:'same-origin'});
      if(!r.ok){const d=await r.json().catch(()=>({}));throw Error(d.detail||`HTTP ${r.status}`);}
      const blob=await r.blob(), url=URL.createObjectURL(blob);
      const a=document.createElement('a');a.href=url;a.download='AlertaEdu_Reporte.'+format;
      document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);
      out.textContent='Se preparó la descarga '+format.toUpperCase()+'. Se aplicaron los filtros y permisos del usuario.';
    }catch(err){out.textContent='No se pudo exportar: '+err.message;}
    finally{btn.disabled=false;}
  }));
})();
// [RF10-RF13-END]

// [ALERTAEDU-GMAIL-BEGIN]
(function initGmailRecoverySettings(){
  const form=$('gmail-register-form'),state=$('gmail-current-status'),message=$('gmail-register-message');
  if(!form)return;
  async function load(){
    try{
      const d=await api('/api/auth/email/mine');
      state.textContent=d.verified_email?'Gmail verificado: '+d.verified_email:'Todavía no has confirmado un Gmail de recuperación.';
      if(!d.configured)state.textContent+=' El servidor no tiene configurado el envío de Gmail.';
    }catch(err){state.textContent='No se pudo consultar Gmail: '+err.message;}
  }
  form.addEventListener('submit',async e=>{
    e.preventDefault();message.textContent='Enviando correo...';
    const submit=form.querySelector('button[type="submit"]');submit.disabled=true;
    try{
      const res=await api('/api/auth/email/register',{method:'POST',body:JSON.stringify({email:form.elements.email.value.trim(),current_password:form.elements.current_password.value})});
      message.textContent=res.message;form.elements.current_password.value='';await load();
    }catch(err){message.textContent='No se envió: '+err.message;}
    finally{submit.disabled=false;}
  });
  document.querySelector('.nav[data-page="account"]')?.addEventListener('click',()=>load());
  load();
})();
// [ALERTAEDU-GMAIL-END]
