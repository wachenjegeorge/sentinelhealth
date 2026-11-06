"""Seed realistic facilities for all 47 Kenyan counties across KEPH levels 1-6.

Data sources:
- KEPH 2024 guidelines (MoH)
- KMHFL 2021 facility counts (CRA State of Inequality report)
- Known county referral hospital names (OAG audit, MoH)
"""
import asyncio
import uuid
from sqlalchemy import text
from app.db import admin_engine

# Real Level 5 County Referral Hospitals
COUNTY_REFERRALS = {
    "Mombasa": "Coast General Teaching & Referral Hospital",
    "Kwale": "Msambweni County Referral Hospital",
    "Kilifi": "Kilifi County Referral Hospital",
    "Tana River": "Hola County Referral Hospital",
    "Lamu": "Lamu County Referral Hospital",
    "Taita-Taveta": "Moi County Referral Hospital",
    "Garissa": "Garissa County Referral Hospital",
    "Wajir": "Wajir County Referral Hospital",
    "Mandera": "Mandera County Referral Hospital",
    "Marsabit": "Marsabit County Referral Hospital",
    "Isiolo": "Isiolo County Referral Hospital",
    "Meru": "Meru Teaching & Referral Hospital",
    "Tharaka-Nithi": "Chuka County Referral Hospital",
    "Embu": "Embu Level 5 Hospital",
    "Kitui": "Kitui County Referral Hospital",
    "Machakos": "Machakos County Referral Hospital",
    "Makueni": "Makueni County Referral Hospital",
    "Nyandarua": "Nyandarua County Referral Hospital",
    "Nyeri": "Nyeri County Referral Hospital",
    "Kirinyaga": "Kerugoya County Referral Hospital",
    "Murang'a": "Murang'a County Referral Hospital",
    "Kiambu": "Thika Level 5 Hospital",
    "Turkana": "Lodwar County Referral Hospital",
    "West Pokot": "Kapenguria County Referral Hospital",
    "Samburu": "Samburu County Referral Hospital",
    "Trans Nzoia": "Kitale County Referral Hospital",
    "Uasin Gishu": "Uasin Gishu County Hospital",
    "Elgeyo-Marakwet": "Iten County Referral Hospital",
    "Nandi": "Kapsabet County Referral Hospital",
    "Baringo": "Baringo County Referral Hospital",
    "Laikipia": "Nanyuki County Referral Hospital",
    "Nakuru": "Nakuru Level 5 Hospital",
    "Narok": "Narok County Referral Hospital",
    "Kajiado": "Kajiado County Referral Hospital",
    "Kericho": "Kericho County Referral Hospital",
    "Bomet": "Longisa County Referral Hospital",
    "Kakamega": "Kakamega County General Hospital",
    "Vihiga": "Vihiga County Referral Hospital",
    "Bungoma": "Bungoma County Referral Hospital",
    "Busia": "Busia County Referral Hospital",
    "Siaya": "Siaya County Referral Hospital",
    "Kisumu": "Jaramogi Oginga Odinga Teaching & Referral Hospital",
    "Homa Bay": "Homa Bay County Teaching & Referral Hospital",
    "Migori": "Migori County Referral Hospital",
    "Kisii": "Kisii Teaching & Referral Hospital",
    "Nyamira": "Nyamira County Referral Hospital",
    "Nairobi": "Mbagathi County Hospital",
}

# Level 6 National Hospitals (not per county)
NATIONAL_HOSPITALS = [
    ("Kenyatta National Hospital", "Nairobi", "National Referral"),
    ("Moi Teaching & Referral Hospital", "Uasin Gishu", "National Referral"),
    ("Kenyatta University Teaching, Referral & Research Hospital", "Kiambu", "National Referral"),
    ("Mathari National Teaching & Referral Hospital", "Nairobi", "National Referral"),
]

