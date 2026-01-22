"""Code execution tool for Research Agent.

Uses E2B sandboxes for secure Python code execution with Claude Sonnet
for intelligent code generation and analysis.
"""
import json
import os
from typing import Any, Dict, List, Optional, Tuple, Type, TYPE_CHECKING

from pydantic import BaseModel, Field, PrivateAttr

from src.utils.logger import logger
from src.utils.model_factory import create_chat_model, extract_text_content

from .base import ResearchBaseTool

if TYPE_CHECKING:
    from src.growth_chat.schemas import AttachedFile


class CodeExecuteInput(BaseModel):
    """Input for code execution tool."""
    code: str = Field(
        "",
        description="Python code to execute directly. Leave empty if providing a task description."
    )
    task: str = Field(
        "",
        description="Natural language description of what to compute/analyze. The tool will generate and run Python code."
    )
    context: str = Field(
        "",
        description="Optional context data or information to use in the code (e.g., data to analyze, variables to use)."
    )
    packages: List[str] = Field(
        default_factory=list,
        description="Additional pip packages to install before running (e.g., ['pandas', 'numpy'])."
    )
    input_files: List[str] = Field(
        default_factory=list,
        description="Filenames from attached files to load into sandbox (e.g., ['data.xlsx']). Files will be available at /home/user/<filename>"
    )
    output_files: List[str] = Field(
        default_factory=list,
        description="Paths to output files to make downloadable (e.g., ['/home/user/report.docx'])"
    )


# System prompt for code generation
CODE_GENERATION_PROMPT = """You are an expert Python programmer. Generate clean, efficient Python code to accomplish the given task.

RULES:
1. Write complete, runnable Python code
2. Include all necessary imports at the top
3. Print results clearly using print() statements
4. Handle potential errors gracefully
5. Keep code concise but readable
6. Use pandas, numpy, or other common data science libraries when appropriate
7. If the task involves data analysis, provide clear output with labels
8. VISUALIZATION: When appropriate, create matplotlib charts/graphs to visualize data.
   - Charts will be automatically captured and displayed in the chat
   - Use plt.show() to render charts (PNG format)
   - Supported: line charts, bar charts, scatter plots, pie charts, histograms, etc.
   - Add titles, labels, and legends for clarity

OUTPUT FORMAT:
Return ONLY the Python code, no explanations or markdown. The code should be ready to execute directly.
"""

# System prompt for result analysis
RESULT_ANALYSIS_PROMPT = """You are an expert at analyzing code execution results. Given the code that was run and its output, provide a clear summary.

RULES:
1. Summarize what the code did
2. Explain the key results/findings
3. Highlight any important numbers or insights
4. If there were errors, explain what went wrong
5. Keep the analysis concise and focused

Be direct and informative.
"""

# System prompt for error fixing
ERROR_FIX_PROMPT = """You are an expert Python debugger. The following code failed with an error. Fix the code to make it work.

RULES:
1. Analyze the error message carefully
2. Fix the specific issue causing the error
3. Return ONLY the corrected Python code
4. Keep the same logic/intent as the original code
5. Add error handling if needed

OUTPUT FORMAT:
Return ONLY the fixed Python code, no explanations or markdown.
"""


