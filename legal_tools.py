"""
LegalEase.AI Legal Tools Module
================================
Comprehensive legal tools powered by LM Studio LLM.
"""

import re
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    import datefinder
    DATEFINDER_AVAILABLE = True
except ImportError:
    DATEFINDER_AVAILABLE = False

# IPC to BNS Mapping Database
IPC_TO_BNS_MAP = {
    # Offenses against the State
    "121": {"bns": "147", "description": "Waging war against Government of India"},
    "122": {"bns": "148", "description": "Collecting arms with intention of waging war"},
    "124A": {"bns": "152", "description": "Sedition (now acts endangering sovereignty)"},
    
    # Offenses against Public Tranquility
    "141": {"bns": "189", "description": "Unlawful assembly"},
    "143": {"bns": "191", "description": "Punishment for unlawful assembly"},
    "144": {"bns": "192", "description": "Joining unlawful assembly armed with weapon"},
    "147": {"bns": "195", "description": "Rioting"},
    "148": {"bns": "196", "description": "Rioting armed with deadly weapon"},
    
    # Offenses against Human Body
    "299": {"bns": "100", "description": "Culpable homicide"},
    "300": {"bns": "101", "description": "Murder"},
    "302": {"bns": "103", "description": "Punishment for murder"},
    "304": {"bns": "105", "description": "Culpable homicide not amounting to murder"},
    "304A": {"bns": "106", "description": "Death by negligence"},
    "304B": {"bns": "80", "description": "Dowry death"},
    "306": {"bns": "108", "description": "Abetment of suicide"},
    "307": {"bns": "109", "description": "Attempt to murder"},
    "308": {"bns": "110", "description": "Attempt to commit culpable homicide"},
    "319": {"bns": "114", "description": "Hurt"},
    "320": {"bns": "115", "description": "Grievous hurt"},
    "321": {"bns": "115(2)", "description": "Voluntarily causing hurt"},
    "322": {"bns": "117", "description": "Voluntarily causing grievous hurt"},
    "323": {"bns": "115(2)", "description": "Punishment for voluntarily causing hurt"},
    "324": {"bns": "118", "description": "Voluntarily causing hurt by dangerous weapons"},
    "325": {"bns": "117", "description": "Punishment for grievous hurt"},
    "326": {"bns": "118", "description": "Grievous hurt by dangerous weapons"},
    "354": {"bns": "74", "description": "Assault on woman with intent to outrage modesty"},
    "354A": {"bns": "75", "description": "Sexual harassment"},
    "354B": {"bns": "76", "description": "Assault with intent to disrobe woman"},
    "354C": {"bns": "77", "description": "Voyeurism"},
    "354D": {"bns": "78", "description": "Stalking"},
    "363": {"bns": "137", "description": "Kidnapping"},
    "365": {"bns": "139", "description": "Kidnapping for ransom"},
    "366": {"bns": "139", "description": "Kidnapping woman to compel marriage"},
    "375": {"bns": "63", "description": "Rape"},
    "376": {"bns": "64", "description": "Punishment for rape"},
    "377": {"bns": "Decriminalized", "description": "Unnatural offences (Section 377 read down)"},
    
    # Offenses against Property
    "378": {"bns": "303", "description": "Theft"},
    "379": {"bns": "303(2)", "description": "Punishment for theft"},
    "380": {"bns": "305", "description": "Theft in dwelling house"},
    "382": {"bns": "304", "description": "Theft after preparation for causing death"},
    "383": {"bns": "308", "description": "Extortion"},
    "384": {"bns": "308(2)", "description": "Punishment for extortion"},
    "390": {"bns": "309", "description": "Robbery"},
    "392": {"bns": "309(2)", "description": "Punishment for robbery"},
    "395": {"bns": "310", "description": "Dacoity"},
    "396": {"bns": "310(2)", "description": "Dacoity with murder"},
    "397": {"bns": "310(3)", "description": "Robbery or dacoity with attempt to cause death"},
    "406": {"bns": "316", "description": "Criminal breach of trust"},
    "409": {"bns": "316(5)", "description": "Criminal breach of trust by public servant"},
    "415": {"bns": "318", "description": "Cheating"},
    "417": {"bns": "318(2)", "description": "Punishment for cheating"},
    "418": {"bns": "318(4)", "description": "Cheating with knowledge"},
    "420": {"bns": "318(4)", "description": "Cheating and dishonestly inducing delivery"},
    "426": {"bns": "324", "description": "Mischief"},
    "427": {"bns": "324(2)", "description": "Mischief causing damage"},
    "447": {"bns": "329", "description": "Criminal trespass"},
    "448": {"bns": "329(2)", "description": "House trespass"},
    "449": {"bns": "331", "description": "House trespass to commit offence"},
    "452": {"bns": "333", "description": "House trespass after preparation"},
    "453": {"bns": "334", "description": "Lurking house-trespass"},
    "454": {"bns": "335", "description": "Lurking house-trespass by night"},
    "456": {"bns": "337", "description": "House-breaking by night"},
    "457": {"bns": "306", "description": "Lurking house-trespass by night to commit offence"},
    
    # Offenses relating to Documents
    "463": {"bns": "336", "description": "Forgery"},
    "464": {"bns": "336", "description": "Making false document"},
    "465": {"bns": "336(2)", "description": "Punishment for forgery"},
    "467": {"bns": "338", "description": "Forgery of valuable security"},
    "468": {"bns": "338(3)", "description": "Forgery for purpose of cheating"},
    "471": {"bns": "340", "description": "Using forged document as genuine"},
    
    # Defamation
    "499": {"bns": "356", "description": "Defamation"},
    "500": {"bns": "356(2)", "description": "Punishment for defamation"},
    
    # Criminal Intimidation
    "503": {"bns": "351", "description": "Criminal intimidation"},
    "506": {"bns": "351(2)", "description": "Punishment for criminal intimidation"},
    "507": {"bns": "351(3)", "description": "Criminal intimidation by anonymous communication"},
    
    # Cruelty
    "498A": {"bns": "85", "description": "Cruelty by husband or relatives"},
}


