"""Employee import service with lazy pandas import."""
from io import BytesIO
from msd.database.connection import get_conn

class ImportDependencyError(RuntimeError):
    pass

def _ensure_pandas():
    try:
        import pandas as pd  # type: ignore
    except ImportError:
        raise ImportDependencyError(
            "ميزة استيراد الموظفين من Excel تتطلب تثبيت الحزم: pandas و openpyxl.\n"
            "ثبّت عبر:\n"
            "  pip install pandas openpyxl"
        )
    return pd

def import_employees_from_excel(file_storage, dry_run: bool = False):
    """
    يستقبل ملف مرفوع (werkzeug FileStorage) ويستورد الموظفين.
    - dry_run=True: يفحص فقط دون إدخال فعلي.
    يعيد عدد السجلات أو قائمة الأخطاء.
    """
    pd = _ensure_pandas()

    # قراءة الملف إلى DataFrame
    stream = BytesIO(file_storage.read())
    try:
        df = pd.read_excel(stream, engine="openpyxl")
    except Exception as e:
        raise RuntimeError(f"فشل قراءة ملف Excel: {e}")

    required_cols = {"name", "job_title", "department_id"}
    missing = required_cols - set(map(str.lower, df.columns))
    if missing:
        raise ValueError(f"أعمدة مفقودة في الملف: {', '.join(missing)}")

    # توحيد أسماء الأعمدة للحروف الصغيرة
    df.columns = [c.lower().strip() for c in df.columns]

    inserted = 0
    errors = []

    with get_conn() as conn:
        cur = conn.cursor()
        for idx, row in df.iterrows():
            try:
                name = str(row.get("name", "")).strip()
                job_title = str(row.get("job_title", "")).strip()
                dept_id = row.get("department_id")

                if not name or not job_title or pd.isna(dept_id):
                    raise ValueError("سطر غير صالح: name/job_title/department_id مطلوب")

                if not dry_run:
                    cur.execute(
                        """
                        INSERT INTO employees (name, job_title, department_id)
                        VALUES (?, ?, ?)
                        """,
                        (name, job_title, int(dept_id)),
                    )
                inserted += 1
            except Exception as e:
                errors.append(f"سطر {idx+1}: {e}")

        if not dry_run and inserted > 0:
            conn.commit()

    return {"inserted": inserted, "errors": errors}