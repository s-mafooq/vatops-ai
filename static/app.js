const state = {
    invoiceFiles: [],
    records: [],
    bankLoaded: false,
    bankCount: 0,
};

if (!document.cookie.includes("vatops_session")) {
    document.cookie = `vatops_session=session_${Date.now()}; path=/`;
}

// ── Navigation ──────────────────────────────────────────────────────────────
document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
});

function switchView(view) {
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    document.querySelector(`[data-view="${view}"]`).classList.add("active");
    document.getElementById(`view-${view}`).classList.add("active");
    if (view === "review") renderReview();
    if (view === "audit") loadAudit();
}

// ── Bank upload ──────────────────────────────────────────────────────────────
const bankDrop = document.getElementById("bank-drop");
const bankInput = document.getElementById("bank-input");

bankDrop.addEventListener("click", () => bankInput.click());
bankInput.addEventListener("change", () => { if (bankInput.files[0]) uploadBank(bankInput.files[0]); });
setupDragDrop(bankDrop, file => uploadBank(file));

async function uploadBank(file) {
    const status = document.getElementById("bank-status");
    status.innerHTML = '<span class="badge badge-gray">Uploading...</span>';
    const form = new FormData();
    form.append("file", file);
    try {
        const res = await fetch("/api/bank", { method: "POST", body: form });
        const data = await res.json();
        if (res.ok) {
            state.bankLoaded = true;
            state.bankCount = data.count;
            status.innerHTML = `<span class="badge badge-green">✓ ${data.count} transactions loaded</span>`;
            bankDrop.classList.add("loaded");
            bankDrop.querySelector(".drop-title").textContent = `✓ ${file.name}`;
            bankDrop.querySelector(".drop-hint").textContent = `${data.count} transactions loaded`;
            checkReadyToProcess();
        } else {
            status.innerHTML = `<span class="badge badge-red">✕ ${data.detail}</span>`;
        }
    } catch (e) {
        status.innerHTML = `<span class="badge badge-red">✕ Upload failed</span>`;
    }
}

// ── Invoice file selection ───────────────────────────────────────────────────
const invoiceDrop = document.getElementById("invoice-drop");
const invoiceInput = document.getElementById("invoice-input");

invoiceDrop.addEventListener("click", () => invoiceInput.click());
invoiceInput.addEventListener("change", () => addFiles(Array.from(invoiceInput.files)));
setupDragDrop(invoiceDrop, file => addFiles([file]));

function addFiles(files) {
    files.forEach(f => {
        if (!state.invoiceFiles.find(x => x.name === f.name)) {
            state.invoiceFiles.push(f);
        }
    });
    renderFileList();
    checkReadyToProcess();
}

function renderFileList() {
    const list = document.getElementById("file-list");
    const actions = document.getElementById("upload-actions");
    if (state.invoiceFiles.length === 0) {
        list.innerHTML = "";
        actions.style.display = "none";
        return;
    }
    actions.style.display = "block";
    list.innerHTML = state.invoiceFiles.map((f, i) => `
        <div class="file-item">
            <span class="file-item-name">📄 ${f.name}</span>
            <span class="file-item-size">${(f.size / 1024).toFixed(0)} KB</span>
            <button class="file-item-remove" onclick="removeFile(${i})">✕</button>
        </div>
    `).join("");
}

function removeFile(i) {
    state.invoiceFiles.splice(i, 1);
    renderFileList();
    checkReadyToProcess();
}

// ── Confirm modal ────────────────────────────────────────────────────────────
function checkReadyToProcess() {
    if (state.bankLoaded && state.invoiceFiles.length > 0) {
        showConfirmModal();
    }
}

function showConfirmModal() {
    const modal = document.getElementById("confirm-modal");
    document.getElementById("modal-invoice-count").textContent =
        `${state.invoiceFiles.length} invoice${state.invoiceFiles.length > 1 ? "s" : ""}`;
    document.getElementById("modal-bank-count").textContent =
        `${state.bankCount} transactions`;
    modal.classList.add("open");
}

function closeModal() {
    document.getElementById("confirm-modal").classList.remove("open");
}

