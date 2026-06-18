# Changelog - LegalEase.AI

## [2.1.0] - 2026-05-19 - LM Studio, Per-User RAG, and Windows Hardening

### Fixed

- Default LM Studio URL is now `http://127.0.0.1:1234` (same PC) instead of a hardcoded LAN IP, so Knowledge Base and other modes work out of the box when LM Studio is local.
- RAG embeddings default to the SentenceTransformer path (`RAG_USE_LANGCHAIN_HF` defaults to off) to avoid repeated Windows WinError 1455 failures when importing `langchain_huggingface`.
- `app.py` loads `.env` before importing `llms` so `LM_STUDIO_URL` and models apply on every run.
- Normalized LM Studio URLs so roots like `http://127.0.0.1:1234` automatically resolve to the OpenAI-compatible `/v1` API.
- Fixed Knowledge Base retrieval failures caused by an overly strict FAISS score cutoff.
- Replaced the global FAISS workflow with per-user indexes under `faiss_indexes/`.
- Upload & Process now uploads PDFs and rebuilds the user's knowledge base in one step.
- Web Search now prefers Google Custom Search (`GOOGLE_API_KEY` + `GOOGLE_CSE_ID`) with fallback search only when Google is not configured.
- Converted `dynamic_app.py` into a compatibility entrypoint for the upgraded main app.

### Security

- Sanitized PDF filenames and enforced a configurable upload-size limit.
- Escaped chat content before rendering inside custom message bubbles.
- Restricted FAISS deserialization to project-owned index directories.
- Document deletion now removes related metadata and refreshes the user's index.

### Windows

- Added `run_windows.bat`, `.env.example`, and VS Code interpreter settings for `venv\Scripts\python.exe`.

## [2.0.0] - 2024-12-XX - Major Refactor: Free LLM Integration

### 🎉 Major Changes

#### Replaced Gemini with Free Open-Source LLMs

- **Removed**: Google Gemini API dependencies (`ChatGoogleGenerativeAI`, `google.generativeai`)
- **Added**: Local transformers support (`google/flan-t5-small` as default)
- **Added**: Optional HuggingFace Inference API support (free tier)
- **Result**: App now works completely free, no paid API keys required

#### New LLM Provider Architecture

- Created `LLMProvider` class in `llms.py` with unified interface
- Supports multiple backends:
  - `local`: Uses transformers library (default)
  - `hf_inference`: Uses HuggingFace Inference API (optional)
- Automatic fallback: If HF API unavailable, falls back to local model
- Environment variable configuration: `LLM_BACKEND` and `HF_API_TOKEN`

### ✨ New Features

#### Three AI Modes (Fully Implemented)

1. **Knowledge Base Mode** (Strict RAG)
   - Answers only from uploaded PDFs
   - Provides citations: `[[filename:chunk_index]]`
   - Returns "NOT_FOUND_IN_KB" when information not available
   - BNS prioritization over IPC

2. **Web Search Mode** (Internet-enabled)
   - Uses DuckDuckGo search (free)
   - HTTP fallback if `duckduckgo-search` package unavailable
   - Cites sources with URLs and dates

3. **Deep Case Assistant** (Pro/Legal Pro only)
   - Combines KB + web search
   - Larger similarity search (k=50)
   - Structured case study output
   - Extracts verdicts, judgments, entities

#### Legal Tools

- **IPC → BNS Transition Engine**
  - Mapping file: `mappings/ipc_to_bns.json`
  - Automatic annotation of IPC sections with BNS equivalents
  - Admin UI for editing mappings (future)

- **Timeline & Date Extractor**
  - Extracts chronological events from documents
  - Uses `datefinder` + regex patterns
  - Stores in `document_timeline` table
  - UI display in Documents section

- **Case Entity Extraction**
  - Extracts: Plaintiff, Defendant, Judge, Court, Case Number, Sections, Dates
  - Uses spaCy (with regex fallback)
  - Stores in `case_entities` table
  - Dashboard view available

- **Automated Legal Drafting**
  - Templates: FIR, Notice, Affidavit, Chargesheet
  - Fillable placeholders from extracted entities
  - Export as .docx or .txt

