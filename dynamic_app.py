"""
Legacy compatibility entrypoint.

The production application now lives in app.py. This file remains so old
shortcuts that run `streamlit run dynamic_app.py` still launch the upgraded
LM Studio/RAG application instead of the deprecated Gemini/global-index app.
"""

from app import main


if __name__ == "__main__":
    main()