document.getElementById("modal-confirm-btn").addEventListener("click", () => {
    closeModal();
    processAll();
});

document.getElementById("modal-cancel-btn").addEventListener("click", closeModal);

document.getElementById("confirm-modal").addEventListener("click", function(e) {
    if (e.target === this) closeModal();
});

// ── Processing ───────────────────────────────────────────────────────────────
document.getElementById("process-btn").addEventListener("click", () => {
    if (state.bankLoaded) {
        showConfirmModal();
    } else {
        processAll();
    }
});

async function processAll() {
    if (state.invoiceFiles.length === 0) return;
    const progressWrap = document.getElementById("progress-wrap");
    const progressFill = document.getElementById("progress-fill");
    const progressLabel = document.getElementById("progress-label");
    const resultsWrap = document.getElementById("upload-results");

    progressWrap.style.display = "block";
    resultsWrap.style.display = "none";
    document.getElementById("upload-actions").style.display = "none";

    const results = [];
    const total = state.invoiceFiles.length;

    for (let i = 0; i < total; i++) {
        const f = state.invoiceFiles[i];
        progressLabel.textContent = `Processing ${f.name} (${i + 1} of ${total})...`;
        progressFill.style.width = `${((i + 1) / total) * 100}%`;
        const form = new FormData();
        form.append("file", f);
        try {
            const res = await fetch("/api/process", { method: "POST", body: form });
            const data = await res.json();
            state.records.push(data);
            results.push(data);
        } catch (e) {
            results.push({ filename: f.name, status: "exception", error: "Network error" });
        }
    }

    progressWrap.style.display = "none";
    state.invoiceFiles = [];
    renderFileList();

    const exceptions = results.filter(r => r.status === "exception");
    const pending = results.filter(r => r.status === "pending");

    resultsWrap.style.display = "block";
    resultsWrap.innerHTML = `
        <div class="metrics-row">
            <div class="metric-card"><div class="metric-val">${results.length}</div><div class="metric-lbl">Processed</div></div>
            <div class="metric-card"><div class="metric-val">${pending.length}</div><div class="metric-lbl">Pending review</div></div>
            <div class="metric-card"><div class="metric-val">${exceptions.length}</div><div class="metric-lbl">Exceptions</div></div>
            <div class="metric-card"><div class="metric-val">0</div><div class="metric-lbl">Approved</div></div>
        </div>
        ${exceptions.map(e => `<div class="notice warn" style="margin-bottom:8px">⚠ <strong>${e.filename}</strong> — ${e.error}</div>`).join("")}
        ${pending.length > 0 ? `
            <button class="btn btn-primary" onclick="switchView('review')" style="margin-top:0.75rem">
                Review ${pending.length} invoice${pending.length > 1 ? "s" : ""} →
            </button>` : ""}
    `;
    updatePendingBadge();
}

