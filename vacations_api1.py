import sqlite3
from datetime import datetime, date
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from msd.database.connection import get_conn

vacations_api_bp = Blueprint("vacations_api_bp", __name__, url_prefix="/api/v1/vacations")

S_PENDING_DEPT = "pending_dept"
S_PENDING_MANAGER = "pending_manager"
S_APPROVED = "approved"
S_REJECTED_DEPT = "rejected_dept"
S_REJECTED_MANAGER = "rejected_manager"
S_CANCELLED = "cancelled"
PENDING_SET = {S_PENDING_DEPT, S_PENDING_MANAGER}

AR_TO_CODE = {
    "سنوية": "annual",
    "طارئة": "emergency",
    "وفاة الزوج": "death_spouse",
    "وفاة درجة أولى": "death1",
    "وفاة درجة ثانية": "death2",
    "حج": "hajj",
    "زواج": "marriage",
    "وضع": "birth_single",
    "وضع (عادي)": "birth_single",
    "وضع (توأم)": "birth_twins",
    "مرضية": "sick",
}

DEATH1_RELATIONS = {"أب","أم","ابن","ابنة","جد","جدة"}

def user_is_manager():
    return current_user.is_authenticated and current_user.role in ("manager","admin")

def user_is_dept_head():
    return current_user.is_authenticated and current_user.role == "department_head"

def ensure_history(vac_id, action, from_status, to_status, note=""):
    with get_conn() as conn:
        conn.execute("""
          INSERT INTO vacation_history
            (vacation_id, action, from_status, to_status, actor_id, actor_role, note, created_at)
          VALUES (?,?,?,?,?,?,?,?)
        """,(vac_id, action, from_status, to_status,
             getattr(current_user,"employee_id",None),
             getattr(current_user,"role",None),
             note, datetime.utcnow().isoformat(timespec="seconds")))
        conn.commit()

def fetch_vacation(vac_id:int):
    with get_conn() as conn:
        return conn.execute("""
          SELECT vr.*, e.name AS employee_name,
                 e.vacation_balance,
                 COALESCE(e.emergency_vacation_balance, e.emergency_balance,0) AS emergency_balance
            FROM vacation_requests vr
            JOIN employees e ON e.id=vr.employee_id
           WHERE vr.id=?""",(vac_id,)).fetchone()

def overlap_exists(emp_id,start,end, exclude_id=None):
    sql = """
      SELECT 1 FROM vacation_requests
       WHERE employee_id=?
         AND status NOT IN (?, ?, ?)
         AND NOT (date(end_date)<date(?) OR date(start_date)>date(?))
    """
    params = [emp_id,S_CANCELLED,S_REJECTED_DEPT,S_REJECTED_MANAGER,start,end]
    if exclude_id:
        sql += " AND id != ?"
        params.append(exclude_id)
    with get_conn() as conn:
        return conn.execute(sql, params).fetchone() is not None

def compute_days(start,end):
    d1=date.fromisoformat(start); d2=date.fromisoformat(end)
    return (d2-d1).days+1

def load_type(code):
    with get_conn() as conn:
        return conn.execute("""
          SELECT code,name_ar,fixed_duration,max_per_request,requires_relation,
                 affects_annual_balance,affects_emergency_balance
            FROM vacation_types WHERE code=?""",(code,)).fetchone()

def adjust_balances_on_approve(vac_row):
    code = vac_row["type_code"]
    days = vac_row["requested_days"]
    with get_conn() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(employees)")}
        if code=="annual":
            conn.execute("UPDATE employees SET vacation_balance = vacation_balance - ? WHERE id=?",
                         (days, vac_row["employee_id"]))
        elif code=="emergency":
            if "emergency_vacation_balance" in cols:
                conn.execute("UPDATE employees SET emergency_vacation_balance=COALESCE(emergency_vacation_balance,0)-? WHERE id=?",
                             (days, vac_row["employee_id"]))
            elif "emergency_balance" in cols:
                conn.execute("UPDATE employees SET emergency_balance=COALESCE(emergency_balance,0)-? WHERE id=?",
                             (days, vac_row["employee_id"]))
        conn.commit()

def normalize_type(label: str):
    if not label: return None
    return AR_TO_CODE.get(label.strip(), label.strip())

