/**
 * AlertaEdu - Remitente Gmail para recuperación de contraseñas.
 * Configura en Project Settings > Script Properties:
 * ALERTAEDU_SHARED_SECRET=<secreto aleatorio (32+ caracteres)>
 * Implementar como Web App: Execute as Me; Who has access: Anyone.
 * No publiques este secreto en Github ni como parametro URL.
 */
function doPost(e) {
  try {
    const expected = PropertiesService.getScriptProperties().getProperty('ALERTAEDU_SHARED_SECRET');
    if (!expected || expected.length < 32) return respond_({ok:false});
    const body = JSON.parse(e && e.postData && e.postData.contents || '{}');
    if (!body || typeof body.secret !== 'string' || body.secret !== expected) return respond_({ok:false});
    const to = String(body.to || '').trim().toLowerCase();
    const subject = String(body.subject || '').trim();
    const message = String(body.body || '');
    // Sólo mensajes propios de AlertaEdu, no un servicio genérico de correo.
    if (!/^[a-z0-9.!#$%&'*+\/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,63}$/i.test(to) ||
        !/^AlertaEdu[ —-]/.test(subject) || subject.length > 160 ||
        !message || message.length > 12000) return respond_({ok:false});
    MailApp.sendEmail({to:to, subject:subject, body:message, name:'AlertaEdu'});
    return respond_({ok:true});
  } catch (err) {
    // No divulgar tokens de recuperación ni credenciales en la respuesta ni los registros.
    return respond_({ok:false});
  }
}
function respond_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