// ── Review ───────────────────────────────────────────────────────────────────
function renderReview() {
    const pending   = state.records.filter(r => r.status === "pending");
    const approved  = state.records.filter(r => r.status === "approved");
    const rejected  = state.records.filter(r => r.status === "rejected");
    const exceptions = state.records.filter(r => r.status === "exception");

    const metricsRow = document.getElementById("metrics-row");
    const reviewList = document.getElementById("review-list");
    const exportBar  = document.getElementById("export-bar");

    if (state.records.length === 0) {
        metricsRow.style.display = "none";
        exportBar.style.display = "none";
        reviewList.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <div class="empty-state-title">No invoices to review yet</div>
                <div class="empty-state-hint">Upload and process invoices first</div>
            </div>`;
        return;
    }

    // Progress strip
    const total = state.records.length;
    const done = approved.length + rejected.length + exceptions.length;
    const progressEl = document.getElementById("review-progress");
    if (progressEl) {
        progressEl.innerHTML = `
            <div class="progress-strip">
                <div class="step-dot ${done > 0 ? 'done' : 'current'}"></div>
                <div class="step-line ${done >= total ? 'done' : ''}"></div>
                <div class="step-dot ${done >= total ? 'done' : done > 0 ? 'current' : ''}"></div>
                <span style="margin-left:6px">${done} of ${total} invoices reviewed</span>
            </div>`;
    }

    metricsRow.style.display = "grid";
    metricsRow.innerHTML = `
        <div class="metric-card"><div class="metric-val">${total}</div><div class="metric-lbl">Total</div></div>
        <div class="metric-card"><div class="metric-val">${pending.length}</div><div class="metric-lbl">Pending</div></div>
        <div class="metric-card"><div class="metric-val">${approved.length}</div><div class="metric-lbl">Approved</div></div>
        <div class="metric-card"><div class="metric-val">${rejected.length + exceptions.length}</div><div class="metric-lbl">Rejected/Errors</div></div>
    `;

    exportBar.style.display = approved.length > 0 ? "flex" : "none";
    reviewList.innerHTML = "";

    pending.forEach(rec => reviewList.appendChild(buildInvoiceCard(rec)));

    exceptions.forEach(rec => {
        const el = document.createElement("div");
        el.className = "notice warn";
        el.style.marginBottom = "8px";
        el.innerHTML = `⚠ <strong>${rec.filename}</strong> — ${rec.error}`;
        reviewList.appendChild(el);
    });

    [...approved, ...rejected].forEach(rec => {
        const el = document.createElement("div");
        el.className = "audit-record";
        el.innerHTML = `
            <span class="audit-filename">${rec.filename}</span>
            <span class="audit-meta">${rec.supplier_name || "—"} · £${(rec.total_amount || 0).toFixed(2)}</span>
            ${statusBadge(rec.status)}
        `;
        reviewList.appendChild(el);
    });
}

function buildInvoiceCard(rec) {
    const card = document.createElement("div");
    card.className = "invoice-card";
    card.id = `card-${rec.audit_id}`;

    const fc = rec.field_confidence || {};
    const flags = Array.isArray(rec.vat_flags) ? rec.vat_flags : [];
    const certainty = rec.vat_certainty || "unknown";
    const isMissingVat = certainty === "missing" || certainty === "unknown";
    const confPct = Math.round((rec.confidence || 0) * 100);
    const confCls = confPct >= 80 ? "high" : confPct >= 60 ? "med" : "low";

    // Build notices
    let noticesHtml = "";
    if (isMissingVat) {
        noticesHtml += `<div class="notice warn" style="margin:1rem 1.25rem 0">
            ⚠ No VAT was found on this invoice. Please choose a VAT rate below before approving.
        </div>`;
    }
    if (rec.bank_matched) {
        noticesHtml += `<div class="notice ok" style="margin:8px 1.25rem 0">
            ✓ Bank match found — ${rec.bank_description} · £${(rec.bank_amount || 0).toFixed(2)}
        </div>`;
    }
    if (rec.reasoning) {
        noticesHtml += `<div class="notice info" style="margin:8px 1.25rem 0;font-style:italic">
            💭 ${rec.reasoning}
        </div>`;
    }

    // Confidence detail rows
    const confRows = Object.entries(fc).map(([field, score]) => {
        const pct = Math.round(score * 100);
        const col = pct >= 80 ? "#16a34a" : pct >= 60 ? "#d97706" : "#dc2626";
        return `<div class="conf-item">
            <span class="conf-name">${field.replace(/_/g,' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
            <div class="conf-bar-bg"><div class="conf-bar-fg" style="width:${pct}%;background:${col}"></div></div>
            <span class="conf-pct">${pct}%</span>
        </div>`;
    }).join("");

    card.innerHTML = `
        <div class="invoice-card-top" onclick="toggleCard(${rec.audit_id})">
            <div class="invoice-file-icon">📄</div>
            <div>
                <div class="invoice-card-filename">${rec.filename}</div>
                <div class="invoice-card-meta">${rec.supplier_name || "Unknown"} · ${rec.invoice_date || "No date"} · ⏱ ${rec.processing_time}s</div>
            </div>
            <div>
                <div class="invoice-card-amount">£${(rec.total_amount || 0).toFixed(2)}</div>
                <div class="invoice-card-amount-label">Total</div>
            </div>
        </div>

        <div class="invoice-card-body ${isMissingVat ? 'open' : ''}" id="body-${rec.audit_id}">
            ${noticesHtml}

            <div class="fields-section">
                <div class="field-row">
                    <div class="field-group">
                        <div class="field-label ${!rec.supplier_name ? 'error' : ''}">
                            ${!rec.supplier_name ? '⚠ ' : ''}Supplier name
                        </div>
                        <input class="field-input ${!rec.supplier_name ? 'error-border' : ''}"
                            id="f-supplier-${rec.audit_id}"
                            value="${rec.supplier_name || ''}"
                            placeholder="Supplier name"
                            oninput="validateCard(${rec.audit_id}, ${isMissingVat})">
                    </div>
                    <div class="field-group">
                        <div class="field-label">Invoice number</div>
                        <input class="field-input" id="f-invnum-${rec.audit_id}"
                            value="${rec.invoice_number || ''}" placeholder="INV-001">
                    </div>
                </div>

                <div class="field-row">
                    <div class="field-group">
                        <div class="field-label ${!rec.invoice_date ? 'error' : ''}">
                            ${!rec.invoice_date ? '⚠ ' : ''}Invoice date
                        </div>
                        <input class="field-input ${!rec.invoice_date ? 'error-border' : ''}"
                            id="f-date-${rec.audit_id}"
                            value="${rec.invoice_date || ''}"
                            placeholder="DD/MM/YYYY"
                            oninput="validateCard(${rec.audit_id}, ${isMissingVat})">
                    </div>
                    <div class="field-group">
                        <div class="field-label">Total amount (£)</div>
                        <input class="field-input" type="number" step="0.01" min="0"
                            id="f-total-${rec.audit_id}"
                            value="${rec.total_amount || ''}"
                            oninput="recalcVat(${rec.audit_id}, ${isMissingVat})">
                        <div style="display:flex;gap:12px;margin-top:5px">
                            <label style="font-size:0.72rem;color:var(--text-muted);display:flex;align-items:center;gap:4px;cursor:pointer">
                                <input type="radio" name="tt-${rec.audit_id}" value="gross" checked onchange="recalcVat(${rec.audit_id}, ${isMissingVat})"> Gross (inc. VAT)
                            </label>
                            <label style="font-size:0.72rem;color:var(--text-muted);display:flex;align-items:center;gap:4px;cursor:pointer">
                                <input type="radio" name="tt-${rec.audit_id}" value="net" onchange="recalcVat(${rec.audit_id}, ${isMissingVat})"> Net (ex. VAT)
                            </label>
                        </div>
                    </div>
                </div>

                <div class="field-row">
                    <div class="field-group">
                        <div class="field-label ${isMissingVat ? 'error' : ''}">
                            ${isMissingVat ? '⚠ ' : ''}VAT rate
                        </div>
                        <select class="field-select ${isMissingVat ? 'error-border' : ''}"
                            id="f-rate-${rec.audit_id}"
                            onchange="recalcVat(${rec.audit_id}, ${isMissingVat})">
                            ${isMissingVat ? '<option value="">Choose VAT rate...</option>' : ''}
                            <option value="20" ${rec.vat_rate == 20 ? 'selected' : ''}>20% — Standard rate</option>
                            <option value="5"  ${rec.vat_rate == 5  ? 'selected' : ''}>5% — Reduced rate</option>
                            <option value="0"  ${rec.vat_rate == 0 && !isMissingVat ? 'selected' : ''}>0% — Zero rated / exempt</option>
                        </select>
                    </div>
                    <div class="field-group">
                        <div class="field-label">VAT amount (£)</div>
                        <input class="field-input readonly" type="number" step="0.01"
                            id="f-vat-${rec.audit_id}"
                            value="${rec.vat_amount || ''}"
                            placeholder="Auto-calculated" readonly>
                        <div class="calc-hint" id="calc-note-${rec.audit_id}">Select a VAT rate to auto-calculate</div>
                    </div>
                </div>
            </div>

            <div class="conf-row" onclick="toggleConf(${rec.audit_id})">
                <span>AI confidence</span>
                <span class="conf-pill ${confCls}">● ${confPct}%</span>
                <span style="color:var(--text-muted);font-size:0.75rem">— tap to see field details</span>
                <span class="conf-chevron" id="conf-chev-${rec.audit_id}">▼</span>
            </div>

            <div class="conf-detail" id="conf-detail-${rec.audit_id}">
                ${confRows}
            </div>

            <div id="issues-${rec.audit_id}"></div>

            <div class="card-actions">
                <button class="btn-approve" id="approve-btn-${rec.audit_id}"
                    onclick="approveInvoice(${rec.audit_id})" disabled>
                    ✓ Approve
                </button>
                <button class="btn-reject" onclick="rejectInvoice(${rec.audit_id})">
                    ✕ Reject
                </button>
                <div class="blocked-hint" id="blocked-hint-${rec.audit_id}">
                    🔒 ${isMissingVat ? 'Select a VAT rate first' : 'Fill in required fields'}
                </div>
            </div>
        </div>
    `;

    setTimeout(() => validateCard(rec.audit_id, isMissingVat), 0);
    return card;
}

function toggleCard(auditId) {
    document.getElementById(`body-${auditId}`).classList.toggle("open");
}

function toggleConf(auditId) {
    document.getElementById(`conf-detail-${auditId}`).classList.toggle("open");
    document.getElementById(`conf-chev-${auditId}`).classList.toggle("open");
}

function recalcVat(auditId, isMissingVat) {
    const rate = parseFloat(document.getElementById(`f-rate-${auditId}`).value);
    const total = parseFloat(document.getElementById(`f-total-${auditId}`).value);
    const totalType = document.querySelector(`input[name="tt-${auditId}"]:checked`)?.value || "gross";
    const vatInput = document.getElementById(`f-vat-${auditId}`);
    const note = document.getElementById(`calc-note-${auditId}`);

    if (!isNaN(rate) && !isNaN(total) && total > 0) {
        let vat, noteText;
        if (rate === 0) {
            vat = 0; noteText = "Zero rated — no VAT on this invoice";
        } else if (totalType === "gross") {
            const net = total / (1 + rate / 100);
            vat = Math.round((total - net) * 100) / 100;
            noteText = `£${total.toFixed(2)} gross → net £${net.toFixed(2)} + VAT £${vat.toFixed(2)}`;
        } else {
            vat = Math.round(total * (rate / 100) * 100) / 100;
            noteText = `£${total.toFixed(2)} net × ${rate}% = VAT £${vat.toFixed(2)}`;
        }
        vatInput.value = vat.toFixed(2);
        note.textContent = noteText;
    } else {
        vatInput.value = "";
        note.textContent = "Select a VAT rate to auto-calculate";
    }
    validateCard(auditId, isMissingVat);
}

function validateCard(auditId, isMissingVat) {
    const supplier = document.getElementById(`f-supplier-${auditId}`)?.value.trim();
    const date = document.getElementById(`f-date-${auditId}`)?.value.trim();
    const total = parseFloat(document.getElementById(`f-total-${auditId}`)?.value);
    const rate = document.getElementById(`f-rate-${auditId}`)?.value;
    const approveBtn = document.getElementById(`approve-btn-${auditId}`);
    const blockedHint = document.getElementById(`blocked-hint-${auditId}`);

    const issues = [];
    if (!supplier) issues.push("supplier name");
    if (!date) issues.push("invoice date");
    if (!total || total === 0) issues.push("total amount");
    if (isMissingVat && !rate) issues.push("VAT rate");

    const canApprove = issues.length === 0;
    if (approveBtn) approveBtn.disabled = !canApprove;
    if (blockedHint) {
        blockedHint.style.display = canApprove ? "none" : "flex";
        if (!canApprove) {
            blockedHint.textContent = `🔒 Still needed: ${issues.join(", ")}`;
        }
    }
}

async function approveInvoice(auditId) {
    const data = {
        supplier_name: document.getElementById(`f-supplier-${auditId}`).value,
        invoice_number: document.getElementById(`f-invnum-${auditId}`).value,
        invoice_date: document.getElementById(`f-date-${auditId}`).value,
        total_amount: parseFloat(document.getElementById(`f-total-${auditId}`).value) || 0,
        vat_amount: parseFloat(document.getElementById(`f-vat-${auditId}`).value) || 0,
        vat_rate: parseFloat(document.getElementById(`f-rate-${auditId}`).value) || 0,
    };
    const res = await fetch(`/api/approve/${auditId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    });
    if (res.ok) {
        const rec = state.records.find(r => r.audit_id === auditId);
        if (rec) { Object.assign(rec, data); rec.status = "approved"; }
        updatePendingBadge();
        renderReview();
    }
}

async function rejectInvoice(auditId) {
    const res = await fetch(`/api/reject/${auditId}`, { method: "POST" });
    if (res.ok) {
        const rec = state.records.find(r => r.audit_id === auditId);
        if (rec) rec.status = "rejected";
        updatePendingBadge();
        renderReview();
    }
}

// ── Audit ────────────────────────────────────────────────────────────────────
async function loadAudit() {
    const res = await fetch("/api/audit");
    const { records, stats } = await res.json();
    document.getElementById("audit-stats").innerHTML = `
        <div class="metric-card"><div class="metric-val">${stats.total}</div><div class="metric-lbl">Total</div></div>
        <div class="metric-card"><div class="metric-val">${stats.approved}</div><div class="metric-lbl">Approved</div></div>
        <div class="metric-card"><div class="metric-val">${stats.avg_confidence}%</div><div class="metric-lbl">Avg confidence</div></div>
        <div class="metric-card"><div class="metric-val">${stats.avg_processing_time}s</div><div class="metric-lbl">Avg time</div></div>
    `;
    const list = document.getElementById("audit-list");
    if (!records.length) {
        list.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🗄️</div><div class="empty-state-title">No records yet</div></div>`;
        return;
    }
    list.innerHTML = records.map(r => {
        let extracted = {};
        try { extracted = JSON.parse(r.extracted_data || "{}"); } catch {}
        return `
        <div class="audit-record">
            <div>
                <div class="audit-filename">${r.filename}</div>
                <div class="audit-meta">${(r.upload_time || "").slice(0,16).replace("T"," ")}</div>
            </div>
            <span class="audit-meta">${extracted.supplier_name || "—"} · £${(extracted.total_amount || 0).toFixed(2)} · VAT ${extracted.vat_rate || 0}%</span>
            ${confBadge(r.confidence || 0)}
            ${statusBadge(r.status)}
        </div>`;
    }).join("");
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function confBadge(score) {
    const pct = Math.round(score * 100);
    const cls = pct >= 80 ? "badge-green" : pct >= 60 ? "badge-amber" : "badge-red";
    return `<span class="badge ${cls}">● ${pct}%</span>`;
}

function statusBadge(status) {
    const map = {
        approved:  ["badge-green", "✓ Approved"],
        rejected:  ["badge-red",   "✕ Rejected"],
        pending:   ["badge-amber", "~ Pending"],
        exception: ["badge-red",   "✕ Error"],
    };
    const [cls, label] = map[status] || ["badge-gray", status];
    return `<span class="badge ${cls}">${label}</span>`;
}

function updatePendingBadge() {
    const count = state.records.filter(r => r.status === "pending").length;
    const badge = document.getElementById("pending-count");
    const reviewBtn = document.querySelector('[data-view="review"]');
    if (count > 0) {
        badge.textContent = count;
        badge.style.display = "inline-flex";
        reviewBtn.classList.add("needs-action");
    } else {
        badge.style.display = "none";
        reviewBtn.classList.remove("needs-action");
    }
}

function setupDragDrop(zone, onDrop) {
    zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("dragover"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", e => {
        e.preventDefault(); zone.classList.remove("dragover");
        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) onDrop(files[0]);
    });
}

document.addEventListener("DOMContentLoaded", () => {
    if (new URLSearchParams(window.location.search).get("go") === "start") {
        switchView("upload");
        window.history.replaceState({}, "", "/app");
    }
});