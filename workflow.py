VALID_STATUS_TRANSITIONS = {
    "pending_dept": {"pending_manager", "rejected_dept", "cancelled"},
    "pending_manager": {"approved", "rejected_manager", "cancelled"},
    "approved": {"cancelled"},
    "rejected_dept": set(),
    "rejected_manager": set(),
    "cancelled": set()
}

def can_transition(current, target):
    return target in VALID_STATUS_TRANSITIONS.get(current, set())