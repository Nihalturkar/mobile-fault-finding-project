"""
Smart Diagnostics Page — Cross-Fault Correlation + Baseline Comparison + Predictive Scoring.

Combines three advanced features into one powerful diagnostics page:
  Tab 1: Cross-Fault Correlation — find root causes from multiple faults
  Tab 2: Baseline Comparison — compare device against known-good reference
  Tab 3: Predictive Health — score components and predict failures
"""

import customtkinter as ctk
import threading
import json
from pathlib import Path


def render_smart_diagnostics(app):
    """Render the Smart Diagnostics page."""
    colors = app.colors
    content = app.content

    # Title
    ctk.CTkLabel(content, text="🧠 Smart Diagnostics",
                 font=("Segoe UI", 24, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(content, text="Cross-fault correlation • Baseline comparison • Predictive failure scoring",
                 font=("Segoe UI", 13),
                 text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # Tab frame
    tab_bar = ctk.CTkFrame(content, fg_color=colors["bg_medium"], corner_radius=10, height=45)
    tab_bar.pack(fill="x", padx=20, pady=(0, 10))

    # Content frame for tabs
    tab_content = ctk.CTkFrame(content, fg_color="transparent")
    tab_content.pack(fill="both", expand=True, padx=0, pady=0)

    tabs = {}
    tab_buttons = {}

    def show_tab(name):
        for n, frame in tabs.items():
            frame.pack_forget()
        for n, btn in tab_buttons.items():
            if n == name:
                btn.configure(fg_color=colors["accent"], text_color=colors["text"])
            else:
                btn.configure(fg_color="transparent", text_color=colors["text_dim"])
        tabs[name].pack(fill="both", expand=True)

    tab_names = [
        ("🔗 Cross-Fault Correlation", "correlation"),
        ("📊 Baseline Comparison", "baseline"),
        ("📈 Predictive Health", "predictive"),
    ]

    for label, key in tab_names:
        btn = ctk.CTkButton(tab_bar, text=label, font=("Segoe UI", 13, "bold"),
                            fg_color="transparent", text_color=colors["text_dim"],
                            hover_color=colors["bg_light"], corner_radius=8, height=35,
                            command=lambda k=key: show_tab(k))
        btn.pack(side="left", padx=4, pady=5)
        tab_buttons[key] = btn

        frame = ctk.CTkFrame(tab_content, fg_color="transparent")
        tabs[key] = frame

    # Build tab content
    _build_correlation_tab(tabs["correlation"], app, colors)
    _build_baseline_tab(tabs["baseline"], app, colors)
    _build_predictive_tab(tabs["predictive"], app, colors)

    # Show first tab
    show_tab("correlation")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: CROSS-FAULT CORRELATION
# ═══════════════════════════════════════════════════════════════════════════

def _build_correlation_tab(parent, app, colors):
    """Build the cross-fault correlation analysis tab."""

    # Description card
    desc_card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=12)
    desc_card.pack(fill="x", padx=20, pady=10)
    ctk.CTkLabel(desc_card, text="🔗 Cross-Fault Correlation Engine",
                 font=("Segoe UI", 16, "bold"),
                 text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 5))
    ctk.CTkLabel(desc_card, text="Chains multiple fault signals to find the REAL root cause.\n"
                 "Example: 'Dead phone + no VBAT + PMIC not responding' → Battery connector or PMIC failure.",
                 font=("Segoe UI", 12), text_color=colors["text_dim"],
                 wraplength=800, justify="left").pack(anchor="w", padx=20, pady=(0, 15))

    # Source selection
    src_card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=12)
    src_card.pack(fill="x", padx=20, pady=5)

    ctk.CTkLabel(src_card, text="Select Fault Source:",
                 font=("Segoe UI", 14, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(15, 10))

    src_frame = ctk.CTkFrame(src_card, fg_color="transparent")
    src_frame.pack(fill="x", padx=20, pady=(0, 15))

    source_var = ctk.StringVar(value="history")

    ctk.CTkRadioButton(src_frame, text="From Detection History",
                       variable=source_var, value="history",
                       font=("Segoe UI", 12),
                       fg_color=colors["accent"],
                       text_color=colors["text"]).pack(side="left", padx=(0, 20))
    ctk.CTkRadioButton(src_frame, text="Manual Symptoms Entry",
                       variable=source_var, value="manual",
                       font=("Segoe UI", 12),
                       fg_color=colors["accent"],
                       text_color=colors["text"]).pack(side="left", padx=(0, 20))

    # Manual symptom entry frame
    manual_frame = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=12)
    manual_frame.pack(fill="x", padx=20, pady=5)

    ctk.CTkLabel(manual_frame, text="Describe symptoms (one per line):",
                 font=("Segoe UI", 13),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(15, 5))

    symptom_box = ctk.CTkTextbox(manual_frame, height=120,
                                 fg_color=colors["bg_light"],
                                 font=("Consolas", 12),
                                 text_color=colors["text"])
    symptom_box.pack(fill="x", padx=20, pady=(0, 10))
    symptom_box.insert("1.0", "Phone dead — no boot\nNo VBAT voltage\nPMIC not responding")

    ctk.CTkLabel(manual_frame, text="Chipset family (optional):",
                 font=("Segoe UI", 12),
                 text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(5, 0))
    chipset_entry = ctk.CTkEntry(manual_frame, placeholder_text="e.g. MediaTek, Qualcomm",
                                 fg_color=colors["bg_light"],
                                 font=("Segoe UI", 12), width=300)
    chipset_entry.pack(anchor="w", padx=20, pady=(0, 15))

    # Results area
    results_frame = ctk.CTkFrame(parent, fg_color="transparent")
    results_frame.pack(fill="both", expand=True, padx=0, pady=0)

    report_box = ctk.CTkTextbox(results_frame, fg_color=colors["bg_light"],
                                font=("Consolas", 11),
                                text_color=colors["text"],
                                height=400)

    status_label = ctk.CTkLabel(results_frame, text="",
                                font=("Segoe UI", 12),
                                text_color=colors["text_dim"])

    def run_correlation():
        from app.hardware.correlation_engine import CorrelationEngine, generate_correlation_report
        from app.hardware.fault_analyzer import Fault

        report_box.pack(fill="both", expand=True, padx=20, pady=10)
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        status_label.pack(anchor="w", padx=20)
        status_label.configure(text="🔄 Analyzing fault correlations...", text_color=colors["info"])

        def _analyze():
            engine = CorrelationEngine()
            faults = []
            chipset = chipset_entry.get().strip()

            if source_var.get() == "manual":
                # Parse manual symptoms into Fault objects
                text = symptom_box.get("1.0", "end").strip()
                for line in text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    # Try to extract component from symptom
                    component = _guess_component(line)
                    faults.append(Fault(
                        severity="critical",
                        component=component,
                        problem=line,
                        evidence="Manual entry",
                        confidence=70,
                    ))
            else:
                # Load from detection history
                hist_path = Path(__file__).parent.parent.parent.parent / "config" / "repair_history.json"
                if hist_path.exists():
                    with open(hist_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Get the most recent detection with faults
                    for det in reversed(data.get("detections", [])):
                        if det.get("faults_count", 0) > 0:
                            faults_summary = det.get("faults_summary", "")
                            for line in faults_summary.split(";"):
                                line = line.strip()
                                if line:
                                    component = _guess_component(line)
                                    faults.append(Fault(
                                        severity="warning",
                                        component=component,
                                        problem=line,
                                        evidence="From detection history",
                                    ))
                            break

                if not faults:
                    # No faults in history — use manual symptoms
                    text = symptom_box.get("1.0", "end").strip()
                    for line in text.split("\n"):
                        line = line.strip()
                        if line:
                            component = _guess_component(line)
                            faults.append(Fault(
                                severity="critical",
                                component=component,
                                problem=line,
                                evidence="Manual entry (no faults in history)",
                            ))

            if not faults:
                def _no_faults():
                    report_box.insert("end", "No faults to correlate. Enter symptoms above or run a detection first.")
                    status_label.configure(text="⚠️ No fault data available", text_color=colors["warning"])
                app.content.after(0, _no_faults)
                return

            root_causes = engine.analyze(faults, chipset)
            report_text = generate_correlation_report(root_causes)

            def _show():
                from app.gui.ui_utils import setup_report_tags, get_line_tag
                setup_report_tags(report_box)
                report_box.configure(state="normal")
                report_box.delete("1.0", "end")

                for line in report_text.split("\n"):
                    tag = get_line_tag(line)
                    if tag:
                        start = report_box._textbox.index("end-1c")
                        report_box.insert("end", line + "\n")
                        end = report_box._textbox.index("end-1c")
                        report_box._textbox.tag_add(tag, start, end)
                    else:
                        report_box.insert("end", line + "\n")
                report_box.see("1.0")

                n = len(root_causes)
                if n == 0:
                    status_label.configure(text="✅ No correlated root causes found — faults may be independent",
                                           text_color=colors["success"])
                else:
                    status_label.configure(text=f"🔗 Found {n} correlated root cause(s)",
                                           text_color=colors["accent"])

            app.content.after(0, _show)

        threading.Thread(target=_analyze, daemon=True).start()

    # Analyze button
    btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=5)

    ctk.CTkButton(btn_frame, text="🔗 Analyze Correlations",
                  font=("Segoe UI", 14, "bold"), height=42,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  command=run_correlation).pack(side="left", padx=(0, 10))

    def _copy():
        try:
            text = report_box.get("1.0", "end").strip()
            app.clipboard_clear()
            app.clipboard_append(text)
            status_label.configure(text="📋 Copied to clipboard!", text_color=colors["success"])
        except Exception:
            pass

    ctk.CTkButton(btn_frame, text="📋 Copy Report",
                  font=("Segoe UI", 13), height=42,
                  fg_color=colors["bg_light"], hover_color=colors["bg_card"],
                  text_color=colors["text"],
                  command=_copy).pack(side="left")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: BASELINE COMPARISON
