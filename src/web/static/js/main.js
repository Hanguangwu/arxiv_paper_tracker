/* =========================================================================
 * ArXiv Paper Radar - Frontend application logic
 * Works in two modes:
 *   - dynamic (Flask): fetches /api/... endpoints
 *   - static (GitHub Pages / docs deployment): fetches the generated JSON
 *     files under /data/... and renders markdown with `marked`.
 * Mode is selected by window.APP_BASE / window.STATIC_MODE injected into
 * index.html by Flask (render_template) or by src/web/export_static.py.
 * Depends only on Bootstrap 5 (bundle) + native DOM API. All interactions use
 * event delegation; no inline onclick handlers.
 * ========================================================================= */
'use strict';

/* ---------- Mode resolution ---------- */
const STATIC_MODE = window.STATIC_MODE === true;
const BASE = String(window.APP_BASE || '').replace(/\/+$/, '');

function staticFileFor(urlPath) {
    const p = String(urlPath).split('?')[0];
    const parts = p.split('/').filter(Boolean);
    if (!parts.length || parts[0] !== 'api') return null;
    const endpoint = parts[1];
    if (endpoint === 'stats') return 'data/stats.json';
    if (endpoint === 'categories') return 'data/categories.json';
    if (endpoint === 'papers' && parts.length === 2) return 'data/papers/latest.json';
    if (endpoint === 'summaries') return 'data/summaries/latest.json';
    if (endpoint === 'analysis') return 'data/analysis/latest.json';
    if (endpoint === 'wordcloud') return 'data/analysis/latest.json';
    if (endpoint === 'history' && parts.length === 2) return 'data/records/index.json';
    if (endpoint === 'history' && parts.length === 3) return 'data/summaries/summaries_' + parts[2] + '.json';
    return null;
}

/* ---------- Shared utilities ---------- */

function tNoData() {
    return '<div class="state"><i class="bi bi-inboxes"></i><span>No data</span></div>';
}

function tNo(msg) {
    return '<div class="state"><i class="bi bi-inboxes"></i><span>' + (msg || 'No data') + '</span></div>';
}

function tError(msg) {
    return '<div class="state"><i class="bi bi-exclamation-triangle"></i><span>' +
        (msg || 'Failed to load data') + '</span></div>';
}

function spinner() {
    return '<div class="state"><div class="spin"></div><span>Loading...</span></div>';
}

function finger(n) {
    return (typeof n === 'number' ? n : 0).toLocaleString('en-US');
}

function esc(text) {
    return String(text == null ? '' : text).replace(/[&<>"']/g, function (m) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
    });
}

function kwWord(kw) {
    return kw.word || kw.keyword;
}

function authors(list) {
    if (!list || !list.length) return 'Unknown authors';
    if (list.length <= 3) return list.join(', ');
    return list.slice(0, 3).join(', ') + ' et al. (' + list.length + ')';
}

function renderMarkdown(text) {
    if (window.marked && marked.parse) {
        try { return marked.parse(String(text)); } catch (e) { /* fall through */ }
    }
    return '<p>' + esc(text).replace(/\n/g, '<br>') + '</p>';
}

function llmFieldHtml(llm, key) {
    const html = llm[key + '_html'];
    if (html) return html;
    if (llm[key]) {
        return STATIC_MODE ? renderMarkdown(llm[key]) : '<p>' + esc(llm[key]).replace(/\n/g, '<br>') + '</p>';
    }
    return '';
}

function llmFieldPlain(llm, key) {
    return llm[key + '_html'] || llm[key] || '';
}

function wordcloudUrl(wc) {
    if (!wc) return null;
    const path = (typeof wc.path === 'string' && wc.path) ? wc.path
        : (typeof wc === 'string' ? wc : null);
    if (!path) return null;
    return BASE + '/data/analysis/' + path.split(/[\\/]/).pop();
}

const $ = (id) => document.getElementById(id);

