/**
 * تحويل الجداول ذات الصنف (make-cards) إلى بطاقات على الشاشات الصغيرة.
 * يعتمد على:
 *  - data-card-columns="0,1,2" لتحديد الأعمدة المسموح بها (اختياري).
 *  - قراءة ترويسة الجدول <th>.
 *  - الاحتفاظ بخلايا الإجراءات (إن كانت ضمن الأعمدة المحددة).
 */
(function(){
  function cardifyTable(tbl){
    if(!tbl || tbl.dataset.cardified === '1') return;
    const width = window.innerWidth || document.documentElement.clientWidth;
    if(width > 600) return; // فقط للشاشات الصغيرة
    const thead = tbl.querySelector('thead');
    const headers = [...(thead ? thead.querySelectorAll('th') : [])].map(th => th.innerText.trim());
    const allowedAttr = tbl.getAttribute('data-card-columns');
    let allowed = null;
    if(allowedAttr){
      allowed = allowedAttr.split(',').map(s=>parseInt(s.trim(),10)).filter(n=>!isNaN(n));
    }
    const tbody = tbl.querySelector('tbody');
    if(!tbody) return;
    const rows = [...tbody.querySelectorAll('tr')];
    const wrap = document.createElement('div');
    wrap.className = 'rt-cards-wrap';

    rows.forEach(tr=>{
      const cells = [...tr.children];
      const card = document.createElement('div');
      card.className='rt-card';
      let actionsFragment=null;

      cells.forEach((td, idx)=>{
        // تجاهل أعمدة غير مسموحة (لو تم تحديدها)
        if(allowed && !allowed.includes(idx)) return;
        const label = headers[idx] || '';
        const html = td.innerHTML.trim();

        // محاولة تمييز عمود "إجراءات" بوجود أزرار
        const hasButtons = /<button|<a\b/i.test(html) && label.includes('إجراء') || label.includes('إجراءات');

        if(hasButtons){
          const actions = document.createElement('div');
            actions.className='rt-actions';
            actions.innerHTML = html;
            actionsFragment = actions;
            return;
        }

        const line = document.createElement('div');
        line.className='rt-line';
        const lab = document.createElement('span');
        lab.className='rt-label';
        lab.textContent=label || '#';
        const val = document.createElement('span');
        val.className='rt-value';
        val.innerHTML = html || '';
        line.appendChild(lab);
        line.appendChild(val);
        card.appendChild(line);
      });

      if(actionsFragment){
        card.appendChild(actionsFragment);
      }
      wrap.appendChild(card);
    });

    // إدراج بعد الجدول
    tbl.insertAdjacentElement('afterend', wrap);
    // إخفاء الجدول
    tbl.style.display='none';
    tbl.dataset.cardified='1';
  }

  function init(){
    document.querySelectorAll('table.make-cards').forEach(cardifyTable);
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // إعادة الفحص عند تغيير الاتجاه (مثلاً تدوير الهاتف)
  window.addEventListener('resize', function(){
    // لا نكرر التحويل، لكن لو كبر الحجم يمكن لاحقاً إظهار الجدول (تطوير مستقبلي)
  });
})();