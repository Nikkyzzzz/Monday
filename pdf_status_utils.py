# ============================== PDF Status Widget ==============================
import streamlit as st
from background_processor import background_processor

def show_pdf_processing_status():
    """Display PDF processing status widget - can be called from any page"""
    
    # Check if there are PDFs being processed
    pdf_data = st.session_state.get("uploaded_pdfs_data", [])
    if not pdf_data:
        return  # No PDFs to process
    
    # Get current status
    status_info = background_processor.get_status()
    status = status_info["status"]
    progress = status_info["progress"]
    
    # Only show results when Completed, hide processing status
    if status == "Completed":
        st.success("✅ PDF data extraction completed!")
        results = status_info["results"]
        if results.get("consolidated_data") is not None and not results["consolidated_data"].empty:
            with st.expander("📊 View Extracted PDF Data", expanded=False):
                st.dataframe(results["consolidated_data"], use_container_width=True)
    elif status == "Failed":
        error = status_info.get("error", "Unknown error")
        st.error(f"❌ PDF data extraction failed: {error}")
    # Hide all processing/pending states from user

def show_compact_pdf_status():
    """Silent background processing - no status shown to user"""
    # Completely silent - user should not know processing is happening
    pass