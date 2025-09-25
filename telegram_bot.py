import os
import logging
import sqlite3
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from typing import Dict, Optional, List

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters
)

# ================== إعدادات أساسية ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8166976337:AAGyF-Hv35S4S5g0C2JA-OUclCjtqn9u7e0")
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "adw2025")

# توحيد مسار قاعدة البيانات (اطبع المسار ليسهل فحص المشكلة)
DEFAULT_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "employees.db"))
DB_PATH = os.getenv("DATABASE_PATH", DEFAULT_DB)

MANAGER_CHAT_IDS = [
    cid.strip() for cid in os.getenv("MANAGER_CHAT_IDS","").split(",")
    if cid.strip().isdigit()
]

# ================== Logging ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("HRBot")
logger.info("[DB] Using database path: %s", DB_PATH)

# ================== حالات المحادثة ==================
(
    ST_PASSWORD,
    ST_NATIONAL_ID,
    ST_SERIAL,
    ST_MAIN_MENU,
    ST_VAC_TYPE,
    ST_VAC_SUBTYPE,
    ST_VAC_DEATH_TYPE,
    ST_VAC_DEATH_RELATION,
    ST_VAC_DATE_START,
    ST_VAC_DURATION,
    ST_VAC_CONFIRM,
    ST_CANCEL_SELECT
) = range(12)

# ================== ثوابت حالات الإجازة ==================
VAC_STATUS_PENDING_DEPT = "pending_dept"
VAC_STATUS_PENDING_MANAGER = "pending_manager"
VAC_STATUS_APPROVED = "approved"
VAC_STATUS_REJECTED_DEPT = "rejected_dept"
VAC_STATUS_REJECTED_MANAGER = "rejected_manager"
VAC_STATUS_CANCELLED = "cancelled"
PENDING_SET = {VAC_STATUS_PENDING_DEPT, VAC_STATUS_PENDING_MANAGER}

STATUS_AR = {
    VAC_STATUS_PENDING_DEPT: "بانتظار رئيس القسم",
    VAC_STATUS_PENDING_MANAGER: "بانتظار المدير",
    VAC_STATUS_APPROVED: "معتمدة",
    VAC_STATUS_REJECTED_DEPT: "مرفوضة (قسم)",
    VAC_STATUS_REJECTED_MANAGER: "مرفوضة (مدير)",
    VAC_STATUS_CANCELLED: "ملغاة"
}

# ================== طلبات خدمية (إفادة / شهادة مرتب) ==================
SERVICE_REQ_CERT = "طلب إفادة"
SERVICE_REQ_SALARY = "طلب شهادة مرتب"
SERVICE_OPTIONS = {SERVICE_REQ_CERT, SERVICE_REQ_SALARY}

SERVICE_TYPE_CODES = {
    SERVICE_REQ_CERT: "CERT",
    SERVICE_REQ_SALARY: "SALARY"
}

CERT_EMPLOYEE_REPLY = "تم تسجيل طلب الإفادة. ستصلك رسالة عند التجهيز."
SALARY_EMPLOYEE_REPLY = "تم تسجيل طلب شهادة المرتب. ستصلك رسالة عند التجهيز."

MANAGER_SERVICE_TEMPLATE = (
    "📥 طلب إداري جديد:\n"
    "الموظف: {name} (ID:{id})\n"
    "النوع: {req_type}\n"
    "التاريخ: {ts}"
)

# زر حالة الطلبات (تعريب /requests)
BUTTON_REQUESTS_LABEL = "📄 حالة الطلبات"

# ================== نموذج بيانات نوع الإجازة ==================
@dataclass
class VacationTypeMeta:
    code: str
    name_ar: str
    fixed_duration: Optional[int] = None
    max_per_request: Optional[int] = None
    requires_relation: bool = False
    affects_annual_balance: bool = False
    affects_emergency_balance: bool = False

# ================== DB Helpers ==================
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_one(sql: str, params=()):
    with db_connect() as c:
        cur = c.execute(sql, params)
        return cur.fetchone()

