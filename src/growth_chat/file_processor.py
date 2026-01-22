"""
File Processor for Chat Attachments.

Handles downloading and parsing files attached to chat messages.
Uses direct GCS access via service account credentials.

Supported file types:
- Excel (.xlsx, .xls)
- CSV
- Text (.txt)
- PDF

The processor downloads files to temporary storage, parses them,
and returns structured content for inclusion in the agent context.
"""
import io
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from google.cloud import storage
from pydantic import BaseModel

from .schemas import AttachedFile

logger = logging.getLogger(__name__)

# ============================================
# Configuration
# ============================================

# Maximum content length to return (to avoid context overflow)
MAX_CONTENT_LENGTH = 50000  # ~50KB of text
MAX_ROWS_PREVIEW = 100  # For tabular data
MAX_COLUMNS_PREVIEW = 20

# ============================================
# Processed File Result
# ============================================


class ProcessedFileContent(BaseModel):
    """Result of processing an attached file."""
    
    file_id: int
    filename: str
    mime_type: str
    success: bool
    content: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}
    
    @property
    def summary(self) -> str:
        """Generate a brief summary for the agent."""
        if not self.success:
            return f"[File: {self.filename} - Error: {self.error}]"
        
        meta_parts = []
        if "rows" in self.metadata:
            meta_parts.append(f"{self.metadata['rows']} rows")
        if "columns" in self.metadata:
            meta_parts.append(f"{self.metadata['columns']} columns")
        if "pages" in self.metadata:
            meta_parts.append(f"{self.metadata['pages']} pages")
        if "characters" in self.metadata:
            meta_parts.append(f"{self.metadata['characters']} characters")
        if "truncated" in self.metadata and self.metadata["truncated"]:
            meta_parts.append("truncated")
        
        meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""
        return f"[File: {self.filename}{meta_str}]"


# ============================================
# GCS Client
# ============================================

_storage_client: Optional[storage.Client] = None


def get_storage_client() -> storage.Client:
    """Get or create the GCS storage client."""
    global _storage_client
    if _storage_client is None:
        # Uses Application Default Credentials (ADC) in GCP environment
        _storage_client = storage.Client()
        logger.info("Initialized GCS storage client")
    return _storage_client


def download_file_from_gcs(bucket_name: str, gcs_path: str) -> bytes:
    """
    Download a file from GCS.
    
    Args:
        bucket_name: Name of the GCS bucket
        gcs_path: Full path within the bucket
        
    Returns:
        File contents as bytes
        
    Raises:
        google.cloud.exceptions.NotFound: If file doesn't exist
    """
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    
    content = blob.download_as_bytes()
    logger.info(f"Downloaded file from GCS: gs://{bucket_name}/{gcs_path} ({len(content)} bytes)")
    
    return content


# ============================================
# File Parsers
# ============================================

