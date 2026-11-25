"""
LYFTR AI - Transparent Crop Suitability & Recommendation Engine
Uses agronomic parameter ranges and a documented 100-point weighted scoring method.
"""

from typing import Optional

SCORING_METHODOLOGY = (
    "Suitability score (0-100) is computed from five weighted agronomic factors: "
    "Temperature fit (30 pts), Soil type match (25 pts), Water/Rainfall & irrigation fit (20 pts), "
    "Season alignment (15 pts), and Soil pH fit (10 pts). "
    "Unknown soil type or pH uses conservative neutral defaults and is flagged in assumptions."
)

CROP_PROFILES = [
    {
        "crop": "Rice (Paddy)",
        "temp_opt": (22.0, 34.0),
        "temp_tol": (16.0, 40.0),
        "soils": {"clay", "loamy", "alluvial", "silt"},
        "ph_opt": (5.5, 7.0),
        "water_need": "high",
        "rain_opt": (100.0, 300.0),
        "seasons": {"kharif", "monsoon", "summer", "all"},
        "limitations": "Requires standing water or reliable high irrigation; sensitive to prolonged drought and salinity.",
    },
    {
        "crop": "Wheat",
        "temp_opt": (12.0, 24.0),
        "temp_tol": (5.0, 30.0),
        "soils": {"loamy", "alluvial", "clay", "black"},
        "ph_opt": (6.0, 7.5),
        "water_need": "medium",
        "rain_opt": (30.0, 110.0),
        "seasons": {"rabi", "winter", "all"},
        "limitations": "High heat during grain-filling (>30°C) reduces kernel weight; poor tolerance to waterlogging.",
    },
    {
        "crop": "Maize (Corn)",
        "temp_opt": (18.0, 30.0),
        "temp_tol": (10.0, 36.0),
        "soils": {"loamy", "alluvial", "sandy", "red"},
        "ph_opt": (5.8, 7.2),
        "water_need": "medium",
        "rain_opt": (50.0, 150.0),
        "seasons": {"kharif", "rabi", "zaid", "summer", "monsoon", "all"},
        "limitations": "Requires well-drained soil; sensitive to waterlogging and frost.",
    },
    {
        "crop": "Chickpea (Gram)",
        "temp_opt": (15.0, 26.0),
        "temp_tol": (8.0, 32.0),
        "soils": {"loamy", "sandy", "black", "alluvial"},
        "ph_opt": (6.0, 8.0),
        "water_need": "low",
        "rain_opt": (15.0, 70.0),
        "seasons": {"rabi", "winter", "all"},
        "limitations": "Excessive moisture or humidity increases risk of Ascochyta blight and wilt.",
    },
    {
        "crop": "Pearl Millet (Bajra)",
        "temp_opt": (25.0, 36.0),
        "temp_tol": (18.0, 44.0),
        "soils": {"sandy", "loamy", "red", "black"},
        "ph_opt": (6.0, 8.0),
        "water_need": "low",
        "rain_opt": (10.0, 75.0),
        "seasons": {"kharif", "zaid", "summer", "monsoon", "all"},
        "limitations": "Does not tolerate waterlogging; best suited to arid and semi-arid regions.",
    },
    {
        "crop": "Soybean",
        "temp_opt": (20.0, 30.0),
        "temp_tol": (14.0, 36.0),
        "soils": {"loamy", "black", "alluvial", "clay"},
        "ph_opt": (6.0, 7.0),
        "water_need": "medium",
        "rain_opt": (60.0, 150.0),
        "seasons": {"kharif", "monsoon", "all"},
        "limitations": "Sensitive to acidic soils (<5.5 pH) and poor drainage during germination.",
    },
    {
        "crop": "Cotton",
        "temp_opt": (22.0, 35.0),
        "temp_tol": (16.0, 42.0),
        "soils": {"black", "alluvial", "loamy"},
        "ph_opt": (6.0, 8.0),
        "water_need": "medium",
        "rain_opt": (45.0, 120.0),
        "seasons": {"kharif", "summer", "monsoon", "all"},
        "limitations": "Requires frost-free growing period and dry weather during boll opening; susceptible to bollworm.",
    },
    {
        "crop": "Potato",
        "temp_opt": (14.0, 22.0),
        "temp_tol": (7.0, 28.0),
        "soils": {"sandy", "loamy", "silt", "alluvial"},
        "ph_opt": (5.2, 6.5),
        "water_need": "medium",
        "rain_opt": (30.0, 100.0),
        "seasons": {"rabi", "winter", "all"},
        "limitations": "Tuber formation drops sharply above 25°C; susceptible to late blight in humid weather.",
    },
    {
        "crop": "Groundnut (Peanut)",
        "temp_opt": (24.0, 33.0),
        "temp_tol": (18.0, 38.0),
        "soils": {"sandy", "loamy", "red"},
        "ph_opt": (5.8, 7.0),
        "water_need": "low",
        "rain_opt": (40.0, 110.0),
        "seasons": {"kharif", "zaid", "summer", "all"},
        "limitations": "Heavy clay soils hinder peg penetration and harvesting; aflatoxin risk under drought stress.",
    },
    {
        "crop": "Mustard",
        "temp_opt": (12.0, 25.0),
        "temp_tol": (6.0, 30.0),
        "soils": {"loamy", "sandy", "alluvial"},
        "ph_opt": (6.0, 7.5),
        "water_need": "low",
        "rain_opt": (15.0, 65.0),
        "seasons": {"rabi", "winter", "all"},
        "limitations": "Aphid pressure increases in warm, cloudy winters; sensitive to waterlogging.",
    },
]