def fetch_all(sql: str, params=()):
    with db_connect() as c:
        cur = c.execute(sql, params)
        return cur.fetchall()

def execute(sql: str, params=()):
    with db_connect() as c:
        cur = c.execute(sql, params)
        c.commit()
        return cur.lastrowid

def ensure_tables():
    """
    تأكد من وجود جدول service_requests (في حال تشغيل البوت قبل الهجرة).
    """
    try:
        execute("""
            CREATE TABLE IF NOT EXISTS service_requests (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              employee_id INTEGER NOT NULL,
              request_type TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'new',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              notes TEXT
            )
        """)
    except Exception as e:
        logger.error("فشل إنشاء/التأكد من جدول service_requests: %s", e)

# ---- إنشاء طلب خدمة ----
def record_service_request(employee_id: int, request_code: str):
    now = datetime.utcnow().isoformat(timespec="seconds")
    try:
        rid = execute("""
            INSERT INTO service_requests (employee_id, request_type, status, created_at, updated_at)
            VALUES (?, ?, 'new', ?, ?)
        """, (employee_id, request_code, now, now))
        logger.info("[SR-DEBUG] Service request inserted id=%s employee_id=%s type=%s", rid, employee_id, request_code)
    except Exception as e:
        logger.exception("تعذر تسجيل الطلب الخدمي (employee_id=%s, type=%s): %s", employee_id, request_code, e)

def list_employee_service_requests(employee_id: int, limit=10):
    rows = fetch_all("""
        SELECT id, request_type, status, created_at, updated_at
          FROM service_requests
         WHERE employee_id=?
         ORDER BY id DESC
         LIMIT ?
    """, (employee_id, limit))
    return [dict(r) for r in rows]

# ================== تحميل أنواع الإجازة ==================
def load_vacation_types() -> Dict[str, VacationTypeMeta]:
    try:
        rows = fetch_all("""
            SELECT code, name_ar, fixed_duration, max_per_request,
                   requires_relation, affects_annual_balance, affects_emergency_balance
            FROM vacation_types
        """)
    except Exception:
        # إذا لم تُزرع بعد (seed) قد يرجع فارغ – نعيد خريطة فارغة حتى لا يتعطل البوت
        rows = []
    t: Dict[str, VacationTypeMeta] = {}
    for r in rows:
        t[r["name_ar"]] = VacationTypeMeta(
            code=r["code"],
            name_ar=r["name_ar"],
            fixed_duration=r["fixed_duration"],
            max_per_request=r["max_per_request"],
            requires_relation=bool(r["requires_relation"]),
            affects_annual_balance=bool(r["affects_annual_balance"]),
            affects_emergency_balance=bool(r["affects_emergency_balance"])
        )
    return t

# ================== موظف ==================
def get_employee_by_ids(national_id: str, serial_number: str) -> Optional[sqlite3.Row]:
    return fetch_one("""
        SELECT id, name, national_id, serial_number, department_id,
               annual_balance, emergency_balance, work_days, hiring_date,
               job_grade, bonus
          FROM employees
         WHERE national_id=? AND serial_number=?
    """, (national_id.strip(), serial_number.strip()))

def save_employee_chat_id(employee_id: int, chat_id: int):
    try:
        execute("UPDATE employees SET tg_chat_id=? WHERE id=?", (str(chat_id), employee_id))
    except Exception:
        pass

# ================== تداخل الإجازات ==================
def has_overlap(employee_id: int, start_date: str, end_date: str) -> List[sqlite3.Row]:
    return fetch_all("""
        SELECT id, type_code, start_date, end_date, status
          FROM vacation_requests
         WHERE employee_id=?
           AND status NOT IN (?, ?, ?)
           AND NOT (date(end_date) < date(?) OR date(start_date) > date(?))
         ORDER BY id DESC
    """, (
        employee_id,
        VAC_STATUS_CANCELLED,
        VAC_STATUS_REJECTED_DEPT,
        VAC_STATUS_REJECTED_MANAGER,
        start_date,
        end_date
    ))