def convert_ipc_to_bns(ipc_section: str) -> Dict[str, str]:
    """
    Convert IPC section to corresponding BNS section.
    
    Args:
        ipc_section: IPC section number (e.g., "302", "420")
    
    Returns:
        Dict with BNS section and description
    """
    # Clean the input
    ipc_clean = ipc_section.strip().upper().replace("IPC", "").replace("SECTION", "").strip()
    
    if ipc_clean in IPC_TO_BNS_MAP:
        mapping = IPC_TO_BNS_MAP[ipc_clean]
        return {
            "ipc_section": f"Section {ipc_clean}",
            "bns_section": f"BNS Section {mapping['bns']}",
            "description": mapping["description"],
            "status": "mapped"
        }
    else:
        return {
            "ipc_section": f"Section {ipc_clean}",
            "bns_section": "Not found in database",
            "description": "Please verify with official BNS documentation",
            "status": "not_found"
        }


def map_law_references(text: str) -> List[Dict[str, str]]:
    """
    Scan text for IPC references and map them to BNS.
    
    Args:
        text: Legal text to scan
    
    Returns:
        List of IPC to BNS mappings found
    """
    # Pattern to find IPC sections
    patterns = [
        r'(?:IPC|I\.P\.C\.?)\s*(?:Section|Sec\.?|S\.?)?\s*(\d+[A-Z]?)',
        r'Section\s+(\d+[A-Z]?)\s+(?:of\s+)?(?:IPC|I\.P\.C\.?|Indian Penal Code)',
        r'u/s\.?\s*(\d+[A-Z]?)\s*(?:IPC|I\.P\.C\.?)',
    ]
    
    found_sections = set()
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found_sections.update(matches)
    
    mappings = []
    for section in found_sections:
        mapping = convert_ipc_to_bns(section)
        if mapping["status"] == "mapped":
            mappings.append(mapping)
    
    return mappings


def extract_timeline(text: str, source_filename: str = "document") -> List[Dict[str, Any]]:
    """
    Extract timeline of events from legal document.
    
    Args:
        text: Document text
        source_filename: Name of source file
    
    Returns:
        List of timeline events with dates
    """
    events = []
    
    if DATEFINDER_AVAILABLE:
        try:
            # Find dates using datefinder
            matches = list(datefinder.find_dates(text, source=True))
            
            for date_obj, source_text in matches:
                # Get surrounding context (100 chars before and after)
                idx = text.find(source_text)
                if idx != -1:
                    start = max(0, idx - 100)
                    end = min(len(text), idx + len(source_text) + 100)
                    context = text[start:end].strip()
                    
                    events.append({
                        "date": date_obj.strftime("%Y-%m-%d"),
                        "mention_text": context,
                        "source_filename": source_filename,
                        "page": 0  # Would need PDF page tracking for accuracy
                    })
        except Exception:
            pass
    
    # Fallback: regex-based date extraction
    if not events:
        date_patterns = [
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4})',
            r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{2,4})',
        ]
        
        for pattern in date_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                date_str = match.group(1)
                idx = match.start()
                start = max(0, idx - 100)
                end = min(len(text), idx + len(date_str) + 100)
                context = text[start:end].strip()
                
                events.append({
                    "date": date_str,
                    "mention_text": context,
                    "source_filename": source_filename,
                    "page": 0
                })
    
    # Remove duplicates and sort
    seen = set()
    unique_events = []
    for event in events:
        key = (event["date"], event["mention_text"][:50])
        if key not in seen:
            seen.add(key)
            unique_events.append(event)
    
    return sorted(unique_events, key=lambda x: x["date"])


