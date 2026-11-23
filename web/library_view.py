"""Render the live Job Library using the approved preview layout."""
import re
from html import escape, unescape
from pathlib import Path
from urllib.parse import urlencode

from collector.job_boards import source_for_url
from documents.files import document_file
from storage.metadata import posting_fields
from storage.visibility import SYDNEY

CSS = Path(__file__).with_name('library.css').read_text()
SCRIPT = Path(__file__).with_name('library.js').read_text()


def icon(name):
    paths = {
        'search': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
        'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
        'briefcase': '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V4h8v3M3 12h18"/>',
        'list': '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
        'grid': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
        'sliders': '<path d="M3 6h18M3 12h18M3 18h18M8 3v6M16 9v6M9 15v6"/>',
    }
    return f'<svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>'


def safe(value):
    return escape(str(value)) if value is not None else ''


def render_shell(title, body, *, active='jobs', history='', script=False):
    navigation = ''.join(
        f'<a class="navitem{ " active" if key == active else ""}" href="{url}"'
        f'{ " aria-current=page" if key == active else ""}>{icon(symbol)}<span>{label}</span></a>'
        for key, url, label, symbol in (
            ('jobs', '/', 'Captured jobs', 'briefcase'),
            ('companies', '/blacklist', 'Company filters', 'sliders'),
            ('titles', '/title-blacklist', 'Title filters', 'sliders'),
        )
    )
    history = f'<div class="eyebrow">Capture history</div><nav class="dates" aria-label="Capture dates">{history}</nav>' if history else ''
    scripts = '<script src="/library.js" defer></script>' if script else ''
    mobile_nav = '<nav class="mobile-nav" aria-label="Workspace navigation">' + navigation + '</nav>'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{safe(title)} · Job Library</title><link rel="stylesheet" href="/library.css">{scripts}</head><body>
<aside class="sidebar"><a href="/" class="brand"><span class="brandmark">JL</span>Job Library</a>{navigation}{history}<div class="sidebarfooter"><strong>Private job workspace</strong><a href="https://www.seek.com.au/java-software-engineer-jobs" target="_blank" rel="noopener">Search SEEK ↗</a><a href="https://au.indeed.com/jobs?q=Java+Software+Engineer" target="_blank" rel="noopener">Search Indeed ↗</a></div></aside>
<div class="shell"><header class="topbar"><div class="breadcrumb"><a href="/">Workspace</a><span>/</span><strong>{safe(title)}</strong></div><a href="/" class="mobilebrand"><span class="brandmark">JL</span>Job Library</a><span class="workspace-label">Personal workspace</span></header>{mobile_nav}<main>{body}</main></div></body></html>'''


def render_library(rows, dates, day, *, show_applied=False, show_excluded=False, keyword=''):
    def view_url(view='', capture_day=day):
        query = {'date': capture_day.isoformat()}
        if view: query[view] = '1'
        return '/?' + urlencode(query)

    current = 'excluded' if show_excluded else 'applied' if show_applied else ''
    heading = 'Search results' if keyword else {'excluded': 'Excluded jobs', 'applied': 'Applied jobs', '': 'Captured jobs'}[current]
    links = []
    date_options = []
    for entry in dates:
        capture_day = entry['day']
        active = not keyword and capture_day == day
        url = safe(view_url(current, capture_day))
        links.append(f'<a class="day{ " active" if active else ""}" href="{url}"{ " aria-current=page" if active else ""}><span>{capture_day:%d %B}</span><small>{entry["total"]}</small></a>')
        date_options.append(f'<option value="{url}"{ " selected" if capture_day == day else ""}>{capture_day:%d %B %Y} · {entry["total"]} jobs</option>')
    strong = sum(r['display_score'] is not None and r['display_score'] >= 75 for r in rows)
    ready = 0
    cards = []
    for row in rows:
        company, location, _ = posting_fields(row)
        company = next((line.strip() for line in (company or '').splitlines() if line.strip() and line.strip() != row['title']), 'Company not stated')
        company = unescape(company)
        initials = ''.join(part[0] for part in re.findall(r'\w+', company)[:2]).upper()
        url = row['canonical_url']
        source = 'Indeed' if url.startswith('urn:manual:indeed:') else source_for_url(url) or 'LinkedIn'
        score = row['display_score']
        score_number = float(score) if score is not None else -1
        score_text = f'{score_number:.2f}'.rstrip('0').rstrip('.') if score is not None else '—'
        docs = {kind: document_file(row['id'], kind) for kind in ('resume', 'cover-letter')}
        complete = all(docs.values()); ready += int(complete)
        document_links = ''.join(f'<a href="/captures/{row["id"]}/download/{kind}">{label}</a>' for kind, label in (('resume','Resume'), ('cover-letter','Cover letter')) if docs[kind])
        model = {'In-house':'In-house', 'Client delivery':'Outsourced'}.get(row['reviewed_delivery_model'], 'Unconfirmed') if row['delivery_reviewed_at'] else 'Pending review'
        mode_match = re.search(r'\b(hybrid|remote|on[ -]site)\b', location or '', re.I)
        city = row['city'] or location or 'Location not stated'
        mode = ' · ' + mode_match[0].title() if mode_match and mode_match[0].lower() not in city.lower() else ''
        captured = f'<span class="dot">·</span><span>{row["captured_at"].astimezone(SYDNEY):%d %b %Y}</span>' if keyword else ''
        tags = ''.join(f'<span class="tag">{safe(t)}</span>' for t in (row['key_technologies'] or []))
        forms = []
        for status in ('applied', 'excluded'):
            marked = row[f'{status}_at'] is not None
            label = ('Undo applied' if marked else 'Mark applied') if status == 'applied' else ('Restore' if marked else 'Exclude')
            search_field = f'<input type="hidden" name="q" value="{safe(keyword)}">' if keyword else ''
            forms.append(f'<form action="/{status}" method="post"><input type="hidden" name="capture_id" value="{row["id"]}">{search_field}<button name="action" value="{ "unmark" if marked else "mark"}" aria-label="{safe(label)}: {safe(row["title"])}">{label}</button></form>')
        cards.append(f'''<article class="jobrow" data-source="{safe(source)}" data-score="{score_number}">
