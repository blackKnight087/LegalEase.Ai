"""
LegalEase.AI Court Fee Calculator
==================================
Calculate Ad Valorem court fees for Indian jurisdictions.
"""

from typing import Dict, Any, Optional


# Comprehensive court fee rates by state
COURT_FEE_RATES = {
    "delhi": {
        "civil": [
            (50000, 0.075),       # Up to 50K: 7.5%
            (100000, 0.05),       # 50K-1L: 5%
            (500000, 0.03),       # 1L-5L: 3%
            (1000000, 0.02),      # 5L-10L: 2%
            (5000000, 0.015),     # 10L-50L: 1.5%
            (float('inf'), 0.01)  # Above 50L: 1%
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 50,
        "maximum": 150000,
        "fixed_fees": {
            "divorce": 500,
            "succession": 1000,
            "probate": 2000
        }
    },
    "maharashtra": {
        "civil": [
            (25000, 0.10),        # Up to 25K: 10%
            (100000, 0.075),      # 25K-1L: 7.5%
            (500000, 0.05),       # 1L-5L: 5%
            (1000000, 0.025),     # 5L-10L: 2.5%
            (5000000, 0.02),      # 10L-50L: 2%
            (float('inf'), 0.01)  # Above 50L: 1%
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 100,
        "maximum": 200000,
        "fixed_fees": {
            "divorce": 750,
            "succession": 1500,
            "probate": 2500
        }
    },
    "karnataka": {
        "civil": [
            (50000, 0.08),
            (200000, 0.05),
            (1000000, 0.03),
            (5000000, 0.02),
            (float('inf'), 0.015)
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 75,
        "maximum": 175000,
        "fixed_fees": {
            "divorce": 600,
            "succession": 1200,
            "probate": 2200
        }
    },
    "tamil_nadu": {
        "civil": [
            (50000, 0.075),
            (100000, 0.05),
            (500000, 0.035),
            (2000000, 0.025),
            (float('inf'), 0.02)
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 60,
        "maximum": 160000,
        "fixed_fees": {
            "divorce": 550,
            "succession": 1100,
            "probate": 2100
        }
    },
    "gujarat": {
        "civil": [
            (50000, 0.08),
            (200000, 0.055),
            (1000000, 0.035),
            (float('inf'), 0.02)
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 80,
        "maximum": 180000,
        "fixed_fees": {
            "divorce": 650,
            "succession": 1300,
            "probate": 2300
        }
    },
    "rajasthan": {
        "civil": [
            (50000, 0.07),
            (200000, 0.05),
            (1000000, 0.03),
            (float('inf'), 0.015)
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 50,
        "maximum": 150000,
        "fixed_fees": {
            "divorce": 500,
            "succession": 1000,
            "probate": 2000
        }
    },
    "uttar_pradesh": {
        "civil": [
            (25000, 0.08),
            (100000, 0.06),
            (500000, 0.04),
            (1000000, 0.025),
            (float('inf'), 0.015)
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 40,
        "maximum": 140000,
        "fixed_fees": {
            "divorce": 450,
            "succession": 900,
            "probate": 1800
        }
    },
    "west_bengal": {
        "civil": [
            (50000, 0.075),
            (200000, 0.05),
            (1000000, 0.03),
            (float('inf'), 0.02)
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 70,
        "maximum": 170000,
        "fixed_fees": {
            "divorce": 600,
            "succession": 1200,
            "probate": 2200
        }
    },
    "kerala": {
        "civil": [
            (50000, 0.08),
            (200000, 0.055),
            (1000000, 0.035),
            (float('inf'), 0.025)
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 75,
        "maximum": 175000,
        "fixed_fees": {
            "divorce": 650,
            "succession": 1300,
            "probate": 2300
        }
    },
    "punjab": {
        "civil": [
            (50000, 0.07),
            (200000, 0.05),
            (1000000, 0.03),
            (float('inf'), 0.02)
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 60,
        "maximum": 160000,
        "fixed_fees": {
            "divorce": 550,
            "succession": 1100,
            "probate": 2100
        }
    },
    "haryana": {
        "civil": [
            (50000, 0.07),
            (200000, 0.05),
            (1000000, 0.03),
            (float('inf'), 0.02)
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 60,
        "maximum": 160000,
        "fixed_fees": {
            "divorce": 550,
            "succession": 1100,
            "probate": 2100
        }
    },
    "telangana": {
        "civil": [
            (50000, 0.075),
            (200000, 0.05),
            (1000000, 0.035),
            (float('inf'), 0.02)
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 70,
        "maximum": 170000,
        "fixed_fees": {
            "divorce": 600,
            "succession": 1200,
            "probate": 2200
        }
    },
    "andhra_pradesh": {
        "civil": [
            (50000, 0.075),
            (200000, 0.05),
            (1000000, 0.035),
            (float('inf'), 0.02)
        ],
        "appeal": 0.5,
        "revision": 0.25,
        "minimum": 70,
        "maximum": 170000,
        "fixed_fees": {
            "divorce": 600,
            "succession": 1200,
            "probate": 2200
        }
    }
}


def compute_court_fee(
    suit_value: float,
    region: str = "delhi",
    suit_type: str = "civil",
    court_level: str = "district"
) -> float:
    """
    Calculate court fees based on suit value and jurisdiction.
    
    Args:
        suit_value: Value of the suit in INR
        region: State/jurisdiction
        suit_type: Type of suit (civil, appeal, revision, divorce, etc.)
        court_level: Level of court (district, high, supreme)
    
    Returns:
        Calculated court fee in INR
    """
    # Normalize region name
    region_lower = region.lower().replace(" ", "_")
    
    # Default to Delhi if region not found
    if region_lower not in COURT_FEE_RATES:
        region_lower = "delhi"
    
    rates = COURT_FEE_RATES[region_lower]
    
    # Check for fixed fee suits
    if suit_type.lower() in rates.get("fixed_fees", {}):
        return rates["fixed_fees"][suit_type.lower()]
    
    # Calculate ad valorem fee
    fee = 0
    remaining = suit_value
    prev_limit = 0
    
    for limit, rate in rates["civil"]:
        if remaining <= 0:
            break
        taxable = min(remaining, limit - prev_limit)
        fee += taxable * rate
        remaining -= taxable
        prev_limit = limit
    
    # Apply multipliers for appeal/revision
    if suit_type.lower() == "appeal":
        fee *= rates.get("appeal", 0.5)
    elif suit_type.lower() == "revision":
        fee *= rates.get("revision", 0.25)
    
    # Apply court level multiplier
    if court_level.lower() == "high":
        fee *= 1.25
    elif court_level.lower() == "supreme":
        fee *= 1.5
    
    # Apply minimum and maximum
    fee = max(fee, rates["minimum"])
    fee = min(fee, rates["maximum"])
    
    return round(fee, 2)


def get_fee_breakdown(
    suit_value: float,
    region: str = "delhi",
    suit_type: str = "civil",
    court_level: str = "district"
) -> Dict[str, Any]:
    """
    Get detailed court fee breakdown.
    
    Args:
        suit_value: Value of the suit in INR
        region: State/jurisdiction
        suit_type: Type of suit
        court_level: Level of court
    
    Returns:
        Dictionary with fee breakdown
    """
    region_lower = region.lower().replace(" ", "_")
    if region_lower not in COURT_FEE_RATES:
        region_lower = "delhi"
    
    rates = COURT_FEE_RATES[region_lower]
    
    # Calculate slab-wise breakdown
    breakdown = []
    remaining = suit_value
    prev_limit = 0
    total_fee = 0
    
    for limit, rate in rates["civil"]:
        if remaining <= 0:
            break
        taxable = min(remaining, limit - prev_limit)
        slab_fee = taxable * rate
        total_fee += slab_fee
        
        breakdown.append({
            "slab": f"₹{prev_limit:,.0f} - ₹{min(limit, suit_value):,.0f}",
            "rate": f"{rate * 100:.1f}%",
            "taxable_amount": taxable,
            "fee": round(slab_fee, 2)
        })
        
        remaining -= taxable
        prev_limit = limit
    
    # Apply multipliers
    multiplier = 1.0
    multiplier_reason = ""
    
    if suit_type.lower() == "appeal":
        multiplier = rates.get("appeal", 0.5)
        multiplier_reason = "Appeal (50% of original)"
    elif suit_type.lower() == "revision":
        multiplier = rates.get("revision", 0.25)
        multiplier_reason = "Revision (25% of original)"
    
    if court_level.lower() == "high":
        multiplier *= 1.25
        multiplier_reason += " + High Court (+25%)"
    elif court_level.lower() == "supreme":
        multiplier *= 1.5
        multiplier_reason += " + Supreme Court (+50%)"
    
    adjusted_fee = total_fee * multiplier
    
    # Apply limits
    final_fee = max(adjusted_fee, rates["minimum"])
    final_fee = min(final_fee, rates["maximum"])
    
    return {
        "suit_value": suit_value,
        "region": region.title(),
        "suit_type": suit_type.title(),
        "court_level": court_level.title(),
        "slab_breakdown": breakdown,
        "base_fee": round(total_fee, 2),
        "multiplier": multiplier,
        "multiplier_reason": multiplier_reason if multiplier_reason else "None",
        "adjusted_fee": round(adjusted_fee, 2),
        "minimum_fee": rates["minimum"],
        "maximum_fee": rates["maximum"],
        "final_fee": round(final_fee, 2),
        "notes": [
            "Fees calculated as per Court Fees Act",
            "Actual fees may vary based on specific case type",
            "Additional process fees may apply",
            "Stamp duty charges are separate"
        ]
    }


def get_available_regions() -> list:
    """Get list of available regions/states."""
    return [r.replace("_", " ").title() for r in COURT_FEE_RATES.keys()]


def get_suit_types() -> list:
    """Get list of available suit types."""
    return [
        "Civil",
        "Appeal",
        "Revision",
        "Divorce",
        "Succession",
        "Probate",
        "Injunction",
        "Recovery",
        "Specific Performance"
    ]
