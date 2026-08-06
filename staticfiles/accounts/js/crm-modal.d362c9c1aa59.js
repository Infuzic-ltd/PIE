/* Shared CRM-themed modal — replaces native alert()/confirm() popups across the app.
   Relies on each page already defining --navy/--blue/--red/--line/--ink CSS variables. */
(function () {
  if (window.crmAlert) return;

  var STYLE = [
    '.crm-modal-scrim{display:none;position:fixed;inset:0;background:rgba(8,16,36,.55);z-index:9999;align-items:center;justify-content:center;padding:20px}',
    '.crm-modal-scrim.open{display:flex}',
    '.crm-modal-box{background:#fff;border-radius:var(--radius,14px);padding:22px;width:100%;max-width:400px;box-shadow:0 20px 60px rgba(8,16,36,.3);font-family:inherit;animation:crmModalIn .16s ease}',
    '@keyframes crmModalIn{from{transform:translateY(6px) scale(.98);opacity:0}to{transform:none;opacity:1}}',
    '.crm-modal-icon{width:42px;height:42px;border-radius:50%;display:grid;place-items:center;margin-bottom:14px;font-size:19px;font-weight:700}',
    '.crm-modal-icon.info{background:#dbeafe;color:var(--blue,#2563eb)}',
    '.crm-modal-icon.danger{background:#fef2f2;color:var(--red,#ef4444)}',
    '.crm-modal-title{font-size:15px;font-weight:700;color:var(--ink,#1a2332);margin-bottom:6px}',
    '.crm-modal-msg{font-size:13px;color:var(--ink-soft,#5a6678);line-height:1.6;margin-bottom:18px;white-space:pre-line}',
    '.crm-modal-actions{display:flex;gap:8px;justify-content:flex-end}',
    '.crm-modal-btn{display:inline-flex;align-items:center;padding:8px 16px;border-radius:9px;font-size:13px;font-weight:600;border:1px solid var(--line,#e7ecf3);background:#fff;color:var(--ink,#1a2332);cursor:pointer;font-family:inherit;transition:background .12s}',
    '.crm-modal-btn:hover{background:#f7f9fc}',
    '.crm-modal-btn.primary{background:var(--blue,#2563eb);border-color:var(--blue,#2563eb);color:#fff}',
    '.crm-modal-btn.primary:hover{background:#1d4ed8}',
    '.crm-modal-btn.danger{background:var(--red,#ef4444);border-color:var(--red,#ef4444);color:#fff}',
    '.crm-modal-btn.danger:hover{background:#dc2626}',
  ].join('');

  var styleTag = document.createElement('style');
  styleTag.textContent = STYLE;
  document.head.appendChild(styleTag);

  var scrim = null, box = null;

  function ensureDom() {
    if (scrim) return;
    scrim = document.createElement('div');
    scrim.className = 'crm-modal-scrim';
    scrim.innerHTML =
      '<div class="crm-modal-box">' +
        '<div class="crm-modal-icon"></div>' +
        '<div class="crm-modal-title"></div>' +
        '<div class="crm-modal-msg"></div>' +
        '<div class="crm-modal-actions"></div>' +
      '</div>';
    document.body.appendChild(scrim);
    box = scrim.querySelector('.crm-modal-box');
  }

  function open(opts) {
    ensureDom();
    return new Promise(function (resolve) {
      var iconEl = box.querySelector('.crm-modal-icon');
      var titleEl = box.querySelector('.crm-modal-title');
      var msgEl = box.querySelector('.crm-modal-msg');
      var actionsEl = box.querySelector('.crm-modal-actions');
      var danger = opts.style === 'danger';

      iconEl.className = 'crm-modal-icon ' + (danger ? 'danger' : 'info');
      iconEl.textContent = danger ? '!' : 'i';
      titleEl.textContent = opts.title || (opts.mode === 'confirm' ? (danger ? 'Are you sure?' : 'Please confirm') : 'Notice');
      msgEl.textContent = opts.message || '';
      actionsEl.innerHTML = '';

      function close(result) {
        scrim.classList.remove('open');
        document.removeEventListener('keydown', onKey);
        resolve(result);
      }
      function onKey(e) {
        if (e.key === 'Escape') close(false);
        else if (e.key === 'Enter') close(true);
      }

      if (opts.mode === 'confirm') {
        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'crm-modal-btn';
        cancelBtn.textContent = opts.cancelLabel || 'Cancel';
        cancelBtn.onclick = function () { close(false); };

        var okBtn = document.createElement('button');
        okBtn.type = 'button';
        okBtn.className = 'crm-modal-btn ' + (danger ? 'danger' : 'primary');
        okBtn.textContent = opts.confirmLabel || (danger ? 'Delete' : 'Confirm');
        okBtn.onclick = function () { close(true); };

        actionsEl.appendChild(cancelBtn);
        actionsEl.appendChild(okBtn);
      } else {
        var okOnly = document.createElement('button');
        okOnly.type = 'button';
        okOnly.className = 'crm-modal-btn primary';
        okOnly.textContent = opts.confirmLabel || 'OK';
        okOnly.onclick = function () { close(true); };
        actionsEl.appendChild(okOnly);
      }

      scrim.onclick = function (e) { if (e.target === scrim) close(false); };
      document.addEventListener('keydown', onKey);
      scrim.classList.add('open');
      setTimeout(function () {
        var btn = actionsEl.querySelector(danger ? '.danger' : '.primary');
        if (btn) btn.focus();
      }, 10);
    });
  }

  window.crmAlert = function (message, opts) {
    opts = opts || {};
    return open({
      mode: 'alert', message: message, title: opts.title,
      style: opts.style, confirmLabel: opts.confirmLabel,
    });
  };

  window.crmConfirm = function (message, opts) {
    opts = opts || {};
    return open({
      mode: 'confirm', message: message, title: opts.title,
      style: opts.style || 'danger', confirmLabel: opts.confirmLabel, cancelLabel: opts.cancelLabel,
    });
  };

  function wireConfirmForms(root) {
    (root || document).querySelectorAll('form.crm-confirm-form').forEach(function (form) {
      if (form.dataset.crmWired === '1') return;
      form.dataset.crmWired = '1';
      form.addEventListener('submit', function (e) {
        if (form.dataset.crmConfirmed === '1') return;
        e.preventDefault();
        window.crmConfirm(form.dataset.confirmMessage || 'Are you sure?', {
          title: form.dataset.confirmTitle,
          style: form.dataset.confirmStyle || 'danger',
          confirmLabel: form.dataset.confirmLabel,
        }).then(function (ok) {
          if (ok) {
            form.dataset.crmConfirmed = '1';
            form.requestSubmit();
          }
        });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () { wireConfirmForms(document); });
  window.crmWireConfirmForms = wireConfirmForms;
})();
