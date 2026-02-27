"""Cross-platform GUI for the reference verification pipeline.

Uses tkinter (stdlib) so no extra dependencies are required.
Launch via: ref-verifier gui
"""

import logging
import queue
import threading
import tkinter as tk
import webbrowser
from collections import Counter
from tkinter import filedialog, messagebox, ttk
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Runs pipeline stages in background threads, posting updates to a queue."""

    def __init__(self, msg_queue: queue.Queue):
        self.queue = msg_queue
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def run_extract(self, pdf_path: str, style: str | None):
        self._thread = threading.Thread(
            target=self._do_extract, args=(pdf_path, style), daemon=True
        )
        self._thread.start()

    def run_verify(self, extraction, use_google_scholar: bool):
        self._thread = threading.Thread(
            target=self._do_verify, args=(extraction, use_google_scholar), daemon=True
        )
        self._thread.start()

    def run_audit(self, pdf_path: str, verification, model: str):
        self._thread = threading.Thread(
            target=self._do_audit, args=(pdf_path, verification, model), daemon=True
        )
        self._thread.start()

    def _do_extract(self, pdf_path, style):
        self.queue.put(("stage_start", "extract"))
        try:
            from .reference_extractor import extract_from_pdf

            result = extract_from_pdf(pdf_path, style=style if style != "auto" else None)
            self.queue.put(("extract_done", result))
        except Exception as e:
            logger.exception("Extraction failed")
            self.queue.put(("error", f"Extraction failed: {e}"))

    def _do_verify(self, extraction, use_google_scholar):
        self.queue.put(("stage_start", "verify"))
        try:
            from .models import VerificationResult
            from .verifier import verify_single_reference

            verified = []
            total = len(extraction.references)
            for i, ref in enumerate(extraction.references):
                self.queue.put(("verify_progress", i + 1, total))
                result = verify_single_reference(ref, use_google_scholar=use_google_scholar)
                verified.append(result)

            status_counts = Counter(v.status.value for v in verified)
            stats = {
                "total": len(verified),
                "verified": status_counts.get("verified", 0),
                "ambiguous": status_counts.get("ambiguous", 0),
                "not_found": status_counts.get("not_found", 0),
            }
            result = VerificationResult(references=verified, stats=stats)
            self.queue.put(("verify_done", result))
        except Exception as e:
            logger.exception("Verification failed")
            self.queue.put(("error", f"Verification failed: {e}"))

    def _do_audit(self, pdf_path, verification, model):
        self.queue.put(("stage_start", "audit"))
        try:
            from .auditor import audit_manuscript
            from .ollama_client import OllamaClient
            from .pdf_parser import parse_pdf

            client = OllamaClient(model=model)
            parsed = parse_pdf(pdf_path)
            report = audit_manuscript(parsed.body_text, verification, client)
            self.queue.put(("audit_done", report))
        except Exception as e:
            logger.exception("Audit failed")
            self.queue.put(("error", f"Audit failed: {e}"))


class RefVerifierGUI:
    """Main application window."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ref-verifier")
        self.root.geometry("1100x750")
        self.root.minsize(800, 500)

        # State
        self.extraction_result = None
        self.verification_result = None
        self.audit_report = None
        self.pdf_path: str | None = None
        self.ollama_connected = False
        self.pipeline_mode = False  # True when running full pipeline

        # Queue and runner
        self.msg_queue: queue.Queue = queue.Queue()
        self.runner = PipelineRunner(self.msg_queue)

        # Build UI
        self._build_config_frame()
        self._build_notebook()
        self._build_status_frame()

        # Start polling and Ollama detection
        self._poll_queue()
        self._refresh_ollama()

    # ── Config bar ──────────────────────────────────────────────

    def _build_config_frame(self):
        frame = ttk.LabelFrame(self.root, text="Settings", padding=8)
        frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        # Row 1: PDF path
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="PDF:").pack(side=tk.LEFT)
        self.pdf_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.pdf_var, width=60).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4)
        )
        ttk.Button(row1, text="Browse", command=self._browse_pdf).pack(side=tk.LEFT)

        # Row 2: Style, Google Scholar, Ollama
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=2)

        ttk.Label(row2, text="Style:").pack(side=tk.LEFT)
        self.style_var = tk.StringVar(value="auto")
        style_combo = ttk.Combobox(
            row2, textvariable=self.style_var, state="readonly", width=12,
            values=["auto", "apa", "ieee", "vancouver", "harvard", "chicago"],
        )
        style_combo.pack(side=tk.LEFT, padx=(4, 12))

        self.gs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Google Scholar", variable=self.gs_var).pack(
            side=tk.LEFT, padx=(0, 12)
        )

        ttk.Label(row2, text="Ollama Model:").pack(side=tk.LEFT)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(
            row2, textvariable=self.model_var, state="readonly", width=20
        )
        self.model_combo.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Button(row2, text="Refresh", command=self._refresh_ollama).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self.ollama_label = ttk.Label(row2, text="Checking...")
        self.ollama_label.pack(side=tk.LEFT)

        # Row 3: Action buttons
        row3 = ttk.Frame(frame)
        row3.pack(fill=tk.X, pady=(4, 0))

        self.btn_pipeline = ttk.Button(
            row3, text="Run Full Pipeline", command=self._run_pipeline
        )
        self.btn_pipeline.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_extract = ttk.Button(
            row3, text="Extract Only", command=self._run_extract
        )
        self.btn_extract.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_verify = ttk.Button(
            row3, text="Verify Only", command=self._run_verify
        )
        self.btn_verify.pack(side=tk.LEFT)

    # ── Notebook with 3 tabs ────────────────────────────────────

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Tab 1: Extraction
        ext_frame = ttk.Frame(self.notebook)
        self.notebook.add(ext_frame, text="Extraction")
        self._build_extraction_tab(ext_frame)

        # Tab 2: Verification
        ver_frame = ttk.Frame(self.notebook)
        self.notebook.add(ver_frame, text="Verification")
        self._build_verification_tab(ver_frame)

        # Tab 3: Audit
        aud_frame = ttk.Frame(self.notebook)
        self.notebook.add(aud_frame, text="Audit")
        self._build_audit_tab(aud_frame)

    def _build_extraction_tab(self, parent):
        pane = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True)

        # Table
        cols = ("id", "authors", "title", "year", "journal", "doi")
        self.ext_tree = ttk.Treeview(pane, columns=cols, show="headings", height=10)
        self.ext_tree.heading("id", text="ID")
        self.ext_tree.heading("authors", text="Authors")
        self.ext_tree.heading("title", text="Title")
        self.ext_tree.heading("year", text="Year")
        self.ext_tree.heading("journal", text="Journal")
        self.ext_tree.heading("doi", text="DOI")
        self.ext_tree.column("id", width=60, stretch=False)
        self.ext_tree.column("authors", width=180)
        self.ext_tree.column("title", width=320)
        self.ext_tree.column("year", width=50, stretch=False)
        self.ext_tree.column("journal", width=150)
        self.ext_tree.column("doi", width=120)

        # Scrollbar
        tree_frame = ttk.Frame(pane)
        self.ext_tree.pack(in_=tree_frame, side=tk.LEFT, fill=tk.BOTH, expand=True)
        ext_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.ext_tree.yview)
        ext_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.ext_tree.configure(yscrollcommand=ext_scroll.set)
        pane.add(tree_frame, weight=3)

        # Detail
        detail_frame = ttk.LabelFrame(pane, text="Raw Reference Text")
        self.ext_detail = tk.Text(detail_frame, wrap=tk.WORD, height=5, state=tk.DISABLED)
        self.ext_detail.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        pane.add(detail_frame, weight=1)

        self.ext_tree.bind("<<TreeviewSelect>>", self._on_extraction_select)

    def _build_verification_tab(self, parent):
        pane = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True)

        # Table
        cols = ("ref_id", "status", "confidence", "source", "title", "year", "doi")
        self.ver_tree = ttk.Treeview(pane, columns=cols, show="headings", height=10)
        self.ver_tree.heading("ref_id", text="Ref ID")
        self.ver_tree.heading("status", text="Status")
        self.ver_tree.heading("confidence", text="Conf.")
        self.ver_tree.heading("source", text="Source")
        self.ver_tree.heading("title", text="Canonical Title")
        self.ver_tree.heading("year", text="Year")
        self.ver_tree.heading("doi", text="DOI")
        self.ver_tree.column("ref_id", width=60, stretch=False)
        self.ver_tree.column("status", width=80, stretch=False)
        self.ver_tree.column("confidence", width=55, stretch=False)
        self.ver_tree.column("source", width=110, stretch=False)
        self.ver_tree.column("title", width=320)
        self.ver_tree.column("year", width=50, stretch=False)
        self.ver_tree.column("doi", width=140)

        self.ver_tree.tag_configure("verified", background="#d4edda")
        self.ver_tree.tag_configure("ambiguous", background="#fff3cd")
        self.ver_tree.tag_configure("not_found", background="#f8d7da")

        tree_frame = ttk.Frame(pane)
        self.ver_tree.pack(in_=tree_frame, side=tk.LEFT, fill=tk.BOTH, expand=True)
        ver_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.ver_tree.yview)
        ver_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.ver_tree.configure(yscrollcommand=ver_scroll.set)
        pane.add(tree_frame, weight=3)

        # Detail with links
        detail_frame = ttk.LabelFrame(pane, text="Verification Details")
        self.ver_detail = tk.Text(detail_frame, wrap=tk.WORD, height=8, state=tk.DISABLED)
        self.ver_detail.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        pane.add(detail_frame, weight=2)

        self.ver_tree.bind("<<TreeviewSelect>>", self._on_verification_select)

    def _build_audit_tab(self, parent):
        pane = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True)

        # Summary at top
        summary_frame = ttk.LabelFrame(pane, text="Audit Summary")
        self.audit_summary = tk.Text(summary_frame, wrap=tk.WORD, height=4, state=tk.DISABLED)
        self.audit_summary.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        pane.add(summary_frame, weight=1)

        # Table
        cols = ("severity", "type", "ref_id", "description")
        self.aud_tree = ttk.Treeview(pane, columns=cols, show="headings", height=8)
        self.aud_tree.heading("severity", text="Severity")
        self.aud_tree.heading("type", text="Type")
        self.aud_tree.heading("ref_id", text="Ref ID")
        self.aud_tree.heading("description", text="Description")
        self.aud_tree.column("severity", width=70, stretch=False)
        self.aud_tree.column("type", width=130, stretch=False)
        self.aud_tree.column("ref_id", width=60, stretch=False)
        self.aud_tree.column("description", width=500)

        self.aud_tree.tag_configure("error", background="#f8d7da")
        self.aud_tree.tag_configure("warning", background="#fff3cd")
        self.aud_tree.tag_configure("info", background="#d1ecf1")

        tree_frame = ttk.Frame(pane)
        self.aud_tree.pack(in_=tree_frame, side=tk.LEFT, fill=tk.BOTH, expand=True)
        aud_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.aud_tree.yview)
        aud_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.aud_tree.configure(yscrollcommand=aud_scroll.set)
        pane.add(tree_frame, weight=2)

        # Detail
        detail_frame = ttk.LabelFrame(pane, text="Issue Details")
        self.aud_detail = tk.Text(detail_frame, wrap=tk.WORD, height=5, state=tk.DISABLED)
        self.aud_detail.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        pane.add(detail_frame, weight=1)

        self.aud_tree.bind("<<TreeviewSelect>>", self._on_audit_select)

    # ── Status / progress bar ───────────────────────────────────

    def _build_status_frame(self):
        frame = ttk.Frame(self.root, padding=(8, 4))
        frame.pack(fill=tk.X)

        self.progress = ttk.Progressbar(frame, orient=tk.HORIZONTAL, length=300)
        self.progress.pack(side=tk.LEFT, padx=(0, 8))

        self.status_label = ttk.Label(frame, text="Ready.")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ── Ollama detection ────────────────────────────────────────

    def _refresh_ollama(self):
        self.ollama_label.configure(text="Checking...")
        threading.Thread(target=self._detect_ollama, daemon=True).start()

    def _detect_ollama(self):
        try:
            import ollama

            client = ollama.Client()
            response = client.list()
            model_names = [m.model for m in response.models]
            self.root.after(0, self._update_ollama, model_names, True)
        except Exception:
            self.root.after(0, self._update_ollama, [], False)

    def _update_ollama(self, models: list[str], connected: bool):
        self.ollama_connected = connected
        if connected and models:
            self.model_combo["values"] = models
            self.model_combo["state"] = "readonly"
            # Select first model if nothing selected
            if not self.model_var.get() or self.model_var.get() not in models:
                self.model_var.set(models[0])
            self.ollama_label.configure(text="Connected", foreground="green")
        elif connected:
            self.model_combo["values"] = []
            self.model_var.set("")
            self.ollama_label.configure(text="Connected (no models)", foreground="orange")
        else:
            self.model_combo["values"] = ["(Ollama offline)"]
            self.model_var.set("(Ollama offline)")
            self.model_combo["state"] = "disabled"
            self.ollama_label.configure(text="Offline", foreground="red")

    # ── File browsing ───────────────────────────────────────────

    def _browse_pdf(self):
        path = filedialog.askopenfilename(
            title="Select PDF manuscript",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self.pdf_var.set(path)

    # ── Pipeline actions ────────────────────────────────────────

    def _validate_pdf(self) -> str | None:
        path = self.pdf_var.get().strip()
        if not path:
            messagebox.showwarning("No PDF", "Please select a PDF file first.")
            return None
        return path

    def _set_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.btn_pipeline.configure(state=state)
        self.btn_extract.configure(state=state)
        self.btn_verify.configure(state=state)

    def _run_extract(self):
        path = self._validate_pdf()
        if not path or self.runner.is_running:
            return
        self.pipeline_mode = False
        self._set_buttons_enabled(False)
        self.runner.run_extract(path, self.style_var.get())

    def _run_verify(self):
        if self.runner.is_running:
            return
        if self.extraction_result is None:
            messagebox.showwarning("No extraction", "Run extraction first.")
            return
        self.pipeline_mode = False
        self._set_buttons_enabled(False)
        self.runner.run_verify(self.extraction_result, self.gs_var.get())

    def _run_pipeline(self):
        path = self._validate_pdf()
        if not path or self.runner.is_running:
            return
        if not self.ollama_connected or not self.model_var.get():
            messagebox.showwarning(
                "Ollama unavailable",
                "Ollama is not connected or no model selected.\n"
                "The full pipeline requires Ollama for the audit stage.",
            )
            return
        self.pipeline_mode = True
        self._set_buttons_enabled(False)
        self.runner.run_extract(path, self.style_var.get())

    # ── Queue polling ───────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle_message(self, msg):
        kind = msg[0]

        if kind == "stage_start":
            stage = msg[1]
            if stage == "extract":
                self.progress.configure(mode="indeterminate")
                self.progress.start(15)
                self.status_label.configure(text="Stage 1: Extracting references...")
            elif stage == "verify":
                self.progress.stop()
                self.progress.configure(mode="determinate", value=0)
                self.status_label.configure(text="Stage 2: Verifying references...")
            elif stage == "audit":
                self.progress.configure(mode="indeterminate")
                self.progress.start(15)
                self.status_label.configure(
                    text="Stage 3: Auditing with LLM (this may take a while)..."
                )

        elif kind == "verify_progress":
            i, total = msg[1], msg[2]
            self.progress.configure(maximum=total, value=i)
            self.status_label.configure(
                text=f"Stage 2: Verifying reference {i}/{total}..."
            )

        elif kind == "extract_done":
            self.progress.stop()
            self.extraction_result = msg[1]
            self._populate_extraction_table(self.extraction_result)
            self.notebook.select(0)
            n = len(self.extraction_result.references)
            self.status_label.configure(
                text=f"Extraction complete: {n} references found "
                f"({self.extraction_result.model_used})"
            )
            if self.pipeline_mode:
                self.runner.run_verify(self.extraction_result, self.gs_var.get())
            else:
                self._set_buttons_enabled(True)

        elif kind == "verify_done":
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.verification_result = msg[1]
            self._populate_verification_table(self.verification_result)
            self.notebook.select(1)
            stats = self.verification_result.stats
            self.status_label.configure(
                text=f"Verification complete: {stats.get('verified', 0)} verified, "
                f"{stats.get('ambiguous', 0)} ambiguous, "
                f"{stats.get('not_found', 0)} not found"
            )
            if self.pipeline_mode:
                self.runner.run_audit(
                    self.pdf_var.get().strip(),
                    self.verification_result,
                    self.model_var.get(),
                )
            else:
                self._set_buttons_enabled(True)

        elif kind == "audit_done":
            self.progress.stop()
            self.audit_report = msg[1]
            self._populate_audit_table(self.audit_report)
            self.notebook.select(2)
            self.status_label.configure(
                text=f"Pipeline complete. {self.audit_report.issues_found} issues found."
            )
            self.pipeline_mode = False
            self._set_buttons_enabled(True)

        elif kind == "error":
            self.progress.stop()
            self.status_label.configure(text=f"Error: {msg[1]}")
            self.pipeline_mode = False
            self._set_buttons_enabled(True)
            messagebox.showerror("Error", msg[1])

    # ── Table population ────────────────────────────────────────

    def _populate_extraction_table(self, result):
        self.ext_tree.delete(*self.ext_tree.get_children())
        for ref in result.references:
            authors = ", ".join(ref.authors) if ref.authors else ""
            self.ext_tree.insert(
                "", tk.END,
                iid=ref.id,
                values=(
                    ref.id,
                    authors[:80],
                    ref.title[:120],
                    ref.year or "",
                    (ref.journal or "")[:60],
                    ref.doi or "",
                ),
            )

    def _populate_verification_table(self, result):
        self.ver_tree.delete(*self.ver_tree.get_children())
        for vref in result.references:
            status = vref.status.value
            self.ver_tree.insert(
                "", tk.END,
                iid=vref.ref_id,
                values=(
                    vref.ref_id,
                    status,
                    f"{vref.confidence:.0%}",
                    vref.source or "",
                    (vref.canonical_title or "")[:120],
                    vref.canonical_year or "",
                    vref.canonical_doi or "",
                ),
                tags=(status,),
            )

    def _populate_audit_table(self, report):
        # Summary
        self.audit_summary.configure(state=tk.NORMAL)
        self.audit_summary.delete("1.0", tk.END)
        self.audit_summary.insert(
            tk.END,
            f"Total references: {report.total_references}  |  "
            f"Verified: {report.verified_count}  |  "
            f"Issues found: {report.issues_found}\n\n"
            f"{report.summary}",
        )
        self.audit_summary.configure(state=tk.DISABLED)

        # Table
        self.aud_tree.delete(*self.aud_tree.get_children())
        for i, issue in enumerate(report.issues):
            sev = issue.severity.value
            self.aud_tree.insert(
                "", tk.END,
                iid=str(i),
                values=(
                    sev.upper(),
                    issue.issue_type,
                    issue.ref_id or "",
                    issue.description[:200],
                ),
                tags=(sev,),
            )

    # ── Row selection handlers ──────────────────────────────────

    def _on_extraction_select(self, _event):
        sel = self.ext_tree.selection()
        if not sel or self.extraction_result is None:
            return
        ref_id = sel[0]
        ref = next((r for r in self.extraction_result.references if r.id == ref_id), None)
        if not ref:
            return
        self.ext_detail.configure(state=tk.NORMAL)
        self.ext_detail.delete("1.0", tk.END)
        self.ext_detail.insert(tk.END, ref.raw_text)
        self.ext_detail.configure(state=tk.DISABLED)

    def _on_verification_select(self, _event):
        sel = self.ver_tree.selection()
        if not sel or self.verification_result is None:
            return
        ref_id = sel[0]
        vref = next(
            (v for v in self.verification_result.references if v.ref_id == ref_id), None
        )
        if not vref:
            return

        self.ver_detail.configure(state=tk.NORMAL)
        self.ver_detail.delete("1.0", tk.END)

        # Basic info
        if vref.canonical_authors:
            self.ver_detail.insert(
                tk.END, f"Authors: {', '.join(vref.canonical_authors)}\n\n"
            )

        if vref.canonical_title:
            self.ver_detail.insert(tk.END, f"Title: {vref.canonical_title}\n\n")

        if vref.notes:
            self.ver_detail.insert(tk.END, f"Notes: {vref.notes}\n\n")

        # Verification links
        self.ver_detail.insert(tk.END, "--- Verification Links ---\n")

        if vref.canonical_doi:
            doi_url = f"https://doi.org/{vref.canonical_doi}"
            self._insert_link(self.ver_detail, f"DOI: {doi_url}", doi_url)

        if vref.canonical_title:
            # Google Scholar search link
            gs_url = (
                f"https://scholar.google.com/scholar?q={quote_plus(vref.canonical_title)}"
            )
            self._insert_link(self.ver_detail, "Search on Google Scholar", gs_url)

            # Semantic Scholar search link
            s2_url = (
                f"https://www.semanticscholar.org/search?q={quote_plus(vref.canonical_title)}"
            )
            self._insert_link(self.ver_detail, "Search on Semantic Scholar", s2_url)

        self.ver_detail.insert(tk.END, "\n")

        # Abstract / TLDR
        if vref.tldr:
            self.ver_detail.insert(tk.END, f"TLDR: {vref.tldr}\n\n")

        if vref.abstract:
            self.ver_detail.insert(tk.END, f"Abstract:\n{vref.abstract}\n")

        self.ver_detail.configure(state=tk.DISABLED)

    def _on_audit_select(self, _event):
        sel = self.aud_tree.selection()
        if not sel or self.audit_report is None:
            return
        idx = int(sel[0])
        if idx >= len(self.audit_report.issues):
            return
        issue = self.audit_report.issues[idx]

        self.aud_detail.configure(state=tk.NORMAL)
        self.aud_detail.delete("1.0", tk.END)
        self.aud_detail.insert(
            tk.END,
            f"Type: {issue.issue_type}\n"
            f"Severity: {issue.severity.value.upper()}\n"
            f"Ref ID: {issue.ref_id or 'N/A'}\n\n"
            f"{issue.description}\n",
        )
        if issue.manuscript_excerpt:
            self.aud_detail.insert(
                tk.END, f"\nManuscript excerpt:\n\"{issue.manuscript_excerpt}\"\n"
            )
        self.aud_detail.configure(state=tk.DISABLED)

    # ── Clickable link helper ───────────────────────────────────

    def _insert_link(self, text_widget: tk.Text, label: str, url: str):
        tag = f"link_{id(url)}_{label[:10]}"
        text_widget.insert(tk.END, label, tag)
        text_widget.insert(tk.END, "\n")
        text_widget.tag_configure(tag, foreground="blue", underline=True)
        text_widget.tag_bind(tag, "<Button-1>", lambda _e, u=url: webbrowser.open(u))
        text_widget.tag_bind(
            tag, "<Enter>", lambda _e: text_widget.configure(cursor="hand2")
        )
        text_widget.tag_bind(
            tag, "<Leave>", lambda _e: text_widget.configure(cursor="")
        )


def launch_gui():
    """Public entry point for the GUI."""
    root = tk.Tk()
    RefVerifierGUI(root)
    root.mainloop()