class CodeExecuteTool(ResearchBaseTool):
    """Execute Python code in a secure E2B sandbox.
    
    Uses Claude Sonnet for intelligent code generation from task descriptions,
    error analysis, and result interpretation.
    """
    
    name: str = "code_execute"
    
    # Private attribute to store attached files (injected from agent state)
    _attached_files: List[Any] = PrivateAttr(default_factory=list)
    
    def set_attached_files(self, files: List[Any]) -> None:
        """Set attached files from agent state.
        
        Called by the agent graph before tool execution to inject
        file metadata for sandbox uploads.
        
        Args:
            files: List of AttachedFile objects from agent state
        """
        self._attached_files = files or []
        logger.info(f"[CodeExecute] Received {len(self._attached_files)} attached files")
    
    description: str = """Execute Python code in a secure sandbox for data analysis and computation.

INPUT OPTIONS (provide one):
- code: Direct Python code to execute
- task: Natural language description (AI generates the code)

OPTIONAL:
- context: Data or information to use in the code
- packages: Additional pip packages to install (e.g., ["pandas", "numpy"])
- input_files: Filenames from user attachments to load into sandbox (e.g., ["data.xlsx"])
- output_files: Paths to output files to make downloadable (e.g., ["/home/user/report.docx"])

RETURNS: Code output, results, AI analysis, and download links for output files.

USE FOR:
- Complex calculations or data transformations
- Statistical analysis
- Data processing tasks
- Custom computations not available in other tools
- Verifying numerical claims or calculations
- Creating data visualizations and charts
- Processing user-uploaded files (Excel, CSV, etc.)
- Generating downloadable reports (docx, xlsx, pdf, etc.)

FILE SUPPORT:
- Input files: User attachments are uploaded to /home/user/<filename> in the sandbox
- Output files: Specify paths to files created by code; download links will be generated
- Example: input_files=["sales.xlsx"], output_files=["/home/user/analysis_report.docx"]

VISUALIZATION SUPPORT:
- Generate matplotlib charts that will be displayed inline in the chat
- Charts are automatically captured as PNG images
- Supported: line charts, bar charts, scatter plots, pie charts, histograms, box plots
- Example: task="Create a bar chart showing token distribution", context="[data]"

EXAMPLES:
- task="Calculate the compound annual growth rate from 100 to 250 over 5 years"
- task="Analyze this voting data and find the winner", context="[voting data here]"
- task="Create a pie chart showing the vote distribution", context="[vote data]"
- task="Process the uploaded Excel and create a summary report", input_files=["data.xlsx"], output_files=["/home/user/summary.docx"]
- code="import math; print(math.sqrt(144))"

NOTE: Uses Claude Sonnet for code generation and analysis. Execution is sandboxed for security."""
    args_schema: Type[BaseModel] = CodeExecuteInput
    
    # Model for code generation/analysis (uses Sonnet)
    _code_model: Optional[Any] = None
    
    # E2B sandbox instance
    _sandbox: Optional[Any] = None
    
    def _get_code_model(self):
        """Get or create the code model (Claude Sonnet)."""
        if self._code_model is None:
            model_name = os.getenv("CODE_EXECUTION_MODEL", "claude-3-5-sonnet-latest")
            logger.info(f"[CodeExecute] Initializing code model: {model_name}")
            self._code_model = create_chat_model(
                model_name=model_name,
                temperature=0.2  # Lower temperature for more deterministic code
            )
        return self._code_model
    
    def _generate_code(self, task: str, context: str = "") -> str:
        """Use Sonnet to generate Python code from a task description."""
        model = self._get_code_model()
        
        prompt = f"{CODE_GENERATION_PROMPT}\n\nTASK: {task}"
        if context:
            prompt += f"\n\nCONTEXT/DATA:\n{context}"
        
        logger.info(f"[CodeExecute] Generating code for task: {task[:100]}...")
        response = model.invoke(prompt)
        code = extract_text_content(response.content)
        
        # Clean up any markdown code blocks if present
        code = code.strip()
        if code.startswith("```python"):
            code = code[9:]
        if code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]
        
        return code.strip()
    
    def _fix_code(self, code: str, error: str) -> str:
        """Use Sonnet to fix code that failed."""
        model = self._get_code_model()
        
        prompt = f"{ERROR_FIX_PROMPT}\n\nORIGINAL CODE:\n```python\n{code}\n```\n\nERROR:\n{error}"
        
        logger.info(f"[CodeExecute] Attempting to fix code error: {error[:100]}...")
        response = model.invoke(prompt)
        fixed_code = extract_text_content(response.content)
        
        # Clean up any markdown code blocks
        fixed_code = fixed_code.strip()
        if fixed_code.startswith("```python"):
            fixed_code = fixed_code[9:]
        if fixed_code.startswith("```"):
            fixed_code = fixed_code[3:]
        if fixed_code.endswith("```"):
            fixed_code = fixed_code[:-3]
        
        return fixed_code.strip()
    
    def _analyze_results(self, code: str, output: str, error: str = "") -> str:
        """Use Sonnet to analyze and summarize the execution results."""
        model = self._get_code_model()
        
        prompt = f"{RESULT_ANALYSIS_PROMPT}\n\nCODE EXECUTED:\n```python\n{code}\n```\n\n"
        
        if error:
            prompt += f"ERROR:\n{error}\n\n"
        
        prompt += f"OUTPUT:\n{output}"
        
        logger.info("[CodeExecute] Analyzing execution results...")
        response = model.invoke(prompt)
        return extract_text_content(response.content)
    
    def _upload_files_to_sandbox(
        self,
        sandbox,
        input_files: List[str],
    ) -> List[str]:
        """Download files from GCS and upload to e2b sandbox.
        
        Uses attached files stored on the tool instance (injected from agent state).
        
        Args:
            sandbox: E2B sandbox instance
            input_files: List of filenames to upload
            
        Returns:
            List of sandbox paths where files were uploaded
        """
        from src.growth_chat.file_processor import download_file_from_gcs
        
        uploaded_paths = []
        attached_files = self._attached_files
        
        for filename in input_files:
            # Find matching attached file by filename
            # AttachedFile is a Pydantic model with .filename attribute
            attached = None
            for f in attached_files:
                # Handle both Pydantic model and dict for backwards compatibility
                file_name = getattr(f, 'filename', None) or (f.get('filename') if isinstance(f, dict) else None)
                if file_name == filename:
                    attached = f
                    break
            
            if not attached:
                logger.warning(f"[CodeExecute] File not found in attachments: {filename}")
                logger.info(f"[CodeExecute] Available files: {[getattr(f, 'filename', f.get('filename') if isinstance(f, dict) else '?') for f in attached_files]}")
                continue
            
            try:
                # Get GCS info - handle both Pydantic model and dict
                if isinstance(attached, dict):
                    gcs_bucket = attached.get("gcs_bucket")
                    gcs_path = attached.get("gcs_path")
                else:
                    gcs_bucket = getattr(attached, 'gcs_bucket', None)
                    gcs_path = getattr(attached, 'gcs_path', None)
                
                if not gcs_bucket or not gcs_path:
                    logger.warning(f"[CodeExecute] Missing GCS info for file: {filename}")
                    continue
                
                logger.info(f"[CodeExecute] Downloading {filename} from GCS bucket={gcs_bucket}, path={gcs_path}...")
                content = download_file_from_gcs(gcs_bucket, gcs_path)
                
                # Upload to sandbox at /home/user/<filename>
                sandbox_path = f"/home/user/{filename}"
                sandbox.files.write(sandbox_path, content)
                uploaded_paths.append(sandbox_path)
                
                logger.info(f"[CodeExecute] Uploaded {filename} to sandbox at {sandbox_path} ({len(content)} bytes)")
                
            except Exception as e:
                logger.error(f"[CodeExecute] Failed to upload {filename}: {e}")
        
        return uploaded_paths
    
    def _generate_download_urls(
        self,
        sandbox,
        output_files: List[str]
    ) -> List[Dict[str, str]]:
        """Generate pre-signed download URLs for output files.
        
        Args:
            sandbox: E2B sandbox instance
            output_files: List of file paths in the sandbox
            
        Returns:
            List of dicts with 'filename', 'path', and 'url'
        """
        downloads = []
        
        for path in output_files:
            try:
                # Check if file exists by trying to read it
                try:
                    sandbox.files.read(path)
                except Exception:
                    logger.warning(f"[CodeExecute] Output file not found: {path}")
                    continue
                
                # Generate pre-signed download URL
                url = sandbox.download_url(path)
                
                downloads.append({
                    "filename": os.path.basename(path),
                    "path": path,
                    "url": url
                })
                
                logger.info(f"[CodeExecute] Generated download URL for {path}")
                
            except Exception as e:
                logger.warning(f"[CodeExecute] Could not generate download URL for {path}: {e}")
        
        return downloads
    
    def _execute_in_sandbox(
        self,
        code: str,
        packages: List[str] = None,
        input_files: List[str] = None,
        output_files: List[str] = None,
    ) -> Tuple[str, str, List[Dict[str, str]], List[Dict[str, str]]]:
        """Execute code in E2B sandbox.
        
        Args:
            code: Python code to execute
            packages: Additional pip packages to install
            input_files: Filenames to upload from self._attached_files
            output_files: Paths to files to generate download URLs for
        
        Returns:
            Tuple of (stdout_output, error_output, charts, downloads)
            - charts: list of dicts with 'type' (png/svg) and 'data' (base64)
            - downloads: list of dicts with 'filename', 'path', and 'url'
        """
        try:
            from e2b_code_interpreter import Sandbox
        except ImportError:
            raise RuntimeError(
                "e2b-code-interpreter not installed. Run: pip install e2b-code-interpreter"
            )
        
        api_key = os.getenv("E2B_API_KEY")
        if not api_key:
            raise ValueError("E2B_API_KEY environment variable is required for code execution")
        
        logger.info("[CodeExecute] Creating E2B sandbox...")
        
        stdout_output = ""
        error_output = ""
        charts: List[Dict[str, str]] = []
        downloads: List[Dict[str, str]] = []
        
        input_files = input_files or []
        output_files = output_files or []
        
        # Create sandbox using class method (new SDK API)
        # API key is read from E2B_API_KEY env var automatically
        sandbox = Sandbox.create()
        
        try:
            # Upload input files to sandbox (uses self._attached_files)
            if input_files and self._attached_files:
                logger.info(f"[CodeExecute] Uploading {len(input_files)} input file(s) to sandbox...")
                uploaded_paths = self._upload_files_to_sandbox(sandbox, input_files)
                logger.info(f"[CodeExecute] Uploaded files: {uploaded_paths}")
            
            # Install additional packages if needed
            if packages:
                logger.info(f"[CodeExecute] Installing packages: {packages}")
                for pkg in packages:
                    # Use pip to install packages
                    install_result = sandbox.run_code(f"import subprocess; subprocess.run(['pip', 'install', '{pkg}'], capture_output=True)")
                    if hasattr(install_result, 'error') and install_result.error:
                        logger.warning(f"[CodeExecute] Package install warning for {pkg}: {install_result.error}")
            
            # Execute the code
            logger.info("[CodeExecute] Executing code in sandbox...")
            result = sandbox.run_code(code)
            
            # Collect outputs - E2B SDK structure:
            # result.logs is a Logs object with:
            #   - stdout: List[str] - list of strings printed to stdout
            #   - stderr: List[str] - list of strings printed to stderr
            if hasattr(result, 'logs') and result.logs:
                logs = result.logs
                stdout_parts = []
                
                # Get stdout (list of strings)
                if hasattr(logs, 'stdout') and logs.stdout:
                    for line in logs.stdout:
                        stdout_parts.append(str(line))
                
                # Also get stderr if present
                if hasattr(logs, 'stderr') and logs.stderr:
                    for line in logs.stderr:
                        stdout_parts.append(f"[stderr] {line}")
                
                stdout_output = "\n".join(stdout_parts) if stdout_parts else ""
            
            # Handle text property (returns text representation of main result)
            if hasattr(result, 'text') and result.text:
                if stdout_output:
                    stdout_output += "\n\n[Result]\n" + str(result.text)
                else:
                    stdout_output = "[Result]\n" + str(result.text)
            
            # Check for results list (display outputs, plots, etc.)
            # result.results is List[Result] where each Result can have multiple formats
            if hasattr(result, 'results') and result.results:
                result_parts = []
                for r in result.results:
                    try:
                        # Check for chart/image outputs (PNG or SVG)
                        if hasattr(r, 'png') and r.png:
                            charts.append({"type": "png", "data": r.png})
                            logger.info("[CodeExecute] Captured PNG chart from execution")
                        elif hasattr(r, 'svg') and r.svg:
                            charts.append({"type": "svg", "data": r.svg})
                            logger.info("[CodeExecute] Captured SVG chart from execution")
                        # Also capture text results
                        elif hasattr(r, 'text') and r.text:
                            result_parts.append(str(r.text))
                        elif hasattr(r, 'formats') and callable(r.formats):
                            formats = r.formats()
                            if formats:
                                result_parts.append(str(formats))
                        else:
                            result_parts.append(str(r))
                    except Exception:
                        result_parts.append(repr(r))
                if result_parts and not (hasattr(result, 'text') and result.text):
                    # Only add if we haven't already added from result.text
                    if stdout_output:
                        stdout_output += "\n\n[Results]\n" + "\n".join(result_parts)
                    else:
                        stdout_output = "[Results]\n" + "\n".join(result_parts)
            
            if charts:
                logger.info(f"[CodeExecute] Captured {len(charts)} chart(s) from execution")
            
            # Check for errors
            if hasattr(result, 'error') and result.error:
                error_output = str(result.error)
            
            # Generate download URLs for output files (must be done before sandbox.kill())
            if output_files:
                logger.info(f"[CodeExecute] Generating download URLs for {len(output_files)} output file(s)...")
                downloads = self._generate_download_urls(sandbox, output_files)
                logger.info(f"[CodeExecute] Generated {len(downloads)} download URL(s)")
        
        finally:
            # Clean up sandbox
            try:
                sandbox.kill()
            except Exception:
                pass  # Ignore cleanup errors
        
        return stdout_output, error_output, charts, downloads
    
    def _run_tool(
        self,
        code: str = "",
        task: str = "",
        context: str = "",
        packages: List[str] = None,
        input_files: List[str] = None,
        output_files: List[str] = None,
        **kwargs: Any,
    ) -> str:
        """Execute code and return results with analysis."""
        
        packages = packages or []
        input_files = input_files or []
        output_files = output_files or []
        
        # Log attached files available (injected via set_attached_files)
        if self._attached_files:
            logger.info(f"[CodeExecute] {len(self._attached_files)} attached files available for input")
        
        # Validate input
        if not code and not task:
            return "Error: Please provide either 'code' to execute or a 'task' description."
        
        # Generate code if task provided
        if task and not code:
            try:
                code = self._generate_code(task, context)
                logger.info(f"[CodeExecute] Generated code:\n{code[:500]}...")
            except Exception as e:
                logger.error(f"[CodeExecute] Code generation failed: {e}")
                return f"Error generating code: {str(e)}"
        
        # If context is provided but code was given directly, inject context
        if context and not task:
            # Prepend context as a variable
            context_code = f'# Context data\n_context = """{context}"""\n\n'
            code = context_code + code
        
        # Execute in sandbox
        max_attempts = 2
        attempt = 0
        final_output = ""
        final_error = ""
        final_charts: List[Dict[str, str]] = []
        final_downloads: List[Dict[str, str]] = []
        executed_code = code
        
        while attempt < max_attempts:
            attempt += 1
            logger.info(f"[CodeExecute] Execution attempt {attempt}/{max_attempts}")
            
            try:
                output, error, charts, downloads = self._execute_in_sandbox(
                    executed_code,
                    packages if attempt == 1 else [],
                    input_files if attempt == 1 else [],  # Only upload files on first attempt
                    output_files,
                )
                final_output = output
                final_error = error
                final_charts = charts
                final_downloads = downloads
                
                if not error:
                    # Success!
                    logger.info("[CodeExecute] Code executed successfully")
                    break
                else:
                    # Error occurred - try to fix on first attempt
                    if attempt < max_attempts:
                        logger.info("[CodeExecute] Attempting to fix code...")
                        executed_code = self._fix_code(executed_code, error)
                    
            except Exception as e:
                logger.error(f"[CodeExecute] Sandbox execution failed: {e}")
                final_error = str(e)
                break
        
        # Build response
        output_parts = []
        
        # Show the code that was executed
        output_parts.append("## Code Executed")
        output_parts.append(f"```python\n{executed_code}\n```")
        output_parts.append("")
        
        # Show raw output
        if final_output:
            output_parts.append("## Output")
            output_parts.append(f"```\n{final_output}\n```")
            output_parts.append("")
        
        # Show any errors
        if final_error:
            output_parts.append("## Error")
            output_parts.append(f"```\n{final_error}\n```")
            output_parts.append("")
        
        # Add AI analysis
        try:
            analysis = self._analyze_results(executed_code, final_output, final_error)
            output_parts.append("## Analysis")
            output_parts.append(analysis)
        except Exception as e:
            logger.error(f"[CodeExecute] Result analysis failed: {e}")
            output_parts.append("## Analysis")
            output_parts.append(f"Unable to generate analysis: {str(e)}")
        
        # Create preview data
        preview_data = {
            "task": task if task else "Direct code execution",
            "success": not final_error,
            "has_output": bool(final_output),
            "has_charts": len(final_charts) > 0,
            "has_downloads": len(final_downloads) > 0,
            "packages": packages,
            "input_files": input_files,
            "output_files": output_files,
        }
        preview_block = self._format_preview_block("code-execution", preview_data)
        
        # Add chart preview blocks for each captured chart
        chart_blocks = []
        for i, chart in enumerate(final_charts):
            chart_data = {
                "type": chart["type"],
                "data": chart["data"],
                "index": i,
                "title": f"Chart {i + 1}" if len(final_charts) > 1 else "Generated Chart",
            }
            chart_block = f"```chart-preview\n{json.dumps(chart_data)}\n```"
            chart_blocks.append(chart_block)
        
        # Add file download blocks for each output file
        download_blocks = []
        for download in final_downloads:
            download_data = {
                "filename": download["filename"],
                "path": download["path"],
                "url": download["url"],
            }
            download_block = f"```file-download\n{json.dumps(download_data)}\n```"
            download_blocks.append(download_block)
        
        if final_downloads:
            output_parts.append("")
            output_parts.append("## Generated Files")
            output_parts.append(f"Created {len(final_downloads)} downloadable file(s):")
            for d in final_downloads:
                output_parts.append(f"- {d['filename']}")
        
        # Combine all parts: preview block, chart blocks, download blocks, then text output
        result_parts = [preview_block]
        if chart_blocks:
            result_parts.extend(chart_blocks)
        if download_blocks:
            result_parts.extend(download_blocks)
        result_parts.append("\n".join(output_parts))
        
        return "\n\n".join(result_parts)