def _score_range(value: float, opt: tuple[float, float], tol: tuple[float, float], max_pts: float) -> float:
    lo_opt, hi_opt = opt
    lo_tol, hi_tol = tol
    if lo_opt <= value <= hi_opt:
        return max_pts
    if value < lo_tol or value > hi_tol:
        return 0.0
    if value < lo_opt:
        span = max(lo_opt - lo_tol, 1e-6)
        return round(max_pts * (value - lo_tol) / span, 1)
    span = max(hi_tol - hi_opt, 1e-6)
    return round(max_pts * (hi_tol - value) / span, 1)


def _score_water(
    water_need: str,
    rain_opt: tuple[float, float],
    rainfall_mm: Optional[float],
    irrigation: Optional[str],
) -> tuple[float, str]:
    irr = (irrigation or "moderate").strip().lower()
    # Map irrigation to effective water availability
    irr_level = {
        "none": 0, "rainfed": 0, "low": 0,
        "limited": 1, "moderate": 1, "medium": 1,
        "good": 2, "high": 2, "canal": 2, "drip": 2, "full": 2,
    }.get(irr, 1)

    rain_val = rainfall_mm if rainfall_mm is not None else 0.0
    # Score combines observed rainfall and irrigation capacity
    if water_need == "high":
        if irr_level == 2 or rain_val >= rain_opt[0]:
            pts = 20.0 if (irr_level == 2 and rain_val >= 20) else 15.0
            return pts, f"High water demand supported by {'strong irrigation' if irr_level == 2 else 'rainfall'}."
        if irr_level == 1:
            return 9.0, "High water demand may be constrained without assured irrigation."
        return 3.0, "High water demand poorly matched to low rainfall / rainfed conditions."

    if water_need == "medium":
        if irr_level >= 1 or rain_val >= rain_opt[0]:
            return 18.0 if irr_level >= 1 else 15.0, "Moderate water demand fits available moisture/irrigation."
        return 9.0, "Moderate water demand faces mild moisture risk under rainfed conditions."

    # low water need
    if rain_val > 150.0 and irr_level == 2:
        return 11.0, "Low water crop may face excess moisture/waterlogging."
    return 19.0, "Low water requirement fits well with available moisture."


