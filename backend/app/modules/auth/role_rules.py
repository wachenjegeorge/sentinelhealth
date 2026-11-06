"""Role-to-facility-level validation rules.

Level 1: Community Health Promoters (Worker) + CHU In-charge (Department Head)
Level 2: Nurses/Clinical Officers (Worker) + Facility In-charge (Hospital Head)
Level 3: Nurses/Clinical Officers (Worker) + Facility In-charge (Hospital Head)
Level 4: Clinicians/Nurses (Worker) + Department Heads + Medical Superintendent (Hospital Head)
Level 5: Specialists (Worker) + Department Heads + Medical Superintendent (Hospital Head)
Level 6: Specialists (Worker) + Department Heads + CEO (Hospital Head)
"""

ROLE_ALLOWED_LEVELS = {
    "worker": {1, 2, 3, 4, 5, 6},
    "department_head": {1, 4, 5, 6},       # CHU in-charge, clinical dept heads, ward in-charges
    "hospital_head": {2, 3, 4, 5, 6},      # Facility in-charge, Medical Superintendent, CEO
    "county_officer": {1, 2, 3, 4, 5, 6},   # Oversees all facilities in county
    "admin": {1, 2, 3, 4, 5, 6},
}


def role_allowed_for_level(role: str, keph_level: int) -> bool:
    """Check if a role is allowed at a facility of the given KEPH level."""
    allowed = ROLE_ALLOWED_LEVELS.get(role, set())
    return keph_level in allowed


def department_allowed_for_level(department: str, keph_level: int) -> bool:
    """Check if a department exists at the given KEPH level."""
    level_depts = {
        1: {"Community Health"},
        2: {"Outpatient (OPD)", "Pharmacy"},
        3: {"Outpatient (OPD)", "Maternity", "Laboratory", "Pharmacy"},
        4: {"Emergency Department", "Outpatient (OPD)", "Maternity",
            "Paediatrics", "Nursing Wards", "Laboratory", "Pharmacy"},
        5: {"Emergency Department", "ICU / Critical Care", "Maternity",
            "Paediatrics", "Outpatient (OPD)", "Laboratory", "Radiology",
            "Pharmacy", "Nursing Wards", "Kitchen & Laundry", "Community Health",
            "Waste & Mortuary"},
        6: {"Emergency Department", "ICU / Critical Care", "Maternity",
            "Paediatrics", "Outpatient (OPD)", "Laboratory", "Radiology",
            "Pharmacy", "Nursing Wards", "Kitchen & Laundry", "Community Health",
            "Waste & Mortuary", "Administration", "Research"},
    }
    return department in level_depts.get(keph_level, set())
