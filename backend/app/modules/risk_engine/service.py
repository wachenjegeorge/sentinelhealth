WEIGHTS = {"fatigue":0.30,"heat":0.20,"symptom":0.25,"staffing":0.15,"biometric":0.10}
CRIT, MOD = 65, 35
SEV = {"headache":14,"dizziness":20,"nausea":18,"cough":14,"sore_throat":10,
       "shortness_of_breath":26,"muscle_strain":18,"eye_irritation":10,
       "anxiety":16,"needlestick_worry":22}
HEAT = {"headache","dizziness","nausea"}
RESP = {"cough","sore_throat","shortness_of_breath"}


def clamp(x, lo=0.0, hi=100.0): return max(lo, min(hi, x))
def level_for(s): return "Critical" if s>=CRIT else "Moderate" if s>=MOD else "Low"


def score(*, fatigue, heat_exposure, hours_worked, symptoms,
          department_load=7, ambient_heat_index=30.0, staffing_density=15.0):
    hn = clamp((ambient_heat_index - 24) / 16 * 100)
    heat = clamp(0.6 * hn + 0.4 * (heat_exposure / 10 * 100))
    fp = fatigue / 10 * 100
    hp = clamp((hours_worked - 8) / 8 * 100)
    fl = clamp(0.7 * fp + 0.3 * hp)
    ss = set(symptoms)
    sev = sum(SEV.get(s, 0) for s in ss)
    if len(ss & HEAT) >= 2: sev += 20
    if len(ss & RESP) >= 2: sev += 20
    sl = clamp(sev)
    staff = clamp(100 - staffing_density * 3.4)
    bio = clamp(department_load * 5 + fl * 0.3)
    comp = {"fatigue":round(fl,1),"heat":round(heat,1),"symptom":round(sl,1),
            "staffing":round(staff,1),"biometric":round(bio,1)}
    tot = clamp(sum(WEIGHTS[k] * v for k, v in comp.items()))
    return {"score":round(tot,1),"level":level_for(tot),"components":comp}