# ═══════════════════════════════════════════════════════════════════════════

def _build_baseline_tab(parent, app, colors):
    """Build the baseline comparison tab."""

    desc_card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=12)
    desc_card.pack(fill="x", padx=20, pady=10)
    ctk.CTkLabel(desc_card, text="📊 Known-Good Baseline Comparison",
                 font=("Segoe UI", 16, "bold"),
                 text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 5))
    ctk.CTkLabel(desc_card, text="Compare a device under test against a known-good baseline.\n"
                 "Save 'golden' snapshots from working devices, then diff new devices to spot anomalies.",
                 font=("Segoe UI", 12), text_color=colors["text_dim"],
                 wraplength=800, justify="left").pack(anchor="w", padx=20, pady=(0, 15))

    # Actions
    action_card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=12)
    action_card.pack(fill="x", padx=20, pady=5)

    ctk.CTkLabel(action_card, text="Actions:",
                 font=("Segoe UI", 14, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(15, 10))

    btn_row = ctk.CTkFrame(action_card, fg_color="transparent")
    btn_row.pack(fill="x", padx=20, pady=(0, 15))

    results_frame = ctk.CTkFrame(parent, fg_color="transparent")
    results_frame.pack(fill="both", expand=True, padx=0, pady=0)

    report_box = ctk.CTkTextbox(results_frame, fg_color=colors["bg_light"],
                                font=("Consolas", 11),
                                text_color=colors["text"],
                                height=400)

    status_label = ctk.CTkLabel(results_frame, text="",
                                font=("Segoe UI", 12),
                                text_color=colors["text_dim"])

    def save_baseline():
        """Save current ADB-connected device as baseline."""
        report_box.pack(fill="both", expand=True, padx=20, pady=10)
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        status_label.pack(anchor="w", padx=20)
        status_label.configure(text="🔄 Capturing baseline from ADB device...", text_color=colors["info"])

        def _capture():
            try:
                from app.hardware.adb_detector import detect_via_adb
                from app.hardware.baseline_comparator import BaselineComparator

                result = detect_via_adb(lambda msg: None)
                if not result or not result.brand:
                    def _err():
                        report_box.insert("end", "❌ No ADB device found. Connect a device and enable USB debugging.")
                        status_label.configure(text="❌ No device connected", text_color=colors["accent"])
                    app.content.after(0, _err)
                    return

                comparator = BaselineComparator()
                baseline = comparator.capture_baseline_from_adb(result)
                comparator.save_new_baseline(baseline)

                def _done():
                    report_box.insert("end", f"✅ Baseline saved successfully!\n\n")
                    report_box.insert("end", f"  Device:   {baseline.device_model}\n")
                    report_box.insert("end", f"  Brand:    {baseline.brand}\n")
                    report_box.insert("end", f"  Chipset:  {baseline.chipset}\n")
                    report_box.insert("end", f"  ID:       {baseline.baseline_id}\n")
                    report_box.insert("end", f"  Entries:  {len(baseline.entries)} data points\n\n")
                    report_box.insert("end", f"  Data points captured:\n")
                    for entry in baseline.entries:
                        report_box.insert("end", f"    • {entry.key}: {entry.expected_value} {entry.unit}\n")
                    status_label.configure(text=f"✅ Baseline saved: {baseline.device_model}",
                                           text_color=colors["success"])
                app.content.after(0, _done)

            except Exception as e:
                def _err():
                    report_box.insert("end", f"❌ Error: {e}")
                    status_label.configure(text="❌ Failed", text_color=colors["accent"])
                app.content.after(0, _err)

        threading.Thread(target=_capture, daemon=True).start()

    def compare_device():
        """Compare ADB device against its baseline."""
        report_box.pack(fill="both", expand=True, padx=20, pady=10)
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        status_label.pack(anchor="w", padx=20)
        status_label.configure(text="🔄 Comparing device against baseline...", text_color=colors["info"])

        def _compare():
            try:
                from app.hardware.adb_detector import detect_via_adb
                from app.hardware.baseline_comparator import BaselineComparator, generate_comparison_report

                result = detect_via_adb(lambda msg: None)
                if not result or not result.brand:
                    def _err():
                        report_box.insert("end", "❌ No ADB device found. Connect a device and enable USB debugging.")
                        status_label.configure(text="❌ No device connected", text_color=colors["accent"])
                    app.content.after(0, _err)
                    return

                comparator = BaselineComparator()
                report = comparator.compare_adb(result)
                report_text = generate_comparison_report(report)

                def _show():
                    from app.gui.ui_utils import setup_report_tags, get_line_tag
                    setup_report_tags(report_box)
                    report_box.configure(state="normal")
                    report_box.delete("1.0", "end")

                    for line in report_text.split("\n"):
                        tag = get_line_tag(line)
                        if tag:
                            start = report_box._textbox.index("end-1c")
                            report_box.insert("end", line + "\n")
                            end = report_box._textbox.index("end-1c")
                            report_box._textbox.tag_add(tag, start, end)
                        else:
                            report_box.insert("end", line + "\n")
                    report_box.see("1.0")

                    score = report.health_score
                    if score >= 80:
                        status_label.configure(text=f"✅ Health: {score}% — Device matches baseline",
                                               text_color=colors["success"])
                    elif score >= 50:
                        status_label.configure(text=f"🟡 Health: {score}% — Some deviations found",
                                               text_color=colors["warning"])
                    else:
                        status_label.configure(text=f"🔴 Health: {score}% — Significant deviations!",
                                               text_color=colors["accent"])
                app.content.after(0, _show)

            except Exception as e:
                def _err():
                    report_box.insert("end", f"❌ Error: {e}")
                    status_label.configure(text="❌ Failed", text_color=colors["accent"])
                app.content.after(0, _err)

        threading.Thread(target=_compare, daemon=True).start()

    def list_baselines():
        """Show all saved baselines."""
        report_box.pack(fill="both", expand=True, padx=20, pady=10)
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")

        from app.hardware.baseline_comparator import BaselineComparator
        comparator = BaselineComparator()
        baselines = comparator.get_all_baselines()

        report_box.insert("end", f"═══ Saved Baselines ({len(baselines)}) ═══\n\n")
        for bl in baselines:
            report_box.insert("end", f"  📱 {bl.device_model}\n")
            report_box.insert("end", f"     Brand: {bl.brand} | Chipset: {bl.chipset}\n")
            report_box.insert("end", f"     Source: {bl.source} | Date: {bl.created_date}\n")
            report_box.insert("end", f"     Data points: {len(bl.entries)}\n")
            report_box.insert("end", f"     ID: {bl.baseline_id}\n\n")

        status_label.pack(anchor="w", padx=20)
        status_label.configure(text=f"📊 {len(baselines)} baseline(s) available",
                               text_color=colors["info"])

    ctk.CTkButton(btn_row, text="💾 Save Current Device as Baseline",
                  font=("Segoe UI", 13, "bold"), height=40,
                  fg_color=colors["success"], hover_color="#3ce882",
                  text_color="#000000",
                  command=save_baseline).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_row, text="📊 Compare Device vs Baseline",
                  font=("Segoe UI", 13, "bold"), height=40,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  command=compare_device).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_row, text="📋 List All Baselines",
                  font=("Segoe UI", 13), height=40,
                  fg_color=colors["bg_light"], hover_color=colors["bg_card"],
                  text_color=colors["text"],
                  command=list_baselines).pack(side="left")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: PREDICTIVE HEALTH SCORING
