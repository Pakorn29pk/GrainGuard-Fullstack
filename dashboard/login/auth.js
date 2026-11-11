/* GrainGuard account client. Authorization is enforced by the Hub, never by this page. */
(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));
  const channel = document.body.dataset.channel === 'online' ? 'online' : 'local';
  const rememberKey = 'gg-login-identifier';
  // Discard identifiers retained by the earlier UI walkthrough, not user input.
  try { localStorage.removeItem('gg-login-demo-v2-identifier'); } catch (_) {}
  const languageKey = 'gg-language';
  const text = (value) => String(value || '').trim().normalize('NFKC');
  const copy = {
    th: {
      login:'เข้าสู่ระบบ', identifier:'ชื่อผู้ใช้หรือเบอร์โทรศัพท์', identifierPlaceholder:'ชื่อผู้ใช้ / เบอร์โทรศัพท์',
      password:'รหัสผ่าน', passwordPlaceholder:'กรอกรหัสผ่าน', remember:'จดจำชื่อผู้ใช้', forgotLink:'ลืมรหัสผ่าน?',
      noAccount:'ยังไม่มีบัญชี?', createAccount:'สร้างบัญชี', fullName:'ชื่อ–นามสกุล', phone:'เบอร์โทรศัพท์',
      phoneHint:'1 เบอร์ ต่อ 1 บัญชี', role:'บทบาทหน้าที่', entrepreneur:'ผู้ประกอบการ', employee:'พนักงาน',
      username:'ชื่อผู้ใช้', usernameHint:'4–32 ตัว เริ่มด้วย a–z ใช้ตัวเลข . _ - ได้',
      newPasswordPlaceholder:'อย่างน้อย 8 ตัวอักษร', passwordHint:'อย่างน้อย 8 ตัวอักษร', confirmPassword:'ยืนยันรหัสผ่าน',
      forgotTitle:'ลืมรหัสผ่าน', recovery:'ติดต่อผู้ดูแลโรงสีเพื่อยืนยันตัวตนและตั้งรหัสผ่านใหม่',
      show:'แสดง', hide:'ซ่อน', showPassword:'แสดงรหัสผ่าน', hidePassword:'ซ่อนรหัสผ่าน',
      showConfirm:'แสดงรหัสผ่านยืนยัน', hideConfirm:'ซ่อนรหัสผ่านยืนยัน',
      switchLanguage:'เปลี่ยนภาษาเป็นอังกฤษ', logoAlt:'โลโก้ GrainGuard', busy:'กำลังดำเนินการ…',
      identifierRequired:'กรอกชื่อผู้ใช้หรือเบอร์โทรศัพท์', passwordRequired:'กรอกรหัสผ่าน',
      fullNameInvalid:'กรอกชื่อและนามสกุล โดยเว้นวรรคระหว่างกัน', phoneInvalid:'กรอกเบอร์ไทย 9–10 หลัก',
      roleRequired:'เลือกบทบาทหน้าที่', usernameInvalid:'ใช้ 4–32 ตัว เริ่มด้วย a–z ใช้ตัวเลข . _ - ได้',
      passwordShort:'รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร', passwordLong:'รหัสผ่านต้องไม่เกิน 128 ตัวอักษร',
      passwordRange:'รหัสผ่านต้องมี 8–128 ตัวอักษร', passwordMismatch:'รหัสผ่านทั้งสองช่องไม่ตรงกัน',
      invalidLogin:'ชื่อผู้ใช้ เบอร์โทร หรือรหัสผ่านไม่ถูกต้อง', duplicatePhone:'เบอร์นี้มีบัญชีแล้ว',
      duplicateUsername:'ชื่อผู้ใช้นี้มีแล้ว', created:'สร้างบัญชีแล้ว เข้าสู่ระบบได้เลย',
      connectionError:'เชื่อมต่อไม่ได้ กรุณาลองอีกครั้ง', serverError:'ทำรายการไม่ได้ กรุณาลองอีกครั้ง',
      requestInvalid:'รูปแบบข้อมูลไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง', notAllowed:'ไม่สามารถทำรายการนี้ได้',
      joinTitle:'เชื่อมต่อโรงสี', joinCopy:'ใส่ Code จากผู้ดูแลที่โรงงานเพื่อขอสิทธิ์ดูข้อมูล', hubCode:'Code โรงสี', requestAccess:'ขอสิทธิ์เข้าดู',
      codeRequired:'กรอก Code โรงสี', codeInvalid:'Code ไม่ถูกต้อง หรือถูกเปลี่ยนแล้ว', pendingTitle:'รออนุมัติ', pendingCopy:'ส่งคำขอแล้ว กรุณารอผู้ดูแลที่โรงงานอนุมัติ',
      unlinkedTitle:'เชื่อมต่อโรงสี', unlinkedCopy:'ใช้ Code จากผู้ดูแลที่โรงงานเพื่อขอเข้าดูข้อมูล', revokedTitle:'สิทธิ์ถูกถอน', revokedCopy:'ติดต่อผู้ดูแลที่โรงงานเพื่อขอสิทธิ์อีกครั้ง',
      checkStatus:'ตรวจสอบสถานะ', logout:'ออกจากระบบ', rateLimited:'ทำรายการบ่อยเกินไป กรุณารอสักครู่', localRestricted:'สร้างบัญชี Local ได้บน Pi4 ที่โรงงานเท่านั้น',
      localAlreadyCreated:'มีบัญชี Local แล้ว กรุณาเข้าสู่ระบบ', duplicateAccount:'ชื่อผู้ใช้หรือเบอร์โทรนี้มีบัญชีแล้ว', noChange:'ยังรอผู้ดูแลอนุมัติ',

    },
    en: {
      login:'Log in', identifier:'Username or phone number', identifierPlaceholder:'Username / phone number',
      password:'Password', passwordPlaceholder:'Enter your password', remember:'Remember username', forgotLink:'Forgot password?',
      noAccount:'New here?', createAccount:'Create account', fullName:'Full name', phone:'Phone number',
      phoneHint:'One phone number per account', role:'Role', entrepreneur:'Business owner', employee:'Employee',
      username:'Username', usernameHint:'4–32 characters. Start with a–z; numbers . _ - allowed.',
      newPasswordPlaceholder:'At least 8 characters', passwordHint:'At least 8 characters', confirmPassword:'Confirm password',
      forgotTitle:'Forgot password', recovery:'Contact your mill administrator to verify your identity and reset your password.',
      show:'Show', hide:'Hide', showPassword:'Show password', hidePassword:'Hide password',
      showConfirm:'Show confirmation password', hideConfirm:'Hide confirmation password',
      switchLanguage:'Switch language to Thai', logoAlt:'GrainGuard logo', busy:'Please wait…',
      identifierRequired:'Enter your username or phone number.', passwordRequired:'Enter your password.',
      fullNameInvalid:'Enter your first and last name, separated by a space.', phoneInvalid:'Enter a 9–10 digit Thai phone number.',
      roleRequired:'Select your role.', usernameInvalid:'Use 4–32 characters, starting with a–z. Numbers . _ - are allowed.',
      passwordShort:'Use at least 8 characters.', passwordLong:'Use no more than 128 characters.',
      passwordRange:'Use 8–128 characters.', passwordMismatch:'The passwords do not match.',
      invalidLogin:'The username, phone number or password is incorrect.', duplicatePhone:'This phone number already has an account.',
      duplicateUsername:'This username is already in use.', created:'Account created. You can now log in.',
      connectionError:'Unable to connect. Please try again.', serverError:'Unable to complete your request. Please try again.',
      requestInvalid:'Check your details and try again.', notAllowed:'This action is not available.',
      joinTitle:'Connect to your mill', joinCopy:'Enter the Code from your mill administrator to request monitoring access.', hubCode:'Mill Code', requestAccess:'Request access',
      codeRequired:'Enter your mill Code.', codeInvalid:'The Code is incorrect or has been changed.', pendingTitle:'Awaiting approval', pendingCopy:'Request sent. Your mill administrator must approve your access.',
      unlinkedTitle:'Connect to your mill', unlinkedCopy:'Use the Code from your mill administrator to request access.', revokedTitle:'Access revoked', revokedCopy:'Contact your mill administrator to request access again.',
      checkStatus:'Check status', logout:'Log out', rateLimited:'Too many attempts. Please wait and try again.', localRestricted:'Create a Local account on the factory Pi4 only.',
      localAlreadyCreated:'A Local account already exists. Please log in.', duplicateAccount:'This username or phone number already has an account.', noChange:'Still awaiting administrator approval.',

    },
  };
  let language = 'th';
  let busy = false;
  let messageState = null;
  const errors = new Map();
  try {
    const saved = localStorage.getItem(languageKey) || localStorage.getItem('gg-login-demo-v2-language');
    if (saved === 'en') language = 'en';
  } catch (_) {}
  let session = null;
  let pollTimer = null;
  let statusRequest = null;
  let joiningError = null;
  let accessStatusKey = null;
  const t = (key) => copy[language][key] || copy.th[key] || copy[language].serverError;

  function normalizePhone(value) {
    let phone = text(value).replace(/[๐-๙]/g, (digit) => String(digit.charCodeAt(0) - 0x0e50)).replace(/[\s()\-]/g, '');
    if (phone.startsWith('+66')) phone = `0${phone.slice(3)}`;
    else if (phone.startsWith('0066')) phone = `0${phone.slice(4)}`;
    else if (/^66\d{8,9}$/.test(phone)) phone = `0${phone.slice(2)}`;
    return phone;
  }
  function setDescription(input, id, add) {
    const ids = new Set((input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
    if (add) ids.add(id); else ids.delete(id);
    if (ids.size) input.setAttribute('aria-describedby', Array.from(ids).join(' '));
    else input.removeAttribute('aria-describedby');
  }
  function clearField(input) {
    if (!input) return;
    errors.delete(input.id);
    input.removeAttribute('aria-invalid');
    const id = `${input.id}-error`;
    const output = document.getElementById(id);
    if (output) { output.hidden = true; output.textContent = ''; }
    setDescription(input, id, false);
  }
  function clearErrors() {
    messageState = null;
    const message = $('#form-message');
    if (message) { message.hidden = true; message.textContent = ''; message.removeAttribute('data-kind'); }
    $$('input[id]').forEach(clearField);
    errors.delete('signup-role');
    const roleError = $('#signup-role-error');
    if (roleError) { roleError.hidden = true; roleError.textContent = ''; }
    $$('input[name="role"]').forEach((input) => {
      input.removeAttribute('aria-invalid');
      setDescription(input, 'signup-role-error', false);
    });
  }
  function showMessage(key, kind = 'error') {
    messageState = { key, kind };
    const output = $('#form-message');
    if (!output) return;
    output.textContent = t(key);
    output.dataset.kind = kind;
    output.hidden = false;
  }
  function fieldError(id, key, focus = false) {
    errors.set(id, key);
    if (id === 'signup-role') {
      const output = $('#signup-role-error');
      if (output) { output.textContent = t(key); output.hidden = false; }
      $$('input[name="role"]').forEach((input) => {
        input.setAttribute('aria-invalid', 'true'); setDescription(input, 'signup-role-error', true);
      });
      if (focus) $('input[name="role"]')?.focus();
      return;
    }
    const input = document.getElementById(id);
    const output = document.getElementById(`${id}-error`);
    if (!input) return;
    input.setAttribute('aria-invalid', 'true');
    if (output) { output.textContent = t(key); output.hidden = false; setDescription(input, output.id, true); }
    if (focus) input.focus();
  }
  function updatePasswordButtons() {
    $$('[data-password]').forEach((button) => {
      const input = document.getElementById(button.dataset.password);
      const visible = input?.type === 'text';
      const confirmation = input?.id === 'signup-confirm';
      button.textContent = t(visible ? 'hide' : 'show');
      button.setAttribute('aria-pressed', String(visible));
      const key = confirmation ? (visible ? 'hideConfirm' : 'showConfirm') : (visible ? 'hidePassword' : 'showPassword');
      button.setAttribute('aria-label', t(key));
      button.title = t(key);
    });
  }
  function renderLanguage() {
    document.documentElement.lang = language;
    $$('[data-i18n]').forEach((element) => { element.textContent = t(element.dataset.i18n); });
    $$('[data-i18n-placeholder]').forEach((input) => { input.placeholder = t(input.dataset.i18nPlaceholder); });
    $$('[data-i18n-alt]').forEach((image) => { image.alt = t(image.dataset.i18nAlt); });
    ['#language-toggle','#join-language-toggle'].forEach(selector => {
      const toggle = $(selector);
      if (toggle) { toggle.setAttribute('aria-label', t('switchLanguage')); toggle.title = t('switchLanguage'); }
    });
    $('#language-code').textContent = language.toUpperCase();
    updatePasswordButtons();
    errors.forEach((key, id) => { const output = document.getElementById(`${id}-error`); if (output) output.textContent = t(key); });
    if (messageState) $('#form-message').textContent = t(messageState.key);
    if (joiningError) $('#hub-code-error').textContent = t(joiningError);
    if (accessStatusKey) $('#access-status').textContent = t(accessStatusKey);
    if (session?.authenticated) renderAccessLabels();
    renderSiteIdentity();
    const heading = $('[data-screen]:not([hidden]) h1');
    document.title = `GrainGuard · ${heading?.textContent || t('login')}`;
  }
  function hidePasswords() {
    $$('[data-password]').forEach((button) => { const input = document.getElementById(button.dataset.password); if (input) input.type = 'password'; });
    updatePasswordButtons();
  }
  function showScreen(name) {
    const panel = $(`[data-screen="${name}"]`);
    if (!panel) return;
    clearErrors(); hidePasswords();
    $$('input[autocomplete="current-password"],input[autocomplete="new-password"]').forEach((input) => { input.value = ''; });
    $$('[data-screen]').forEach((item) => { item.hidden = item !== panel; });
    $('.form-panel').dataset.view = name;
    renderLanguage();
    panel.querySelector('h1')?.focus({ preventScroll: true });
    if (innerWidth <= 720) panel.scrollIntoView({ block: 'start', behavior: 'auto' });
  }
  function backendKey(result, status) {
    if (status === 401) return 'invalidLogin';
    if (status === 429) return 'rateLimited';
    if (result.detail === 'local_already_created') return 'localAlreadyCreated';
    if (result.detail === 'local_only') return 'localRestricted';
    if (result.detail === 'Local login is available only on the Pi') return 'localRestricted';
    if (result.detail === 'Username or phone is already registered') return 'duplicateAccount';
    if (status === 409 && result.field === 'phone') return 'duplicatePhone';
    if (status === 409 && result.field === 'username') return 'duplicateUsername';
    const known = {
      'กรอกชื่อและนามสกุล':'fullNameInvalid', 'กรอกเบอร์โทรไทย 9–10 หลัก':'phoneInvalid', 'เลือกบทบาทหน้าที่':'roleRequired',
      'ชื่อผู้ใช้ 4–32 ตัว เริ่มด้วย a–z':'usernameInvalid', 'รหัสผ่าน 8–128 ตัวอักษร':'passwordRange',
      'รหัสผ่านไม่ตรงกัน':'passwordMismatch', 'เบอร์นี้มีบัญชีแล้ว':'duplicatePhone', 'ชื่อผู้ใช้นี้มีแล้ว':'duplicateUsername',
      'ชื่อผู้ใช้ เบอร์โทร หรือรหัสผ่านไม่ถูกต้อง':'invalidLogin', 'รูปแบบข้อมูลไม่ถูกต้อง':'requestInvalid',
      'ข้อมูลยาวเกินไป':'requestInvalid', 'ไม่อนุญาตข้ามเว็บไซต์':'notAllowed', 'Online ดูข้อมูลอย่างเดียว':'notAllowed',
    };
    if (known[result.detail]) return known[result.detail];
    const byField = { full_name:'fullNameInvalid', phone:'phoneInvalid', role:'roleRequired', username:'usernameInvalid', password:'passwordRange', confirm_password:'passwordMismatch' };
    return byField[result.field] || (status === 403 ? 'notAllowed' : 'serverError');
  }
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    let response;
    try {
      response = await fetch(`/auth/${path}`, { credentials:'same-origin', cache:'no-store', ...options, signal:controller.signal });
    } catch (_) {
      const error = new Error('connectionError'); error.key = 'connectionError'; throw error;
    } finally { clearTimeout(timer); }
    let result;
    try { result = await response.json(); }
    catch (_) { const error = new Error('serverError'); error.key = 'serverError'; throw error; }
    if (!response.ok || result.ok === false) {
      const error = new Error('serverError');
      error.key = path === 'join' && [400,404].includes(response.status) ? 'codeInvalid'
        : path === 'signup' && channel === 'local' && response.status === 401 ? 'localAlreadyCreated'
        : backendKey(result,response.status);
      error.field = result.field; error.status = response.status; throw error;
    }
    return result;
  }
  async function post(path, data = {}) {
    return request(path, {method:'POST',headers:{'Content-Type':'application/json','X-GG-CSRF':session?.csrf_token || '1'},body:JSON.stringify({...data,...(['login','signup'].includes(path) ? {channel} : {})})});
  }
  function renderAccessLabels() {
    const state = ['pending','revoked'].includes(session?.access) ? session.access : 'unlinked';
    const heading = $('#access-title');
    const description = $('#access-description');
    if (heading) { heading.dataset.i18n = `${state}Title`; heading.textContent = t(`${state}Title`); }
    if (description) { description.dataset.i18n = `${state}Copy`; description.textContent = t(`${state}Copy`); }
  }
  function renderSiteIdentity() {
    const output = $('#login-site-context');
    if (!output) return;
    const site = globalThis.GGSiteContext?.context(session,language);
    output.hidden = !session?.authenticated || !session?.site;
    output.textContent = output.hidden ? '' : `${site?.name || 'GrainGuard'}${site?.mock ? ' · '+site.modeLabel : ''}`;
  }
  function stopPolling() { clearTimeout(pollTimer); pollTimer = null; }
  function showAccessStatus(key = null) {
    accessStatusKey = key;
    const output = $('#access-status');
    output.hidden = !key; output.textContent = key ? t(key) : '';
  }
  function schedulePoll() {
    stopPolling();
    if (session?.authenticated && !document.hidden) pollTimer = setTimeout(() => checkSession(), 5000);
  }
  function routeSession() {
    const dialog = $('#join-dialog');
    renderSiteIdentity();
    if (!session?.authenticated) {
      stopPolling(); if (dialog.open) dialog.close(); showScreen('login'); return;
    }
    if (['admin','approved'].includes(session.access)) { stopPolling(); location.replace('/'); return; }
    if (dialog.open && session.access !== 'unlinked') dialog.close();
    showScreen('access'); renderAccessLabels();
    if (session.access === 'unlinked' && !dialog.open) { dialog.showModal(); $('#hub-code').focus(); }
    schedulePoll();
  }
  async function checkSession(manual = false) {
    if (statusRequest) return statusRequest;
    statusRequest = (async () => {
      try {
        const previous = session;
        const next = await request('session');
        // A session check that began before a sign-in must not reset the form.
        if (busy || session !== previous) return;
        session = next;
        const existing = $('[data-screen="access"]')?.hidden === false;
        if (!session.authenticated && !previous?.authenticated && !existing) return;
        if (!session.authenticated || ['admin','approved'].includes(session.access) || !existing || previous?.access !== session.access) routeSession();
        else { renderAccessLabels(); renderSiteIdentity(); if (session.access !== 'unlinked' && $('#join-dialog').open) $('#join-dialog').close(); schedulePoll(); }
        showAccessStatus(manual && session.authenticated && !['admin','approved'].includes(session.access)
          ? session.access === 'pending' ? 'noChange' : `${session.access}Copy` : null);
      } catch (error) {
        if (session?.authenticated) {
          showAccessStatus(error.key || 'connectionError'); schedulePoll();
        } else showMessage(error.key || 'connectionError');
      } finally { statusRequest = null; }
    })();
    return statusRequest;
  }
  async function submit(form, action, fieldMap = {}) {
    if (busy) return;
    busy = true;
    const button = form.querySelector('[type="submit"]');
    const label = button?.querySelector('[data-i18n]');
    const labelKey = label?.dataset.i18n;
    if (button) { button.disabled = true; button.setAttribute('aria-busy','true'); }
    if (label) { label.dataset.i18n = 'busy'; label.textContent = t('busy'); }
    try { await action(); }
    catch (error) {
      const key = error.key || 'serverError';
      showMessage(key);
      const field = fieldMap[error.field];
      if (field) fieldError(field,key,true); else $('#form-message')?.focus();
    } finally {
      busy = false;
      if (button) { button.disabled = false; button.removeAttribute('aria-busy'); }
      if (label) { label.dataset.i18n = labelKey; label.textContent = t(labelKey); }
    }
  }
  function saveIdentifier(value) {
    try { if ($('#remember-identifier')?.checked) localStorage.setItem(rememberKey,value); else localStorage.removeItem(rememberKey); } catch (_) {}
  }
  function signupErrors() {
    const name = text($('#signup-name')?.value).replace(/\s+/g,' ');
    const phone = normalizePhone($('#signup-phone')?.value);
    const role = $('input[name="role"]:checked')?.value;
    const username = text($('#signup-username')?.value).toLowerCase();
    const password = $('#signup-password')?.value || '';
    const confirm = $('#signup-confirm')?.value || '';
    const issues = [];
    if (!/\S+\s+\S+/.test(name)) issues.push(['signup-name','fullNameInvalid']);
    if (!/^0\d{8,9}$/.test(phone)) issues.push(['signup-phone','phoneInvalid']);
    if (!['entrepreneur','employee'].includes(role)) issues.push(['signup-role','roleRequired']);
    if (!/^[a-z][a-z0-9._-]{3,31}$/.test(username)) issues.push(['signup-username','usernameInvalid']);
    if (password.length < 8) issues.push(['signup-password','passwordShort']);
    else if (password.length > 128) issues.push(['signup-password','passwordLong']);
    if (!confirm || password !== confirm) issues.push(['signup-confirm','passwordMismatch']);
    return {issues,data:{full_name:name,phone,role,username,password,confirm_password:confirm}};
  }
  $('#login-form')?.addEventListener('submit',(event) => {
    event.preventDefault(); clearErrors();
    const identifier = text($('#login-identifier').value);
    const password = $('#login-password').value;
    if (!identifier) return fieldError('login-identifier','identifierRequired',true);
    if (!password) return fieldError('login-password','passwordRequired',true);
    submit(event.currentTarget,async () => {
      await post('login',{identifier,password});
      saveIdentifier(identifier); $('#login-password').value = '';
      session = await request('session'); routeSession();
    },{identifier:'login-identifier',password:'login-password'});
  });
  $('#signup-form')?.addEventListener('submit',(event) => {
    event.preventDefault(); clearErrors();
    const {issues,data} = signupErrors();
    if (issues.length) { issues.forEach(([id,key],index) => fieldError(id,key,index===0)); return; }
    const form = event.currentTarget;
    submit(form,async () => {
      await post('signup',data); form.reset();
      session = await request('session'); routeSession();
    },{full_name:'signup-name',name:'signup-name',phone:'signup-phone',role:'signup-role',username:'signup-username',password:'signup-password',confirm_password:'signup-confirm'});
  });
  $$('[data-go]').forEach((button) => button.addEventListener('click',() => { if (!busy) showScreen(button.dataset.go); }));
  $$('[data-password]').forEach((button) => button.addEventListener('click',() => {
    const input = document.getElementById(button.dataset.password);
    if (input) { input.type = input.type === 'password' ? 'text' : 'password'; updatePasswordButtons(); }
  }));
  const toggleLanguage = () => {
    language = language === 'th' ? 'en' : 'th';
    try { localStorage.setItem(languageKey,language); } catch (_) {}
    renderLanguage();
  };
  ['#language-toggle','#join-language-toggle'].forEach(selector => $(selector)?.addEventListener('click',toggleLanguage));
  $$('#signup-form input[id]').forEach((input) => input.addEventListener('blur',() => {
    if (!input.value) return;
    clearField(input);
    const issue = signupErrors().issues.find(([id]) => id===input.id);
    if (issue) fieldError(issue[0],issue[1]);
  }));
  $$('input[name="role"]').forEach((input) => input.addEventListener('change',() => {
    errors.delete('signup-role'); $('#signup-role-error').hidden = true;
    $$('input[name="role"]').forEach((item) => { item.removeAttribute('aria-invalid'); setDescription(item,'signup-role-error',false); });
  }));
  try {
    const identifier = localStorage.getItem(rememberKey);
    if (identifier) { $('#login-identifier').value = identifier; $('#remember-identifier').checked = true; }
  } catch (_) {}
  $('#join-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const input = $('#hub-code');
    const code = input.value.trim();
    const output = $('#hub-code-error');
    joiningError = null; output.hidden = true; input.removeAttribute('aria-invalid');
    if (!code) { joiningError = 'codeRequired'; output.textContent = t(joiningError); output.hidden = false; input.setAttribute('aria-invalid','true'); input.focus(); return; }
    const button = event.currentTarget.querySelector('[type="submit"]');
    if (button.disabled) return;
    button.disabled = true; button.setAttribute('aria-busy','true');
    try {
      await post('join', {code}); input.value = '';
      session = await request('session'); routeSession();
    } catch (error) {
      joiningError = error.key || 'serverError'; output.textContent = t(joiningError); output.hidden = false; input.setAttribute('aria-invalid','true'); input.focus();
    } finally { button.disabled = false; button.removeAttribute('aria-busy'); }
  });
  $('#join-dialog')?.addEventListener('cancel', event => event.preventDefault());
  $$('[data-auth-logout]').forEach(button => button.addEventListener('click', async () => {
    if (button.disabled) return; button.disabled = true;
    try { await post('logout'); session = null; routeSession(); }
    catch(error) {
      if ($('#join-dialog').open) {
        joiningError = error.key || 'connectionError';
        $('#hub-code-error').textContent = t(joiningError); $('#hub-code-error').hidden = false;
      } else showMessage(error.key || 'connectionError');
    }
    finally { button.disabled = false; }
  }));
  $('#access-refresh')?.addEventListener('click', () => checkSession(true));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopPolling();
    else if (session?.authenticated) checkSession();
  });
  window.addEventListener('pagehide', stopPolling);
  renderLanguage();
  checkSession();
})();
