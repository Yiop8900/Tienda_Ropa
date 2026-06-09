/* Tienda Ropa — main.js */

document.addEventListener('DOMContentLoaded', () => {

  /* ── Auto-cerrar mensajes flash después de 4 s ── */
  setTimeout(() => {
    document.querySelectorAll('.alert.fade.show').forEach(el => {
      const a = bootstrap.Alert.getOrCreateInstance(el);
      if (a) a.close();
    });
  }, 4000);

  /* ── Toast "Agregado al carrito" ── */
  insertToastContainer();

  document.addEventListener('click', e => {
    const btn = e.target.closest('.btn-agregar-ajax');
    if (!btn) return;

    e.preventDefault();
    const url      = btn.dataset.url;
    const fallback = btn.dataset.fallback;

    // Efecto visual inmediato en el botón
    const original = btn.innerHTML;
    btn.disabled   = true;
    btn.innerHTML  = '<i class="bi bi-check2 me-1"></i>¡Listo!';
    btn.classList.add('btn-added');

    fetch(url, {
      method:      'POST',
      credentials: 'same-origin',
      headers:     { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(r => r.json())
      .then(data => {
        if (!data.ok) { window.location.href = fallback; return; }
        updateCartBadge(data.cart_count);
        showToast(data.nombre);
      })
      .catch(() => { window.location.href = fallback; })
      .finally(() => {
        setTimeout(() => {
          btn.disabled  = false;
          btn.innerHTML = original;
          btn.classList.remove('btn-added');
        }, 1400);
      });
  });

  /* ── Helpers ── */

  function updateCartBadge(count) {
    let badge = document.querySelector('.navbar .badge.bg-warning');
    const link = document.querySelector('a[href*="carrito"]');
    if (!link) return;

    if (count > 0) {
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'position-absolute top-0 start-100 translate-middle badge rounded-pill bg-warning text-dark';
        link.classList.add('position-relative');
        link.appendChild(badge);
      }
      badge.textContent = count;
      badge.classList.add('badge-bounce');
      setTimeout(() => badge.classList.remove('badge-bounce'), 500);
    } else if (badge) {
      badge.remove();
    }
  }

  function insertToastContainer() {
    if (document.getElementById('tr-toast-container')) return;
    const el = document.createElement('div');
    el.id        = 'tr-toast-container';
    el.className = 'position-fixed bottom-0 end-0 p-3';
    el.style.zIndex = '1100';
    document.body.appendChild(el);
  }

  function showToast(nombre) {
    const container = document.getElementById('tr-toast-container');
    const id  = 'toast-' + Date.now();
    const div = document.createElement('div');
    div.id        = id;
    div.className = 'toast align-items-center text-white border-0 tr-toast-item';
    div.setAttribute('role', 'alert');
    div.setAttribute('aria-live', 'assertive');
    div.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">
          <i class="bi bi-bag-check-fill me-2 text-warning"></i>
          <strong>${nombre}</strong> agregado al carrito
        </div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto"
                data-bs-dismiss="toast"></button>
      </div>`;
    container.appendChild(div);

    const t = new bootstrap.Toast(div, { delay: 3000 });
    t.show();
    div.addEventListener('hidden.bs.toast', () => div.remove());
  }

});
