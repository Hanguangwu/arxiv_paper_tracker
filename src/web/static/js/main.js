/* =========================================================================
 * ArXiv 论文雷达 - 前端应用逻辑
 * 依赖: 仅 Bootstrap 5 (bundle) + 原生 DOM API。所有交互通过事件委托,
 *       不在内联中写任何 onclick。
 * ========================================================================= */
'use strict';

/* ---------- 通用工具 ---------- */

function tNoData() {
    return '<div class="state"><i class="bi bi-inboxes"></i><span>暂无数据</span></div>';
}

function tNo(msg) {
    return '<div class="state"><i class="bi bi-inboxes"></i><span>' + (msg || '暂无数据') + '</span></div>';
}

function tError(msg) {
    return '<div class="state"><i class="bi bi-exclamation-triangle"></i><span>' +
        (msg || '数据加载失败') + '</span></div>';
}

function spinner() {
    return '<div class="state"><div class="spin"></div><span>加载中...</span></div>';
}

function finger(n) {
    return (typeof n === 'number' ? n : 0).toLocaleString('zh-CN');
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
    if (!list || !list.length) return '未知作者';
    if (list.length <= 3) return list.join(', ');
    return list.slice(0, 3).join(', ') + ' 等 ' + list.length + ' 人';
}

const $ = (id) => document.getElementById(id);

/** 统一 fetch: 解析 JSON, 失败时抛出含中文提示的错误。 */
async function api(url) {
    let res;
    try {
        res = await fetch(url);
    } catch (e) {
        throw new Error('网络请求失败');
    }
    let data = null;
    try { data = await res.json(); } catch (e) { /* 空响应体 */ }
    if (!res.ok) {
        const msg = (data && (data.message || data.error)) || '请求失败';
        throw new Error(msg);
    }
    return data;
}

/* ---------- 概览 ---------- */
async function loadStats() {
    try {
        const d = await api('/api/stats');
        $('stat-papers').textContent = finger(d.papers_count);
        $('stat-summaries').textContent = finger(d.summaries_count);
        $('stat-categories').textContent = finger(d.categories_count);
        $('stat-keywords').textContent = finger(d.keywords_count);
        $('stat-update').textContent = d.last_update || '暂无';
        $('stat-days').textContent = finger(d.total_days);
        if (!d.papers_count) {
            $('stat-papers-hint').textContent = '暂无数据';
            $('stat-categories-hint').textContent = '暂无数据';
        }
    } catch (e) {
        $('stat-update').textContent = '加载失败';
    }
}

/* ---------- 类别下拉 ---------- */
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
    } catch (e) { /* 无类别数据 */ }
}

/* ---------- 论文列表 ---------- */
const papersState = { page: 1, perPage: 20, q: '', category: '' };

