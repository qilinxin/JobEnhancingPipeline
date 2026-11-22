(() => {
  const byId = id => document.getElementById(id);
  const cards = [...document.querySelectorAll('.jobrow')];
  const source = byId('source');
  const minimum = byId('minimum');
  let shortlist = false;
  function filter() {
    let count = 0;
    for (const card of cards) {
      const visible = (source.value === 'all' || card.dataset.source === source.value)
        && Number(card.dataset.score) >= Math.max(Number(minimum.value), shortlist ? 75 : -1);
      card.hidden = !visible;
      count += Number(visible);
    }
    byId('showing').textContent = `${count} ${count === 1 ? 'opportunity' : 'opportunities'}`;
    byId('filteredEmpty').hidden = count > 0 || cards.length === 0;
  }
  source.addEventListener('change', filter);
  minimum.addEventListener('change', filter);
  byId('shortlist').addEventListener('click', event => {
    shortlist = !shortlist;
    event.currentTarget.setAttribute('aria-pressed', String(shortlist));
    event.currentTarget.classList.toggle('selected', shortlist);
    filter();
  });
  function density(compact) {
    document.body.classList.toggle('compact', compact);
    byId('comfortable').setAttribute('aria-pressed', String(!compact));
    byId('compact').setAttribute('aria-pressed', String(compact));
    try { localStorage.setItem('job-library-density', compact ? 'compact' : 'comfortable'); } catch (_) { /* Storage is optional. */ }
  }
  byId('comfortable').addEventListener('click', () => density(false));
  byId('compact').addEventListener('click', () => density(true));
  try { density(localStorage.getItem('job-library-density') === 'compact'); } catch (_) { /* Use the default density. */ }
  byId('captureDate').addEventListener('change', event => { window.location.assign(event.target.value); });
  byId('resetFilters').addEventListener('click', () => {
    source.value = 'all'; minimum.value = '-1'; shortlist = false;
    byId('shortlist').setAttribute('aria-pressed', 'false');
    byId('shortlist').classList.remove('selected'); filter();
  });
  filter();
})();
