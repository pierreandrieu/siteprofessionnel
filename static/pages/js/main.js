document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-check]');
    if (!btn) return;
    const wrap = btn.closest('[data-ex]');
    if (!wrap) return;
    const input = wrap.querySelector('input[data-answer]');
    const out = wrap.querySelector('[data-feedback]');
    if (!input || !out) return;
    const expected = (input.dataset.answer || '').trim().toLowerCase();
    const got = (input.value || '').trim().toLowerCase();
    const ok = expected && got === expected;
    out.textContent = ok ? '✔️ correct' : '✖️ essaye encore';
    out.className = ok ? 'text-success' : 'text-danger';
});