@vacations_api_bp.get("")
@login_required
def list_vacations():
    args=request.args
    page=max(int(args.get("page",1)),1)
    limit=min(max(int(args.get("limit",10)),1),200)
    off=(page-1)*limit
    filters=[]; params=[]
    if not user_is_manager() and not user_is_dept_head():
        filters.append("vr.employee_id=?"); params.append(current_user.employee_id)
    else:
        if args.get("employee_id"):
            filters.append("vr.employee_id=?"); params.append(args.get("employee_id"))
    if args.get("status"):
        filters.append("vr.status=?"); params.append(args.get("status"))
    if args.get("type_code"):
        filters.append("vr.type_code=?"); params.append(args.get("type_code"))
    where="WHERE "+" AND ".join(filters) if filters else ""
    base = "FROM vacation_requests vr JOIN employees e ON e.id=vr.employee_id"
    sql_count="SELECT COUNT(*) "+base+" "+where
    sql_data=f"""
      SELECT vr.id, vr.employee_id, e.name, vr.type_code,
             vr.start_date, vr.end_date, vr.requested_days,
             vr.status, vr.rejection_reason, vr.notes, vr.created_at
        {base} {where}
       ORDER BY vr.id DESC
       LIMIT ? OFFSET ?
    """
    with get_conn() as conn:
        total=conn.execute(sql_count,params).fetchone()[0]
        rows=conn.execute(sql_data,params+[limit,off]).fetchall()
    def rdict(r):
        return {
            "id":r[0],"employee_id":r[1],"employee_name":r[2],"type_code":r[3],
            "start_date":r[4],"end_date":r[5],"requested_days":r[6],
            "status":r[7],"rejection_reason":r[8],"notes":r[9],"created_at":r[10]
        }
    return jsonify(total=total,page=page,limit=limit,pages=(total+limit-1)//limit,
                   items=[rdict(r) for r in rows])

@vacations_api_bp.post("")
@login_required
def create_vacation():
    data = request.get_json(force=True)
    emp_id = data.get("employee_id") or getattr(current_user,"employee_id",None)
    if not emp_id:
        return jsonify(error="employee_id مطلوب"),400

    raw_type = data.get("type") or data.get("type_code")
    if not raw_type:
        return jsonify(error="نوع الإجازة مطلوب"),400
    type_code = normalize_type(raw_type)

    relation = (data.get("relation") or "").strip() or None
    notes = (data.get("notes") or "").strip()
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    if not (start_date and end_date):
        return jsonify(error="تواريخ ناقصة"),400

    meta = load_type(type_code)
    if not meta:
        return jsonify(error="نوع غير موجود"),400

    if type_code=="death_spouse":
        relation = "زوج"
        start = date.fromisoformat(start_date)
        end_date = date.fromordinal(start.toordinal()+130-1).isoformat()
        requested_days = 130
    else:
        if meta["fixed_duration"]:
            fd=meta["fixed_duration"]
            s=date.fromisoformat(start_date)
            end_date = date.fromordinal(s.toordinal()+fd-1).isoformat()
        requested_days = compute_days(start_date,end_date)

    if type_code=="death1":
        if not relation or relation not in DEATH1_RELATIONS:
            return jsonify(error="العلاقة مطلوبة وصحيحة (وفاة درجة أولى)"),400
    if type_code=="death2" and not relation:
        relation="أقارب آخرون"

    if meta["max_per_request"] and requested_days>meta["max_per_request"]:
        return jsonify(error=f"الحد الأقصى {meta['max_per_request']}"),400

    if overlap_exists(emp_id,start_date,end_date):
        return jsonify(error="تداخل مع إجازة أخرى"),400

    with get_conn() as conn:
        erow = conn.execute("""
          SELECT vacation_balance,
                 COALESCE(emergency_vacation_balance, emergency_balance,0) AS emer
            FROM employees WHERE id=?""",(emp_id,)).fetchone()
        if not erow:
            return jsonify(error="الموظف غير موجود"),404
        annual_bal = erow[0] or 0
        emer_bal = erow[1] or 0
        if type_code=="annual" and requested_days>annual_bal:
            return jsonify(error="رصيد السنوية غير كافٍ"),400
        if type_code=="emergency" and requested_days>emer_bal:
            return jsonify(error="رصيد الطارئة غير كافٍ"),400

    if not user_is_manager() and not user_is_dept_head():
        if emp_id != getattr(current_user,"employee_id",None):
            return jsonify(error="غير مسموح"),403

    with get_conn() as conn:
        cur=conn.cursor()
        cur.execute("""
          INSERT INTO vacation_requests
            (employee_id,type_code,relation,start_date,end_date,requested_days,status,notes,created_at)
          VALUES (?,?,?,?,?,?,?,?,?)
        """,(emp_id,type_code,relation,start_date,end_date,requested_days,
             S_PENDING_DEPT,notes,datetime.utcnow().isoformat(timespec="seconds")))
        vid=cur.lastrowid
        conn.commit()
    ensure_history(vid,"create",None,S_PENDING_DEPT,"")
    return jsonify(id=vid,type_code=type_code,status=S_PENDING_DEPT,
                   requested_days=requested_days,start_date=start_date,end_date=end_date)

