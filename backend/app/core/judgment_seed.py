"""Seed judgments table for live judicial analytics."""
from __future__ import annotations

from .db import session_scope
from .orm_models import Judgment

_SEED = [
    ("(1973) 4 SCC 225", "Kesavananda Bharati v. State of Kerala", "Sikri", "437", "Constitutional", "Affirmed", "Kesavananda"),
    ("(1980) 3 SCC 625", "Minerva Mills v. Union of India", "Chandrachud", "368", "Constitutional", "Affirmed", "Kesavananda"),
    ("(2015) 5 SCC 1", "Shreya Singhal v. Union of India", "Nariman", "66A", "IT Act", "Overruled", "Section 66A batch"),
    ("(2019) 3 SCC 39", "Rafale Review", "Gogoi", "CrPC 218", "Criminal", "Bail Denied", "Political cases"),
    ("(2020) 4 SCC 761", "Arnab Goswami v. State", "Bhushan", "437", "CrPC", "Bail Granted", "Media bail"),
    ("(2021) 2 SCC 118", "Siddharth v. State of UP", "Chandrachud", "437", "CrPC", "Bail Granted", "Economic offences bail"),
    ("(2022) 1 SCC 801", "Satender Kumar Antil", "Nariman", "437", "CrPC", "Bail Granted", "Arrest guidelines"),
    ("(2018) 11 SCC 1", "Common Cause v. Union", "Misra", "302", "IPC", "Conviction", "Murder sentencing"),
    ("(2017) 9 SCC 321", "Rajesh Sharma v. State", "Goel", "498A", "IPC", "Distinguished", "498A guidelines"),
    ("(2024) 2 SCC 100", "Sample Bail Matter A", "Khanna", "437", "BNSS", "Bail Granted", "CrPC 437"),
    ("(2024) 3 SCC 200", "Sample Bail Matter B", "Khanna", "437", "BNSS", "Bail Denied", "CrPC 437"),
    ("(2023) 5 SCC 50", "Sample Acquittal X", "Kaul", "302", "IPC", "Acquittal", "Murder"),
    ("(2023) 6 SCC 60", "Sample Conviction Y", "Kaul", "302", "IPC", "Conviction", "Murder"),
    ("(2022) 8 SCC 90", "Bail Grant Z", "Nageswara Rao", "437", "CrPC", "Bail Granted", "Default bail"),
    ("(2022) 9 SCC 91", "Bail Denied W", "Nageswara Rao", "437", "CrPC", "Bail Denied", "NDPS"),
]


def seed_judgments_if_empty() -> int:
    with session_scope() as db:
        if db.query(Judgment).count() > 0:
            return 0
        for cit, name, judge, sec, court, disp, landmark in _SEED:
            db.add(
                Judgment(
                    citation=cit,
                    case_name=name,
                    judge_name=judge,
                    statute_section=sec,
                    court=court,
                    year=int(cit[1:5]) if len(cit) > 5 and cit[1:5].isdigit() else 2020,
                    disposition_outcome=disp,
                    relation_to_landmark=disp.split()[0] if disp else "referred",
                    landmark_citation=landmark,
                )
            )
        return len(_SEED)
