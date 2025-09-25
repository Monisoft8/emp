// مساحة مستقبلية لإضافات JS عامة (Toast - Utilities)
window.AdminUtils = {
  flash(msg,type="info",timeout=3500){
    let box=document.querySelector(".dynamic-flash-box");
    if(!box){
      box=document.createElement("div");
      box.className="dynamic-flash-box position-fixed top-0 start-50 translate-middle-x mt-2 z-3";
      document.body.appendChild(box);
    }
    const el=document.createElement("div");
    el.className=`alert alert-${type} py-2 px-3 shadow-sm mb-2`;
    el.textContent=msg;
    box.appendChild(el);
    setTimeout(()=>el.remove(), timeout);
  }
};