/** Unified fetch: resolves to the API (dynamic) or a static JSON file (static). */
async function api(url) {
    let res;
    const target = STATIC_MODE ? BASE + '/' + staticFileFor(url) : url;
    try {
        res = await fetch(target);
    } catch (e) {
        throw new Error('Network request failed');
    }
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (!res.ok) {
        const msg = (data && (data.message || data.error)) || 'Request failed';
        throw new Error(msg);
    }
    return data;
}

/* ---------- Overview ---------- */
async function loadStats() {
    try {
        const d = await api('/api/stats');
        $('stat-papers').textContent = finger(d.papers_count);
        $('stat-summaries').textContent = finger(d.summaries_count);
        $('stat-categories').textContent = finger(d.categories_count);
        $('stat-keywords').textContent = finger(d.keywords_count);
        $('stat-update').textContent = d.last_update || '—';
        $('stat-days').textContent = finger(d.total_days);
        if (!d.papers_count) {
            $('stat-papers-hint').textContent = 'No data';
            $('stat-categories-hint').textContent = 'No data';
        }
    } catch (e) {
        $('stat-update').textContent = 'Load failed';
    }
}

/* ---------- Category dropdown ---------- */
async function initCategories() {
    const sel = $('papers-category');
    try {
        const list = await api('/api/categories');
        list.forEach(function (c) {
            const opt = document.createElement('option');
            opt.value = c.name;
            opt.textContent = c.name + ' (' + c.count + ')';
            sel.appendChild(opt);
        });
    } catch (e) { /* no category data */ }
}

/* ---------- Paper list ---------- */
const papersState = { page: 1, perPage: 20, q: '', category: '' };

function filterPapers(all) {
    let list = all || [];
    if (papersState.category) {
        list = list.filter(function (p) {
            return (p.categories || []).indexOf(papersState.category) >= 0;
        });
    }
    if (papersState.q) {
        const ql = papersState.q.toLowerCase();
        list = list.filter(function (p) {
            const hay = [
                String(p.title || ''),
                (p.authors || []).join(' '),
                String(p.abstract || '')
            ].join(' ').toLowerCase();
            return hay.indexOf(ql) >= 0;
        });
    }
    return list;
}

function attachSummaryFlag(list) {
    // Mark papers that already carry a summary (from summaries json merged earlier).
    return list.map(function (p) {
        if (p.summary) { p.__hasSummary = true; }
        return p;
    });
}

async function loadPapers() {
    const box = $('papers-list');
    box.innerHTML = spinner();
    try {
        const d = await api('/api/papers?' + new URLSearchParams({
            page: papersState.page,
            per_page: papersState.perPage,
            q: papersState.q,
            category: papersState.category,
        }).toString());

        let papers, totalPages;
        if (STATIC_MODE) {
            const all = attachSummaryFlag(d.papers || []);
            const filtered = filterPapers(all);
            const total = filtered.length;
            totalPages = Math.max(1, Math.ceil(total / papersState.perPage));
            const start = (papersState.page - 1) * papersState.perPage;
            papers = filtered.slice(start, start + papersState.perPage);
            $('papers-count-line').textContent = total + ' papers';
        } else {
            papers = (d.papers || []).map(function (p) { if (p.summary) p.__hasSummary = true; return p; });
            totalPages = d.total_pages || 0;
            $('papers-count-line').textContent = 'Total ' + d.total + ' papers';
        }

        if (!papers.length) {
            box.innerHTML = tNo('No matching papers');
            renderPagination(0);
            return;
        }
        box.innerHTML = papers.map(paperCard).join('');
        renderPagination(totalPages);
    } catch (e) {
        box.innerHTML = tError(e.message);
        renderPagination(0);
    }
}

