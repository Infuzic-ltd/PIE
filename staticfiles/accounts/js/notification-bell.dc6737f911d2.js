/* Floating notification bell — red-dot badge, Gmail/Instagram-style dropdown
   (unread highlighted, read plain), polling for new arrivals, and a short
   Web-Audio chime when the unread count goes up. Self-contained: mounts
   itself into document.body, no per-page markup required beyond this tag. */
(function () {
  if (window.__notifBellInit) return;
  window.__notifBellInit = true;

  var FEED_URL = '/crm/notifications/feed/';
  var LIST_URL = '/crm/notifications/';
  var MARK_ALL_URL = '/crm/notifications/mark-all-read/';
  var POLL_MS = 25000;

  var STYLE = [
    '.notif-bell-wrap{position:fixed;bottom:22px;right:22px;z-index:200;font-family:"Inter",system-ui,sans-serif}',
    '.notif-bell-btn{position:relative;width:44px;height:44px;border-radius:50%;border:1px solid var(--line,#e7ecf3);background:#fff;cursor:pointer;display:grid;place-items:center;box-shadow:0 4px 14px rgba(16,30,60,.16);transition:transform .15s,box-shadow .15s;padding:0}',
    '.notif-bell-btn:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(16,30,60,.22)}',
    '.notif-bell-btn svg{width:20px;height:20px;stroke:var(--ink,#1a2332);fill:none;stroke-width:1.8;transform-origin:50% 12%}',
    '.notif-bell-btn.ring svg{animation:notifRing .6s ease-in-out}',
    '@keyframes notifRing{0%,100%{transform:rotate(0)}15%{transform:rotate(16deg)}30%{transform:rotate(-13deg)}45%{transform:rotate(10deg)}60%{transform:rotate(-7deg)}75%{transform:rotate(4deg)}90%{transform:rotate(-2deg)}}',
    '.notif-red-dot{position:absolute;top:6px;right:7px;width:9px;height:9px;border-radius:50%;background:var(--red,#ef4444);border:2px solid #fff;display:none}',
    '.notif-red-dot.show{display:block;animation:notifPulse 1.6s ease-in-out infinite}',
    '@keyframes notifPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.3)}}',
    '.notif-dropdown{position:absolute;bottom:52px;right:0;width:360px;max-width:calc(100vw - 32px);background:#fff;border-radius:14px;box-shadow:0 20px 50px rgba(8,16,36,.22);border:1px solid var(--line,#e7ecf3);overflow:hidden;display:none;flex-direction:column;max-height:480px;animation:notifDropIn .15s ease}',
    '@keyframes notifDropIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}',
    '.notif-dropdown.open{display:flex}',
    '.notif-dropdown-head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--line,#e7ecf3);font-weight:700;font-size:14px;color:var(--ink,#1a2332);flex:0 0 auto}',
    '.notif-dropdown-head button{background:none;border:none;color:var(--blue,#2563eb);font-size:12px;font-weight:600;cursor:pointer;font-family:inherit;padding:0}',
    '.notif-dropdown-head button:hover{text-decoration:underline}',
    '.notif-list{overflow-y:auto;flex:1}',
    '.notif-item{display:flex;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line,#e7ecf3);cursor:pointer;text-decoration:none;transition:background .12s}',
    '.notif-item:last-child{border-bottom:none}',
    '.notif-item:hover{background:#f7f9fc}',
    '.notif-item.unread{background:#eff6ff}',
    '.notif-item.unread:hover{background:#e3edfd}',
    '.notif-dot{width:8px;height:8px;border-radius:50%;background:var(--blue,#2563eb);flex:0 0 8px;margin-top:6px}',
    '.notif-item.read .notif-dot{background:transparent}',
    '.notif-body{flex:1;min-width:0}',
    '.notif-title{font-size:13px;font-weight:700;color:var(--ink,#1a2332);margin-bottom:2px}',
    '.notif-item.read .notif-title{font-weight:500;color:var(--ink-soft,#5a6678)}',
    '.notif-text{font-size:12.5px;color:var(--ink-soft,#5a6678);line-height:1.4;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}',
    '.notif-time{font-size:11px;color:var(--ink-faint,#8a94a6);margin-top:4px}',
    '.notif-empty{padding:36px 20px;text-align:center;color:var(--ink-faint,#8a94a6);font-size:13px}',
    '.notif-dropdown-foot{display:block;text-align:center;padding:11px;font-size:12.5px;font-weight:600;color:var(--blue,#2563eb);border-top:1px solid var(--line,#e7ecf3);text-decoration:none;flex:0 0 auto}',
    '.notif-dropdown-foot:hover{background:#f7f9fc}',
    '@media(max-width:480px){.notif-bell-wrap{bottom:16px;right:14px}.notif-dropdown{width:calc(100vw - 24px);right:-6px}}',
  ].join('');

  var styleTag = document.createElement('style');
  styleTag.textContent = STYLE;
  document.head.appendChild(styleTag);

  function getCookie(name) {
    var match = document.cookie.match('(?:^|; )' + name + '=([^;]*)');
    return match ? decodeURIComponent(match[1]) : null;
  }

  function relativeTime(iso) {
    var diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return 'Just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    if (diff < 172800) return 'Yesterday';
    return Math.floor(diff / 86400) + 'd ago';
  }

  var audioCtx = null;
  function playDing() {
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      var now = audioCtx.currentTime;
      [880, 1318.5].forEach(function (freq, i) {
        var osc = audioCtx.createOscillator();
        var gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.value = freq;
        var start = now + i * 0.11;
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(0.16, start + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.32);
        osc.connect(gain).connect(audioCtx.destination);
        osc.start(start);
        osc.stop(start + 0.35);
      });
    } catch (e) { /* Web Audio unavailable or blocked — ignore */ }
  }
  document.addEventListener('click', function () {
    if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
  });

  document.addEventListener('DOMContentLoaded', function () {
    var wrap = document.createElement('div');
    wrap.className = 'notif-bell-wrap';
    wrap.innerHTML =
      '<button type="button" class="notif-bell-btn" id="notifBellBtn" title="Notifications" aria-label="Notifications">' +
        '<svg viewBox="0 0 24 24"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>' +
        '<span class="notif-red-dot" id="notifRedDot"></span>' +
      '</button>' +
      '<div class="notif-dropdown" id="notifDropdown">' +
        '<div class="notif-dropdown-head"><span>Notifications</span><button type="button" id="notifMarkAllBtn">Mark all read</button></div>' +
        '<div class="notif-list" id="notifList"></div>' +
        '<a class="notif-dropdown-foot" href="' + LIST_URL + '">View All</a>' +
      '</div>';
    document.body.appendChild(wrap);

    var bellBtn = document.getElementById('notifBellBtn');
    var dropdown = document.getElementById('notifDropdown');
    var redDot = document.getElementById('notifRedDot');
    var list = document.getElementById('notifList');
    var markAllBtn = document.getElementById('notifMarkAllBtn');
    var lastUnreadCount = null;

    function ringBell() {
      bellBtn.classList.remove('ring');
      void bellBtn.offsetWidth; // force reflow so the animation restarts on back-to-back arrivals
      bellBtn.classList.add('ring');
      setTimeout(function () { bellBtn.classList.remove('ring'); }, 650);
    }

    function buildItem(n) {
      var a = document.createElement('a');
      a.className = 'notif-item ' + (n.is_read ? 'read' : 'unread');
      a.href = '/crm/notifications/' + n.id + '/open/';

      var dot = document.createElement('div');
      dot.className = 'notif-dot';

      var body = document.createElement('div');
      body.className = 'notif-body';

      var title = document.createElement('div');
      title.className = 'notif-title';
      title.textContent = n.title;
      body.appendChild(title);

      if (n.body) {
        var text = document.createElement('div');
        text.className = 'notif-text';
        text.textContent = n.body;
        body.appendChild(text);
      }

      var time = document.createElement('div');
      time.className = 'notif-time';
      time.textContent = relativeTime(n.created_at);
      body.appendChild(time);

      a.appendChild(dot);
      a.appendChild(body);
      return a;
    }

    function renderList(items) {
      list.innerHTML = '';
      if (!items.length) {
        var empty = document.createElement('div');
        empty.className = 'notif-empty';
        empty.textContent = 'No notifications yet.';
        list.appendChild(empty);
        return;
      }
      items.forEach(function (n) { list.appendChild(buildItem(n)); });
    }

    function loadFeed(allowSound) {
      fetch(FEED_URL, { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          renderList(data.notifications || []);
          var count = data.unread_count || 0;
          redDot.classList.toggle('show', count > 0);
          if (allowSound && lastUnreadCount !== null && count > lastUnreadCount) {
            playDing();
            ringBell();
          }
          lastUnreadCount = count;
        })
        .catch(function () { /* offline / transient error — try again next poll */ });
    }

    bellBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var opening = !dropdown.classList.contains('open');
      dropdown.classList.toggle('open');
      if (opening) loadFeed(false);
    });
    document.addEventListener('click', function (e) {
      if (!wrap.contains(e.target)) dropdown.classList.remove('open');
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') dropdown.classList.remove('open');
    });

    markAllBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      fetch(MARK_ALL_URL, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
      }).then(function () {
        list.querySelectorAll('.notif-item.unread').forEach(function (item) {
          item.classList.remove('unread');
          item.classList.add('read');
        });
        redDot.classList.remove('show');
        lastUnreadCount = 0;
      }).catch(function () {});
    });

    loadFeed(false);
    setInterval(function () { loadFeed(true); }, POLL_MS);
  });
})();
