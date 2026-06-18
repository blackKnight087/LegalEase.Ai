# LegalEase — AI Chat, Learning & Model Improvement Automation Workflow

This document maps the **end-to-end automation** for chat modes, human/implicit learning, and Ollama/Gemini improvement pipelines as implemented in the codebase.

---

## 1. Master overview (request → answer → learn → improve)

```mermaid
flowchart TB
    subgraph USER["User (Web Chat)"]
        U1[Send message]
        U2[Thumbs / Copy / Regenerate / Tags]
        U3[Follow-up click / Export / Dwell]
        U4[Mode switch KB → Open Law]
    end

    subgraph AUTH["Auth & tenancy"]
        A1[JWT + user_id context]
        A2[Plan gate Free vs Pro]
    end

    subgraph ROUTE["Mode routing"]
        R1[User-selected mode pill]
        R2[mode_router.route_query]
        R3[Plan guard Hybrid blocked on Free]
        R4[Session + thread + matter scope]
    end

    subgraph MODES["Chat engines"]
        M1[Knowledge Base<br/>Ollama + FAISS]
        M2[Open Law<br/>Gemini grounded web]
        M3[Hybrid / Deep Case<br/>KB + web fusion]
    end

    subgraph LEARN["Learning layer"]
        L1[record_interaction per turn]
        L2[learning_signals processor]
        L3[Preferences + retrieval + human labels]
    end

    subgraph IMPROVE["Improvement automation"]
        I1[Neural embed train per user]
        I2[KB re-index]
        I3[Modelfile export + ollama create]
        I4[Gemini Coach Settings-only]
        I5[Daily / Weekly / Monthly scheduler]
    end

    U1 --> A1 --> R1 --> R2 --> R3 --> R4
    R4 --> M1 & M2 & M3
    M1 & M2 & M3 --> L1
    U2 & U3 & U4 --> L2 --> L3
    L3 --> I1 --> I2 --> I3
    L3 --> I4 --> I5
    I3 --> M1
    I4 --> M1
```

---

## 2. Chat mode routing & engines

```mermaid
flowchart LR
    subgraph INPUT
        Q[User query]
        H[History + session memory]
        TID[thread_id / matter_id]
    end

    subgraph ROUTER["mode_router.py"]
        P[parse_legal_query]
        FU[Semantic follow-up intent]
        EXP[expand_kb_query]
        RD{RouteDecision}
    end

    subgraph KB["Mode: Knowledge Base"]
        KB1[kb_pipeline]
        KB2[FAISS retrieve user/matter index]
        KB3[KB depth classifier]
        KB4[User preference prompt block]
        KB5[Ollama synthesize — documents only]
        KB6[NOT_FOUND if no chunks]
    end

    subgraph OL["Mode: Open Law"]
        OL1[classify_open_law_request]
        OL2[Gemini + Google Search Grounding]
        OL3[Depth: quick / standard / detailed]
        OL4[Disclaimer appended]
    end

    subgraph HY["Mode: Hybrid / Deep Case"]
        HY1[run_jurisprudence_turn]
        HY2[KB chunks FIRST priority]
        HY3[Gemini web for gaps / jurisprudence]
        HY4[Fusion + executive report format]
    end

    Q --> P --> FU --> EXP --> RD
    H --> P
    TID --> KB1

    RD -->|knowledge_base| KB1 --> KB2 --> KB3 --> KB4 --> KB5
    RD -->|open_law| OL1 --> OL2 --> OL3 --> OL4
    RD -->|hybrid| HY1 --> HY2 --> HY3 --> HY4

    KB5 --> OUT[Answer + follow-ups + interaction_id]
    OL4 --> OUT
    HY4 --> OUT
```

### Mode rules (hard separation)

| Mode | LLM | Data source | When used |
|------|-----|-------------|-----------|
| **Knowledge Base** | Ollama (local) | User-uploaded FAISS index only | Default; document Q&A |
| **Open Law** | Gemini (cloud) | Grounded web search | Statutes, news, live law |
| **Hybrid / Deep Case** | Ollama + Gemini | KB first, then web | Pro; case strategy + docs |
| **Gemini Coach** | Gemini (Settings only) | Feedback meta — never chat | Tuning coach, not answers |

```mermaid
flowchart TB
    subgraph GUARDS["Non-negotiable guards"]
        G1["GEMINI_KB_SYNTHESIS=0 → Gemini never writes KB answers"]
        G2["Coach = style/format only — no legal substance"]
        G3["SFT pairs ONLY from human-verified signals"]
        G4["Per-user Ollama model + embedding scope"]
    end
```

---

## 3. Knowledge Base turn (detailed automation)