function paperCard(p) {
    const cats = (p.categories || []).map(function (c) {
        const active = c === p.primary_category;
        return '<span class="chip' + (active ? '' : ' chip-ghost') + '">' + esc(c) + '</span>';
    }).join(' ');
    const publishedDate = (p.published_date || p.published || '').toString().slice(0, 10);
    return '' +
        '<article class="paper-card">' +
            '<h3><a href="' + esc(p.entry_url || p.pdf_url || '#') + '" target="_blank" rel="noopener">' + esc(p.title) + '</a></h3>' +
            '<div class="paper-authors"><i class="bi bi-person-badge"></i> ' + esc(authors(p.authors)) + '</div>' +
            '<p class="paper-abstract">' + esc(p.abstract) + '</p>' +
            '<div class="d-flex flex-wrap gap-2 align-items-center">' + cats +
                '<span class="stat-pill"><i class="bi bi-calendar3"></i> ' + esc(publishedDate || 'No date') + '</span>' +
                (p.__hasSummary ? '<span class="stat-pill notag"><i class="bi bi-stars"></i> Analyzed</span>' : '') +
                '<span class="ms-auto d-flex gap-2">' +
                    '<button class="btn btn-sm" data-action="analysis" data-id="' + esc(p.id) +
                        '" style="border-radius:999px;background:var(--accent);color:#fff;border-color:var(--accent);">' +
                        '<i class="bi bi-stars"></i> View analysis</button>' +
                    '<a class="btn btn-sm btn-outline-secondary" style="border-radius:999px;" href="' +
                        esc(p.entry_url || p.pdf_url || '#') + '" target="_blank" rel="noopener">' +
                        '<i class="bi bi-box-arrow-up-right"></i> arXiv original</a>' +
                '</span>' +
            '</div>' +
        '</article>';
}

function renderPagination(totalPages) {
    const ul = $('papers-pagination');
    ul.innerHTML = '';
    if (!totalPages || totalPages <= 1) return;
    const cur = papersState.page;

    const btn = function (label, page, cls) {
        const li = document.createElement('li');
        li.className = 'page-item ' + (cls || '');
        const a = document.createElement('button');
        a.className = 'page-link';
        a.type = 'button';
        a.innerHTML = label;
        if (!cls || cls.indexOf('disabled') < 0) {
            a.addEventListener('click', function () { papersState.page = page; loadPapers(); });
        }
        li.appendChild(a);
        ul.appendChild(li);
    };

    btn('&laquo;', cur - 1, cur <= 1 ? 'disabled' : '');
    const start = Math.max(1, cur - 2), end = Math.min(totalPages, cur + 2);
    for (let p = start; p <= end; p++) btn(p, p, p === cur ? 'active' : '');
    btn('&raquo;', cur + 1, cur >= totalPages ? 'disabled' : '');
}

/* ---------- Paper detail modal ---------- */
function openPaper(id) {
    const title = $('paperModal-title');
    const body = $('paperModal-body');
    title.textContent = 'Loading...';
    body.innerHTML = spinner();

    const done = function (p) {
        title.textContent = p.title || id;
        body.innerHTML = paperDetailHtml(p);
    };
    const fail = function (e) {
        body.innerHTML = tError(e.message);
    };

    if (STATIC_MODE) {
        loadStaticPaper(id).then(done).catch(fail);
    } else {
        api('/api/papers/' + encodeURIComponent(id)).then(done).catch(fail);
    }

    bootstrap.Modal.getOrCreateInstance($('paperModal')).show();
}

async function loadStaticPaper(id) {
    const papersData = await api('/api/papers');
    const paper = (papersData.papers || []).find(function (p) { return p.id === id; });
    if (!paper) throw new Error('Paper not found');
    const sumsData = await api('/api/summaries');
    const sum = (sumsData.papers || []).find(function (s) { return s.id === id; });
    if (sum && sum.summary) {
        paper.summary = sum.summary;
        paper.summary_html = renderMarkdown(sum.summary);
    }
    return paper;
}