# Representative Level 4 sub-county hospitals per county
SUBCOUNTY_HOSPITALS = {
    "Mombasa": ["Likoni Sub-County Hospital", "Changamwe Sub-County Hospital", "Port Reitz Sub-County Hospital"],
    "Kwale": ["Kwale Sub-County Hospital", "Kinango Sub-County Hospital", "Lungalunga Sub-County Hospital"],
    "Kilifi": ["Malindi Sub-County Hospital", "Mariakani Sub-County Hospital", "Bamba Sub-County Hospital"],
    "Tana River": ["Bura Sub-County Hospital", "Garsen Sub-County Hospital", "Wenje Sub-County Hospital"],
    "Lamu": ["Mpeketoni Sub-County Hospital", "Faza Sub-County Hospital"],
    "Taita-Taveta": ["Taveta Sub-County Hospital", "Wundanyi Sub-County Hospital", "Wesu Sub-County Hospital"],
    "Garissa": ["Dadaab Sub-County Hospital", "Balambala Sub-County Hospital", "Fafi Sub-County Hospital"],
    "Wajir": ["Habaswein Sub-County Hospital", "Bute Sub-County Hospital", "Elwak Sub-County Hospital"],
    "Mandera": ["Elwak Sub-County Hospital", "Takaba Sub-County Hospital", "Rhamu Sub-County Hospital"],
    "Marsabit": ["Moyale Sub-County Hospital", "Laisamis Sub-County Hospital", "North Horr Sub-County Hospital"],
    "Isiolo": ["Garbatulla Sub-County Hospital", "Merti Sub-County Hospital"],
    "Meru": ["Maua Sub-County Hospital", "Nkubu Sub-County Hospital", "Mikinduri Sub-County Hospital"],
    "Tharaka-Nithi": ["Marimanti Sub-County Hospital", "Magutuni Sub-County Hospital"],
    "Embu": ["Runyenjes Sub-County Hospital", "Siakago Sub-County Hospital", "Kiritiri Sub-County Hospital"],
    "Kitui": ["Mwingi Sub-County Hospital", "Mutomo Sub-County Hospital", "Kyuso Sub-County Hospital"],
    "Machakos": ["Kangundo Sub-County Hospital", "Kathiani Sub-County Hospital", "Mwala Sub-County Hospital"],
    "Makueni": ["Makindu Sub-County Hospital", "Kibwezi Sub-County Hospital", "Tawa Sub-County Hospital"],
    "Nyandarua": ["Engineer Sub-County Hospital", "Ndaragwa Sub-County Hospital"],
    "Nyeri": ["Karatina Sub-County Hospital", "Othaya Sub-County Hospital", "Mukurweini Sub-County Hospital"],
    "Kirinyaga": ["Kianyaga Sub-County Hospital", "Sagana Sub-County Hospital", "Baricho Sub-County Hospital"],
    "Murang'a": ["Kenol Sub-County Hospital", "Kangema Sub-County Hospital", "Maragua Sub-County Hospital"],
    "Kiambu": ["Gatundu Sub-County Hospital", "Limuru Sub-County Hospital", "Ruiru Sub-County Hospital"],
    "Turkana": ["Kakuma Sub-County Hospital", "Lokichogio Sub-County Hospital", "Lokitaung Sub-County Hospital"],
    "West Pokot": ["Ortum Sub-County Hospital", "Chepareria Sub-County Hospital", "Kacheliba Sub-County Hospital"],
    "Samburu": ["Baragoi Sub-County Hospital", "Wamba Sub-County Hospital"],
    "Trans Nzoia": ["Kiminini Sub-County Hospital", "Endebess Sub-County Hospital", "Cherangany Sub-County Hospital"],
    "Uasin Gishu": ["Burnt Forest Sub-County Hospital", "Turbo Sub-County Hospital", "Moiben Sub-County Hospital"],
    "Elgeyo-Marakwet": ["Kapsowar Sub-County Hospital", "Chepkorio Sub-County Hospital"],
    "Nandi": ["Nandi Hills Sub-County Hospital", "Kabiyet Sub-County Hospital", "Mosoriot Sub-County Hospital"],
    "Baringo": ["Eldama Ravine Sub-County Hospital", "Marigat Sub-County Hospital", "Tangulbei Sub-County Hospital"],
    "Laikipia": ["Nyahururu Sub-County Hospital", "Rumuruti Sub-County Hospital", "Nanyuki Cottage Hospital"],
    "Nakuru": ["Naivasha Sub-County Hospital", "Gilgil Sub-County Hospital", "Molo Sub-County Hospital", "Lumakanda Hospital"],
    "Narok": ["Kilgoris Sub-County Hospital", "Ololulunga Sub-County Hospital", "Suswa Sub-County Hospital"],
    "Kajiado": ["Ngong Sub-County Hospital", "Kitengela Sub-County Hospital", "Loitokitok Sub-County Hospital"],
    "Kericho": ["Londiani Sub-County Hospital", "Kapkatet Sub-County Hospital", "Sigowet Sub-County Hospital"],
    "Bomet": ["Sotik Sub-County Hospital", "Chepalungu Sub-County Hospital"],
    "Kakamega": ["Mumias Sub-County Hospital", "Butere Sub-County Hospital", "Malava Sub-County Hospital"],
    "Vihiga": ["Emuhaya Sub-County Hospital", "Hamisi Sub-County Hospital", "Sabatia Sub-County Hospital"],
    "Bungoma": ["Webuye Sub-County Hospital", "Kimilili Sub-County Hospital", "Chwele Sub-County Hospital"],
    "Busia": ["Alupe Sub-County Hospital", "Port Victoria Sub-County Hospital", "Khunyangu Sub-County Hospital"],
    "Siaya": ["Bondo Sub-County Hospital", "Yala Sub-County Hospital", "Ugunja Sub-County Hospital"],
    "Kisumu": ["Kisumu County Hospital", "Muhoroni Sub-County Hospital", "Ahero Sub-County Hospital"],
    "Homa Bay": ["Rachuonyo Sub-County Hospital", "Ndhiwa Sub-County Hospital", "Suba Sub-County Hospital"],
    "Migori": ["Kehancha Sub-County Hospital", "Rongo Sub-County Hospital", "Awendo Sub-County Hospital"],
    "Kisii": ["Kisii County Hospital", "Nyamache Sub-County Hospital", "Gesusu Sub-County Hospital"],
    "Nyamira": ["Nyansiongo Sub-County Hospital", "Ekerenyo Sub-County Hospital", "Gesima Sub-County Hospital"],
    "Nairobi": ["Mama Lucy Kibaki Hospital", "Pumwani Maternity Hospital", "Mbagathi Sub-County Hospital", "Nairobi West Hospital"],
}

