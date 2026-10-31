import asyncio
from sqlalchemy import text
from app.db import seed_engine

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


def slug(name):
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


async def seed():
    async with seed_engine.begin() as conn:
        inserted = 0
        for county, name in COUNTY_REFERRALS.items():
            r = await conn.execute(text(
                "INSERT INTO facilities (id, name, county, keph_level, facility_type, active) "
                "VALUES (:id, :name, :county, 5, 'County Referral', true) "
                "ON CONFLICT (id) DO NOTHING"
            ), {"id": slug(name), "name": name, "county": county})
            inserted += r.rowcount
        total = (await conn.execute(text("SELECT count(*) FROM facilities"))).scalar()
        print("Seed: %d new facilities, %d total" % (inserted, total))


if __name__ == "__main__":
    asyncio.run(seed())