def parse_excel(content: bytes, filename: str) -> ProcessedFileContent:
    """Parse Excel file (.xlsx, .xls) and extract content."""
    try:
        import pandas as pd
        
        # Try to read all sheets
        excel_file = pd.ExcelFile(io.BytesIO(content))
        sheet_names = excel_file.sheet_names
        
        all_content = []
        total_rows = 0
        max_columns = 0
        
        for sheet_name in sheet_names[:5]:  # Limit to first 5 sheets
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            # Limit rows and columns for preview
            preview_df = df.head(MAX_ROWS_PREVIEW).iloc[:, :MAX_COLUMNS_PREVIEW]
            
            total_rows += len(df)
            max_columns = max(max_columns, len(df.columns))
            
            # Convert to string representation
            sheet_content = f"\n### Sheet: {sheet_name}\n"
            sheet_content += f"Columns: {', '.join(df.columns.astype(str)[:MAX_COLUMNS_PREVIEW])}\n"
            sheet_content += preview_df.to_string(index=False, max_rows=MAX_ROWS_PREVIEW)
            
            all_content.append(sheet_content)
        
        combined_content = "\n".join(all_content)
        
        # Truncate if too long
        truncated = False
        if len(combined_content) > MAX_CONTENT_LENGTH:
            combined_content = combined_content[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated...]"
            truncated = True
        
        return ProcessedFileContent(
            file_id=0,  # Will be set by caller
            filename=filename,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            success=True,
            content=combined_content,
            metadata={
                "sheets": len(sheet_names),
                "rows": total_rows,
                "columns": max_columns,
                "truncated": truncated,
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to parse Excel file {filename}: {e}")
        return ProcessedFileContent(
            file_id=0,
            filename=filename,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            success=False,
            error=str(e),
        )


def parse_csv(content: bytes, filename: str) -> ProcessedFileContent:
    """Parse CSV file and extract content."""
    try:
        import pandas as pd
        
        # Try different encodings
        for encoding in ['utf-8', 'latin1', 'cp1252']:
            try:
                df = pd.read_csv(io.BytesIO(content), encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Could not decode CSV with any supported encoding")
        
        total_rows = len(df)
        total_cols = len(df.columns)
        
        # Limit for preview
        preview_df = df.head(MAX_ROWS_PREVIEW).iloc[:, :MAX_COLUMNS_PREVIEW]
        
        csv_content = f"Columns: {', '.join(df.columns.astype(str)[:MAX_COLUMNS_PREVIEW])}\n"
        csv_content += f"Total rows: {total_rows}, showing first {min(MAX_ROWS_PREVIEW, total_rows)}\n\n"
        csv_content += preview_df.to_string(index=False, max_rows=MAX_ROWS_PREVIEW)
        
        # Truncate if too long
        truncated = False
        if len(csv_content) > MAX_CONTENT_LENGTH:
            csv_content = csv_content[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated...]"
            truncated = True
        
        return ProcessedFileContent(
            file_id=0,
            filename=filename,
            mime_type="text/csv",
            success=True,
            content=csv_content,
            metadata={
                "rows": total_rows,
                "columns": total_cols,
                "truncated": truncated,
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to parse CSV file {filename}: {e}")
        return ProcessedFileContent(
            file_id=0,
            filename=filename,
            mime_type="text/csv",
            success=False,
            error=str(e),
        )


def parse_text(content: bytes, filename: str) -> ProcessedFileContent:
    """Parse text file and extract content."""
    try:
        # Try different encodings
        text_content = None
        for encoding in ['utf-8', 'latin1', 'cp1252']:
            try:
                text_content = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if text_content is None:
            raise ValueError("Could not decode text with any supported encoding")
        
        total_chars = len(text_content)
        
        # Truncate if too long
        truncated = False
        if len(text_content) > MAX_CONTENT_LENGTH:
            text_content = text_content[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated...]"
            truncated = True
        
        return ProcessedFileContent(
            file_id=0,
            filename=filename,
            mime_type="text/plain",
            success=True,
            content=text_content,
            metadata={
                "characters": total_chars,
                "truncated": truncated,
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to parse text file {filename}: {e}")
        return ProcessedFileContent(
            file_id=0,
            filename=filename,
            mime_type="text/plain",
            success=False,
            error=str(e),
        )


def parse_pdf(content: bytes, filename: str) -> ProcessedFileContent:
    """Parse PDF file and extract text content."""
    try:
        import pypdf
        
        reader = pypdf.PdfReader(io.BytesIO(content))
        total_pages = len(reader.pages)
        
        all_text = []
        for i, page in enumerate(reader.pages[:50]):  # Limit to first 50 pages
            page_text = page.extract_text() or ""
            if page_text.strip():
                all_text.append(f"--- Page {i + 1} ---\n{page_text}")
        
        combined_text = "\n\n".join(all_text)
        
        # Truncate if too long
        truncated = False
        if len(combined_text) > MAX_CONTENT_LENGTH:
            combined_text = combined_text[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated...]"
            truncated = True
        
        return ProcessedFileContent(
            file_id=0,
            filename=filename,
            mime_type="application/pdf",
            success=True,
            content=combined_text if combined_text.strip() else "[PDF contains no extractable text]",
            metadata={
                "pages": total_pages,
                "truncated": truncated,
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to parse PDF file {filename}: {e}")
        return ProcessedFileContent(
            file_id=0,
            filename=filename,
            mime_type="application/pdf",
            success=False,
            error=str(e),
        )


# ============================================
# Main Processing Function
# ============================================

def process_file(attached_file: AttachedFile) -> ProcessedFileContent:
    """
    Process a single attached file.
    
    Downloads the file from GCS and parses it based on MIME type.
    
    Args:
        attached_file: File metadata including GCS location
        
    Returns:
        ProcessedFileContent with extracted text or error
    """
    try:
        # Download from GCS
        content = download_file_from_gcs(
            bucket_name=attached_file.gcs_bucket,
            gcs_path=attached_file.gcs_path,
        )
        
        # Parse based on MIME type
        if attached_file.mime_type in [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        ]:
            result = parse_excel(content, attached_file.filename)
        elif attached_file.mime_type == "text/csv":
            result = parse_csv(content, attached_file.filename)
        elif attached_file.mime_type == "text/plain":
            result = parse_text(content, attached_file.filename)
        elif attached_file.mime_type == "application/pdf":
            result = parse_pdf(content, attached_file.filename)
        else:
            result = ProcessedFileContent(
                file_id=attached_file.id,
                filename=attached_file.filename,
                mime_type=attached_file.mime_type,
                success=False,
                error=f"Unsupported file type: {attached_file.mime_type}",
            )
        
        # Set the file ID
        result.file_id = attached_file.id
        return result
        
    except Exception as e:
        logger.error(f"Failed to process file {attached_file.filename}: {e}")
        return ProcessedFileContent(
            file_id=attached_file.id,
            filename=attached_file.filename,
            mime_type=attached_file.mime_type,
            success=False,
            error=str(e),
        )


def process_files(attached_files: List[AttachedFile]) -> List[ProcessedFileContent]:
    """
    Process multiple attached files.
    
    Args:
        attached_files: List of file metadata
        
    Returns:
        List of processed file results
    """
    if not attached_files:
        return []
    
    results = []
    for file in attached_files:
        result = process_file(file)
        results.append(result)
        logger.info(f"Processed file {file.filename}: success={result.success}")
    
    return results


def format_files_for_context(processed_files: List[ProcessedFileContent]) -> str:
    """
    Format processed files for inclusion in the agent context.
    
    Creates a formatted string that can be prepended to the user's query.
    
    Args:
        processed_files: List of processed file results
        
    Returns:
        Formatted string for agent context
    """
    if not processed_files:
        return ""
    
    parts = ["The user has attached the following files:\n"]
    
    for pf in processed_files:
        parts.append(f"\n{pf.summary}")
        if pf.success and pf.content:
            parts.append(f"\n```\n{pf.content}\n```\n")
        elif not pf.success:
            parts.append(f"\n[Could not read file: {pf.error}]\n")
    
    return "\n".join(parts)

