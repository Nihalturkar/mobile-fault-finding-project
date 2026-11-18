"""
Shared scan engines for HW Detect (UART) and ADB Detect.

The report logic used to live inside the GUI pages. It now lives here so the
pages AND Jack run exactly the same scan and produce exactly the same report.

Both runners:
  * stream every report line through  emit(line)            (live display)
  * report progress through           progress(pct, msg)    (0.0 – 1.0)
  * auto-save the report + raw logs to config/logs/ and add a history entry
  * return a dict with the outcome (lines, saved paths, summary for the UI)
"""

import datetime as _dt
import json
from typing import Any, Callable, Dict, List, Optional

Emit = Callable[[str], None]
Progress = Callable[[float, str], None]


def _noop_progress(pct: float, msg: str) -> None:
    pass


def _fmt_confidence(conf) -> str:
    """Detector confidence may be 0-1 or 0-100 — always show a sane percentage."""
    try:
        c = float(conf)
    except (TypeError, ValueError):
        return "?"
    return f"{c:.0f}%" if c > 1 else f"{c:.0%}"


# ═══════════════════════════════════════════════════════════════════════════
#  UART / HW DETECT
# ═══════════════════════════════════════════════════════════════════════════

def run_uart_scan(port: str, baud: int, duration: int, emit: Emit,
                  progress: Optional[Progress] = None, stop_event=None) -> Dict[str, Any]:
    """Listen on a UART port while the phone boots, then build the full hardware report."""
    from app.gui.pages.hw_detect import _lookup_phone_db, _format_phone_db_section

    progress = progress or _noop_progress
    lines: List[str] = []
    out: Dict[str, Any] = {"type": "UART", "port": port, "baud": baud, "duration": duration,
                           "detected": False, "stopped": False, "parsed": None, "lines": lines}

    def _track(text: str) -> None:
        lines.append(text)
        emit(text)

    def _track_lines(items: List[str]) -> None:
        for t in items:
            _track(t)

    # ── Header ──
    _track_lines([
        "=" * 70,
        "  MOOXY AI FAULT DETECTOR — HARDWARE DETECTION REPORT",
        "=" * 70,
        f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Port: {port} @ {baud} baud | Listen: {duration} sec",
        "=" * 70,
        "",
    ])

    # ═══ PHASE 1: DETECTION ═══
    _track("")
    _track("═══ PHASE 1: DETECTION ═══")
    _track("")
    _track("🔴 BOOT THE PHONE NOW! Listening...")
    _track("")

    uart_result = None
    try:
        from app.hardware.device_detector import DeviceAutoDetector

        def uart_cb(elapsed, total_bytes):
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError("Scan stopped by user")
            pct = elapsed / duration * 0.7
            remaining = int(duration - elapsed)
            progress(min(pct, 0.7), f"Scanning: {remaining}s left | {total_bytes} bytes | BOOT PHONE NOW!")

        detector = DeviceAutoDetector(port=port, baud=baud)
        try:
            uart_result = detector.detect(listen_duration=duration, callback=uart_cb)
        except InterruptedError:
            _track("")
            _track("⏹ Scan stopped by user")
            progress(0.0, "Scan stopped")
            out["stopped"] = True
            return out

        if not uart_result.detected:
            err_msg = uart_result.error or "No data received — check TX/GND connections"
            _track(f"  ⚠️ {err_msg}")
        else:
            r = uart_result.raw_responses

            # 1. DEVICE INFO (one line)
            chip_name = r.get("chipset_marketing_name", "")
            db_match = r.get("chipset_db_match", "")
            pmic = r.get("pmic_model", "")
            product_name = r.get("qcom_product_name", "")
            brand_display = uart_result.brand or "Unknown"
            if product_name:
                brand_display += f" ({product_name})"
            device_line = f"  {brand_display}"
            if db_match:
                device_line += f" | {db_match} ({chip_name})"
            else:
                device_line += f" | {uart_result.chipset}"
            if pmic:
                device_line += f" | PMIC: {pmic}"
            bat = r.get("battery_vbat", "")
            if bat:
                device_line += f" | Battery: {bat}"
            _track(device_line)

            # 2. Collect all faults by confidence level
            confirmed_faults = []   # >= 75% — PROBLEM
            possible_faults = []    # 50-74% — "check kijiye"

            try:
                _det = DeviceAutoDetector(port=port, baud=baud)
                _raw_bytes = (bytes.fromhex(uart_result.raw_data) if isinstance(uart_result.raw_data, str)
                              else uart_result.raw_data)
                _parsed = _det._parse_boot_data(_raw_bytes)
            except Exception as _parse_err:
                print(f"[HW Detect] Re-parse error: {_parse_err}")
                _parsed = {}
            out["parsed"] = _parsed

            for fault in _parsed.get("faults_detected", []):
                conf = fault.get("confidence", 50)
                if conf >= 75:
                    confirmed_faults.append(fault)
                elif conf >= 50:
                    possible_faults.append(fault)

            known_fault = _parsed.get("known_fault_info")
            correlated = _parsed.get("correlated_faults", [])
            boot_stuck = _parsed.get("boot_stuck", False)
            matched_patterns = _parsed.get("matched_fault_patterns", [])

            # ── CONFIRMED PROBLEMS
            has_problem = bool(known_fault or correlated or confirmed_faults or boot_stuck)

            if has_problem:
                _track("")
                _track("=" * 55)
                _track("  🔴 PROBLEM DETECTED")
                _track("=" * 55)

                if known_fault:
                    _track("")
                    _track(f"  Problem: {known_fault.get('symptom', '')}")
                    _track(f"  Cause:   {known_fault.get('root_cause', '')}")
                    _track(f"  Confidence: {known_fault.get('confidence', 0)}%")
                    _track("")
                    _track("  How to Fix:")
                    for i, step in enumerate(known_fault.get("repair_steps", []), 1):
                        _track(f"    {i}. {step}")
                    _track(f"  Difficulty: {known_fault.get('difficulty', '?')}")
                elif correlated:
                    for cf in correlated:
                        _track("")
                        _track(f"  Problem: {cf.get('title', '')}")
                        _track(f"  Cause:   {cf.get('root_cause', '')}")
                        _track(f"  Confidence: {cf.get('confidence', 0)}%")
                        _track("")
                        _track("  How to Fix:")
                        for i, step in enumerate(cf.get("repair_steps", []), 1):
                            _track(f"    {i}. {step}")

                if confirmed_faults:
                    seen_names = set()
                    for fault in confirmed_faults:
                        name = fault.get("name", "")
                        if name in seen_names:
                            continue
                        seen_names.add(name)
                        count = fault.get("repeat_count", 1)
                        count_str = f" (x{count})" if count > 1 else ""
                        _track(f"  ⚠️ {name}{count_str}: {fault.get('message', '')[:100]}")

                ddr_rails = _parsed.get("ddr_voltage_rails", {})
                if ddr_rails:
                    ddr_type = _parsed.get("ddr_type_detected", "DDR")
                    abort_reason = _parsed.get("ddr_abort_reason", "")
                    _track("")
                    _track(f"  ── {ddr_type} Voltage Rails (measure with multimeter) ──")
                    if abort_reason:
                        _track(f"  Abort Reason: {abort_reason}")
                    _track("")
                    for rail_name, rail_info in ddr_rails.items():
                        expected = rail_info.get("expected", "?")
                        status = rail_info.get("status", "check")
                        if status == "ok":
                            _track(f"    {rail_name}: {expected} ✅ OK")
                        elif status == "missing":
                            _track(f"    {rail_name}: {expected} ❌ MISSING")
                        elif status == "low":
                            _track(f"    {rail_name}: {expected} ⚠️ LOW")
                        else:
                            _track(f"    {rail_name}: {expected} — measure this")
                    _track("")
                    _track("  Repair: Check each rail with multimeter on PMIC output.")
                    _track("  Missing voltage = trace back to PMIC regulator / inductor / capacitor.")

                _track("")
                _track("=" * 55)
            else:
                _track("")
                _track("  ✅ No confirmed faults detected")

            # ── POSSIBLE ISSUES
            if possible_faults:
                seen_names = set()
                has_possible_header = False
                for fault in possible_faults:
                    name = fault.get("name", "")
                    if name in seen_names:
                        continue
                    seen_names.add(name)
                    if not has_possible_header:
                        _track("")
                        _track("  ── Isse bhi check kijiye ──")
                        has_possible_header = True
                    count = fault.get("repeat_count", 1)
                    count_str = f" (x{count})" if count > 1 else ""
                    _track(f"  ℹ️ {name}{count_str} — {fault.get('message', '')[:80]}")

            # ── MATCHED FAULT PATTERNS
            if matched_patterns and not known_fault:
                _track("")
                _track("  ── Database se match ──")
                for mp in matched_patterns[:2]:
                    info = mp["info"]
                    _track(f"  ℹ️ {info['symptom'][:70]}")
                    top_cause = info.get("possible_causes", [{}])[0]
                    if top_cause:
                        _track(f"     Check: {top_cause.get('ic', '?')} — {top_cause.get('check', '')[:70]}")

            # ── FULL DEVICE DATA ──
            _track("")
            _track("=" * 55)
            _track("  FULL DEVICE DATA")
            _track("=" * 55)

            _track("")
            _track("── Chipset / SoC ──")
            _track(f"  Chipset: {uart_result.chipset or 'Unknown'}")
            if r.get("chipset_db_match"):
                _track(f"  DB Match: {r['chipset_db_match']}")
            if r.get("chipset_marketing_name"):
                _track(f"  Marketing Name: {r['chipset_marketing_name']}")
            for k in ("qcom_chip_name", "qcom_chip_ver", "qcom_codename", "qcom_jtag_id",
                      "qcom_oem_id", "qcom_serial", "qcom_device_code",
                      "qcom_secure_boot", "qcom_vb_state",
                      "mtk_chip_code", "mtk_chip_name"):
                if r.get(k):
                    label = k.replace("qcom_", "QC ").replace("mtk_", "MTK ").replace("_", " ").title()
                    _track(f"  {label}: {r[k]}")

            _track("")
            _track("── CPU ──")
            cpu_cores = _parsed.get("cpu_cores", "")
            if cpu_cores:
                _track(f"  Cores: {cpu_cores}")
            if r.get("qcom_core_freq"):
                _track(f"  Frequency: {r['qcom_core_freq']}")

            _track("")
            _track("── RAM / DDR ──")
            ram = _parsed.get("ram", "")
            if ram:
                _track(f"  Size: {ram}")
            if _parsed.get("ram_type"):
                _track(f"  Type: {_parsed['ram_type']}")
            if _parsed.get("ram_freq"):
                _track(f"  Frequency: {_parsed['ram_freq']}")
            if _parsed.get("ram_manufacturer"):
                _track(f"  Manufacturer: {_parsed['ram_manufacturer']}")
            for k in ("qcom_ddr_ranks", "ddr_type_detected", "ddr_dsf_version",
                      "ddr_abort_reason", "ddr_abort_freq", "ddr_abort_channel"):
                if r.get(k):
                    label = k.replace("qcom_", "").replace("ddr_", "DDR ").replace("_", " ").title()
                    _track(f"  {label}: {r[k]}")

            _track("")
            _track("── Storage ──")
            storage = _parsed.get("storage", "")
            if storage:
                _track(f"  Type: {storage}")
            if _parsed.get("storage_type"):
                _track(f"  Interface: {_parsed['storage_type']}")
            if _parsed.get("storage_max_speed"):
                _track(f"  Max Speed: {_parsed['storage_max_speed']}")
            if r.get("qcom_ufs_id"):
                _track(f"  UFS ID: {r['qcom_ufs_id']}")
            if r.get("qcom_ufs_spec"):
                _track(f"  UFS Spec: {r['qcom_ufs_spec']}")

            _track("")
            _track("── Battery & Power ──")
            vbat = _parsed.get("battery_vbat", "")
            if vbat:
                _track(f"  VBAT: {vbat}")
            if _parsed.get("battery_vchr"):
                _track(f"  Charger Voltage: {_parsed['battery_vchr']}")
            if r.get("qcom_ibat"):
                _track(f"  Battery Current: {r['qcom_ibat']}")
            if r.get("qcom_battery_id"):
                _track(f"  Battery ID: {r['qcom_battery_id']}")

            _track("")
            _track("── PMIC ──")
            pmic = _parsed.get("pmic_model", "")
            if pmic:
                _track(f"  Model: {pmic}")
            rst = _parsed.get("pmic_reset_cause", "")
            if rst:
                _track(f"  Last Reset: {rst}")
            for reg_name, reg_val in (_parsed.get("pmic_registers", {}) or {}).items():
                _track(f"  {reg_name}: {reg_val}")

            voltages = _parsed.get("voltage_rails", {})
            if voltages:
                _track("")
                _track("── Voltage Rails ──")
                for rail, uv in voltages.items():
                    _track(f"  {rail}: {uv/1000:.1f}mV ({uv}uV)")

            display = _parsed.get("qcom_display", "")
            if display:
                _track("")
                _track("── Display ──")
                _track(f"  Panel: {display}")
                if _parsed.get("qcom_display_res"):
                    _track(f"  Resolution: {_parsed['qcom_display_res']}")

            if r.get("qcom_wifi") or r.get("qcom_bluetooth"):
                _track("")
                _track("── Connectivity ──")
                if r.get("qcom_wifi"):
                    _track(f"  WiFi: {r['qcom_wifi']}")
                if r.get("qcom_bluetooth"):
                    _track(f"  Bluetooth: {r['qcom_bluetooth']}")

            _track("")
            _track("── Boot Information ──")
            for key, label in (("boot_reason", "Boot Reason"), ("boot_reason_detail", "Boot Detail"),
                               ("boot_mode", "Boot Mode"), ("abnormal_boot", "Abnormal Boot"),
                               ("boot_stage", "Boot Stage"), ("boot_stuck_stage", "Boot Stuck At"),
                               ("boot_stuck_reason", "Stuck Cause")):
                if _parsed.get(key):
                    _track(f"  {label}: {_parsed[key]}")
            if r.get("qcom_boot_time_ms"):
                _track(f"  SBL Boot Time: {r['qcom_boot_time_ms']}")
            if r.get("qcom_uefi_total"):
                _track(f"  UEFI Boot Time: {r['qcom_uefi_total']}")

            if r.get("firmware_version") or _parsed.get("atf_version") or _parsed.get("trustzone_version"):
                _track("")
                _track("── Firmware ──")
                if r.get("firmware_version"):
                    _track(f"  Version: {r['firmware_version']}")
                for key, label in (("atf_version", "ATF/BL31"), ("trustzone_version", "TrustZone"),
                                   ("spm_firmware", "SPM"), ("kernel_entry", "Kernel Entry")):
                    if _parsed.get(key):
                        _track(f"  {label}: {_parsed[key]}")
                if r.get("qcom_mbm_version"):
                    _track(f"  MBM Version: {r['qcom_mbm_version']}")

            i2c_keys = sorted(k for k in _parsed if k.startswith("i2c_error"))
            if i2c_keys:
                _track("")
                _track("── I2C Bus Errors ──")
                for key in i2c_keys:
                    _track(f"  {_parsed[key]}")

            ic_probes = _parsed.get("ic_probes_failed", [])
            if ic_probes:
                _track("")
                _track("── IC Probes Failed ──")
                for probe in ic_probes:
                    _track(f"  ⚪ {probe}")

            companion = _parsed.get("companion_ics", {})
            if companion:
                _track("")
                _track("── Board ICs (from DB) ──")
                for ic_name, ic_info in companion.items():
                    if isinstance(ic_info, dict):
                        addr = ic_info.get("i2c_address", "")
                        func = ic_info.get("function", "")
                        _track(f"  {ic_name}: {func} (I2C: {addr})" if addr else f"  {ic_name}: {func}")
                    else:
                        _track(f"  {ic_name}")

            dmesg = _parsed.get("dmesg_data", {})
            if dmesg:
                _track("")
                _track("── Live Dmesg Data ──")
                for dk, dv in dmesg.items():
                    _track(f"  {dk.replace('_', ' ').title()}: {dv}")

            shown_keys = {
                "chipset", "chipset_detail", "brand", "boot_registers", "boot_stage",
                "version", "ram", "storage", "board_name", "ram_type", "ram_freq",
                "ram_manufacturer", "cpu_cores", "atf_version", "trustzone_version",
                "spm_firmware", "boot_mode", "abnormal_boot", "boot_reason",
                "kernel_entry", "mtk_chip_code", "mtk_chip_name", "pmic_model",
                "pmic_reset_cause", "boot_reason_detail", "storage_type",
                "storage_max_speed", "battery_vbat", "battery_vchr",
                "boot_stuck_stage", "boot_stuck_reason", "boot_stuck",
                "qcom_chip_name", "qcom_chip_ver", "qcom_codename", "qcom_jtag_id",
                "qcom_core_freq", "qcom_ufs_id", "qcom_ufs_spec", "qcom_ddr_ranks",
                "qcom_ibat", "qcom_battery_id", "qcom_display", "qcom_display_res",
                "qcom_wifi", "qcom_bluetooth", "qcom_vb_state", "qcom_secure_boot",
                "qcom_serial", "qcom_device_code", "qcom_uefi_total",
                "qcom_boot_time_ms", "qcom_mbm_version", "qcom_oem_id", "qcom_product_name",
                "ddr_type_detected", "ddr_dsf_version",
                "ddr_abort_reason", "ddr_abort_freq", "ddr_abort_channel",
                "voltage_rails", "pmic_registers", "ic_probes_failed",
                "companion_ics", "dmesg_data", "faults_detected",
                "known_fault_info", "correlated_faults", "matched_fault_patterns",
                "chipset_db_match", "chipset_marketing_name", "data_received",
            }
            extra = {k: v for k, v in _parsed.items()
                     if k not in shown_keys and not k.startswith("i2c_error") and v}
            if extra:
                _track("")
                _track("── Additional Data ──")
                for ek, ev in extra.items():
                    label = ek.replace("_", " ").title()
                    if isinstance(ev, (list, dict)):
                        _track(f"  {label}: {json.dumps(ev, default=str)}")
                    else:
                        _track(f"  {label}: {ev}")

            _codename = r.get("qcom_product_name", "") or _parsed.get("qcom_product_name", "")
            _db_hit = _lookup_phone_db(brand=uart_result.brand or "",
                                       chipset=db_match or uart_result.chipset or "",
                                       codename_hint=_codename)
            if _db_hit:
                for line in _format_phone_db_section(*_db_hit):
                    _track(line)

    except Exception as e:
        _track(f"  ❌ Detection Error: {str(e)}")

    progress(0.9, "Fault analysis...")

    # ═══ ADDITIONAL FAULT ANALYSIS ═══
    faults_count = 0
    faults_summary_text = ""
    healthy_list = []
    if uart_result and uart_result.detected:
        try:
            from app.hardware.fault_analyzer import analyze_uart_result
            report = analyze_uart_result(uart_result)
            faults_count = len(report.faults)
            if report.faults:
                faults_summary_text = "; ".join(f"{f.component}: {f.problem}" for f in report.faults[:5])
            if report.healthy_components:
                healthy_list = report.healthy_components
        except Exception:
            pass

    _track("")
    _track("=" * 70)
    _track("  Report generated by Mooxy AI Fault Detector v1.0")
    _track("=" * 70)

    # ── Summary for the UI ──
    out["detected"] = bool(uart_result and uart_result.detected)
    if out["detected"]:
        r = uart_result.raw_responses
        out["summary_text"] = (f"✅ {uart_result.chipset} | CPU: {r.get('cpu_cores', '?')} cores | "
                               f"RAM: {r.get('ram_type', '?')} {r.get('ram_freq', '')} | {r.get('data_received', '')}")
        out["summary_ok"] = True
    else:
        out["summary_text"] = "⚠️ Limited data — check report"
        out["summary_ok"] = False

    # ── Auto-save ──
    from app.gui.history_manager import get_unique_log_path, add_detection
    log_path = get_unique_log_path("boot_log")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        out["log_path"] = str(log_path)
    except Exception:
        pass

    raw_log_path = None
    if uart_result and uart_result.raw_data:
        raw_log_path = get_unique_log_path("raw_boot")
        try:
            with open(raw_log_path, "wb") as f:
                f.write(bytes.fromhex(uart_result.raw_data))
        except Exception:
            raw_log_path = None

    try:
        device_name, summary_text = "Unknown Device", "Scan completed"
        if out["detected"]:
            device_name = f"{uart_result.brand} ({uart_result.chipset})"
            summary_text = (f"Chipset: {uart_result.chipset} | Brand: {uart_result.brand} | "
                            f"Confidence: {_fmt_confidence(uart_result.confidence)}")
        out["device_name"] = device_name
        add_detection(
            detection_type="UART", device_name=device_name, summary=summary_text,
            faults_count=faults_count, faults_summary=faults_summary_text, report_file=str(log_path),
            extra={"port": port, "baud": baud, "duration": duration, "healthy_components": healthy_list,
                   "raw_log_file": str(raw_log_path) if raw_log_path else ""},
        )
    except Exception as e:
        print(f"[HW Detect] History save error: {e}")

    out["faults_count"] = faults_count
    progress(1.0, "Detection complete — full report above")
    return out


