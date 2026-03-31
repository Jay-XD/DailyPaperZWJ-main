document.addEventListener("DOMContentLoaded", () => {
    const monthFilters = document.getElementById("monthFilters");
    const trackFilters = document.getElementById("trackFilters");
    const statusFilters = document.getElementById("statusFilters");
    const paperTypeFilters = document.getElementById("paperTypeFilters");
    const venueFilters = document.getElementById("venueFilters");
    const venueTierFilters = document.getElementById("venueTierFilters");
    const topicFilters = document.getElementById("topicFilters");
    const methodFilters = document.getElementById("methodFilters");
    const scenarioFilters = document.getElementById("scenarioFilters");
    const sortFilters = document.getElementById("sortFilters");
    const searchInput = document.getElementById("searchInput");
    const resultsCount = document.getElementById("resultsCount");
    const papersContainer = document.getElementById("papersContainer");
    const loadMoreBtn = document.getElementById("loadMoreBtn");
    const exportBtn = document.getElementById("exportBtn");
    const selectedCount = document.getElementById("selectedCount");
    const selectAllBtn = document.getElementById("selectAllBtn");
    const clearAllBtn = document.getElementById("clearAllBtn");

    const filterGroups = [
        { key: "interest_track", container: trackFilters, className: "track" },
        { key: "publication_status", container: statusFilters, className: "status" },
        { key: "paper_type", container: paperTypeFilters, className: "paper-type" },
        { key: "venues", container: venueFilters, className: "venue-name" },
        { key: "venue_tier", container: venueTierFilters, className: "venue-tier" },
        { key: "topic_tags", container: topicFilters, className: "topic" },
        { key: "method_tags", container: methodFilters, className: "method" },
        { key: "scenario_tags", container: scenarioFilters, className: "scenario" },
    ];

    const labelMaps = {
        interest_track: {
            all: "全部",
        },
        publication_status: {
            all: "全部",
        },
        paper_type: {
            all: "全部",
        },
        venue_tier: {
            all: "全部",
        },
        venues: {
            all: "全部",
        },
    };

    let indexMeta = null;
    let allPapers = [];
    let filteredPapers = [];
    let selectedPaperIds = new Set();
    let visibleCount = 30;

    const state = {
        month: "all",
        interest_track: "all",
        publication_status: "all",
        paper_type: "all",
        venues: "all",
        venue_tier: "all",
        topic_tags: "all",
        method_tags: "all",
        scenario_tags: "all",
        sort: "relevance-desc",
        search: "",
    };

    init();

    async function init() {
        try {
            const response = await fetch("data/index.json");
            indexMeta = await response.json();
            state.interest_track = indexMeta.defaults.interest_track;
            state.sort = indexMeta.defaults.sort;
            renderMonthFilters();
            bindSearch();
            bindSort();
            await loadMonthData("all");
        } catch (error) {
            console.error(error);
            papersContainer.innerHTML = `<div class="empty-state">无法加载索引数据，请检查 docs/data/index.json 是否已生成。</div>`;
        }
    }

    function bindSearch() {
        searchInput.addEventListener("input", (event) => {
            state.search = event.target.value.trim().toLowerCase();
            refreshView();
        });
    }

    function bindSort() {
        sortFilters.querySelectorAll(".sort-btn").forEach((button) => {
            button.classList.toggle("active", button.dataset.sort === state.sort);
            button.addEventListener("click", () => {
                sortFilters.querySelectorAll(".sort-btn").forEach((node) => {
                    node.classList.remove("active");
                });
                button.classList.add("active");
                state.sort = button.dataset.sort;
                refreshView();
            });
        });
    }

    async function loadMonthData(month) {
        state.month = month;
        resultsCount.textContent = "加载中...";
        papersContainer.innerHTML = `<div class="empty-state">正在加载论文数据...</div>`;

        if (month === "all") {
            allPapers = [];
            for (const monthInfo of indexMeta.months) {
                const papers = await fetchMonth(monthInfo.month);
                allPapers.push(...papers);
            }
        } else {
            allPapers = await fetchMonth(month);
        }

        refreshView();
    }

    async function fetchMonth(month) {
        const response = await fetch(`data/${month}.json`);
        return await response.json();
    }

    function renderMonthFilters() {
        const buttons = [
            createFilterButton({
                key: "month",
                value: "all",
                label: `全部 (${indexMeta.months.reduce((sum, item) => sum + item.count, 0)})`,
                active: true,
                className: "month",
                onClick: () => setMonth("all"),
            }),
        ];

        indexMeta.months.forEach((monthInfo) => {
            buttons.push(
                createFilterButton({
                    key: "month",
                    value: monthInfo.month,
                    label: `${monthInfo.month} (${monthInfo.count})`,
                    active: false,
                    className: "month",
                    onClick: () => setMonth(monthInfo.month),
                })
            );
        });

        monthFilters.replaceChildren(...buttons);
    }

    function setMonth(month) {
        monthFilters.querySelectorAll(".filter-btn").forEach((button) => {
            button.classList.toggle("active", button.dataset.value === month);
        });
        loadMonthData(month);
    }

    function refreshView() {
        visibleCount = 30;
        renderDynamicFilters();
        applyFilters();
        renderPapers();
        updateSelectedCount();
    }

    function renderDynamicFilters() {
        filterGroups.forEach((group) => {
            const options = indexMeta.filters[group.key] || [];
            const basePapers = getFilteredPapers(group.key);

            const buttons = [
                createFilterButton({
                    key: group.key,
                    value: "all",
                    label: `${getLabel(group.key, "all")} (${basePapers.length})`,
                    active: state[group.key] === "all",
                    className: `${group.className} ${state[group.key]}`,
                    onClick: () => setFilter(group.key, "all"),
                    title: getTitle(group.key, "all"),
                }),
            ];

            options.forEach((option) => {
                const count = basePapers.filter((paper) => matchesFilter(paper, group.key, option.value)).length;
                if (count === 0 && state[group.key] !== option.value) {
                    return;
                }

                buttons.push(
                    createFilterButton({
                        key: group.key,
                        value: option.value,
                        label: `${option.label} (${count})`,
                        active: state[group.key] === option.value,
                        className: `${group.className} ${option.value}`,
                        onClick: () => setFilter(group.key, option.value),
                        title: option.title || option.label,
                    })
                );
            });

            group.container.replaceChildren(...buttons);
        });
    }

    function createFilterButton({ key, value, label, active, className, onClick, title }) {
        const button = document.createElement("button");
        const keyToken = safeToken(key);
        const valueToken = safeToken(value);
        const extraClasses = (className || "")
            .split(/\s+/)
            .filter(Boolean)
            .map((token) => safeToken(token))
            .join(" ");
        button.type = "button";
        button.className = `filter-btn ${keyToken}-${valueToken} ${extraClasses}`.trim();
        button.dataset.key = key;
        button.dataset.value = value;
        button.textContent = label;
        if (title) {
            button.title = title;
        }
        if (active) {
            button.classList.add("active");
        }
        button.addEventListener("click", onClick);
        return button;
    }

    function setFilter(key, value) {
        state[key] = value;
        refreshView();
    }

    function applyFilters() {
        filteredPapers = getFilteredPapers(null).sort(sortPapers);
        resultsCount.textContent = `显示 ${filteredPapers.length} / ${allPapers.length} 篇`;
    }

    function getFilteredPapers(excludedKey) {
        return allPapers.filter((paper) => {
            for (const key of [
                "interest_track",
                "publication_status",
                "paper_type",
                "venues",
                "venue_tier",
                "topic_tags",
                "method_tags",
                "scenario_tags",
            ]) {
                if (key === excludedKey) {
                    continue;
                }
                if (!matchesFilter(paper, key, state[key])) {
                    return false;
                }
            }

            if (state.search) {
                const haystack = [
                    paper.title,
                    (paper.authors || []).join(" "),
                    paper.abstract,
                    paper.venue_name,
                    paper.venue_acronym,
                    paper.venue_filter_label,
                    paper.paper_type,
                    paper.source_provider,
                    (paper.tags || []).join(" "),
                ]
                    .filter(Boolean)
                    .join(" ")
                    .toLowerCase();
                if (!haystack.includes(state.search)) {
                    return false;
                }
            }

            return true;
        });
    }

    function matchesFilter(paper, key, value) {
        if (value === "all") {
            return true;
        }

        if (key === "venues") {
            return (paper.venue_filter_value || "") === value;
        }

        if (key === "interest_track" || key === "publication_status" || key === "paper_type" || key === "venue_tier") {
            return (paper[key] || "other") === value;
        }

        const values = paper[key] || [];
        return values.includes(value);
    }

    function sortPapers(left, right) {
        const leftDate = Date.parse(left.published || "1970-01-01");
        const rightDate = Date.parse(right.published || "1970-01-01");
        const leftScore = Number(left.relevance_score || 0);
        const rightScore = Number(right.relevance_score || 0);

        if (state.sort === "date-asc") {
            return leftDate - rightDate || rightScore - leftScore;
        }
        if (state.sort === "date-desc") {
            return rightDate - leftDate || rightScore - leftScore;
        }
        return rightScore - leftScore || rightDate - leftDate;
    }

    function renderPapers() {
        if (filteredPapers.length === 0) {
            papersContainer.innerHTML = `<div class="empty-state">当前筛选条件下没有论文。可以尝试切到次级兴趣轨或放宽 Venue / 文献类型条件。</div>`;
            loadMoreBtn.disabled = true;
            return;
        }

        const papersToRender = filteredPapers.slice(0, visibleCount);
        papersContainer.innerHTML = papersToRender.map(createPaperCard).join("");
        bindCardEvents();

        loadMoreBtn.disabled = visibleCount >= filteredPapers.length;
        loadMoreBtn.textContent = loadMoreBtn.disabled
            ? "已经到底"
            : `加载更多 (${filteredPapers.length - visibleCount} 篇待显示)`;
    }

    loadMoreBtn.addEventListener("click", () => {
        visibleCount += 30;
        renderPapers();
        updateSelectedCount();
    });

    function bindCardEvents() {
        papersContainer.querySelectorAll(".paper-checkbox").forEach((checkbox) => {
            checkbox.addEventListener("change", () => {
                if (checkbox.checked) {
                    selectedPaperIds.add(checkbox.dataset.paperId);
                } else {
                    selectedPaperIds.delete(checkbox.dataset.paperId);
                }
                updateSelectedCount();
            });
        });
    }

    function createPaperCard(paper) {
        const paperKey = paper.arxiv_id || paper.doi || paper.id || "paper";
        const paperId = escapeAttribute(paperKey);
        const paperUrl = paper.arxiv_url || paper.doi_url || paper.source_url || paper.pdf_url || "#";
        const pdfUrl = paper.pdf_url ? escapeAttribute(paper.pdf_url) : "";
        const arxivUrl = paper.arxiv_url ? escapeAttribute(paper.arxiv_url) : "";
        const doiUrl = paper.doi_url ? escapeAttribute(paper.doi_url) : "";
        const sourceUrl = paper.source_url ? escapeAttribute(paper.source_url) : "";
        const projectLink = paper.project_link ? `<a class="link-btn" href="${escapeAttribute(paper.project_link)}" target="_blank" rel="noreferrer">Project</a>` : "";
        const codeLink = paper.code_link ? `<a class="link-btn" href="${escapeAttribute(paper.code_link)}" target="_blank" rel="noreferrer">Code</a>` : "";
        const venueLabel = paper.venue_filter_label || paper.venue_acronym || paper.venue_name || "";
        const venuePill = paper.venue_name
            ? `<span class="meta-pill venue-${escapeHtml(paper.venue_tier || "other")}" title="${escapeAttribute(paper.venue_name)}">${escapeHtml(venueLabel)}</span>`
            : "";
        const statusPill = `<span class="meta-pill status-${escapeHtml(paper.publication_status || "unknown")}">${escapeHtml(getLabel("publication_status", paper.publication_status || "unknown"))}</span>`;
        const paperTypePill = `<span class="meta-pill">${escapeHtml(getLabel("paper_type", paper.paper_type || "other"))}</span>`;
        const scorePill = `<span class="meta-pill">相关性 ${escapeHtml(String(paper.relevance_score || 0))}</span>`;
        const trackPill = `<span class="meta-pill">${escapeHtml(getLabel("interest_track", paper.interest_track || "other"))}</span>`;
        const sourcePill = `<span class="meta-pill">${escapeHtml((paper.source_provider || "unknown").toUpperCase())}</span>`;

        const linkButtons = [];
        if (arxivUrl) {
            linkButtons.push(`<a class="link-btn" href="${arxivUrl}" target="_blank" rel="noreferrer">ArXiv</a>`);
        }
        if (pdfUrl) {
            linkButtons.push(`<a class="link-btn" href="${pdfUrl}" target="_blank" rel="noreferrer">PDF</a>`);
        }
        if (doiUrl) {
            linkButtons.push(`<a class="link-btn" href="${doiUrl}" target="_blank" rel="noreferrer">DOI</a>`);
        }
        if (sourceUrl && sourceUrl !== doiUrl && sourceUrl !== arxivUrl) {
            linkButtons.push(`<a class="link-btn" href="${sourceUrl}" target="_blank" rel="noreferrer">Venue</a>`);
        }
        if (projectLink) {
            linkButtons.push(projectLink);
        }
        if (codeLink) {
            linkButtons.push(codeLink);
        }

        return `
            <article class="paper-card">
                <div class="paper-head">
                    <label class="paper-select">
                        <input
                            class="paper-checkbox"
                            type="checkbox"
                            data-paper-id="${paperId}"
                            ${selectedPaperIds.has(paperKey) ? "checked" : ""}
                        >
                    </label>
                    <div>
                        <h2 class="paper-title">
                            <a href="${escapeAttribute(paperUrl)}" target="_blank" rel="noreferrer">${escapeHtml(paper.title || "Untitled")}</a>
                        </h2>
                        <div class="paper-meta">
                            <span class="meta-pill">${escapeHtml(paper.published || "未知日期")}</span>
                            ${statusPill}
                            ${paperTypePill}
                            ${trackPill}
                            ${scorePill}
                            ${sourcePill}
                            ${venuePill}
                        </div>
                    </div>
                    <div class="paper-meta">
                        <span class="meta-pill">${escapeHtml(paper.primary_category || "unknown")}</span>
                    </div>
                </div>

                <div class="paper-authors">${escapeHtml((paper.authors || []).join(", "))}</div>

                <div class="tag-groups">
                    ${renderTagRow("Topic", paper.topic_tags || [], "topic")}
                    ${renderTagRow("Method", paper.method_tags || [], "method")}
                    ${renderTagRow("Scenario", paper.scenario_tags || [], "scenario")}
                </div>

                <div class="paper-reasons">${escapeHtml((paper.match_reasons || []).slice(0, 5).join(" | "))}</div>

                <div class="paper-abstract">
                    <details>
                        <summary>查看摘要</summary>
                        <p>${escapeHtml(paper.abstract || "")}</p>
                    </details>
                </div>

                <div class="paper-links">
                    ${linkButtons.join("")}
                </div>
            </article>
        `;
    }

    function renderTagRow(label, values, kind) {
        if (!values.length) {
            return "";
        }
        return `
            <div class="tag-group-row">
                <div class="tag-label">${escapeHtml(label)}</div>
                <div class="tag-row">
                    ${values.map((value) => `<span class="tag-chip ${kind}">${escapeHtml(value)}</span>`).join("")}
                </div>
            </div>
        `;
    }

    function getLabel(key, value) {
        if (labelMaps[key] && labelMaps[key][value]) {
            return labelMaps[key][value];
        }
        const options = indexMeta?.filters?.[key] || [];
        const found = options.find((item) => item.value === value);
        return found ? found.label : value;
    }

    function getTitle(key, value) {
        const options = indexMeta?.filters?.[key] || [];
        const found = options.find((item) => item.value === value);
        return found ? (found.title || found.label) : value;
    }

    function updateSelectedCount() {
        selectedCount.textContent = String(selectedPaperIds.size);
    }

    selectAllBtn.addEventListener("click", () => {
        filteredPapers.forEach((paper) => {
            selectedPaperIds.add(paper.arxiv_id || paper.doi || paper.id);
        });
        renderPapers();
        updateSelectedCount();
    });

    clearAllBtn.addEventListener("click", () => {
        selectedPaperIds.clear();
        renderPapers();
        updateSelectedCount();
    });

    exportBtn.addEventListener("click", () => {
        if (selectedPaperIds.size === 0) {
            alert("请先选择至少一篇论文。");
            return;
        }

        const selected = allPapers.filter((paper) => selectedPaperIds.has(paper.arxiv_id || paper.doi || paper.id));
        const bibtex = selected.map(toBibtex).join("\n\n");
        downloadFile(bibtex, "daily-paper-selection.bib", "text/plain");
    });

    function toBibtex(paper) {
        const paperId = (paper.arxiv_id || paper.doi || paper.id || "paper").replace(/[^\w]+/g, "_");
        const authors = (paper.authors || []).join(" and ");
        const year = (paper.published || "1970").slice(0, 4);
        const entryType = paper.venue_type === "conference" ? "inproceedings" : "article";
        const venueField = paper.venue_type === "journal" ? "journal" : "booktitle";
        const venueLine = paper.venue_name ? `,\n  ${venueField}={${paper.venue_name}}` : "";
        const doiLine = paper.doi ? `,\n  doi={${paper.doi}}` : "";
        return `@${entryType}{${paperId},
  title={${paper.title}},
  author={${authors}},
  year={${year}}${venueLine}${doiLine},
  note={interest_track=${paper.interest_track || "other"}; relevance_score=${paper.relevance_score || 0}}
}`;
    }

    function downloadFile(content, filename, type) {
        const blob = new Blob([content], { type });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
    }

    function escapeHtml(value) {
        return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    function escapeAttribute(value) {
        return escapeHtml(value);
    }

    function safeToken(value) {
        return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-");
    }
});
