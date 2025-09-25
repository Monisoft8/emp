// HR Departments Modal with "Assign Head" action
// Requires Bootstrap CSS/JS. Works with Flask-Login session cookies (same-origin).
(() => {
  const API = {
    listDepts: "/api/v1/manager/departments",
    renameDept: (id) => `/api/v1/manager/departments/${id}`,
    deleteDept: (id) => `/api/v1/manager/departments/${id}`,
    assignHead: (id) => `/api/v1/manager/departments/${id}/assign-head`,
    listEmployees: (deptId, limit=500) => `/api/v1/manager/employees?department_id=${encodeURIComponent(deptId)}&limit=${limit}`
  };

  const fetchJSON = (url, opts={}) =>
    fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(opts.headers||{}) },
      ...opts
    }).then(async r => {
      let data = null;
      try { data = await r.json(); } catch { /* HTML error page? */ }
      if (!r.ok) throw new Error((data && (data.error || data.message)) || `HTTP ${r.status}`);
      return data;
    });

  function makeModal(id, titleHTML, bodyHTML, footerHTML="") {
    const old = document.getElementById(id);
    if (old) old.remove();
    const wrap = document.createElement("div");
    wrap.id = id;
    wrap.className = "modal fade";
    wrap.tabIndex = -1;
    wrap.innerHTML = `
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">${titleHTML}</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body">${bodyHTML}</div>
          <div class="modal-footer">${footerHTML || `<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">إغلاق</button>`}</div>
        </div>
      </div>
    `;
    document.body.appendChild(wrap);
    return new bootstrap.Modal(wrap);
  }

  function buildDepartmentsTable(rows) {
    const tbody = rows.map((r, idx) => `
      <tr data-dept-id="${r.id}" data-dept-name="${r.name}">
        <td class="text-muted">${idx+1}</td>
        <td>${escapeHTML(r.name)}</td>
        <td class="text-nowrap">
          <button class="btn btn-sm btn-success me-1 js-assign-head">تعيين رئيس</button>
          <button class="btn btn-sm btn-warning me-1 js-rename">إعادة تسمية</button>
          <button class="btn btn-sm btn-danger js-delete">حذف</button>
        </td>
      </tr>
    `).join("");
    return `
      <div class="d-flex mb-2">
        <input id="new-dept-name" class="form-control me-2" placeholder="اسم قسم جديد">
        <button class="btn btn-primary" id="btn-add-dept">إضافة</button>
      </div>
      <div class="table-responsive">
        <table class="table table-sm align-middle">
          <thead>
            <tr>
              <th>#</th>
              <th>الاسم</th>
              <th class="text-end">إجراءات</th>
            </tr>
          </thead>
          <tbody>${tbody}</tbody>
        </table>
      </div>
    `;
  }

  function escapeHTML(s){ return String(s??"").replace(/[&<>"']/g,c=>({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c])); }

  async function showAssignHeadDialog(deptId, deptName) {
    // fetch employees of this department
    const employees = await fetchJSON(API.listEmployees(deptId));
    const options = employees.map(e => `<option value="${e.id}">${escapeHTML(e.name)} (ID:${e.id})</option>`).join("");
    const modal = makeModal(
      "assignHeadModal",
      `تعيين رئيس لقسم <span class="text-primary">${escapeHTML(deptName)}</span>`,
      `
        <div class="mb-3">
          <label class="form-label">اختر الموظف</label>
          <select id="ah-employee" class="form-select">
            <option value="">-- اختر موظف --</option>
            ${options}
          </select>
        </div>
        <div class="mb-3">
          <label class="form-label">اسم المستخدم (لرئيس القسم)</label>
          <input id="ah-username" class="form-control" placeholder="username">
        </div>
        <div class="mb-1">
          <label class="form-label">كلمة المرور</label>
          <input id="ah-password" type="password" class="form-control" placeholder="password">
        </div>
        <small class="text-muted">سيتم إنشاء/تحديث مستخدم بدور department_head وتعيينه على هذا القسم.</small>
      `,
      `
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">إلغاء</button>
        <button type="button" class="btn btn-success" id="ah-save">حفظ</button>
      `
    );
    modal.show();

    const root = document.getElementById("assignHeadModal");
    root.querySelector("#ah-save").onclick = async () => {
      const employee_id = parseInt(root.querySelector("#ah-employee").value, 10);
      const username = (root.querySelector("#ah-username").value||"").trim();
      const password = (root.querySelector("#ah-password").value||"").trim();
      if (!employee_id) return alert("اختر الموظف.");
      if (!username || !password) return alert("اكتب اسم المستخدم وكلمة المرور.");

      try {
        await fetchJSON(API.assignHead(deptId), {
          method: "POST",
          body: JSON.stringify({ employee_id, username, password })
        });
        alert("تم تعيين رئيس القسم بنجاح.");
        modal.hide();
      } catch (e) {
        alert("فشل التعيين: " + e.message);
      }
    };
  }

  async function showDepartmentsModal() {
    let modal = makeModal("departmentsModal", "إدارة الأقسام", `<div class="text-muted">جاري التحميل...</div>`);
    modal.show();

    const root = document.getElementById("departmentsModal");

    async function reload() {
      try {
        const list = await fetchJSON(API.listDepts);
        root.querySelector(".modal-body").innerHTML = buildDepartmentsTable(list);
        bindRowEvents();
      } catch (e) {
        root.querySelector(".modal-body").innerHTML = `<div class="alert alert-danger">فشل التحميل: ${escapeHTML(e.message)}</div>`;
      }
    }

    function bindRowEvents() {
      // Add new
      root.querySelector("#btn-add-dept").onclick = async () => {
        const name = root.querySelector("#new-dept-name").value.trim();
        if (!name) return alert("أدخل اسم القسم.");
        try {
          await fetchJSON("/api/v1/manager/departments", { method:"POST", body: JSON.stringify({ name }) });
          await reload();
        } catch (e) { alert("فشل الإضافة: " + e.message); }
      };

      // row actions
      root.querySelectorAll("tbody tr").forEach(tr => {
        const did = tr.getAttribute("data-dept-id");
        const dname = tr.getAttribute("data-dept-name");

        tr.querySelector(".js-rename").onclick = async () => {
          const nn = prompt("اسم القسم الجديد:", dname || "");
          if (!nn) return;
          try {
            await fetchJSON(API.renameDept(did), { method:"PUT", body: JSON.stringify({ name: nn }) });
            await reload();
          } catch (e) { alert("فشل إعادة التسمية: " + e.message); }
        };

        tr.querySelector(".js-delete").onclick = async () => {
          if (!confirm(`حذف قسم "${dname}"؟`)) return;
          try {
            await fetchJSON(API.deleteDept(did), { method:"DELETE" });
            await reload();
          } catch (e) { alert("فشل الحذف: " + e.message); }
        };

        tr.querySelector(".js-assign-head").onclick = () => showAssignHeadDialog(did, dname);
      });
    }

    await reload();
  }

  // Try to bind to an existing "إدارة الأقسام" opening button; fallback to expose global
  function attachOpenButton() {
    const btn = document.querySelector('#manage-departments-btn, button.manage-departments, [data-open="departments"]');
    if (btn) btn.addEventListener("click", (e) => { e.preventDefault(); showDepartmentsModal(); });
    // also expose for manual call (if existing code opens another modal you prefer ours):
    window.openDepartmentsModal = showDepartmentsModal;
  }

  // Auto-attach
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attachOpenButton);
  } else {
    attachOpenButton();
  }
})();