# ═══════════════════════════════════════════════════════════════════════════

def _build_predictive_tab(parent, app, colors):
    """Build the predictive failure scoring tab."""

    desc_card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=12)
    desc_card.pack(fill="x", padx=20, pady=10)
    ctk.CTkLabel(desc_card, text="📈 Predictive Failure Scoring",
                 font=("Segoe UI", 16, "bold"),
                 text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 5))
    ctk.CTkLabel(desc_card, text="Score battery health, storage SMART data, thermal patterns to predict failures.\n"
                 "Catches degrading components BEFORE they fail catastrophically.",
                 font=("Segoe UI", 12), text_color=colors["text_dim"],
                 wraplength=800, justify="left").pack(anchor="w", padx=20, pady=(0, 15))

    # Results area
    results_frame = ctk.CTkFrame(parent, fg_color="transparent")
    results_frame.pack(fill="both", expand=True, padx=0, pady=0)

    # Health score cards (will be populated after scan)
    cards_frame = ctk.CTkFrame(results_frame, fg_color="transparent")
    cards_frame.pack(fill="x", padx=20, pady=10)

    report_box = ctk.CTkTextbox(results_frame, fg_color=colors["bg_light"],
                                font=("Consolas", 11),
                                text_color=colors["text"],
                                height=350)

    status_label = ctk.CTkLabel(results_frame, text="",
                                font=("Segoe UI", 12),
                                text_color=colors["text_dim"])

    def run_predictive():
        """Run predictive analysis on ADB-connected device."""
        # Clear previous cards
        for w in cards_frame.winfo_children():
            w.destroy()

        report_box.pack(fill="both", expand=True, padx=20, pady=10)
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        status_label.pack(anchor="w", padx=20)
        status_label.configure(text="🔄 Running predictive analysis via ADB...", text_color=colors["info"])

        def _analyze():
            try:
                from app.hardware.adb_detector import detect_via_adb
                from app.hardware.predictive_scorer import PredictiveScorer, generate_predictive_report

                result = detect_via_adb(lambda msg: None)
                if not result or not result.brand:
                    def _err():
                        report_box.insert("end", "❌ No ADB device found. Connect a device and enable USB debugging.")
                        status_label.configure(text="❌ No device connected", text_color=colors["accent"])
                    app.content.after(0, _err)
                    return

                scorer = PredictiveScorer()
                report = scorer.score_from_adb(result)
                report_text = generate_predictive_report(report)

                def _show():
                    # Build health score cards
                    _build_health_cards(cards_frame, report, colors)

                    # Show text report
                    from app.gui.ui_utils import setup_report_tags, get_line_tag
                    setup_report_tags(report_box)
                    report_box.configure(state="normal")
                    report_box.delete("1.0", "end")

                    for line in report_text.split("\n"):
                        tag = get_line_tag(line)
                        if tag:
                            start = report_box._textbox.index("end-1c")
                            report_box.insert("end", line + "\n")
                            end = report_box._textbox.index("end-1c")
                            report_box._textbox.tag_add(tag, start, end)
                        else:
                            report_box.insert("end", line + "\n")
                    report_box.see("1.0")

                    score = report.overall_score
                    risk = report.overall_risk
                    if score >= 80:
                        status_label.configure(text=f"✅ Overall Health: {score}/100 ({risk} risk)",
                                               text_color=colors["success"])
                    elif score >= 50:
                        status_label.configure(text=f"🟡 Overall Health: {score}/100 ({risk} risk)",
                                               text_color=colors["warning"])
                    else:
                        status_label.configure(text=f"🔴 Overall Health: {score}/100 ({risk} risk)",
                                               text_color=colors["accent"])

                app.content.after(0, _show)

            except Exception as e:
                def _err():
                    report_box.insert("end", f"❌ Error: {e}")
                    status_label.configure(text="❌ Failed", text_color=colors["accent"])
                app.content.after(0, _err)

        threading.Thread(target=_analyze, daemon=True).start()

    # Button
    btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=5)

    ctk.CTkButton(btn_frame, text="📈 Run Predictive Analysis",
                  font=("Segoe UI", 14, "bold"), height=42,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  command=run_predictive).pack(side="left", padx=(0, 10))

    def _copy():
        try:
            text = report_box.get("1.0", "end").strip()
            app.clipboard_clear()
            app.clipboard_append(text)
            status_label.configure(text="📋 Copied to clipboard!", text_color=colors["success"])
        except Exception:
            pass

    ctk.CTkButton(btn_frame, text="📋 Copy Report",
                  font=("Segoe UI", 13), height=42,
                  fg_color=colors["bg_light"], hover_color=colors["bg_card"],
                  text_color=colors["text"],
                  command=_copy).pack(side="left")