- **Court Fee Calculator**
  - Configurable rules in JSON
  - State/regulation-based calculation
  - UI in Tools section

### 🔧 Technical Improvements

#### Modular Architecture

- **`llms.py`**: LLM provider abstraction
  - `LLMProvider` class with local/HF API support
  - `get_generator()` factory function
  - `search_web()` with caching and fallbacks
  - `generator_status()` for UI status display

- **`rag.py`**: RAG pipeline
  - `index_documents()`: FAISS indexing with metadata
  - `query_kb()`: Similarity search with scores
  - `build_faiss_index()`: UI-friendly wrapper

- **`prompts.py`**: Prompt templates
  - `kb_prompt()`: Strict RAG prompt with citations
  - `web_prompt()`: Web search synthesis prompt
  - `deepcase_prompt()`: Structured case study prompt

- **`legal_tools.py`**: Legal utilities
  - `map_law_references()`: IPC→BNS mapping
  - `extract_timeline()`: Date/event extraction
  - `extract_case_entities()`: Entity extraction

#### Database Schema Updates

- Added `case_entities` table
- Added `document_timeline` table
- Maintained backward compatibility with existing tables

#### Error Handling

- Graceful degradation when models unavailable
- Clear error messages for users
- Fallback mechanisms throughout
- Model download UI button

### 🐛 Bug Fixes

- Fixed indentation errors in chat section
- Fixed mode selection logic
- Fixed Deep Case Assistant access control (Pro/Legal Pro only)
- Fixed web search fallback when package unavailable
- Fixed IPC→BNS mapping display

### 📦 Dependencies

#### Removed
- `langchain_google_genai` (Gemini)
- `google-generativeai` (Gemini)

#### Added
- `transformers` (local LLM support)
- `torch` (for transformers)
- `requests` (HTTP fallback for web search)

#### Updated
- `duckduckgo-search`: Made optional with fallback
- All other dependencies maintained

### 🧪 Testing

- Added `tests/test_llm_backends.py`: LLM provider tests
- Added `tests/test_rag.py`: FAISS indexing/querying tests
- Added `tests/test_prompts.py`: Prompt template tests
- Added `tests/test_tools.py`: Legal tools tests
- Added `tests/test_integration_demo.py`: End-to-end integration test

### 📚 Documentation

- Created comprehensive `README.md`
- Added installation instructions
- Added configuration guide
- Added troubleshooting section
- Added model information

### 🔒 Security & Privacy

- All processing local by default
- No external API calls (unless HF Inference API used)
- Passwords hashed with bcrypt
- Documents stored locally

### ⚡ Performance

- CPU-optimized models (flan-t5-small)
- Batch processing for embeddings
- Caching for web search results
- Efficient FAISS indexing

### 🎨 UI Improvements

- Model status display in sidebar
- Download button for missing models
- Clear mode descriptions
- Better error messages
- IPC→BNS mapping display
- Timeline and entity dashboards

### 📝 Configuration

- Environment variables:
  - `LLM_BACKEND`: "local" or "hf_inference" (default: "local")
  - `LLM_MODEL`: Model name (default: "google/flan-t5-small")
  - `HF_API_TOKEN`: HuggingFace token (optional, for HF Inference API)

### 🔄 Migration Notes

For existing users:
1. No database migration needed (backward compatible)
2. Re-index documents after update (recommended)
3. Model will download automatically on first use
4. Old Gemini API keys no longer needed

### 🚀 Next Steps (Future)

- [ ] Admin UI for IPC→BNS mapping editing
- [ ] More legal document templates
- [ ] Multi-language support improvements
- [ ] Export case studies as PDF
- [ ] Advanced entity relationship extraction
- [ ] Court fee rules for all Indian states
- [ ] Batch document processing
- [ ] API endpoints for integration

---

## [1.0.0] - Previous Version

- Initial release with Gemini integration
- Basic RAG functionality
- User authentication
- Document upload
- Knowledge base mode

---

**Note**: This changelog documents the major refactor from Gemini to free LLMs. All previous features maintained with improved architecture.