async function loadPapers() {
    const box = $('papers-list');
    box.innerHTML = spinner();
    const params = new URLSearchParams({
        page: papersState.page,
        per_page: papersState.perPage,
        q: papersState.q,
        category: papersState.category,
    });
    try {
        const d = await api('/api/papers?' + params.toString());
        $('papers-count-line').textContent = '共 ' + d.total + ' 篇';
        if (!d.papers.length) {
            box.innerHTML = tNo('暂无匹配的论文');
            renderPagination(0);
            return;
        }
        box.innerHTML = d.papers.map(paperCard).join('');
        renderPagination(d.total_pages);
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
                '<span class="stat-pill"><i class="bi bi-calendar3"></i> ' + esc(publishedDate || '暂无日期') + '</span>' +
                (p.summary ? '<span class="stat-pill notag"><i class="bi bi-stars"></i> 已分析</span>' : '') +
                '<span class="ms-auto d-flex gap-2">' +
                    '<button class="btn btn-sm" data-action="analysis" data-id="' + esc(p.id) +
                        '" style="border-radius:999px;background:var(--accent);color:#fff;border-color:var(--accent);">' +
                        '<i class="bi bi-stars"></i> 查看分析</button>' +
                    '<a class="btn btn-sm btn-outline-secondary" style="border-radius:999px;" href="' +
                        esc(p.entry_url || p.pdf_url || '#') + '" target="_blank" rel="noopener">' +
                        '<i class="bi bi-box-arrow-up-right"></i> arXiv原文</a>' +
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

/* ---------- 论文详情弹窗 ---------- */
function openPaper(id) {
    const title = $('paperModal-title');
    const body = $('paperModal-body');
    title.textContent = '加载中...';
    body.innerHTML = spinner();

    api('/api/papers/' + encodeURIComponent(id)).then(function (p) {
        title.textContent = p.title || id;
        body.innerHTML = paperDetailHtml(p);
    }).catch(function (e) {
        body.innerHTML = tError(e.message);
    });

    bootstrap.Modal.getOrCreateInstance($('paperModal')).show();
}

function paperDetailHtml(p) {
    const cats = (p.categories || []).map(function (c) {
        return '<span class="chip">' + esc(c) + '</span>';
    }).join(' ');

    let summaryHtml;
    if (p.summary_html) {
        summaryHtml = p.summary_html;
    } else if (p.summary) {
        summaryHtml = '<p>' + esc(p.summary) + '</p>';
    } else {
        summaryHtml = '';
    }

    const metaRows = [
        ['作者', authors(p.authors)],
        ['主分类', p.primary_category || '—'],
        ['发布时间', (p.published || '—').toString().replace('T', ' ').slice(0, 16)],
        ['更新日期', (p.updated || '—').toString().replace('T', ' ').slice(0, 16)],
    ].map(function (r) {
        return '<div><span class="k">' + esc(r[0]) + '</span>：' + esc(r[1]) + '</div>';
    }).join('');

    return '' +
        '<div class="meta-grid">' + metaRows + '</div>' +
        '<div class="d-flex flex-wrap gap-2 mt-3">' + cats + '</div>' +
        '<div class="section-title"><i class="bi bi-file-text"></i> 摘要</div>' +
        '<p class="text-muted">' + esc(p.abstract) + '</p>' +
        '<div class="section-title"><i class="bi bi-stars"></i> AI 六节分析</div>' +
        (summaryHtml ? '<div class="summary-body">' + summaryHtml + '</div>'
                     : '<div>' + tNo('该论文暂无 AI 分析') + '</div>') +
        '<div class="d-flex gap-2 mt-4">' +
            '<a class="btn btn-dark" style="border-radius:999px;" href="' + esc(p.entry_url || '#') + '" target="_blank" rel="noopener">' +
                '<i class="bi bi-box-arrow-up-right"></i> arXiv 原文页</a>' +
            '<a class="btn btn-outline-secondary" style="border-radius:999px;" href="' + esc(p.pdf_url || '#') + '" target="_blank" rel="noopener">' +
                '<i class="bi bi-file-earmark-pdf"></i> PDF</a>' +
        '</div>';
}

/* ---------- 趋势分析 ---------- */
async function loadAnalysis() {
    const kwBox = $('trend-keywords');
    const wcBox = $('trend-wordcloud');

    let analysis = null;
    try { analysis = await api('/api/analysis'); } catch (e) { /* 空态处理 */ }

    if (analysis) {
        $('trend-date').textContent = analysis.date || '—';
        const kws = (analysis.keywords || []).slice(0, 30);
        kwBox.innerHTML = kws.length
            ? kws.map(function (k) {
                const score = typeof k.score === 'number' ? (Math.round(k.score * 1000) / 10) : '';
                return '<span class="kw-chip">' + esc(kwWord(k)) +
                    (score !== '' ? '<span class="score">' + score + '</span>' : '') + '</span>';
            }).join('')
            : tNo('暂无关键词');
        renderLLM(analysis.llm_analysis || {});
    } else {
        kwBox.innerHTML = tNoData();
        renderLLM({});
    }

    try {
        const wc = await api('/api/wordcloud');
        wcBox.innerHTML = wc.url
            ? '<img src="' + esc(wc.url) + '" alt="词云图" loading="lazy">'
            : '<div class="state"><i class="bi bi-cloud-slash"></i><span>暂无词云图片</span></div>';
    } catch (e) {
        wcBox.innerHTML = tError('词云加载失败');
    }
}

function renderLLM(llm) {
    const wrap = $('llm-wrapper');
    const sections = [
        ['fire', '研究热点', llm.hotspots, llm.hotspots_html],
        ['arrow-up-right-circle', '技术趋势与演进', llm.trends, llm.trends_html],
        ['compass', '未来发展方向', llm.future_directions, llm.future_directions_html],
        ['clipboard2-check', '分析总结', llm.analysis_summary, llm.analysis_summary_html],
    ];

    if (!sections.some(function (s) { return s[2] || s[3]; })) {
        wrap.innerHTML = '<div class="col-12">' + tNo('暂无 AI 深度分析') + '</div>';
        return;
    }

    wrap.innerHTML = sections.map(function (s, i) {
        const html = s[3] || (s[2] ? '<p>' + esc(s[2]).replace(/\n/g, '<br>') + '</p>' : '');
        return '<div class="col-12 analysis-sec">' +
            '<div class="card-e p-3">' +
                '<h5><i class="bi bi-' + s[0] + '"></i>' +
                    '<span class="badge rounded-pill me-1" style="background:var(--accent);">' + (i + 1) + '</span>' + s[1] +
                '</h5>' +
                '<div class="analysis-body">' + (html || '<span class="text-muted">暂无内容</span>') + '</div>' +
            '</div>' +
        '</div>';
    }).join('');
}

/* ---------- 历史记录 ---------- */
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
                        '<i class="bi bi-journal-text"></i> ' + (r.papers_count || 0) + ' 篇' +
                        ' · <i class="bi bi-stars"></i> ' + (r.summaries_count || 0) + ' 摘要' +
                        (r.email_sent ? ' · <i class="bi bi-envelope-check text-success"></i> 已发邮件' : '') +
                        (r.took ? ' · <i class="bi bi-stopwatch"></i> ' + r.took + 's' : '') +
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
    modalTitle.textContent = date + ' · 当日总结';
    body.innerHTML = spinner();
    try {
        const d = await api('/api/history/' + date);
        const papers = d.papers || [];
        if (!papers.length) { body.innerHTML = tNoData(); return; }
        body.innerHTML = papers.map(function (p) {
            return '' +
                '<div class="card-e p-3 mb-3">' +
                    '<h6 class="fw-bold">' + esc(p.title || '未知标题') + '</h6>' +
                    '<div class="paper-authors mb-2">' + esc(authors(p.authors)) + '</div>' +
                    (p.summary_html
                        ? '<div class="summary-body">' + p.summary_html + '</div>'
                        : (p.summary ? '<p>' + esc(p.summary) + '</p>' : '<div>' + tNo('无摘要') + '</div>')) +
                '</div>';
        }).join('');
    } catch (e) {
        body.innerHTML = tError(e.message);
    }
    bootstrap.Modal.getOrCreateInstance($('historyModal')).show();
}

/* ---------- 事件绑定 (全部通过委托, 无内联) ---------- */
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

/* ---------- 启动 ---------- */
document.addEventListener('DOMContentLoaded', function () {
    loadStats();
    initCategories();
    loadPapers();
    loadAnalysis();
    loadHistory();
    bindEvents();
});