def recommend_crops(
    location: Optional[str] = None,
    soil_type: Optional[str] = None,
    soil_ph: Optional[float] = None,
    season: Optional[str] = None,
    temperature_c: Optional[float] = None,
    rainfall_mm: Optional[float] = None,
    irrigation: Optional[str] = None,
    top_n: int = 4,
) -> dict:
    """
    Compute ranked crop recommendations using transparent weighted scoring.
    """
    assumptions: list[str] = []

    norm_soil = (soil_type or "").strip().lower()
    if not norm_soil or norm_soil in ("unknown", "unsure", "none"):
        norm_soil = ""
        assumptions.append(
            "Soil type was not specified; neutral loamy-equivalent soil compatibility (15/25 pts) was assumed. Perform a local soil test for higher accuracy."
        )

    if soil_ph is None:
        assumptions.append(
            "Soil pH was not provided; neutral pH (6.5) compatibility (6/10 pts) was assumed."
        )

    norm_season = (season or "").strip().lower()
    if not norm_season or norm_season in ("unknown", "any", "all"):
        norm_season = ""
        assumptions.append("Season was not specified; year-round suitability was evaluated.")

    if temperature_c is None:
        temperature_c = 25.0
        assumptions.append("Temperature was unavailable; 25.0°C baseline was assumed.")

    if rainfall_mm is None:
        rainfall_mm = 40.0
        assumptions.append("Rainfall was unavailable; 40.0 mm baseline was assumed.")

    if not irrigation or not irrigation.strip():
        irrigation = "moderate"
        assumptions.append("Irrigation availability was not specified; moderate supplemental irrigation was assumed.")

    scored = []
    for profile in CROP_PROFILES:
        reasons: list[str] = []

        # 1. Temperature (30 pts)
        t_score = _score_range(temperature_c, profile["temp_opt"], profile["temp_tol"], 30.0)
        if t_score >= 25:
            reasons.append(
                f"Temperature ({temperature_c:.1f}°C) is within optimal range ({profile['temp_opt'][0]}–{profile['temp_opt'][1]}°C)."
            )
        elif t_score > 0:
            reasons.append(
                f"Temperature ({temperature_c:.1f}°C) is tolerable ({profile['temp_tol'][0]}–{profile['temp_tol'][1]}°C) though slightly outside optimal."
            )
        else:
            reasons.append(
                f"Temperature ({temperature_c:.1f}°C) is outside tolerable range ({profile['temp_tol'][0]}–{profile['temp_tol'][1]}°C)."
            )

        # 2. Soil type (25 pts)
        if not norm_soil:
            s_score = 15.0
            reasons.append(f"Prefers {', '.join(sorted(profile['soils']))} soils (assumed neutral fit).")
        elif any(s in norm_soil for s in profile["soils"]):
            s_score = 25.0
            reasons.append(f"Well-suited to {soil_type} soil.")
        else:
            s_score = 8.0
            reasons.append(f"Sub-optimal soil match; prefers {', '.join(sorted(profile['soils']))} rather than {soil_type}.")

        # 3. Water / Rainfall & Irrigation (20 pts)
        w_score, w_reason = _score_water(profile["water_need"], profile["rain_opt"], rainfall_mm, irrigation)
        reasons.append(w_reason)

        # 4. Season (15 pts)
        if not norm_season or norm_season in profile["seasons"]:
            sea_score = 15.0
            if norm_season:
                reasons.append(f"Matches the {season} growing season.")
        else:
            sea_score = 4.0
            reasons.append(f"Typically grown in {', '.join(s for s in sorted(profile['seasons']) if s != 'all')}, not {season}.")

        # 5. Soil pH (10 pts)
        if soil_ph is None:
            ph_score = 6.0
        else:
            ph_lo, ph_hi = profile["ph_opt"]
            ph_score = _score_range(soil_ph, (ph_lo, ph_hi), (ph_lo - 1.0, ph_hi + 1.0), 10.0)
            if ph_score >= 8:
                reasons.append(f"Soil pH ({soil_ph:.1f}) fits optimal {ph_lo}–{ph_hi} range.")
            else:
                reasons.append(f"Soil pH ({soil_ph:.1f}) is outside optimal {ph_lo}–{ph_hi} range.")

        total = round(t_score + s_score + w_score + sea_score + ph_score, 1)
        confidence = "High" if total >= 80 else "Moderate" if total >= 60 else "Low"

        scored.append({
            "crop": profile["crop"],
            "suitability_score": total,
            "confidence": confidence,
            "score_breakdown": {
                "temperature_pts": t_score,
                "soil_pts": s_score,
                "water_pts": w_score,
                "season_pts": sea_score,
                "ph_pts": ph_score,
            },
            "reasons": reasons,
            "suitable_conditions": {
                "temperature_c": f"{profile['temp_opt'][0]}–{profile['temp_opt'][1]}°C",
                "soil_types": sorted(profile["soils"]),
                "soil_ph": f"{profile['ph_opt'][0]}–{profile['ph_opt'][1]}",
                "water_need": profile["water_need"],
                "seasons": sorted(s for s in profile["seasons"] if s != "all"),
            },
            "limitations": profile["limitations"],
        })

    scored.sort(key=lambda x: x["suitability_score"], reverse=True)
    return {
        "location": location,
        "inputs_used": {
            "soil_type": soil_type or "Not provided (assumed neutral)",
            "soil_ph": soil_ph,
            "season": season or "Any",
            "temperature_c": temperature_c,
            "rainfall_mm": rainfall_mm,
            "irrigation": irrigation,
        },
        "scoring_methodology": SCORING_METHODOLOGY,
        "assumptions": assumptions,
        "recommendations": scored[:top_n],
    }