<div class="jobmain"><div class="companyicon" aria-hidden="true">{safe(initials)}</div><div class="jobinfo">
<h2 class="jobtitle"><a href="/captures/{row['id']}">{safe(row['title'])}</a></h2>
<div class="companyline"><span>{safe(company)}</span><span class="dot">·</span><span>{safe(city)}{safe(mode)}</span><span class="source{ ' linkedin' if source == 'LinkedIn' else ''}">{safe(source)}</span>{captured}</div>
<div class="tags">{tags}<span class="type"><i></i>{model}</span><span class="documentlinks">{document_links or 'Documents not generated'}</span></div></div></div>
<div class="score{ ' pending' if score is None else ''}" aria-label="Match score: {score_text}"><strong>{score_text}</strong><small>{'PENDING' if score is None else 'MATCH SCORE'}</small><progress class="scoreline" max="100" value="{max(0,min(100,score_number))}" aria-label="Match score progress"></progress></div>
<div class="actions"><div class="status-buttons">{''.join(forms)}</div></div></article>''')
    navigation = []
    for value, label in (('', 'Captured jobs'), ('applied', 'Applied'), ('excluded', 'Excluded')):
        active = current == value and not keyword
        navigation.append(f'<a class="tab" href="{safe(view_url(value))}"{ " aria-current=page" if active else ""}>{label}</a>')
    clear = f'<a class="clearsearch" href="{safe(view_url())}">Clear search for “{safe(keyword)}”</a>' if keyword else ''
    empty = '<p class="empty">No jobs match this view. Choose another capture date or search across all dates.</p>' if not rows else ''
    date_label = 'Across all capture dates' if keyword else day.strftime('%A, %d %B %Y')
    body = f'''<div class="heading"><div><div class="overline">Your opportunity workspace</div><h1>{heading}</h1><p class="subtitle">Review matches, prepare documents and track your applications.</p></div><div class="datebadge">{icon('calendar')}<span>{date_label}</span></div></div>
<div class="mobilehistory"><label for="captureDate" class="searchlabel">Capture date</label><select id="captureDate">{''.join(date_options)}</select></div>
<div class="stats"><div class="stat"><strong>{len(rows)}</strong><span>roles in this view</span></div><div class="stat feature"><strong>{strong}</strong><span>75+ matches</span></div><div class="stat"><strong>{ready}</strong><span>document sets ready</span></div></div>
<div class="toolbar"><form class="job-search" method="get" action="/" role="search"><label class="search"><span class="searchlabel">Search all capture dates</span>{icon('search')}<input name="q" type="search" maxlength="200" value="{safe(keyword)}" placeholder="Search all dates: title, company or technology…"></label><button class="searchbutton">Search</button></form><select id="source" class="select" aria-label="Filter source"><option value="all">All sources</option><option>SEEK</option><option>LinkedIn</option><option>Indeed</option></select><select id="minimum" class="select" aria-label="Minimum match score"><option value="-1">Any score</option><option value="75">75+ matches</option><option value="85">85+ matches</option></select><div class="viewtoggle" aria-label="List density"><button id="comfortable" aria-label="Comfortable layout" aria-pressed="true">{icon('grid')}</button><button id="compact" aria-label="Compact layout" aria-pressed="false">{icon('list')}</button></div></div>{clear}
<nav class="tabsbar" aria-label="Job status">{navigation[0]}<button class="tab" id="shortlist" aria-pressed="false">75+ matches <small>{strong}</small></button>{''.join(navigation[1:])}<span class="sort">Sorted by <strong>best match ↓</strong></span></nav>
<div class="listmeta"><strong id="showing">{len(rows)} opportunities</strong><span class="local-filter-note">Source and score filters apply to this view</span></div><section class="list" aria-label="Job list">{''.join(cards)}{empty}<p class="empty" id="filteredEmpty" hidden>No jobs match these filters. Try another source or match score.</p></section><footer class="footer"><span class="hint">{date_label}</span><button class="reset" id="resetFilters">Reset filters</button></footer>'''
    return render_shell(heading, body, history=''.join(links), script=True)