```mermaid
sequenceDiagram
    participant U as User
    participant CS as chat_service
    participant KP as kb_pipeline
    participant RM as retrieval + adaptive_learning
    participant PR as user_preferences
    participant OL as Ollama
    participant AL as adaptive_learning

    U->>CS: message (mode=KB, matter_id?)
    CS->>KP: expand query + session memory
    KP->>PR: attach preference_block + kb_classification
    KP->>RM: FAISS search + chunk boosts + query expansions
    RM-->>KP: ranked chunks
    alt chunks found
        KP->>OL: synthesize with persona + prefs + chunks
        OL-->>KP: grounded answer
    else NOT_FOUND
        KP-->>CS: NOT_FOUND_IN_KB
    end
    CS->>AL: record_interaction(user, mode, query, chunks)
    CS-->>U: answer + follow_ups + interaction_id
```

---

## 4. Learning signals automation (all sources)

```mermaid
flowchart TB
    subgraph EXPLICIT["Explicit user signals"]
        E1[thumbs_up]
        E2[thumbs_down + comment]
        E3[Structured tags<br/>too_long / wrong_section / …]
        E4[copy]
        E5[regenerate]
        E6[follow_up_click]
        E7[export_docx / pdf]
        E8[save_to_matter]
        E9[edit_diff after copy]
    end

    subgraph IMPLICIT["Implicit signals"]
        I1[dwell_time on answer]
        I2[mode_switch KB→Open Law]
        I3[re-ask after NOT_FOUND]
        I4[KB turn chunk boosts]
    end

    subgraph PROC["learning_signals.py"]
        P1[Record human_labels]
        P2[Apply tag → preferences]
        P3[Retrieval learning expansions]
        P4[Preference pair DPO<br/>chosen vs rejected]
        P5[Regenerate chain pair]
        P6[RLAIF style score — Gemini guarded]
    end

    subgraph STORES["Data stores"]
        S1[(adaptive_interactions)]
        S2[(adaptive_feedback)]
        S3[(human_labels)]
        S4[(preference_pairs)]
        S5[(learning_signal_events)]
        S6[(user_preferences)]
        S7[(neural training pairs)]
    end

    E1 & E2 & E3 & E4 & E5 & E6 & E7 & E8 & E9 --> P1
    I1 & I2 & I3 & I4 --> P1
    P1 --> P2 & P3 & P4 & P5 & P6
    P2 --> S6
    P3 --> S7
    P4 & P5 --> S4
    P1 --> S2 & S3 & S5
    P1 --> S1
```

### Signal → training eligibility

| Signal | Reward | SFT pair? | DPO pair? | Preferences? | Retrieval? |
|--------|--------|-----------|-----------|--------------|------------|
| thumbs_up | +1.0 | Yes | — | Yes | Yes |
| copy | +0.85 | Yes | — | Yes | Yes |
| export_* | +0.95 | Yes | — | — | — |
| thumbs_down | -1.0 | No | Yes | Yes (tags) | Failure |
| regenerate | -0.55 | No | Yes (chain) | — | — |
| follow_up_click | +0.35 | No | — | Yes | — |
| dwell_time | ± | No | — | Yes | — |
| mode_switch | -0.45 | No | — | — | Failure |
| edit_diff | +0.75 | Style pair | Yes | — | — |

---

## 5. Model improvement pipeline (automation)

```mermaid
flowchart TB
    subgraph TRIGGERS["Pipeline triggers"]
        T1[Manual — Settings Run Now]
        T2[Feedback — thumbs_up/down/copy/regenerate]
        T3[Daily scheduler ~1 day]
        T4[Weekly scheduler ~7 days]
        T5[Monthly scheduler ~30 days]
    end

    subgraph PIPE["improvement_automation.py"]
        direction TB
        P0[schedule_improvement_pipeline<br/>background thread per user]
        P1[collect_pairs_from_feedback]
        P2[neural_finetuning — embedding train<br/>scope=user]
        P3[KB re-index FAISS]
        P4{thumbs_up ≥ threshold?}
        P5[Export Modelfile + training.jsonl]
        P6[ollama create legalease-tuned]
        P7[Set active_model.txt per user]
    end

    subgraph COACH["Gemini Ollama Coach — Settings ONLY"]
        C1[analyze_feedback]
        C2[coach_guards validate JSON]
        C3[Apply style prefs + query healings]
        C4[NEVER fill training_pairs]
        C5[RLAIF style scoring]
    end

    subgraph SCHED["coach_scheduler.py tiers"]
        D[Daily: full pipeline]
        W[Weekly: coach + SFT export + pairs]
        M[Monthly: full + DPO export + session reset]
    end

    T1 & T2 & T3 --> P0
    T4 --> W
    T5 --> M
    P0 --> P1 --> P2 --> P3 --> P4
    P4 -->|yes| P5 --> P6 --> P7
    P4 -->|no| P7
    W & M --> C1 --> C2 --> C3
    C1 --> C5
    P7 --> OLLAMA[Next KB chat uses tuned Ollama]
    P2 --> OLLAMA
    P3 --> OLLAMA
```