function paperDetailHtml(p) {
    const cats = (p.categories || []).map(function (c) {
        return '<span class="chip">' + esc(c) + '</span>';
    }).join(' ');

    let summaryHtml;
    if (p.summary_html) {
        summaryHtml = p.summary_html;
    } else if (p.summary) {
        summaryHtml = STATIC_MODE ? renderMarkdown(p.summary) : '<p>' + esc(p.summary) + '</p>';
    } else {
        summaryHtml = '';
    }

    const metaRows = [
        ['Authors', authors(p.authors)],
        ['Primary category', p.primary_category || '—'],
        ['Published', (p.published || '—').toString().replace('T', ' ').slice(0, 16)],
        ['Updated', (p.updated || '—').toString().replace('T', ' ').slice(0, 16)],
    ].map(function (r) {
        return '<div><span class="k">' + esc(r[0]) + '</span>: ' + esc(r[1]) + '</div>';
    }).join('');

    return '' +
        '<div class="meta-grid">' + metaRows + '</div>' +
        '<div class="d-flex flex-wrap gap-2 mt-3">' + cats + '</div>' +
        '<div class="section-title"><i class="bi bi-file-text"></i> Abstract</div>' +
        '<p class="text-muted">' + esc(p.abstract) + '</p>' +
        '<div class="section-title"><i class="bi bi-stars"></i> AI six-section analysis</div>' +
        (summaryHtml ? '<div class="summary-body">' + summaryHtml + '</div>'
                     : '<div>' + tNo('No AI analysis for this paper') + '</div>') +
        '<div class="d-flex gap-2 mt-4">' +
            '<a class="btn btn-dark" style="border-radius:999px;" href="' + esc(p.entry_url || '#') + '" target="_blank" rel="noopener">' +
                '<i class="bi bi-box-arrow-up-right"></i> arXiv page</a>' +
            '<a class="btn btn-outline-secondary" style="border-radius:999px;" href="' + esc(p.pdf_url || '#') + '" target="_blank" rel="noopener">' +
                '<i class="bi bi-file-earmark-pdf"></i> PDF</a>' +
        '</div>';
}

/* ---------- Trend analysis ---------- */
async function loadAnalysis() {
    const kwBox = $('trend-keywords');
    const wcBox = $('trend-wordcloud');

    let analysis = null;
    try { analysis = await api('/api/analysis'); } catch (e) { /* empty-state handled */ }

    if (analysis) {
        $('trend-date').textContent = analysis.date || '—';
        const kws = (analysis.keywords || []).slice(0, 30);
        kwBox.innerHTML = kws.length
            ? kws.map(function (k) {
                const score = typeof k.score === 'number' ? (Math.round(k.score * 1000) / 10) : '';
                return '<span class="kw-chip">' + esc(kwWord(k)) +
                    (score !== '' ? '<span class="score">' + score + '</span>' : '') + '</span>';
            }).join('')
            : tNo('No keywords');
        renderLLM(analysis.llm_analysis || {});
    } else {
        kwBox.innerHTML = tNoData();
        renderLLM({});
    }

    try {
        const wc = await api('/api/wordcloud');
        const url = STATIC_MODE ? wordcloudUrl(wc) : wc.url;
        wcBox.innerHTML = url
            ? '<img src="' + esc(url) + '" alt="Word cloud" loading="lazy">'
            : '<div class="state"><i class="bi bi-cloud-slash"></i><span>No word cloud image</span></div>';
    } catch (e) {
        wcBox.innerHTML = tError('Failed to load word cloud');
    }
}

function renderLLM(llm) {
    const wrap = $('llm-wrapper');
    const sections = [
        ['fire', 'Research Hotspots', llmFieldHtml(llm, 'hotspots'), llmFieldPlain(llm, 'hotspots')],
        ['arrow-up-right-circle', 'Technology Trends & Evolution', llmFieldHtml(llm, 'trends'), llmFieldPlain(llm, 'trends')],
        ['compass', 'Future Directions', llmFieldHtml(llm, 'future_directions'), llmFieldPlain(llm, 'future_directions')],
        ['clipboard2-check', 'Analysis Summary', llmFieldHtml(llm, 'analysis_summary'), llmFieldPlain(llm, 'analysis_summary')],
    ];

    if (!sections.some(function (s) { return s[2] || s[3]; })) {
        wrap.innerHTML = '<div class="col-12">' + tNo('No AI deep analysis') + '</div>';
        return;
    }

    wrap.innerHTML = sections.map(function (s, i) {
        const html = s[2] || '';
        return '<div class="col-12 analysis-sec">' +
            '<div class="card-e p-3">' +
                '<h5><i class="bi bi-' + s[0] + '"></i>' +
                    '<span class="badge rounded-pill me-1" style="background:var(--accent);">' + (i + 1) + '</span>' + s[1] +
                '</h5>' +
                '<div class="analysis-body">' + (html || '<span class="text-muted">No content</span>') + '</div>' +
            '</div>' +
        '</div>';
    }).join('');
}