def extract_case_entities(text: str) -> Dict[str, Any]:
    """
    Extract legal entities from case document.
    
    Args:
        text: Document text
    
    Returns:
        Dict with extracted entities
    """
    entities = {
        "plaintiff": None,
        "defendant": None,
        "petitioner": None,
        "respondent": None,
        "judge": None,
        "court": None,
        "case_number": None,
        "sections": [],
        "dates": [],
        "advocates": []
    }
    
    # Plaintiff/Petitioner patterns
    plaintiff_patterns = [
        r'(?:Plaintiff|Petitioner|Complainant)\s*[:\-]?\s*([A-Z][a-zA-Z\s]+?)(?:\s+(?:vs?\.?|versus|and|$))',
        r'([A-Z][a-zA-Z\s]+?)\s+(?:vs?\.?|versus)\s+',
    ]
    
    for pattern in plaintiff_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            entities["plaintiff"] = match.group(1).strip()
            break
    
    # Defendant/Respondent patterns
    defendant_patterns = [
        r'(?:Defendant|Respondent|Accused)\s*[:\-]?\s*([A-Z][a-zA-Z\s]+?)(?:\s+(?:and|$|\.))',
        r'(?:vs?\.?|versus)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:and|$|\.))',
    ]
    
    for pattern in defendant_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            entities["defendant"] = match.group(1).strip()
            break
    
    # Judge patterns
    judge_patterns = [
        r'(?:Hon\'?ble|Honourable)\s+(?:Justice|Judge|Mr\.?|Mrs\.?|Ms\.?)\s+([A-Z][a-zA-Z\s\.]+)',
        r'(?:Before|Coram)\s*[:\-]?\s*(?:Hon\'?ble)?\s*(?:Justice|Judge)?\s*([A-Z][a-zA-Z\s\.]+)',
    ]
    
    for pattern in judge_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            entities["judge"] = match.group(1).strip()
            break
    
    # Court patterns
    court_patterns = [
        r'((?:Supreme|High|District|Sessions|Metropolitan|Civil|Criminal)\s+Court(?:\s+of\s+[A-Za-z\s]+)?)',
        r'((?:Hon\'?ble\s+)?(?:Supreme|High)\s+Court\s+of\s+[A-Za-z\s]+)',
    ]
    
    for pattern in court_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            entities["court"] = match.group(1).strip()
            break
    
    # Case number patterns
    case_patterns = [
        r'(?:Case\s+No\.?|Crl\.?\s*(?:Appeal|Case|Petition)|Civil\s+(?:Appeal|Suit)|W\.?P\.?\s*(?:\(C\))?)\s*[:\-]?\s*([\w\-/]+\s*(?:of\s*)?\d{4})',
        r'(\d+\s*/\s*\d{4})',
    ]
    
    for pattern in case_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            entities["case_number"] = match.group(1).strip()
            break
    
    # Extract sections (IPC/BNS/CrPC)
    section_patterns = [
        r'(?:Section|Sec\.?|S\.?)\s*(\d+[A-Z]?)\s*(?:of\s+)?(?:IPC|BNS|CrPC|I\.P\.C\.|Cr\.P\.C\.)',
        r'u/s\.?\s*(\d+[A-Z]?)\s*(?:IPC|BNS|CrPC)',
    ]
    
    sections = set()
    for pattern in section_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        sections.update(matches)
    
    entities["sections"] = list(sections)
    
    # Extract dates
    if DATEFINDER_AVAILABLE:
        try:
            dates = list(datefinder.find_dates(text[:5000]))
            entities["dates"] = [d.strftime("%Y-%m-%d") for d in dates[:10]]
        except Exception:
            pass
    
    return entities