---

## 6. Gemini vs Ollama responsibility map

```mermaid
flowchart LR
    subgraph RUNTIME["During chat"]
        O1[Ollama — KB synthesis]
        O2[Ollama — follow-up intent local]
        O3[Ollama — drafting helpers local]
        G1[Gemini — Open Law answers]
        G2[Gemini — Hybrid web gaps]
    end

    subgraph OFFLINE["Offline / Settings only"]
        G3[Gemini Coach — feedback analysis]
        G4[Gemini RLAIF — style scores only]
        O4[Ollama — neural embed fine-tune]
        O5[Ollama — Modelfile personality]
    end

    subgraph BLOCKED["Gemini NEVER does"]
        B1[Write KB answers]
        B2[Inject legal training pairs]
        B3[Bias Ollama legal conclusions]
        B4[Run during KB chat turn]
    end

    G3 -.->|guarded by coach_guards.py| O5
    G4 -.->|style only| O4
```

---

## 7. End-to-end feedback loop (closed automation)

```mermaid
flowchart LR
    A[User chats in mode] --> B[Interaction logged]
    B --> C{User signal?}
    C -->|positive| D[SFT pair + retrieval boost]
    C -->|negative| E[DPO pair + prefs + coach optional]
    C -->|implicit| F[Dwell / mode switch prefs]
    D & E & F --> G[human_training + user_preferences]
    G --> H{Thresholds met?}
    H -->|yes| I[Neural train + re-index]
    I --> J[Modelfile export]
    J --> K[ollama create per user]
    K --> L[Tuned Ollama on next KB turn]
    E --> M[Gemini Coach weekly/monthly]
    M --> N[Style prefs + query healings]
    N --> L
    L --> A
```

---

## 8. API endpoints (learning & automation)

| Endpoint | Purpose |
|----------|---------|
| `POST /api/v1/chat` (stream) | All chat modes |
| `POST /api/v1/learning/feedback` | Explicit signals + tags |
| `POST /api/v1/learning/signals` | Implicit signals (dwell, mode_switch, edit_diff) |
| `GET /api/v1/learning/signals/stats` | Signal analytics |
| `GET /api/v1/learning/training/status` | SFT/DPO readiness |
| `POST /api/v1/learning/automation/run-now` | Force improvement pipeline |
| `GET /api/v1/learning/tuning/coach/status` | Coach + schedule status |
| `POST /api/v1/learning/tuning/coach/run` | Full manual cycle |

---

## 9. Environment knobs

| Variable | Effect |
|----------|--------|
| `LLM_BACKEND=ollama` | KB uses local Ollama |
| `GEMINI_KB_SYNTHESIS=0` | Block Gemini from KB answers |
| `GEMINI_OLLAMA_TUNING=1` | Enable Settings coach |
| `IMPROVEMENT_AUTO=1` | Background improvement jobs |
| `COACH_AUTO_INTERVAL_DAYS=1` | Daily coach tier |
| `COACH_WEEKLY_INTERVAL_DAYS=7` | Weekly tier |
| `COACH_MONTHLY_INTERVAL_DAYS=30` | Monthly tier |
| `GEMINI_RLAIF_STYLE=1` | Style-only AI feedback scores |

---

## 10. File map (quick reference)

| Area | Key files |
|------|-----------|
| Chat orchestration | `backend/app/services/chat_service.py` |
| Mode routing | `backend/app/services/mode_router.py` |
| KB pipeline | `kb_pipeline.py`, `rag.py` |
| Open Law | `backend/app/core/web_intelligence.py` |
| Hybrid | `backend/app/services/hybrid_orchestrator.py` |
| Learning signals | `backend/app/core/learning_signals.py` |
| Human training SFT/DPO | `backend/app/core/human_training.py` |
| Preferences | `backend/app/core/user_preferences.py` |
| Retrieval learning | `backend/app/core/retrieval_learning.py` |
| Neural fine-tune | `backend/app/core/neural_finetuning.py` |
| Improvement auto | `backend/app/core/improvement_automation.py` |
| Coach + guards | `backend/app/core/gemini_ollama_coach.py`, `coach_guards.py` |
| Schedules | `backend/app/core/coach_scheduler.py` |
| UI feedback | `web/components/chat/MessageFeedback.tsx` |

---

*Generated from the LegalEase codebase architecture. Restart backend after env changes for schedulers and pipelines to activate.*