/* ---------- History ---------- */
async function loadHistory() {
    const box = $('history-list');
    box.innerHTML = spinner();
    try {
        const d = await api('/api/history');
        const records = d.records || [];
        if (!records.length) { box.innerHTML = tNoData(); return; }
        box.innerHTML = records.map(function (r) {
            const ok = !r.status || r.status === 'success' || r.status === 'ok';
            return '' +
                '<button class="hist-row" type="button" data-date="' + esc(r.date) + '">' +
                    '<span class="hist-date">' + esc(r.date) + '</span>' +
                    '<span class="hist-badge ' + (ok ? 'ok' : 'fail') + '">' + esc(r.status || 'success') + '</span>' +
                    '<span class="hist-meta">' +
                        '<i class="bi bi-journal-text"></i> ' + (r.papers_count || 0) + ' papers' +
                        ' · <i class="bi bi-stars"></i> ' + (r.summaries_count || 0) + ' summaries' +
                        (r.email_sent ? ' · <i class="bi bi-envelope-check text-success"></i> emailed' : '') +
                        (r.duration_seconds ? ' · <i class="bi bi-stopwatch"></i> ' + r.duration_seconds + 's' : '') +
                        (r.error ? ' · <span class="notag">' + esc(r.error) + '</span>' : '') +
                    '</span>' +
                    '<i class="bi bi-chevron-right ms-auto" style="color:var(--ink-soft)"></i>' +
                '</button>';
        }).join('');
    } catch (e) {
        box.innerHTML = tError(e.message);
    }
}

async function openHistory(date) {
    const modalTitle = $('historyModal-title');
    const body = $('historyModal-body');
    modalTitle.textContent = date + ' · Summary';
    body.innerHTML = spinner();
    try {
        const d = await api('/api/history/' + date);
        const papers = d.papers || [];
        if (!papers.length) { body.innerHTML = tNoData(); return; }
        body.innerHTML = papers.map(function (p) {
            const sh = p.summary_html ||
                (p.summary ? (STATIC_MODE ? renderMarkdown(p.summary) : '<p>' + esc(p.summary) + '</p>') : '');
            return '' +
                '<div class="card-e p-3 mb-3">' +
                    '<h6 class="fw-bold">' + esc(p.title || 'Unknown title') + '</h6>' +
                    '<div class="paper-authors mb-2">' + esc(authors(p.authors)) + '</div>' +
                    (sh
                        ? '<div class="summary-body">' + sh + '</div>'
                        : '<div>' + tNo('No summary') + '</div>') +
                '</div>';
        }).join('');
    } catch (e) {
        body.innerHTML = tError(e.message);
    }
    bootstrap.Modal.getOrCreateInstance($('historyModal')).show();
}

/* ---------- Event binding (all via delegation, no inline handlers) ---------- */
function bindEvents() {
    let timer = null;
    $('papers-search').addEventListener('input', function (e) {
        clearTimeout(timer);
        timer = setTimeout(function () {
            papersState.q = e.target.value.trim();
            papersState.page = 1;
            loadPapers();
        }, 350);
    });

    $('papers-category').addEventListener('change', function (e) {
        papersState.category = e.target.value;
        papersState.page = 1;
        loadPapers();
    });

    document.addEventListener('click', function (e) {
        const analysisBtn = e.target.closest('[data-action="analysis"]');
        if (analysisBtn) {
            e.preventDefault();
            openPaper(analysisBtn.dataset.id);
            return;
        }
        const histBtn = e.target.closest('.hist-row');
        if (histBtn) {
            openHistory(histBtn.dataset.date);
        }
    });
}

/* ---------- Startup ---------- */
document.addEventListener('DOMContentLoaded', function () {
    loadStats();
    initCategories();
    loadPapers();
    loadAnalysis();
    loadHistory();
    bindEvents();
});