def compute_court_fee(suit_value: float, region: str = "delhi", suit_type: str = "civil") -> Dict[str, Any]:
    """
    Calculate court fees based on suit value and jurisdiction.
    
    Args:
        suit_value: Value of the suit in INR
        region: State/jurisdiction (delhi, maharashtra, karnataka, etc.)
        suit_type: Type of suit (civil, criminal, appeal, etc.)
    
    Returns:
        Dict with fee breakdown
    """
    # Court fee rates by region (Ad Valorem)
    fee_rates = {
        "delhi": {
            "civil": [
                (50000, 0.075),      # Up to 50K: 7.5%
                (100000, 0.05),      # 50K-1L: 5%
                (500000, 0.03),      # 1L-5L: 3%
                (1000000, 0.02),     # 5L-10L: 2%
                (float('inf'), 0.01) # Above 10L: 1%
            ],
            "appeal": 0.5,  # 50% of original fee
            "minimum": 50,
            "maximum": 150000
        },
        "maharashtra": {
            "civil": [
                (25000, 0.10),       # Up to 25K: 10%
                (100000, 0.075),     # 25K-1L: 7.5%
                (500000, 0.05),      # 1L-5L: 5%
                (1000000, 0.025),    # 5L-10L: 2.5%
                (float('inf'), 0.01) # Above 10L: 1%
            ],
            "appeal": 0.5,
            "minimum": 100,
            "maximum": 200000
        },
        "karnataka": {
            "civil": [
                (50000, 0.08),
                (200000, 0.05),
                (1000000, 0.03),
                (float('inf'), 0.015)
            ],
            "appeal": 0.5,
            "minimum": 75,
            "maximum": 175000
        },
        "tamil_nadu": {
            "civil": [
                (50000, 0.075),
                (100000, 0.05),
                (500000, 0.035),
                (float('inf'), 0.02)
            ],
            "appeal": 0.5,
            "minimum": 60,
            "maximum": 160000
        }
    }
    
    # Default to Delhi if region not found
    region_lower = region.lower().replace(" ", "_")
    if region_lower not in fee_rates:
        region_lower = "delhi"
    
    rates = fee_rates[region_lower]
    
    # Calculate fee
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
    
    # Apply appeal multiplier if applicable
    if suit_type == "appeal":
        fee *= rates["appeal"]
    
    # Apply minimum and maximum
    fee = max(fee, rates["minimum"])
    fee = min(fee, rates["maximum"])
    
    return {
        "suit_value": suit_value,
        "region": region,
        "suit_type": suit_type,
        "court_fee": round(fee, 2),
        "minimum_fee": rates["minimum"],
        "maximum_fee": rates["maximum"],
        "note": f"Ad Valorem court fee for {region.title()} jurisdiction"
    }


def bulk_ipc_to_bns_convert(sections: List[str]) -> List[Dict[str, str]]:
    """
    Convert multiple IPC sections to BNS at once.
    
    Args:
        sections: List of IPC section numbers
    
    Returns:
        List of conversion results
    """
    results = []
    for section in sections:
        result = convert_ipc_to_bns(section)
        results.append(result)
    return results


def get_bns_by_category(category: str) -> List[Dict[str, str]]:
    """
    Get all BNS sections by category.
    
    Args:
        category: Category name (murder, theft, assault, etc.)
    
    Returns:
        List of relevant sections
    """
    categories = {
        "murder": ["302", "300", "299", "304", "307"],
        "theft": ["378", "379", "380", "382"],
        "robbery": ["390", "392", "395", "396", "397"],
        "assault": ["319", "320", "323", "324", "325", "326"],
        "sexual_offenses": ["354", "354A", "354B", "354C", "354D", "375", "376"],
        "cheating": ["415", "417", "418", "420"],
        "forgery": ["463", "464", "465", "467", "468", "471"],
        "defamation": ["499", "500"],
        "kidnapping": ["363", "365", "366"],
        "dowry": ["304B", "498A"],
        "trespass": ["447", "448", "449", "452", "453", "454", "456", "457"]
    }
    
    category_lower = category.lower().replace(" ", "_")
    if category_lower not in categories:
        return []
    
    results = []
    for section in categories[category_lower]:
        if section in IPC_TO_BNS_MAP:
            mapping = IPC_TO_BNS_MAP[section]
            results.append({
                "ipc_section": f"IPC {section}",
                "bns_section": f"BNS {mapping['bns']}",
                "description": mapping["description"]
            })
    
    return results