# Health Centre name templates (generated per county)
HC_TEMPLATES = [
    "Health Centre", "Medical Clinic", "Dispensary", "Community Clinic",
]

# Community Health Unit name templates
CHU_TEMPLATES = [
    "Community Health Unit", "CHU", "Village Health Unit",
]


def slug(name: str) -> str:
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


async def seed():
    async with admin_engine.begin() as conn:
        total_inserted = 0
        level_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}

        for county, referral_name in COUNTY_REFERRALS.items():
            # Level 5 — County Referral
            fac_id = slug(referral_name)
            r = await conn.execute(text("""
                INSERT INTO facilities (id, name, county, keph_level, keph_sub_level, facility_type, ownership, active)
                VALUES (:id, :name, :county, 5, 'County Referral', 'County Referral Hospital', 'County Government', true)
                ON CONFLICT (id) DO NOTHING
            """), {"id": fac_id, "name": referral_name, "county": county})
            if r.rowcount:
                level_counts[5] += 1

            # Level 4 — Sub-County Hospitals
            for sc_name in SUBCOUNTY_HOSPITALS.get(county, [])[:5]:
                fac_id = slug(sc_name)
                r = await conn.execute(text("""
                    INSERT INTO facilities (id, name, county, keph_level, keph_sub_level, facility_type, ownership, active)
                    VALUES (:id, :name, :county, 4, 'Sub-County Hospital', 'Sub-County Hospital', 'County Government', true)
                    ON CONFLICT (id) DO NOTHING
                """), {"id": fac_id, "name": sc_name, "county": county})
                if r.rowcount:
                    level_counts[4] += 1

            # Level 3 — Health Centres (generate 5 per county)
            for i in range(1, 6):
                hc_name = f"{county} {i} Health Centre"
                fac_id = slug(hc_name)
                r = await conn.execute(text("""
                    INSERT INTO facilities (id, name, county, keph_level, keph_sub_level, facility_type, ownership, active)
                    VALUES (:id, :name, :county, 3, 'Health Centre', 'Health Centre', 'County Government', true)
                    ON CONFLICT (id) DO NOTHING
                """), {"id": fac_id, "name": hc_name, "county": county})
                if r.rowcount:
                    level_counts[3] += 1

            # Level 2 — Dispensaries (generate 10 per county)
            for i in range(1, 11):
                disp_name = f"{county} {i} Dispensary"
                fac_id = slug(disp_name)
                r = await conn.execute(text("""
                    INSERT INTO facilities (id, name, county, keph_level, keph_sub_level, facility_type, ownership, active)
                    VALUES (:id, :name, :county, 2, 'Dispensary', 'Dispensary', 'County Government', true)
                    ON CONFLICT (id) DO NOTHING
                """), {"id": fac_id, "name": disp_name, "county": county})
                if r.rowcount:
                    level_counts[2] += 1

            # Level 1 — Community Health Units (generate 5 per county)
            for i in range(1, 6):
                chu_name = f"{county} {i} Community Health Unit"
                fac_id = slug(chu_name)
                r = await conn.execute(text("""
                    INSERT INTO facilities (id, name, county, keph_level, keph_sub_level, facility_type, ownership, active)
                    VALUES (:id, :name, :county, 1, 'CHU', 'Community Health Unit', 'Community', true)
                    ON CONFLICT (id) DO NOTHING
                """), {"id": fac_id, "name": chu_name, "county": county})
                if r.rowcount:
                    level_counts[1] += 1

        # Level 6 — National Hospitals
        for nat_name, county, sub_level in NATIONAL_HOSPITALS:
            fac_id = slug(nat_name)
            r = await conn.execute(text("""
                INSERT INTO facilities (id, name, county, keph_level, keph_sub_level, facility_type, ownership, active)
                VALUES (:id, :name, :county, 6, :sub, 'National Referral Hospital', 'Ministry of Health', true)
                ON CONFLICT (id) DO NOTHING
            """), {"id": fac_id, "name": nat_name, "county": county, "sub": sub_level})
            if r.rowcount:
                level_counts[6] += 1

        total = (await conn.execute(text("SELECT count(*) FROM facilities"))).scalar()
        print("Facility seeding complete:")
        for lvl in sorted(level_counts.keys()):
            print(f"  Level {lvl}: {level_counts[lvl]} new")
        print(f"  Total in database: {total}")


if __name__ == "__main__":
    asyncio.run(seed())
