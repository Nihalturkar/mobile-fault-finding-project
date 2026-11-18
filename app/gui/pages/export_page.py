"""
Export Page — Export detection reports as professional PDF or plain text.

Supports:
- Selecting a previous report file (adb_log.txt or boot_log.txt)
- Using the last detection result from history
- PDF export with fpdf2 (professional formatting, color-coded status)
- Plain text export
"""

import customtkinter as ctk
import os
from datetime import datetime
from pathlib import Path
from tkinter import filedialog


# Project root (mobile-repair-tool/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def render_export(app):
    """Render the export page."""
    colors = app.colors

    # ── Page Header ──
    ctk.CTkLabel(
        app.content, text="Export Report",
        font=("Segoe UI", 24, "bold"), text_color=colors["text"],
    ).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(
        app.content,
        text="Export detection reports as professional PDF or plain text",
        font=("Segoe UI", 13), text_color=colors["text_dim"],
    ).pack(anchor="w", padx=20, pady=(0, 20))

    # ═══════════════════════════════════════════════════════════
    #  SOURCE SELECTION CARD
    # ═══════════════════════════════════════════════════════════
    source_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    source_card.pack(fill="x", padx=20, pady=(0, 15))
    source_inner = ctk.CTkFrame(source_card, fg_color="transparent")
    source_inner.pack(fill="x", padx=20, pady=20)

    ctk.CTkLabel(
        source_inner, text="Report Source", font=("Segoe UI", 16, "bold"),
        text_color=colors["text"],
    ).pack(anchor="w", pady=(0, 10))

    # Source selection mode
    source_mode = ctk.StringVar(value="auto")
    selected_file_path = ctk.StringVar(value="")

    # ── Option 1: Last detection result ──
    auto_frame = ctk.CTkFrame(source_inner, fg_color="transparent")
    auto_frame.pack(fill="x", pady=(0, 8))

    ctk.CTkRadioButton(
        auto_frame, text="Use last detection result (from history)",
        variable=source_mode, value="auto",
        font=("Segoe UI", 13), text_color=colors["text"],
        fg_color=colors["accent"], hover_color=colors["accent"],
        border_color=colors["border"],
        command=lambda: _on_source_change(),
    ).pack(side="left")

    # ── Option 2: Select report file ──
    file_frame = ctk.CTkFrame(source_inner, fg_color="transparent")
    file_frame.pack(fill="x", pady=(0, 8))

    ctk.CTkRadioButton(
        file_frame, text="Select a report file:",
        variable=source_mode, value="file",
        font=("Segoe UI", 13), text_color=colors["text"],
        fg_color=colors["accent"], hover_color=colors["accent"],
        border_color=colors["border"],
        command=lambda: _on_source_change(),
    ).pack(side="left")

    # Quick-select buttons for known report files
    quick_frame = ctk.CTkFrame(source_inner, fg_color="transparent")
    quick_frame.pack(fill="x", pady=(0, 5), padx=(25, 0))

    adb_log_path = _PROJECT_ROOT / "adb_log.txt"
    boot_log_path = _PROJECT_ROOT / "boot_log.txt"

    def _select_quick(path):
        source_mode.set("file")
        selected_file_path.set(str(path))
        file_path_label.configure(text=str(path))
        _on_source_change()

    ctk.CTkButton(
        quick_frame, text="adb_log.txt",
        width=140, height=32,
        fg_color=colors["info"], hover_color=colors["accent"],
        text_color="#fff", font=("Segoe UI", 12),
        corner_radius=6,
        command=lambda: _select_quick(adb_log_path),
    ).pack(side="left", padx=(0, 8))

    ctk.CTkButton(
        quick_frame, text="boot_log.txt",
        width=140, height=32,
        fg_color=colors["accent"], hover_color=colors["info"],
        text_color="#fff", font=("Segoe UI", 12),
        corner_radius=6,
        command=lambda: _select_quick(boot_log_path),
    ).pack(side="left", padx=(0, 8))

    def _browse_file():
        path = filedialog.askopenfilename(
            title="Select Report File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=str(_PROJECT_ROOT),
        )
        if path:
            source_mode.set("file")
            selected_file_path.set(path)
            file_path_label.configure(text=path)
            _on_source_change()

    ctk.CTkButton(
        quick_frame, text="Browse...",
        width=100, height=32,
        fg_color=colors["bg_light"], hover_color=colors["accent"],
        text_color=colors["text"], font=("Segoe UI", 12),
        corner_radius=6, command=_browse_file,
    ).pack(side="left")

    file_path_label = ctk.CTkLabel(
        source_inner, text="No file selected",
        font=("Segoe UI", 11), text_color=colors["text_dim"],
    )
    file_path_label.pack(anchor="w", padx=(25, 0), pady=(0, 5))

    # ═══════════════════════════════════════════════════════════
    #  DEVICE INFO CARD (editable overrides)
    # ═══════════════════════════════════════════════════════════
    info_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info_card.pack(fill="x", padx=20, pady=(0, 15))
    info_inner = ctk.CTkFrame(info_card, fg_color="transparent")
    info_inner.pack(fill="x", padx=20, pady=15)

    ctk.CTkLabel(
        info_inner, text="Device Information (for PDF header)", font=("Segoe UI", 14, "bold"),
        text_color=colors["text"],
    ).pack(anchor="w", pady=(0, 10))

    fields_row = ctk.CTkFrame(info_inner, fg_color="transparent")
    fields_row.pack(fill="x")

    ctk.CTkLabel(fields_row, text="Device:", font=("Segoe UI", 12),
                 text_color=colors["text"]).pack(side="left")
    device_name_var = ctk.StringVar(value="")
    device_entry = ctk.CTkEntry(
        fields_row, textvariable=device_name_var, width=250, height=34,
        fg_color=colors["bg_light"], border_color=colors["border"],
        font=("Segoe UI", 12), placeholder_text="Auto-detected from report",
    )
    device_entry.pack(side="left", padx=(8, 20))

    ctk.CTkLabel(fields_row, text="Technician:", font=("Segoe UI", 12),
                 text_color=colors["text"]).pack(side="left")
    tech_var = ctk.StringVar(value="")
    ctk.CTkEntry(
        fields_row, textvariable=tech_var, width=200, height=34,
        fg_color=colors["bg_light"], border_color=colors["border"],
        font=("Segoe UI", 12), placeholder_text="Optional",
    ).pack(side="left", padx=(8, 0))

    # ═══════════════════════════════════════════════════════════
    #  EXPORT BUTTONS
    # ═══════════════════════════════════════════════════════════
    export_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    export_card.pack(fill="x", padx=20, pady=(0, 15))
    export_inner = ctk.CTkFrame(export_card, fg_color="transparent")
    export_inner.pack(fill="x", padx=20, pady=15)

    ctk.CTkLabel(
        export_inner, text="Export Format", font=("Segoe UI", 14, "bold"),
        text_color=colors["text"],
    ).pack(anchor="w", pady=(0, 10))

    btn_row = ctk.CTkFrame(export_inner, fg_color="transparent")
    btn_row.pack(fill="x")

    ctk.CTkButton(
        btn_row, text="Export PDF", width=180, height=46,
        fg_color=colors["accent"], hover_color="#c084fc",
        font=("Segoe UI", 15, "bold"), corner_radius=10,
        command=lambda: _do_export("pdf"),
    ).pack(side="left", padx=(0, 15))

    ctk.CTkButton(
        btn_row, text="Export TXT", width=180, height=46,
        fg_color=colors["info"], hover_color=colors["accent"],
        font=("Segoe UI", 15, "bold"), corner_radius=10,
        command=lambda: _do_export("txt"),
    ).pack(side="left")

    # Status message
    status_msg = ctk.CTkLabel(
        export_inner, text="", font=("Segoe UI", 12),
        text_color=colors["success"],
    )
    status_msg.pack(anchor="w", pady=(10, 0))

    # ═══════════════════════════════════════════════════════════
    #  PREVIEW CARD
    # ═══════════════════════════════════════════════════════════
    preview_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    preview_card.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    ctk.CTkLabel(
        preview_card, text="Report Preview",
        font=("Segoe UI", 16, "bold"), text_color=colors["text"],
    ).pack(anchor="w", padx=20, pady=(15, 5))

    preview_text = ctk.CTkTextbox(
        preview_card, font=("Consolas", 11), fg_color=colors["bg_dark"],
        text_color=colors["success"], height=350,
        border_color=colors["border"], border_width=1, wrap="none",
    )
    preview_text.pack(fill="both", expand=True, padx=20, pady=(0, 15))

    # ═══════════════════════════════════════════════════════════
    #  INTERNAL LOGIC
    # ═══════════════════════════════════════════════════════════

    def _get_report_content():
        """Get the report text from the selected source."""
        mode = source_mode.get()

        if mode == "file":
            fpath = selected_file_path.get()
            if fpath and os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        return f.read(), os.path.basename(fpath)
                except Exception as e:
                    return f"Error reading file: {e}", ""
            return "", ""

        # Auto: use last detection from history
        try:
            from app.gui.history_manager import get_history
            history = get_history()
            if history:
                last = history[0]  # newest first
                report_file = last.get("report_file", "")
                device_name_var.set(last.get("device_name", ""))
                if report_file and os.path.exists(report_file):
                    with open(report_file, "r", encoding="utf-8", errors="replace") as f:
                        return f.read(), os.path.basename(report_file)
                # No file but have summary
                return last.get("summary", "No report content available"), ""
        except Exception:
            pass

        return "No detection results available. Run a UART or ADB scan first.", ""

    def _extract_info_from_report(report_text):
        """Try to extract device info, faults, etc. from report text."""
        info = {
            "device": device_name_var.get().strip() or "Unknown Device",
            "detection_type": "Unknown",
            "chipset": "",
            "faults": [],
            "healthy": [],
            "summary_lines": [],
            "sections": {},
        }

        lines = report_text.split("\n")
        current_section = ""

        for line in lines:
            stripped = line.strip()

            # Detect type
            if "HARDWARE DETECTION" in stripped or "UART" in stripped.upper():
                info["detection_type"] = "UART (Hardware)"
            elif "ADB DETECTION" in stripped or "ADB" in stripped.upper():
                if info["detection_type"] == "Unknown":
                    info["detection_type"] = "ADB (Software)"
            elif "UART BOOT LOG ANALYSIS" in stripped.upper():
                info["detection_type"] = "UART (Boot Log)"

            # Chipset
            if "CHIPSET DETECTED:" in stripped:
                info["chipset"] = stripped.split("CHIPSET DETECTED:")[-1].strip()
            elif "Chipset:" in stripped and not info["chipset"]:
                info["chipset"] = stripped.split("Chipset:")[-1].strip().split("|")[0].strip()
                # Also extract from summary format "Chipset: MediaTek (MediaTek SoC)"
                chip = info["chipset"].split("(")[0].strip()
                if chip:
                    info["chipset"] = chip

            # Device name from report
            if "Brand:" in stripped and not device_name_var.get().strip():
                brand = stripped.split("Brand:")[-1].strip().split("|")[0].strip()
                if brand:
                    info["device"] = brand

            # Faults — match both old format and UART report format
            if "Problem:" in stripped:
                problem = stripped.split("Problem:")[-1].strip()
                if problem:
                    info["faults"].append(problem)
            # Match "🟡 WARNING: [LOG] Boot Log Error = ..."
            elif ("WARNING:" in stripped or "CRITICAL:" in stripped) and "Boot Log Error" in stripped:
                error_text = stripped.split("=", 1)[-1].strip() if "=" in stripped else stripped
                if error_text:
                    info["faults"].append(error_text)
            # Match "🔴 CRITICAL: ..." or "🟡 WARNING: ..." severity lines from fault reports
            elif stripped.startswith(("🔴 CRITICAL:", "🟡 WARNING:", "🟠 HIGH:")):
                fault_text = stripped.split(":", 1)[-1].strip() if ":" in stripped else stripped
                if fault_text and "fault" not in fault_text.lower():
                    info["faults"].append(fault_text)
            # Match "[LOG]" format errors
            elif "[LOG]" in stripped and ("Error" in stripped or "fail" in stripped.lower()):
                error_text = stripped.split("=", 1)[-1].strip() if "=" in stripped else stripped
                if error_text:
                    info["faults"].append(error_text)
            # Match UART analysis page fault format
            elif "CRITICAL" in stripped or "WARNING" in stripped:
                if "fault" in stripped.lower() or "problem" in stripped.lower():
                    info["faults"].append(stripped)

            # Healthy components — match multiple formats
            if "HEALTHY" in stripped.upper():
                current_section = "healthy"
            elif "Hardware Health Check" in stripped:
                current_section = "hw_health"
            elif current_section == "healthy" and stripped.startswith(("*", "-", ">", "✓", "✅")):
                comp = stripped.lstrip("*->✓✅ ").strip()
                if comp:
                    info["healthy"].append(comp)
            elif current_section == "hw_health":
                # Match "✅ RAM / Memory: OK (init found in boot log)"
                if stripped.startswith("✅"):
                    comp = stripped.lstrip("✅ ").strip()
                    if comp:
                        info["healthy"].append(comp)
                elif stripped.startswith(("═══", "──", "==", "🚨")):
                    current_section = ""

            # Section detection
            if "PHASE" in stripped or "===" in stripped:
                current_section = stripped
                info["sections"][current_section] = []
            elif current_section and current_section in info["sections"]:
                info["sections"][current_section].append(line)

        # Deduplicate faults
        seen = set()
        unique_faults = []
        for f in info["faults"]:
            # Normalize for dedup (some errors repeat)
            key = f[:60].strip()
            if key not in seen:
                seen.add(key)
                unique_faults.append(f)
        info["faults"] = unique_faults

        return info

    def _on_source_change():
        """Update preview when source changes."""
        content, filename = _get_report_content()
        preview_text.configure(state="normal")
        preview_text.delete("1.0", "end")
        if content:
            preview_text.insert("1.0", content)
        else:
            preview_text.insert("1.0", "No report content to preview.")

    def _do_export(fmt):
        """Export the report in the chosen format."""
        content, filename = _get_report_content()
        if not content or content.startswith("No detection") or content.startswith("Error"):
            status_msg.configure(
                text="No report content to export. Select a source first.",
                text_color=colors["accent"],
            )
            return

        info = _extract_info_from_report(content)
        device = device_name_var.get().strip() or info["device"]
        safe_name = device.replace(" ", "_").replace("/", "-").replace("(", "").replace(")", "")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if fmt == "pdf":
            file_path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
                initialfile=f"Report_{safe_name}_{timestamp}.pdf",
            )
            if not file_path:
                return
            try:
                _export_pdf(content, info, device, file_path)
                status_msg.configure(
                    text=f"PDF exported: {file_path}",
                    text_color=colors["success"],
                )
                app.update_status(f"PDF exported: {file_path}")
            except ImportError:
                status_msg.configure(
                    text="fpdf2 not installed. Run: pip install fpdf2",
                    text_color=colors["warning"],
                )
            except Exception as e:
                status_msg.configure(
                    text=f"PDF export error: {e}",
                    text_color=colors["accent"],
                )

        elif fmt == "txt":
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                initialfile=f"Report_{safe_name}_{timestamp}.txt",
            )
            if not file_path:
                return
            try:
                _export_txt(content, info, device, file_path)
                status_msg.configure(
                    text=f"Text report exported: {file_path}",
                    text_color=colors["success"],
                )
                app.update_status(f"Text exported: {file_path}")
            except Exception as e:
                status_msg.configure(
                    text=f"Export error: {e}",
                    text_color=colors["accent"],
                )

    def _export_txt(content, info, device, file_path):
        """Export as formatted plain text report."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        technician = tech_var.get().strip() or "N/A"

        header = [
            "=" * 70,
            "  MOOXY AI FAULT DETECTOR - DIAGNOSTIC REPORT",
            "=" * 70,
            f"  Date:       {now}",
            f"  Device:     {device}",
            f"  Chipset:    {info.get('chipset', 'N/A')}",
            f"  Type:       {info.get('detection_type', 'N/A')}",
            f"  Technician: {technician}",
            "=" * 70,
            "",
        ]

        faults = info.get("faults", [])
        if faults:
            header.append(f"  DIAGNOSIS: {len(faults)} FAULT(S) DETECTED")
            header.append(f"  {'-' * 40}")
            for i, fault in enumerate(faults, 1):
                header.append(f"    {i}. {fault}")
            header.append("")
        else:
            header.append("  DIAGNOSIS: NO FAULTS DETECTED")
            header.append("")

        header.append("=" * 70)
        header.append("  FULL DETECTION LOG")
        header.append("=" * 70)
        header.append("")

        footer = [
            "",
            "=" * 70,
            "  Generated by Mooxy AI Fault Detector v1.0",
            f"  Export Date: {now}",
            "=" * 70,
        ]

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(header))
            f.write(content)
            f.write("\n")
            f.write("\n".join(footer))

    def _export_pdf(content, info, device, file_path):
        """Export as professional PDF using fpdf2."""
        from fpdf import FPDF

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        technician = tech_var.get().strip() or "N/A"
        faults = info.get("faults", [])
        healthy = info.get("healthy", [])
        chipset = info.get("chipset", "N/A")
        det_type = info.get("detection_type", "N/A")

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        # ── HEADER ──
        # Title bar background
        pdf.set_fill_color(10, 10, 26)  # bg_dark
        pdf.rect(0, 0, 210, 45, "F")

        # Red accent line
        pdf.set_fill_color(233, 69, 96)  # accent
        pdf.rect(0, 45, 210, 3, "F")

        # Title text
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(255, 255, 255)
        pdf.set_y(10)
        pdf.cell(0, 10, "Mooxy AI Fault Detector", ln=True, align="C")

        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(136, 146, 176)  # text_dim
        pdf.cell(0, 7, "Diagnostic Report", ln=True, align="C")

        pdf.ln(10)

        # ── DEVICE INFO TABLE ──
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(233, 69, 96)  # accent
        pdf.cell(0, 10, "Device Information", ln=True)

        pdf.set_draw_color(42, 42, 90)  # border
        pdf.set_fill_color(30, 30, 66)  # bg_card
        pdf.set_text_color(255, 255, 255)

        info_rows = [
            ("Date", now),
            ("Device", device),
            ("Chipset", chipset),
            ("Detection Type", det_type),
            ("Technician", technician),
        ]

        pdf.set_font("Helvetica", "B", 10)
        for label, value in info_rows:
            pdf.set_fill_color(30, 30, 66)
            pdf.cell(50, 8, f"  {label}", border=1, fill=True)
            pdf.set_fill_color(26, 26, 62)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 8, f"  {value}", border=1, ln=True, fill=True)
            pdf.set_font("Helvetica", "B", 10)

        pdf.ln(8)

        # ── DIAGNOSIS SUMMARY ──
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(233, 69, 96)
        pdf.cell(0, 10, "Diagnosis Summary", ln=True)

        if faults:
            # Red status bar for faults
            pdf.set_fill_color(233, 69, 96)  # accent/red
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 10, f"  FAULTS DETECTED: {len(faults)}", ln=True, fill=True)
            pdf.ln(3)

            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            for i, fault in enumerate(faults, 1):
                # Red bullet
                pdf.set_fill_color(233, 69, 96)
                pdf.set_text_color(233, 69, 96)
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(8, 7, str(i) + ".")
                pdf.set_text_color(60, 60, 60)
                pdf.set_font("Helvetica", "", 10)
                # Handle long fault text with multi_cell
                pdf.multi_cell(0, 7, f" {fault}")
        else:
            # Green status bar
            pdf.set_fill_color(46, 213, 115)  # success
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 10, "  ALL CLEAR - NO FAULTS DETECTED", ln=True, fill=True)

        pdf.ln(5)

        # ── HEALTHY COMPONENTS (if any) ──
        if healthy:
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(46, 213, 115)  # success
            pdf.cell(0, 10, "Healthy Components", ln=True)

            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            for comp in healthy:
                pdf.set_fill_color(46, 213, 115)
                pdf.cell(4, 6, "", fill=True)
                pdf.cell(4, 6, "")
                pdf.cell(0, 6, comp, ln=True)
            pdf.ln(5)

        # ── DETAILED COMPONENT REPORT ──
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(30, 144, 255)  # info
        pdf.cell(0, 10, "Detailed Detection Log", ln=True)

        pdf.set_draw_color(42, 42, 90)
        pdf.set_fill_color(245, 245, 250)
        pdf.rect(10, pdf.get_y(), 190, 1, "F")
        pdf.ln(3)

        # Process report content into sections
        lines = content.split("\n")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(40, 40, 40)

        for line in lines:
            stripped = line.strip()

            # Section headers (=== lines)
            if stripped.startswith("===") or stripped.startswith("---"):
                pdf.set_fill_color(30, 30, 66)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font("Helvetica", "B", 9)
                pdf.cell(0, 6, f"  {stripped[:90]}", ln=True, fill=True)
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(40, 40, 40)
                continue

            # Phase headers
            if "PHASE" in stripped or "DETECTION REPORT" in stripped.upper():
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(233, 69, 96)
                pdf.cell(0, 7, f"  {stripped[:90]}", ln=True)
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(40, 40, 40)
                continue

            # Fault lines (red)
            if "CRITICAL" in stripped or "Problem:" in stripped or "fault" in stripped.lower():
                pdf.set_text_color(233, 69, 96)
                pdf.set_font("Helvetica", "B", 8)
                pdf.multi_cell(0, 5, f"  {stripped[:120]}")
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(40, 40, 40)
                continue

            # Success lines (green)
            if "HEALTHY" in stripped or "No faults" in stripped or ("ok" in stripped.lower() and ":" in stripped):
                pdf.set_text_color(46, 160, 100)
                pdf.multi_cell(0, 5, f"  {stripped[:120]}")
                pdf.set_text_color(40, 40, 40)
                continue

            # Warning lines (orange)
            if "WARNING" in stripped or "warning" in stripped.lower():
                pdf.set_text_color(255, 165, 2)
                pdf.multi_cell(0, 5, f"  {stripped[:120]}")
                pdf.set_text_color(40, 40, 40)
                continue

            # Regular lines
            if stripped:
                # Encode-safe: replace emoji and special chars
                safe_line = stripped.encode("latin-1", "replace").decode("latin-1")
                pdf.multi_cell(0, 5, f"  {safe_line[:120]}")

        # ── FAULT ANALYSIS WITH REPAIR STEPS ──
        # Re-parse for structured fault data
        fault_blocks = _parse_fault_blocks(lines)
        if fault_blocks:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            pdf.set_text_color(233, 69, 96)
            pdf.cell(0, 12, "Fault Analysis & Repair Guide", ln=True, align="C")
            pdf.ln(5)

            for i, block in enumerate(fault_blocks, 1):
                # Fault card header
                pdf.set_fill_color(233, 69, 96)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 9, f"  Fault #{i}: {block.get('component', 'Unknown')}", ln=True, fill=True)

                pdf.set_text_color(60, 60, 60)
                pdf.set_font("Helvetica", "", 9)

                if block.get("problem"):
                    pdf.cell(30, 7, "  Problem:")
                    pdf.set_font("Helvetica", "B", 9)
                    pdf.cell(0, 7, block["problem"], ln=True)
                    pdf.set_font("Helvetica", "", 9)

                if block.get("evidence"):
                    pdf.cell(30, 7, "  Evidence:")
                    pdf.cell(0, 7, block["evidence"], ln=True)

                if block.get("severity"):
                    sev = block["severity"]
                    if "critical" in sev.lower():
                        pdf.set_text_color(233, 69, 96)
                    else:
                        pdf.set_text_color(255, 165, 2)
                    pdf.set_font("Helvetica", "B", 9)
                    pdf.cell(30, 7, "  Severity:")
                    pdf.cell(0, 7, sev, ln=True)
                    pdf.set_text_color(60, 60, 60)
                    pdf.set_font("Helvetica", "", 9)

                # Causes
                if block.get("causes"):
                    pdf.set_font("Helvetica", "B", 9)
                    pdf.cell(0, 7, "  Possible Causes:", ln=True)
                    pdf.set_font("Helvetica", "", 9)
                    for cause in block["causes"]:
                        pdf.cell(10, 6, "")
                        pdf.cell(0, 6, f"- {cause}", ln=True)

                # Repair steps
                if block.get("repair_steps"):
                    pdf.set_font("Helvetica", "B", 9)
                    pdf.set_text_color(30, 144, 255)
                    pdf.cell(0, 7, "  Repair Steps:", ln=True)
                    pdf.set_text_color(60, 60, 60)
                    pdf.set_font("Helvetica", "", 9)
                    for step in block["repair_steps"]:
                        pdf.cell(10, 6, "")
                        pdf.multi_cell(0, 6, step)

                # Parts needed
                if block.get("parts"):
                    pdf.set_font("Helvetica", "I", 9)
                    pdf.cell(0, 7, f"  Parts needed: {block['parts']}", ln=True)
                    pdf.set_font("Helvetica", "", 9)

                # Difficulty
                if block.get("difficulty"):
                    pdf.cell(0, 7, f"  Difficulty: {block['difficulty']}", ln=True)

                pdf.ln(5)

        # ── FOOTER ──
        pdf.ln(10)
        pdf.set_fill_color(10, 10, 26)
        pdf.rect(10, pdf.get_y(), 190, 1, "F")
        pdf.ln(5)

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(233, 69, 96)
        pdf.cell(0, 7, "Mooxy AI Fault Detector v1.0", ln=True, align="C")

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(136, 146, 176)
        pdf.cell(0, 6, f"Report generated: {now}", ln=True, align="C")
        pdf.cell(0, 6, "Professional Mobile Diagnostics & Repair", ln=True, align="C")

        pdf.output(file_path)

    def _parse_fault_blocks(lines):
        """Parse fault blocks from report text for structured PDF output."""
        blocks = []
        current = None

        for line in lines:
            stripped = line.strip()

            # Match "─── Problem #1 ───" format (hw_detect.py)
            if "Problem #" in stripped:
                if current:
                    blocks.append(current)
                current = {"causes": [], "repair_steps": []}
                continue

            # Match "Problem:" field
            if "Problem:" in stripped:
                if current is None:
                    current = {"causes": [], "repair_steps": []}
                current["problem"] = stripped.split("Problem:")[-1].strip()
                continue

            # Match UART analysis page fault format:
            # "🔴 CRITICAL: PMIC initialization failure detected"
            if current is None and stripped.startswith(("🔴 CRITICAL:", "🟡 WARNING:", "🟠 HIGH:")):
                if "Boot Log Error" not in stripped:
                    current = {"causes": [], "repair_steps": []}
                    current["severity"] = stripped.split(":")[0].strip()
                    current["problem"] = stripped.split(":", 1)[-1].strip()
                    continue

            # Match UART analysis page component format:
            # "     Component: PMIC (Power Management IC)"
            if current is None and "Component:" in stripped:
                current = {"causes": [], "repair_steps": []}
                current["component"] = stripped.split("Component:")[-1].strip()
                continue

            if current is None:
                continue

            if "Component:" in stripped:
                current["component"] = stripped.split("Component:")[-1].strip()
            elif "Evidence:" in stripped:
                current["evidence"] = stripped.split("Evidence:")[-1].strip()
            elif "CRITICAL" in stripped or "WARNING" in stripped:
                if "severity" not in current:
                    current["severity"] = stripped
            elif "Causes:" in stripped or "🔍 Causes:" in stripped:
                current["_section"] = "causes"
            elif "Check:" in stripped or "🔧 Check:" in stripped:
                current["_section"] = "check"
            elif "Fix:" in stripped or "🛠️ Fix:" in stripped:
                current["_section"] = "repair"
            elif "Repair:" in stripped:
                current["_section"] = "repair"
                # Also capture inline repair text
                repair_text = stripped.split("Repair:")[-1].strip()
                if repair_text:
                    current["repair_steps"].append(repair_text)
            elif "Parts:" in stripped or "📦 Parts:" in stripped:
                current["parts"] = stripped.split("Parts:")[-1].strip().lstrip("📦 ")
            elif "Difficulty:" in stripped:
                current["difficulty"] = stripped.split("Difficulty:")[-1].strip()
            elif stripped.startswith(("*", "-", ">", "•")):
                text = stripped.lstrip("*->•").strip()
                sec = current.get("_section", "")
                if sec == "causes":
                    current["causes"].append(text)
                elif sec in ("repair", "check"):
                    current["repair_steps"].append(text)
            elif stripped and stripped[0].isdigit() and "." in stripped[:4]:
                current.setdefault("repair_steps", []).append(stripped)
            elif "Related ICs:" in stripped:
                current["parts"] = stripped.split("Related ICs:")[-1].strip()

        if current:
            blocks.append(current)

        return blocks

    # ── Initial preview load ──
    _on_source_change()
    app.update_status("Export — Select source and export as PDF or TXT")