# ═══════════════════════════════════════════════════════════════════════════
#  ADB DETECT
# ═══════════════════════════════════════════════════════════════════════════

def run_adb_scan(emit: Emit, progress: Optional[Progress] = None) -> Dict[str, Any]:
    """Full ADB detection with the same smart report as the ADB Detect page."""
    from app.hardware.adb_detector import detect_via_adb, generate_full_report

    progress = progress or _noop_progress
    lines: List[str] = []
    out: Dict[str, Any] = {"type": "ADB", "detected": False, "result": None, "lines": lines}

    def _track(text: str) -> None:
        lines.append(text)
        emit(text)

    last_phase = {"msg": ""}

    def cb(pct, msg):
        progress(pct, msg)
        if msg != last_phase["msg"]:
            last_phase["msg"] = msg
            icon = "🔍"
            ml = msg.lower()
            if "ok" in ml or "found" in ml or "done" in ml:
                icon = "✅"
            elif "error" in ml or "fail" in ml or "not found" in ml:
                icon = "❌"
            elif "reading" in ml or "scanning" in ml or "checking" in ml:
                icon = "🔍"
            elif "sampling" in ml:
                icon = "📊"
            elif "running" in ml or "ai" in ml:
                icon = "🧠"
            _track(f"  {icon} {msg}")

    for t in ["=" * 72, "  MOOXY AI FAULT DETECTOR — ADB DETECTION", "=" * 72,
              f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "=" * 72, "",
              "═══ SCANNING DEVICE ═══", ""]:
        _track(t)

    try:
        result = detect_via_adb(callback=cb)
        out["result"] = result

        if result.error:
            _track("")
            _track(f"  ❌ ERROR: {result.error}")
            _track("")
            out["error"] = result.error
            out["summary_text"] = f"❌ {result.error[:80]}"
            progress(1.0, "")
            return out

        # 1. DEVICE INFO
        _track("")
        device_line = f"  {result.brand} {result.model} | Android {result.android_version}"
        if result.chipset:
            device_line += f" | {result.chipset}"
        _track(device_line)
        info_parts = []
        if result.ram_total_kb:
            info_parts.append(f"RAM: {result.ram_total_kb // 1024}MB")
        if result.storage_total_kb:
            info_parts.append(f"Storage: {result.storage_total_kb // (1024*1024)}GB free "
                              f"{result.storage_free_kb // (1024*1024)}GB")
        if result.battery_level:
            info_parts.append(f"Battery: {result.battery_level}% ({result.battery_health})")
        if info_parts:
            _track(f"  {' | '.join(info_parts)}")

        # 2. CATEGORIZE DIAGNOSES
        faults = [d for d in result.diagnoses if d.status == "FAULT"]
        warnings = [d for d in result.diagnoses if d.status == "WARNING"]
        from app.hardware.fault_analyzer import analyze_adb_result
        fault_report = analyze_adb_result(result)
        confirmed = [f for f in fault_report.faults if f.confidence >= 75]
        possible = [f for f in fault_report.faults if 50 <= f.confidence < 75]

        # 3. CONFIRMED PROBLEMS
        if faults or confirmed:
            _track("")
            _track("=" * 55)
            _track("  🔴 PROBLEM DETECTED")
            _track("=" * 55)
            shown = set()
            for f in confirmed:
                key = f.component + f.problem
                if key in shown:
                    continue
                shown.add(key)
                _track("")
                _track(f"  Problem: {f.problem}")
                _track(f"  Component: {f.component} ({f.confidence}%)")
                if f.repair_steps:
                    _track("  How to Fix:")
                    for i, step in enumerate(f.repair_steps, 1):
                        _track(f"    {i}. {step}")
                if f.parts_needed:
                    _track(f"  Parts: {', '.join(f.parts_needed)}")
            for d in faults:
                if d.component not in shown:
                    _track(f"  🔴 {d.component}: {d.summary}")
                    for fix in d.fixes[:2]:
                        _track(f"     Fix: {fix}")
            _track("")
            _track("=" * 55)
        else:
            _track("")
            _track("  ✅ No confirmed faults detected")

        # 4. POSSIBLE ISSUES
        if possible or warnings:
            _track("")
            _track("  ── Isse bhi check kijiye ──")
            shown_possible = set()
            for f in possible:
                if f.component in shown_possible:
                    continue
                shown_possible.add(f.component)
                _track(f"  ℹ️ {f.component}: {f.problem} ({f.confidence}%)")
            for d in warnings:
                if d.component not in shown_possible:
                    _track(f"  ℹ️ {d.component}: {d.summary}")

        # 5. DEVICE DATA
        _track("")
        _track("── Device Data ──")
        bat_parts = [f"Level:{result.battery_level}%", f"Health:{result.battery_health}",
                     f"Temp:{result.battery_temp_c}C"]
        if result.battery_wear_pct >= 0:
            bat_parts.append(f"Wear:{result.battery_wear_pct}%")
        _track(f"  Battery: {' | '.join(bat_parts)}")
        conn_parts = []
        if result.wifi_state:
            conn_parts.append(f"WiFi:{result.wifi_state}")
        if result.sim_state:
            conn_parts.append(f"SIM:{result.sim_state}")
        if result.bt_mac:
            conn_parts.append("BT:Connected")
        if conn_parts:
            _track(f"  Connectivity: {' | '.join(conn_parts)}")
        oks = [d for d in result.diagnoses if d.status == "OK"]
        if oks:
            _track(f"  OK: {', '.join(d.component for d in oks)}")

        from app.gui.pages.hw_detect import _lookup_phone_db, _format_phone_db_section
        _db_hit = _lookup_phone_db(brand=result.brand or "", chipset=result.chipset or "",
                                   model=f"{result.brand} {result.model}" if result.model else "")
        if _db_hit:
            for line in _format_phone_db_section(*_db_hit):
                _track(line)

        out["detected"] = True
        out["full_detailed_report"] = generate_full_report(result)
        out["device_name"] = f"{result.brand} {result.model}"
        out["faults_count"] = len(faults)
        out["summary_text"] = (f"✅ {result.brand} {result.model} | Android {result.android_version} | "
                               f"Battery: {result.battery_level}% {result.battery_health} | Faults: {len(faults)}")
        progress(1.0, "Detection complete — full report above")

        # ── Save raw files ──
        from app.gui.history_manager import get_unique_log_path, add_detection
        adb_log_path = get_unique_log_path("adb_log")
        try:
            with open(adb_log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            out["log_path"] = str(adb_log_path)

            logcat_all = "\n".join(
                result.logcat_battery_events + result.logcat_display_events +
                result.logcat_touch_events + result.logcat_audio_events +
                result.logcat_camera_events + result.logcat_fingerprint_events +
                result.logcat_wifi_events + result.logcat_bluetooth_events +
                result.logcat_modem_events + result.logcat_sensors_events +
                result.logcat_crash_events + result.logcat_errors +
                result.logcat_hw_driver_lines
            )
            now = _dt.datetime.now()
            if logcat_all:
                with open(get_unique_log_path("raw_logcat"), "w", encoding="utf-8") as f:
                    f.write(f"=== Raw Logcat — {result.logcat_raw_lines} lines ===\n")
                    f.write(f"=== Date: {now} ===\n\n")
                    f.write(logcat_all)
            if result.thermal_service_raw:
                with open(get_unique_log_path("raw_thermalservice"), "w", encoding="utf-8") as f:
                    f.write("=== Raw Thermalservice Dump ===\n")
                    f.write(f"=== Date: {now} ===\n\n")
                    f.write(result.thermal_service_raw)
            if result.battery_sysfs or result.charger_sysfs:
                with open(get_unique_log_path("raw_battery"), "w", encoding="utf-8") as f:
                    f.write("=== Raw Battery/Charging Data ===\n")
                    f.write(f"=== Date: {now} ===\n\n")
                    f.write("--- Battery sysfs ---\n")
                    for k, v in result.battery_sysfs.items():
                        f.write(f"{k}: {v}\n")
                    f.write("\n--- Charger sysfs ---\n")
                    for k, v in result.charger_sysfs.items():
                        f.write(f"{k}: {v}\n")
                    f.write("\n--- dumpsys battery ---\n")
                    f.write(result.battery_dumpsys_raw)
            out["saved_msg"] = f"📁 Saved: {adb_log_path.name} + raw logs → config/logs/"
        except Exception:
            pass

        # ── Save to history ──
        try:
            fault_names = [f"{d.component}: {d.summary}" for d in faults + warnings]
            add_detection(
                detection_type="ADB",
                device_name=f"{result.brand} {result.model}",
                summary=(f"Android {result.android_version} | Chipset: {result.chipset} | "
                         f"Battery: {result.battery_level}% {result.battery_health}"),
                faults_count=len(faults),
                faults_summary="; ".join(fault_names[:5]),
                report_file=str(adb_log_path),
                extra={"android_version": result.android_version, "battery_level": result.battery_level,
                       "battery_health": result.battery_health, "warnings_count": len(warnings),
                       "ok_count": len(oks)},
            )
        except Exception as e:
            print(f"[ADB Detect] History save error: {e}")

    except Exception as e:
        _track("")
        _track(f"  ❌ ERROR: {str(e)}")
        out["error"] = str(e)
        out["summary_text"] = f"❌ {str(e)[:80]}"
        progress(1.0, "")
    return out
