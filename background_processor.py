# ============================== Background Processing Module ==============================
import threading
import time
import streamlit as st
from io import BytesIO
import pdf_extraction
import queue
import logging

class BackgroundProcessor:
    """Handles background processing of PDF extraction"""
    
    def __init__(self):
        self.processing_thread = None
        self.is_processing = False
        self.result_queue = queue.Queue()
        self.status = "Pending"
        self.progress = 0
        self.results = {}
        self.error = None
        
    def start_pdf_processing(self, pdf_data_list):
        """Start PDF processing in background thread"""
        if self.is_processing:
            return  # Already processing
        
        # Set processing flags in both internal state and session state
        self.status = "Processing"
        self.progress = 0
        self.is_processing = True
        
        # Also update session state for compatibility
        try:
            st.session_state["pdf_extraction_status"] = "Processing"
            st.session_state["pdf_extraction_progress"] = 0
            st.session_state["pdf_background_started"] = True
        except:
            pass  # Ignore session state errors in background mode
        
        # Start background thread
        self.processing_thread = threading.Thread(
            target=self._process_pdfs_background,
            args=(pdf_data_list,),
            daemon=True
        )
        self.processing_thread.start()
    
    def _process_pdfs_background(self, pdf_data_list):
        """Background thread function for PDF processing"""
        try:
            # Convert PDF data back to file-like objects
            pdf_files = []
            for pdf_data in pdf_data_list:
                if pdf_data["bytes"]:
                    pdf_file = BytesIO(pdf_data["bytes"])
                    pdf_file.name = pdf_data["name"]
                    pdf_files.append(pdf_file)
            
            if pdf_files:
                # Create a simple progress tracker
                self._update_progress(10, "Starting PDF extraction...")
                
                # Process PDFs without UI refs (background processing)
                pdf_results = pdf_extraction.run_pdf_extraction(pdf_files, ui_refs=None)
                
                self._update_progress(90, "Finalizing results...")
                
                # Put results in queue for thread-safe retrieval
                self.result_queue.put({
                    "status": "Completed",
                    "results": pdf_results,
                    "progress": 100
                })
                
                # Update internal state
                self.status = "Completed"
                self.results = pdf_results
                self.progress = 100
                
                self._update_progress(100, "Completed")
            else:
                self.result_queue.put({
                    "status": "Failed",
                    "error": "No valid PDF files found",
                    "progress": 100
                })
                # Update internal state
                self.status = "Failed"
                self.error = "No valid PDF files found"
                self.progress = 100
                
        except Exception as e:
            # Handle errors gracefully
            error_msg = str(e)
            self.result_queue.put({
                "status": "Failed",
                "error": error_msg,
                "progress": 100
            })
            # Update internal state
            self.status = "Failed"
            self.error = error_msg
            self.progress = 100
        finally:
            self.is_processing = False
    
    def _update_progress(self, progress, message=""):
        """Thread-safe progress update"""
        # Update internal state
        self.progress = progress
        
        # Try to update session state but don't fail if not available
        try:
            st.session_state["pdf_extraction_progress"] = progress
            if message:
                st.session_state["pdf_extraction_message"] = message
        except:
            pass  # Silently handle any session state update issues
    
    def get_status(self):
        """Get current processing status"""
        # Check for Completedd results first
        try:
            result = self.result_queue.get_nowait()
            # Update internal state
            self.status = result["status"]
            self.progress = result["progress"]
            if "results" in result:
                self.results = result["results"]
            if "error" in result:
                self.error = result["error"]
            
            # Also update session state for compatibility
            try:
                st.session_state["pdf_extraction_status"] = result["status"]
                st.session_state["pdf_extraction_progress"] = result["progress"]
                if "results" in result:
                    st.session_state["pdf_results"] = result["results"]
                if "error" in result:
                    st.session_state["pdf_extraction_error"] = result["error"]
            except:
                pass  # Ignore session state errors
            
            self.result_queue.task_done()
        except queue.Empty:
            pass  # No new results
        
        return {
            "status": self.status,
            "progress": self.progress,
            "results": self.results,
            "error": self.error,
            "started": True if self.status != "Pending" else False,
            "message": getattr(self, 'message', "")
        }
    
    def is_Completed(self):
        """Check if processing is Completed"""
        return self.status in ["Completed", "Failed"]

# Global instance
background_processor = BackgroundProcessor()