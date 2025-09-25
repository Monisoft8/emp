from datetime import datetime, date
from msd.database.connection import get_conn

ALLOWED_TYPES = {
    "absence": "غياب",
    "late": "تأخير",
    "early_leave": "انصراف مبكر"
}

# تخزين أعمدة الجدول في الذاكرة بعد أول قراءة
_ABS_COLS_CACHE = None

def _now():
    return datetime.utcnow().isoformat()

def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def _get_abs_cols():
    global _ABS_COLS_CACHE
    if _ABS_COLS_CACHE is not None:
        return _ABS_COLS_CACHE
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(absences)")
        _ABS_COLS_CACHE = {r[1] for r in cur.fetchall()}
    return _ABS_COLS_CACHE

def create_absence(employee_id: int, type_code: str,
                   single_date: str = None,
                   start_date: str = None,
                   end_date: str = None,
                   notes: str = None):
    """
    يدعم:
      - single_date  (حقل date القديم)
      - start_date / end_date (النطاق الجديد)
    إن وُجد العمود date في الجدول يُملأ دائماً بقيمة start_date (للتوافق).
    """
    if type_code not in ALLOWED_TYPES:
        raise ValueError("نوع غير مدعوم")
    if not employee_id:
        raise ValueError("employee_id مطلوب")

    if single_date and (start_date or end_date):
        raise ValueError("استخدم إما تاريخ مفرد أو نطاق (من/إلى)")

    if not single_date and not (start_date and end_date):
        # إذا لم يُرسل أي تاريخ نأخذ اليوم
        single_date = date.today().isoformat()

    if single_date:
        start_date = end_date = single_date

    try:
        sd = _parse_date(start_date)
        ed = _parse_date(end_date)
    except ValueError:
        raise ValueError("تنسيق تاريخ غير صالح (YYYY-MM-DD)")

    if ed < sd:
        raise ValueError("النهاية قبل البداية")

    if type_code == "absence":
        duration = (ed - sd).days + 1
    else:
        # تأخير / انصراف مبكر = يوم واحد فقط
        duration = 1
        start_date = end_date = sd.isoformat()

    cols = _get_abs_cols()
    with get_conn() as conn:
        cur = conn.cursor()
        if "start_date" in cols and "end_date" in cols:
            # الجدول محدث
            if "date" in cols:
                cur.execute("""
                    INSERT INTO absences(employee_id, type, date, start_date, end_date, duration, notes, created_at)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (employee_id, type_code, start_date, start_date, end_date, duration, notes, _now()))
            else:
                cur.execute("""
                    INSERT INTO absences(employee_id, type, start_date, end_date, duration, notes, created_at)
                    VALUES (?,?,?,?,?,?,?)
                """, (employee_id, type_code, start_date, end_date, duration, notes, _now()))
        else:
            # الجدول قديم (لا يملك start/end) – نستخدم date و duration فقط
            # في هذه الحالة لا يدعم النطاق فعلياً بل نخزن اليوم الأول
            if "date" not in cols:
                raise ValueError("بنية جدول الغياب غير مدعومة. أرفق PRAGMA table_info(absences).")
            cur.execute("""
                INSERT INTO absences(employee_id, date, type, duration, notes, created_at)
                VALUES (?,?,?,?,?,?)
            """, (employee_id, start_date, type_code, duration, notes, _now()))
        rid = cur.lastrowid
        conn.commit()
        return rid

def list_absences(page=1, limit=10, employee_id=None, type_code=None,
                  date_from=None, date_to=None, search=None):
    page = max(page,1)
    limit = min(max(limit,1),200)
    offset=(page-1)*limit
    cols = _get_abs_cols()

    # تحديد الأعمدة المتاحة
    has_range = "start_date" in cols and "end_date" in cols
    # إذا الجدول قديم، نستخدم date كلاً من البداية والنهاية
    select_range = "a.start_date, a.end_date" if has_range else "a.date AS start_date, a.date AS end_date"

    clauses=[]
    params=[]
    if employee_id:
        clauses.append("a.employee_id=?")
        params.append(employee_id)
    if type_code:
        clauses.append("a.type=?")
        params.append(type_code)
    if date_from:
        if has_range:
            clauses.append("a.start_date>=?")
        else:
            clauses.append("a.date>=?")
        params.append(date_from)
    if date_to:
        if has_range:
            clauses.append("a.end_date<=?")
        else:
            clauses.append("a.date<=?")
        params.append(date_to)
    if search:
        like=f"%{search.strip()}%"
        clauses.append("(a.notes LIKE ? OR e.name LIKE ?)")
        params.extend([like, like])

    where_sql=("WHERE "+" AND ".join(clauses)) if clauses else ""
    base=f"""
      FROM absences a
      LEFT JOIN employees e ON e.id=a.employee_id
      {where_sql}
    """
    with get_conn() as conn:
        cur=conn.cursor()
        cur.execute(f"SELECT COUNT(*) {base}", params)
        total=cur.fetchone()[0]
        cur.execute(f"""
            SELECT a.id, a.employee_id, e.name AS employee_name,
                   a.type, {select_range}, a.duration, a.notes, a.created_at
              {base}
             ORDER BY a.id DESC
             LIMIT ? OFFSET ?
        """, params+[limit, offset])
        items=[dict(r) for r in cur.fetchall()]
    pages=(total+limit-1)//limit if total else 1
    return {"items":items,"total":total,"page":page,"pages":pages,"limit":limit}

def get_absence(aid: int):
    cols = _get_abs_cols()
    has_range = "start_date" in cols and "end_date" in cols
    select_range = "a.start_date, a.end_date" if has_range else "a.date AS start_date, a.date AS end_date"
    with get_conn() as conn:
        cur=conn.cursor()
        cur.execute(f"""
           SELECT a.id, a.employee_id, e.name AS employee_name,
                  a.type, {select_range}, a.duration, a.notes, a.created_at
             FROM absences a
             LEFT JOIN employees e ON e.id=a.employee_id
            WHERE a.id=?
        """,(aid,))
        row=cur.fetchone()
        return dict(row) if row else None

def update_absence(aid: int, actor_role: str,
                   type_code=None, start_date=None, end_date=None, notes=None):
    if actor_role not in ("manager","admin","department_head"):
        raise ValueError("غير مصرح")

    row = get_absence(aid)
    if not row:
        raise ValueError("السجل غير موجود")

    new_type = type_code or row["type"]
    if new_type not in ALLOWED_TYPES:
        raise ValueError("نوع غير مدعوم")

    sd = start_date or row["start_date"]
    ed = end_date or row["end_date"]

    try:
        sd_d=_parse_date(sd); ed_d=_parse_date(ed)
    except ValueError:
        raise ValueError("تواريخ غير صالحة")

    if ed_d < sd_d:
        raise ValueError("النهاية قبل البداية")

    if new_type == "absence":
        duration=(ed_d - sd_d).days + 1
    else:
        duration=1
        sd = ed = sd_d.isoformat()

    cols=_get_abs_cols()
    with get_conn() as conn:
        cur=conn.cursor()
        if "start_date" in cols and "end_date" in cols:
            if "date" in cols:
                cur.execute("""
                    UPDATE absences
                       SET type=?, date=?, start_date=?, end_date=?, duration=?, notes=?
                     WHERE id=?
                """,(new_type, sd, sd, ed, duration, notes if notes is not None else row["notes"], aid))
            else:
                cur.execute("""
                    UPDATE absences
                       SET type=?, start_date=?, end_date=?, duration=?, notes=?
                     WHERE id=?
                """,(new_type, sd, ed, duration, notes if notes is not None else row["notes"], aid))
        else:
            # جدول قديم (date فقط)
            cur.execute("""
                UPDATE absences
                   SET type=?, date=?, duration=?, notes=?
                 WHERE id=?
            """,(new_type, sd, duration, notes if notes is not None else row["notes"], aid))
        if cur.rowcount==0:
            raise ValueError("فشل التحديث")
        conn.commit()

def delete_absence(aid: int, actor_role: str):
    if actor_role not in ("manager","admin"):
        raise ValueError("غير مصرح")
    with get_conn() as conn:
        cur=conn.cursor()
        cur.execute("DELETE FROM absences WHERE id=?", (aid,))
        if cur.rowcount==0:
            raise ValueError("غير موجود")
        conn.commit()

def type_label(code):
    return ALLOWED_TYPES.get(code, code)