def _build_health_cards(parent, report, colors):
    """Build visual health score cards for each component."""
    # Overall score card
    overall_card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=12)
    overall_card.pack(fill="x", pady=(0, 10))

    score = report.overall_score
    if score >= 80:
        score_color = colors["success"]
    elif score >= 50:
        score_color = colors["warning"]
    else:
        score_color = colors["accent"]

    row = ctk.CTkFrame(overall_card, fg_color="transparent")
    row.pack(fill="x", padx=20, pady=15)

    ctk.CTkLabel(row, text=f"{score}", font=("Segoe UI", 36, "bold"),
                 text_color=score_color).pack(side="left", padx=(0, 10))

    info_frame = ctk.CTkFrame(row, fg_color="transparent")
    info_frame.pack(side="left", fill="x", expand=True)

    ctk.CTkLabel(info_frame, text=f"Overall Device Health — {report.overall_risk} Risk",
                 font=("Segoe UI", 14, "bold"),
                 text_color=colors["text"]).pack(anchor="w")
    ctk.CTkLabel(info_frame, text=report.device_info,
                 font=("Segoe UI", 12),
                 text_color=colors["text_dim"]).pack(anchor="w")

    # Progress bar
    bar = ctk.CTkProgressBar(overall_card, height=8, corner_radius=4,
                             progress_color=score_color,
                             fg_color=colors["bg_light"])
    bar.pack(fill="x", padx=20, pady=(0, 15))
    bar.set(score / 100)

    # Component cards in a grid
    comp_grid = ctk.CTkFrame(parent, fg_color="transparent")
    comp_grid.pack(fill="x")

    for i, comp in enumerate(report.components):
        card = ctk.CTkFrame(comp_grid, fg_color=colors["bg_card"], corner_radius=10)
        card.grid(row=i // 3, column=i % 3, padx=5, pady=5, sticky="nsew")
        comp_grid.columnconfigure(i % 3, weight=1)

        cs = comp.health_score
        if cs >= 80:
            cc = colors["success"]
            icon = "🟢"
        elif cs >= 50:
            cc = colors["warning"]
            icon = "🟡"
        elif cs >= 20:
            cc = "#ff8c00"
            icon = "🟠"
        else:
            cc = colors["accent"]
            icon = "🔴"

        ctk.CTkLabel(card, text=f"{icon} {comp.component}",
                     font=("Segoe UI", 12, "bold"),
                     text_color=colors["text"]).pack(anchor="w", padx=15, pady=(10, 2))

        ctk.CTkLabel(card, text=f"{cs}/100",
                     font=("Segoe UI", 20, "bold"),
                     text_color=cc).pack(anchor="w", padx=15, pady=(0, 2))

        comp_bar = ctk.CTkProgressBar(card, height=6, corner_radius=3,
                                      progress_color=cc,
                                      fg_color=colors["bg_light"])
        comp_bar.pack(fill="x", padx=15, pady=(0, 5))
        comp_bar.set(cs / 100)

        ctk.CTkLabel(card, text=comp.predicted_failure,
                     font=("Segoe UI", 10),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=15, pady=(0, 10))


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _guess_component(symptom: str) -> str:
    """Guess the component from a symptom description."""
    s = symptom.lower()
    mapping = [
        (["pmic", "power management", "vbat", "voltage rail"], "PMIC (Power Management IC)"),
        (["battery", "charging", "charger", "charge"], "Battery / Charging"),
        (["dead phone", "no boot", "not turning", "won't start"], "CPU / SoC"),
        (["ram", "dram", "memory"], "RAM (DRAM)"),
        (["emmc", "ufs", "storage", "nand", "flash"], "Storage (eMMC/UFS)"),
        (["wifi", "bluetooth", "bt", "combo"], "WiFi / Bluetooth Combo IC"),
        (["display", "screen", "lcd", "oled", "no display"], "Display"),
        (["touch", "touchscreen"], "Touchscreen"),
        (["camera", "cam"], "Camera Module"),
        (["speaker", "mic", "audio", "earpiece", "sound"], "Audio"),
        (["sensor", "fingerprint", "proximity", "gyro", "accelero"], "Sensors"),
        (["imei", "baseband", "modem", "network", "sim", "signal"], "Baseband / Modem IC"),
        (["usb", "port"], "USB Port"),
        (["thermal", "heat", "hot", "overheat", "temperature"], "Thermal"),
        (["software", "crash", "boot loop", "reboot", "freeze"], "System Software"),
    ]
    for keywords, component in mapping:
        if any(kw in s for kw in keywords):
            return component
    return "Unknown Component"
