VACATION_TYPES = [
    {"code": "ANNUAL", "name_ar": "سنوية", "fixed_duration": None, "max_per_request": 90,
     "affects_annual_balance": 1, "affects_emergency_balance": 0, "approval_flow": "dept_then_manager",
     "requires_relation": 0},
    {"code": "EMERGENCY", "name_ar": "طارئة", "fixed_duration": None, "max_per_request": 3,
     "affects_annual_balance": 0, "affects_emergency_balance": 1, "approval_flow": "dept_then_manager",
     "requires_relation": 0},
    {"code": "DEATH_L1", "name_ar": "وفاة (درجة أولى)", "fixed_duration": 7, "max_per_request": 7,
     "affects_annual_balance": 0, "affects_emergency_balance": 0, "approval_flow": "dept_then_manager",
     "requires_relation": 1},
    {"code": "DEATH_L2", "name_ar": "وفاة (درجة ثانية)", "fixed_duration": 3, "max_per_request": 3,
     "affects_annual_balance": 0, "affects_emergency_balance": 0, "approval_flow": "dept_then_manager",
     "requires_relation": 0},
    {"code": "DEATH_HUSBAND", "name_ar": "وفاة الزوج", "fixed_duration": 130, "max_per_request": 130,
     "affects_annual_balance": 0, "affects_emergency_balance": 0, "approval_flow": "dept_then_manager",
     "requires_relation": 0},
    {"code": "MATERNITY_SINGLE", "name_ar": "وضع (عادي)", "fixed_duration": 98, "max_per_request": 98,
     "affects_annual_balance": 0, "affects_emergency_balance": 0, "approval_flow": "dept_then_manager",
     "requires_relation": 0},
    {"code": "MATERNITY_TWINS", "name_ar": "وضع (توأم)", "fixed_duration": 112, "max_per_request": 112,
     "affects_annual_balance": 0, "affects_emergency_balance": 0, "approval_flow": "dept_then_manager",
     "requires_relation": 0},
    {"code": "PILGRIMAGE", "name_ar": "حج", "fixed_duration": 20, "max_per_request": 20,
     "affects_annual_balance": 0, "affects_emergency_balance": 0, "approval_flow": "dept_then_manager",
     "requires_relation": 0},
    {"code": "MARRIAGE", "name_ar": "زواج", "fixed_duration": 14, "max_per_request": 14,
     "affects_annual_balance": 0, "affects_emergency_balance": 0, "approval_flow": "dept_then_manager",
     "requires_relation": 0},
    {"code": "SICK", "name_ar": "مرضية", "fixed_duration": None, "max_per_request": None,
     "affects_annual_balance": 0, "affects_emergency_balance": 0, "approval_flow": "dept_then_manager",
     "requires_relation": 0},
]

RELATION_SPECIAL = {
    # لم نعد نحتاج "زوج" هنا
}

ONE_TIME_TYPES = {"PILGRIMAGE", "MARRIAGE", "DEATH_HUSBAND"}  # ممكن تعدها لو لا تريدها مرة واحدة