# ================== إنشاء / إلغاء إجازة ==================
def create_vacation_request(employee_id: int,
                            type_code: str,
                            start_date: str,
                            end_date: str,
                            requested_days: int,
                            relation: Optional[str],
                            notes: str) -> int:
    return execute("""
        INSERT INTO vacation_requests
        (employee_id, type_code, relation, start_date, end_date,
         requested_days, status, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (employee_id, type_code, relation, start_date, end_date,
          requested_days, VAC_STATUS_PENDING_DEPT, notes or "",
          datetime.utcnow().isoformat()))

def cancel_pending_request(employee_id: int, vac_id: int) -> bool:
    row = fetch_one("""
        SELECT status FROM vacation_requests
        WHERE id=? AND employee_id=?
    """, (vac_id, employee_id))
    if not row or row["status"] not in PENDING_SET:
        return False
    execute("""
        UPDATE vacation_requests
           SET status=?
         WHERE id=? AND employee_id=?
    """, (VAC_STATUS_CANCELLED, vac_id, employee_id))
    return True

def list_recent_vacations(employee_id: int, limit=10):
    return fetch_all("""
        SELECT id, type_code, start_date, end_date, requested_days, status, rejection_reason
          FROM vacation_requests
         WHERE employee_id=?
         ORDER BY id DESC
         LIMIT ?
    """, (employee_id, limit))

def list_recent_absences(employee_id: int, limit=30):
    return fetch_all("""
        SELECT start_date, end_date, type, duration
          FROM absences
         WHERE employee_id=?
         ORDER BY id DESC
         LIMIT ?
    """, (employee_id, limit))

# ================== تواريخ ==================
def inclusive_end(start: date, days: int) -> date:
    return start + timedelta(days=days - 1)

# ================== فئة البوت ==================
class VacationTelegramBot:
    def __init__(self, token: str):
        if not token:
            raise RuntimeError("BOT_TOKEN غير مضبوط في متغيرات البيئة.")
        ensure_tables()
        self.token = token
        self.application = ApplicationBuilder().token(token).build()
        self.types_map: Dict[str, VacationTypeMeta] = load_vacation_types()
        self.types_by_code: Dict[str, VacationTypeMeta] = {
            m.code: m for m in self.types_map.values()
        }
        # يمكن التوسع لاحقاً
        self.maternity_subtypes = {}
        self.death_types = {}
        self.death_relations_primary: List[str] = []
        self.setup_handlers()

    def rebuild_type_maps(self):
        self.types_map = load_vacation_types()
        self.types_by_code = {m.code: m for m in self.types_map.values()}

    def code_to_ar(self, code: str) -> str:
        meta = self.types_by_code.get(code)
        return meta.name_ar if meta else code

    # ====== إشعار المديرين ======
    async def notify_managers_service(self, context: ContextTypes.DEFAULT_TYPE, employee: dict, req_label: str):
        if not MANAGER_CHAT_IDS:
            logger.warning("MANAGER_CHAT_IDS غير مضبوطة، لن يُرسل إشعار.")
            return
        msg = MANAGER_SERVICE_TEMPLATE.format(
            name=employee.get("name",""),
            id=employee.get("id"),
            req_type=req_label,
            ts=datetime.utcnow().isoformat(timespec="seconds")
        )
        for cid in MANAGER_CHAT_IDS:
            try:
                await context.bot.send_message(chat_id=int(cid), text=msg)
            except Exception as e:
                logger.error("فشل إرسال إشعار إلى المدير chat_id=%s: %s", cid, e)

    # ====== Handlers ======
    def setup_handlers(self):
        conv = ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={
                ST_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.check_password)],
                ST_NATIONAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_national_id)],
                ST_SERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_serial)],
                ST_MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.main_menu_router)],
                ST_VAC_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_vac_type)],
                ST_VAC_SUBTYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_maternity_subtype)],
                ST_VAC_DEATH_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_death_type)],
                ST_VAC_DEATH_RELATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_death_relation)],
                ST_VAC_DATE_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_date_input)],
                ST_VAC_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_duration)],
                ST_VAC_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_confirm)],
                ST_CANCEL_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_cancel_choice)],
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel),
                MessageHandler(filters.Regex("^إلغاء$"), self.cancel)
            ],
            allow_reentry=True
        )
        self.application.add_handler(conv)
        # أمر /requests يبقى مدعوماً
        self.application.add_handler(CommandHandler("requests", self.cmd_requests))
        # أمر debug اختياري
        self.application.add_handler(CommandHandler("debug_db", self.cmd_debug_db))
        self.application.add_error_handler(self.error_handler)

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.exception("BOT ERROR: %s", context.error)

    # ====== Start / Auth ======
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "أهلاً بك في برنامج إدارة شؤون الموظفين.\nادخل كلمة المرور:",
            reply_markup=ReplyKeyboardMarkup([["إلغاء"]], resize_keyboard=True)
        )
        return ST_PASSWORD

    async def check_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text != BOT_PASSWORD:
            await update.message.reply_text("كلمة مرور غير صحيحة، حاول مجدداً:", reply_markup=ReplyKeyboardMarkup([["إلغاء"]], resize_keyboard=True))
            return ST_PASSWORD
        await update.message.reply_text("أدخل الرقم الوطني:", reply_markup=ReplyKeyboardMarkup([["إلغاء"]], resize_keyboard=True))
        return ST_NATIONAL_ID

    async def handle_national_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["national_id"] = update.message.text.strip()
        await update.message.reply_text("أدخل الرقم الآلي:", reply_markup=ReplyKeyboardMarkup([["إلغاء"]], resize_keyboard=True))
        return ST_SERIAL

    async def handle_serial(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        emp = get_employee_by_ids(context.user_data.get("national_id",""), update.message.text.strip())
        if not emp:
            await update.message.reply_text("بيانات غير صحيحة أو الموظف غير موجود.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        emp_d = dict(emp)
        context.user_data["employee"] = emp_d
        try:
            save_employee_chat_id(emp_d["id"], update.effective_chat.id)
        except Exception:
            pass
        await self.show_main_menu(update)
        return ST_MAIN_MENU

    # ====== Menu ======
    async def show_main_menu(self, update: Update):
        kb = [
            ["📅 طلب إجازة", "📋 سجل الإجازات"],
            ["✈️ رصيد الإجازات", "📝 سجل الغياب"],
            ["📅 أيام العمل", "👤 بياناتي"],
            [SERVICE_REQ_CERT, SERVICE_REQ_SALARY],
            ["❌ إلغاء إجازة معلقة", BUTTON_REQUESTS_LABEL],
            ["إلغاء"]
        ]
        await update.message.reply_text(
            "اختر من القائمة:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )

    async def main_menu_router(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        txt = update.message.text.strip()
        if txt == "إلغاء":
            return await self.cancel(update, context)
        if not context.user_data.get("employee"):
            await update.message.reply_text("انتهت الجلسة. اكتب /start.")
            return ConversationHandler.END

        if txt in SERVICE_OPTIONS:
            emp = context.user_data["employee"]
            code = SERVICE_TYPE_CODES[txt]
            record_service_request(emp["id"], code)
            await self.notify_managers_service(context, emp, txt)
            if txt == SERVICE_REQ_CERT:
                await update.message.reply_text(CERT_EMPLOYEE_REPLY)
            else:
                await update.message.reply_text(SALARY_EMPLOYEE_REPLY)
            await self.show_main_menu(update)
            return ST_MAIN_MENU

        if txt == BUTTON_REQUESTS_LABEL:
            await self.cmd_requests(update, context)
            return ST_MAIN_MENU

        if txt == "📅 طلب إجازة":
            return await self.begin_vacation_request(update, context)
        if txt == "📋 سجل الإجازات":
            return await self.show_vacations_history(update, context)
        if txt == "✈️ رصيد الإجازات":
            return await self.show_balances(update, context)
        if txt == "📝 سجل الغياب":
            return await self.show_absences(update, context)
        if txt == "📅 أيام العمل":
            return await self.show_work_days(update, context)
        if txt == "👤 بياناتي":
            return await self.show_basic_info(update, context)
        if txt == "❌ إلغاء إجازة معلقة":
            return await self.list_cancelable(update, context)

        await self.show_main_menu(update)
        return ST_MAIN_MENU

    # ====== /requests أمر لعرض طلبات الخدمة (و زر حالة الطلبات) ======
    async def cmd_requests(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        emp = context.user_data.get("employee")
        if not emp:
            await update.message.reply_text("ابدأ الجلسة أولاً /start")
            return
        rows = list_employee_service_requests(emp["id"], limit=10)
        if not rows:
            await update.message.reply_text("لا توجد طلبات خدمة مسجلة.", reply_markup=ReplyKeyboardMarkup([["↩️ رجوع","إلغاء"]], resize_keyboard=True))
            return
        status_map = {
            "new":"جديد",
            "preparing":"تحت التجهيز",
            "ready":"جاهز",
            "delivered":"تم التسليم",
            "cancelled":"ملغي"
        }
        msg = "📄 حالة طلباتك الإدارية (آخر 10):\n"
        for r in rows:
            typ = "إفادة" if r["request_type"]=="CERT" else "شهادة مرتب"
            msg += f"- #{r['id']} | {typ} | {status_map.get(r['status'], r['status'])} | {r['created_at']}\n"
        await update.message.reply_text(msg)

    # ====== الأمر التشخيصي ======
    async def cmd_debug_db(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # للمساعدة في التشخيص: يعرض عدد السجلات في جدول الطلبات
        try:
            cnt = fetch_one("SELECT COUNT(*) c FROM service_requests")["c"]
            await update.message.reply_text(f"[Debug]\nDB: {DB_PATH}\nعدد طلبات الخدمة: {cnt}")
        except Exception as e:
            await update.message.reply_text(f"Debug Error: {e}")

    # ====== بقية دوال الإجازات كما هي (مختصرة) ======
    # (تم الإبقاء على تدفق الإجازات الأصلي بدون تغيير جوهري سوى ما سبق)
    async def begin_vacation_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.rebuild_type_maps()
        names = list(self.types_map.keys())
        rows=[]; row=[]
        for name in names:
            row.append(name)
            if len(row)==3:
                rows.append(row); row=[]
        if row: rows.append(row)
        rows.append(["↩️ رجوع","إلغاء"])
        context.user_data["vac_req"]={}
        await update.message.reply_text(
            "اختر نوع الإجازة:",
            reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
        )
        return ST_VAC_TYPE

    async def handle_vac_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        txt=update.message.text
        if txt=="إلغاء": return await self.cancel(update, context)
        if txt=="↩️ رجوع":
            await self.show_main_menu(update); return ST_MAIN_MENU
        if txt not in self.types_map:
            await update.message.reply_text("نوع غير معروف، أعد الاختيار:")
            return ST_VAC_TYPE
        meta=self.types_map[txt]
        context.user_data["vac_req"]={
            "type_name_ar":txt,
            "type_code":meta.code,
            "meta":meta
        }
        context.user_data["vac_req"]["date_step"]="year"
        await update.message.reply_text(
            "أدخل سنة البداية (مثال 2025):",
            reply_markup=ReplyKeyboardMarkup([["↩️ رجوع","إلغاء"]], resize_keyboard=True)
        )
        return ST_VAC_DATE_START

    async def handle_maternity_subtype(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("غير مفعّل حالياً.")
        return ST_MAIN_MENU

    async def handle_death_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("اختر نوع الإجازة من القائمة.")
        return ST_MAIN_MENU

    async def handle_death_relation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("غير مفعّل حالياً.")
        return ST_MAIN_MENU

    async def handle_date_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        vac_req=context.user_data.get("vac_req",{})
        txt=update.message.text
        if txt=="إلغاء": return await self.cancel(update, context)
        if txt=="↩️ رجوع": return await self.begin_vacation_request(update, context)
        try:
            step=vac_req.get("date_step","year")
            if step=="year":
                y=int(txt)
                if y<2000 or y>2100: raise ValueError("سنة خارج النطاق")
                vac_req["year"]=y
                vac_req["date_step"]="month"
                kb=[[str(i) for i in range(1,13)]]
                kb.append(["↩️ رجوع","إلغاء"])
                await update.message.reply_text("أدخل رقم الشهر (1-12):", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
                return ST_VAC_DATE_START
            elif step=="month":
                m=int(txt)
                if m<1 or m>12: raise ValueError("شهر غير صحيح")
                vac_req["month"]=m
                vac_req["date_step"]="day"
                if m==2:
                    y=vac_req["year"]
                    leap=(y%4==0 and y%100!=0) or (y%400==0)
                    days_in = 29 if leap else 28
                elif m in (4,6,9,11):
                    days_in=30
                else:
                    days_in=31
                rows=[]; row=[]
                for d in range(1,days_in+1):
                    row.append(str(d))
                    if len(row)==7:
                        rows.append(row); row=[]
                if row: rows.append(row)
                rows.append(["↩️ رجوع","إلغاء"])
                await update.message.reply_text("اختر اليوم:", reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True))
                return ST_VAC_DATE_START
            elif step=="day":
                day=int(txt)
                start_d=date(vac_req["year"], vac_req["month"], day)
                vac_req["start_date"]=start_d.isoformat()
                meta:VacationTypeMeta=vac_req["meta"]
                if meta.fixed_duration:
                    vac_req["requested_days"]=meta.fixed_duration
                    vac_req["end_date"]=inclusive_end(start_d, meta.fixed_duration).isoformat()
                    return await self.show_vacation_summary(update, context)
                else:
                    await update.message.reply_text("أدخل عدد الأيام:", reply_markup=ReplyKeyboardMarkup([["↩️ رجوع","إلغاء"]], resize_keyboard=True))
                    return ST_VAC_DURATION
        except Exception as e:
            await update.message.reply_text(f"خطأ: {e}\nأعد المحاولة:", reply_markup=ReplyKeyboardMarkup([["↩️ رجوع","إلغاء"]], resize_keyboard=True))
        return ST_VAC_DATE_START

    async def handle_duration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        txt=update.message.text
        if txt=="إلغاء": return await self.cancel(update, context)
        if txt=="↩️ رجوع":
            context.user_data["vac_req"]["date_step"]="day"
            await update.message.reply_text("اختر اليوم مجدداً:", reply_markup=ReplyKeyboardMarkup([["↩️ رجوع","إلغاء"]], resize_keyboard=True))
            return ST_VAC_DATE_START
        try:
            d=int(txt)
            if d<=0: raise ValueError("عدد غير صالح")
            vac_req=context.user_data["vac_req"]
            start_d=datetime.strptime(vac_req["start_date"], "%Y-%m-%d").date()
            vac_req["requested_days"]=d
            vac_req["end_date"]=inclusive_end(start_d, d).isoformat()
            return await self.show_vacation_summary(update, context)
        except Exception as e:
            await update.message.reply_text(f"قيمة غير صالحة: {e}\nأعد الإدخال:")
            return ST_VAC_DURATION

    async def show_vacation_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        vac_req=context.user_data["vac_req"]
        s="📋 ملخص طلب الإجازة:\n"
        s+=f"• النوع: {vac_req['type_name_ar']} ({vac_req['type_code']})\n"
        s+=f"• البداية: {vac_req['start_date']}\n"
        s+=f"• النهاية: {vac_req['end_date']}\n"
        s+=f"• المدة: {vac_req['requested_days']} يوم\n"
        s+="تأكيد الإرسال؟"
        kb=[["نعم","لا","↩️ رجوع","إلغاء"]]
        await update.message.reply_text(s, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return ST_VAC_CONFIRM

    async def handle_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        txt=update.message.text
        vac_req=context.user_data.get("vac_req")
        if not vac_req:
            await update.message.reply_text("لا توجد بيانات. ابدأ /start")
            return ConversationHandler.END
        if txt=="إلغاء": return await self.cancel(update, context)
        if txt=="↩️ رجوع":
            vac_req["date_step"]="day"
            await update.message.reply_text("اختر تاريخاً جديداً:", reply_markup=ReplyKeyboardMarkup([["↩️ رجوع","إلغاء"]], resize_keyboard=True))
            return ST_VAC_DATE_START
        if txt=="لا":
            await update.message.reply_text("تم الإلغاء.")
            await self.show_main_menu(update)
            return ST_MAIN_MENU
        if txt!="نعم":
            await update.message.reply_text("اختر نعم أو لا:")
            return ST_VAC_CONFIRM

        emp=context.user_data["employee"]
        start_date=vac_req["start_date"]
        end_date=vac_req["end_date"]

        conflicts=has_overlap(emp["id"], start_date, end_date)
        if conflicts:
            msg="❗ يوجد تداخل مع طلبات:\n"
            for c in conflicts:
                msg+=f"- ID {c['id']} | {self.code_to_ar(c['type_code'])} | {c['start_date']}→{c['end_date']} | {STATUS_AR.get(c['status'], c['status'])}\n"
            msg+="اختر تاريخاً مختلفاً."
            await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["↩️ رجوع","إلغاء"]], resize_keyboard=True))
            vac_req["date_step"]="day"
            return ST_VAC_DATE_START

        try:
            rid=create_vacation_request(
                employee_id=emp["id"],
                type_code=vac_req["type_code"],
                start_date=start_date,
                end_date=end_date,
                requested_days=vac_req["requested_days"],
                relation=vac_req.get("relation"),
                notes=vac_req.get("notes","")
            )
            await update.message.reply_text(
                "✅ تم إرسال الطلب.\n"
                f"رقم الطلب: {rid}\n"
                f"الفترة: {start_date} → {end_date}\n"
                f"المدة: {vac_req['requested_days']} يوم\n"
                f"الحالة: {STATUS_AR[VAC_STATUS_PENDING_DEPT]}"
            )
        except Exception as e:
            await update.message.reply_text(f"خطأ أثناء الإنشاء: {e}")
        context.user_data.pop("vac_req", None)
        await self.show_main_menu(update)
        return ST_MAIN_MENU

    async def list_cancelable(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        emp=context.user_data["employee"]
        rows=fetch_all("""
            SELECT id, type_code, start_date, end_date, status
              FROM vacation_requests
             WHERE employee_id=?
             ORDER BY id DESC LIMIT 20
        """,(emp["id"],))
        cancellable=[r for r in rows if r["status"] in PENDING_SET]
        if not cancellable:
            await update.message.reply_text("لا توجد طلبات معلقة.", reply_markup=ReplyKeyboardMarkup([["↩️ رجوع","إلغاء"]], resize_keyboard=True))
            return ST_MAIN_MENU
        msg="اختر رقم الطلب للإلغاء:\n"
        kb=[]
        for r in cancellable:
            msg+=f"- {r['id']} | {self.code_to_ar(r['type_code'])} | {r['start_date']}→{r['end_date']} | {STATUS_AR.get(r['status'], r['status'])}\n"
            kb.append([str(r['id'])])
        kb.append(["↩️ رجوع","إلغاء"])
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return ST_CANCEL_SELECT

    async def handle_cancel_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        txt=update.message.text
        if txt=="إلغاء": return await self.cancel(update, context)
        if txt=="↩️ رجوع":
            await self.show_main_menu(update); return ST_MAIN_MENU
        emp=context.user_data["employee"]
        try:
            vid=int(txt)
            if cancel_pending_request(emp["id"], vid):
                await update.message.reply_text("تم إلغاء الطلب.")
            else:
                await update.message.reply_text("لا يمكن الإلغاء (غير موجود أو حالته غير مناسبة).")
        except Exception:
            await update.message.reply_text("معرّف غير صالح.")
        await self.show_main_menu(update)
        return ST_MAIN_MENU

    async def show_vacations_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        emp=context.user_data["employee"]
        rows=list_recent_vacations(emp["id"], 10)
        if not rows:
            await update.message.reply_text("لا يوجد سجل إجازات.", reply_markup=ReplyKeyboardMarkup([["↩️ رجوع","إلغاء"]], resize_keyboard=True))
            return ST_MAIN_MENU
        msg="📋 آخر 10 طلبات:\n\n"
        for r in rows:
            msg+=f"ID {r['id']} | {self.code_to_ar(r['type_code'])} | {r['start_date']}→{r['end_date']} ({r['requested_days']} يوم) | حالة: {STATUS_AR.get(r['status'],r['status'])}\n"
            if r["rejection_reason"]:
                msg+=f"سبب الرفض: {r['rejection_reason']}\n"
            msg+="-----\n"
        await update.message.reply_text(msg)
        return ST_MAIN_MENU

    async def show_absences(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        emp=context.user_data["employee"]
        rows=list_recent_absences(emp["id"], 30)
        if not rows:
            await update.message.reply_text("لا يوجد سجل غياب.", reply_markup=ReplyKeyboardMarkup([["↩️ رجوع","إلغاء"]], resize_keyboard=True))
            return ST_MAIN_MENU
        msg="📝 سجل الغياب:\n"
        for r in rows:
            msg+=f"- {r['start_date']}→{r['end_date']} | {r['type']} | {r['duration']} يوم\n"
        await update.message.reply_text(msg)
        return ST_MAIN_MENU

    async def show_balances(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        emp=context.user_data["employee"]
        row=fetch_one("SELECT annual_balance, emergency_balance FROM employees WHERE id=?",(emp["id"],))
        if row:
            msg=f"✈️ السنوية المتاحة: {row['annual_balance']}\n🚨 الطارئة المتاحة: {row['emergency_balance']}"
        else:
            msg="تعذر جلب الأرصدة."
        await update.message.reply_text(msg)
        return ST_MAIN_MENU

    async def show_work_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        emp=context.user_data["employee"]
        row=fetch_one("SELECT work_days FROM employees WHERE id=?",(emp["id"],))
        if not row or not row["work_days"]:
            await update.message.reply_text("لا توجد أيام عمل مسجلة.")
            return ST_MAIN_MENU
        work_days=row["work_days"]
        msg="📅 أيام العمل:\n"+work_days
        await update.message.reply_text(msg)
        return ST_MAIN_MENU

    async def show_basic_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        emp=context.user_data["employee"]
        msg=(f"👤 بياناتي:\n"
             f"الاسم: {emp['name']}\n"
             f"الرقم الوطني: {emp['national_id']}\n"
             f"الرقم الآلي: {emp['serial_number']}\n"
             f"القسم ID: {emp['department_id']}\n"
             f"تاريخ التعيين: {emp.get('hiring_date','-')}\n"
             f"الدرجة: {emp.get('job_grade','-')} | العلاوة: {emp.get('bonus','-')}")
        await update.message.reply_text(msg)
        return ST_MAIN_MENU

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("تم إنهاء الحوار. اكتب /start للبدء من جديد.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    def run(self):
        logger.info("Starting Telegram Bot with DB=%s", DB_PATH)
        self.application.run_polling()

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("⚠️ BOT_TOKEN غير مضبوط. اضبطه ثم أعد التشغيل.")
    else:
        bot = VacationTelegramBot(BOT_TOKEN)
        bot.run()