@vacations_api_bp.post("/<int:vac_id>/approve")
@login_required
def approve(vac_id):
    r=fetch_vacation(vac_id)
    if not r: return jsonify(error="غير موجود"),404
    st=r["status"]
    if user_is_dept_head() and st==S_PENDING_DEPT:
        with get_conn() as conn:
            conn.execute("UPDATE vacation_requests SET status=? WHERE id=?",(S_PENDING_MANAGER,vac_id))
            conn.commit()
        ensure_history(vac_id,"approve_dept",st,S_PENDING_MANAGER,"")
        return jsonify(success=True,status=S_PENDING_MANAGER)
    if user_is_manager() and st==S_PENDING_MANAGER:
        with get_conn() as conn:
            conn.execute("UPDATE vacation_requests SET status=? WHERE id=?",(S_APPROVED,vac_id))
            conn.commit()
        adjust_balances_on_approve(r)
        ensure_history(vac_id,"approve_manager",st,S_APPROVED,"")
        return jsonify(success=True,status=S_APPROVED)
    return jsonify(error="حالة/صلاحية غير صالحة"),400

@vacations_api_bp.post("/<int:vac_id>/reject")
@login_required
def reject(vac_id):
    r=fetch_vacation(vac_id)
    if not r: return jsonify(error="غير موجود"),404
    st=r["status"]
    body=request.get_json(force=True)
    reason=(body.get("reason") or "").strip()
    if not reason: return jsonify(error="سبب مطلوب"),400
    if user_is_dept_head() and st==S_PENDING_DEPT:
        new=S_REJECTED_DEPT
    elif user_is_manager() and st==S_PENDING_MANAGER:
        new=S_REJECTED_MANAGER
    else:
        return jsonify(error="غير مصرح"),403
    with get_conn() as conn:
        conn.execute("UPDATE vacation_requests SET status=?, rejection_reason=? WHERE id=?",
                     (new,reason,vac_id))
        conn.commit()
    ensure_history(vac_id,"reject",st,new,reason)
    return jsonify(success=True,status=new)

@vacations_api_bp.post("/<int:vac_id>/cancel")
@login_required
def cancel(vac_id):
    r=fetch_vacation(vac_id)
    if not r: return jsonify(error="غير موجود"),404
    if r["status"] not in PENDING_SET and r["status"]!=S_APPROVED:
        return jsonify(error="لا يمكن الإلغاء"),400
    if r["employee_id"]!=getattr(current_user,"employee_id",None) and not (user_is_manager() or user_is_dept_head()):
        return jsonify(error="غير مصرح"),403
    with get_conn() as conn:
        conn.execute("UPDATE vacation_requests SET status=? WHERE id=?",(S_CANCELLED,vac_id))
        conn.commit()
    ensure_history(vac_id,"cancel",r["status"],S_CANCELLED,"")
    return jsonify(success=True,status=S_CANCELLED)

@vacations_api_bp.get("/<int:vac_id>/history")
@login_required
def history(vac_id):
    r=fetch_vacation(vac_id)
    if not r: return jsonify(error="غير موجود"),404
    with get_conn() as conn:
        rows=conn.execute("""
          SELECT action,from_status,to_status,actor_id,actor_role,note,created_at
            FROM vacation_history WHERE vacation_id=? ORDER BY id
        """,(vac_id,)).fetchall()
    out=[]
    for h in rows:
        out.append({
            "action":h[0],"from_status":h[1],"to_status":h[2],
            "actor_id":h[3],"actor_role":h[4],"note":h[5],"created_at":h[6]
        })
    return jsonify(out)

def init_vacations_api(app):
    """
    استدعِ داخل register_blueprints لكنه يحتاج سياق التطبيق
    """
    with app.app_context():
        with get_conn() as conn:
            conn.execute("""
              CREATE TABLE IF NOT EXISTS vacation_requests(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                type_code TEXT NOT NULL,
                relation TEXT,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                requested_days INTEGER NOT NULL,
                status TEXT NOT NULL,
                rejection_reason TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
              )
            """)
            conn.execute("""
              CREATE TABLE IF NOT EXISTS vacation_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vacation_id INTEGER NOT NULL,
                action TEXT,
                from_status TEXT,
                to_status TEXT,
                actor_id INTEGER,
                actor_role TEXT,
                note TEXT,
                created_at TEXT NOT NULL
              )
            """)
            conn.commit()