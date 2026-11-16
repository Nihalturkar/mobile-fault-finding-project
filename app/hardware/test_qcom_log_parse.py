"""Regressions from a real SM6150 (Redmi Note 10 / mojito) 3-reboot capture.

Run: python -m app.hardware.test_qcom_log_parse
"""
import re

from app.hardware.device_detector import DeviceAutoDetector

# Two boot cycles, as the 90s capture actually recorded them.
_CYCLE = """S - QC_IMAGE_VERSION_STRING=BOOT.XF.3.1.c3-00001-SM6150LZB-1
Chip Name          : SM6150
B -    440542 - ufs_error_log: 28c
B -    408395 - UFS INQUIRY ID: MICRON  MT064GASAO2U21  0605
B -    687226 - Manufacturer ID = ff, Device Type = 7
B -    687348 - Rank 0 size = 4096 MB, Rank 1 size  = 0 MB
S - DDR Frequency, 1353 MHz
Total Installed RAM : 4096 MB (0x0100000000)
B -    485743 - PM: POWER ON by USB_CHG, POWER OFF due to FAULT UVLO
Exit EBS        [55690] UEFI End
"""
LOG = _CYCLE * 3


def _parse(text):
    return DeviceAutoDetector()._parse_boot_data(text.encode())


def test_ufs_error_log_is_not_a_storage_failure():
    st = _parse(LOG)["hw_status"]["storage"]["status"]
    assert st != "fail", f"ufs_error_log misread as storage fault: {st}"


def test_ram_not_double_counted_across_reboots():
    r = _parse(LOG)
    assert r.get("ram") == "4 GB", f"expected 4 GB, got {r.get('ram')}"
    assert r.get("qcom_ddr_ranks", "").startswith("2 ranks"), r.get("qcom_ddr_ranks")


def test_watchdog_unknown_when_no_rgu_register():
    comps = _parse(LOG).get("components", [])
    wdt = next(c for c in comps if c["name"].startswith("Watchdog"))
    assert wdt["status"] == "unknown", wdt
    assert "PREVIOUS CRASH" not in wdt["details"]["Reset Status (STA)"]


def test_real_ufs_failure_still_detected():  
    bad = LOG + "\nUFS error: link startup failed\n"
    assert _parse(bad)["hw_status"]["storage"]["status"] == "fail"


def test_real_watchdog_reset_still_warns():
    bad = LOG + "\n[RGU] STA from reg: 0x8000\n"
    comps = _parse(bad).get("components", [])
    wdt = next(c for c in comps if c["name"].startswith("Watchdog"))
    assert wdt["status"] == "warning", wdt


# ── Regressions from the 2026-09-23 mojito captures ──

def _faults(text):
    return {f["name"] for f in _parse(text).get("faults_detected", [])}


# Boot cycles carry a "PBL, End" marker; _CYCLE above omits it.
_PBL = "S -     97074 - PBL, End\n"
_LOOP = (_PBL + _CYCLE) * 3


def test_three_boots_without_keypress_is_a_bootloop():
    assert "Bootloop" in _faults(_LOOP)


def test_user_pressed_power_is_not_a_bootloop():
    pressed = (_PBL + _CYCLE + "PONReason HARD_RESET 1 KPDPWR 1\n") * 3
    assert "Bootloop" not in _faults(pressed)


def test_single_boot_is_not_a_bootloop():
    assert "Bootloop" not in _faults(_PBL + _CYCLE)


def test_zero_volts_with_amps_flowing_is_a_contact_fault():
    # Verbatim from the 14:59 capture: 3.8A into a battery reading 0 mV.
    bad = _CYCLE + "B -   1634434 - PM: Vbatt: 0; Ibatt: 3824\n"
    assert "Battery Sense / Contact Fault" in _faults(bad)


def test_battery_charging_normally_is_not_a_contact_fault():
    ok = _CYCLE + "B -   1634434 - PM: Vbatt: 3770; Ibatt: 1200\n"
    assert "Battery Sense / Contact Fault" not in _faults(ok)


def test_battery_reports_last_cycle_not_first():
    # Dead first boot, recovered by the third — the report must not say 0 mV.
    text = ("PM: EntryVbat: 0;\n" + _CYCLE + "PM: EntryVbat: 3770;\n"
            + _CYCLE + "PM: EntryVbat: 3924;\n")
    assert _parse(text).get("battery_vbat") == "3924 mV"


def test_xiaomi_uefi_noise_is_not_reported():
    noise = _CYCLE + """Error Reading the GetDebugPolicyFlagbuqshuai1
Error Get DebugPolicy: Device Error
ERROR: Could not get splash memory region node
Unable to get FpSensor Config, Not Found
Vibrator protocol locating failed!
"""
    shown = [f for f in _parse(noise).get("faults_detected", [])
             if f.get("confidence", 0) >= 50]
    assert not [f for f in shown if f["name"] == "Boot Log Error"], shown


def test_uvlo_still_reported_when_later_cycles_recover():
    # The 12:58 capture: dead first boot, healthy by the fourth. The shutdown
    # happened, so it must still be reported even though VBAT now reads fine.
    text = (_PBL + _CYCLE + "PM: EntryVbat: 0;\nPM: ExitVbatt: 3648;\n"
            + _PBL + "PM: EntryVbat: 3777;\n")
    assert "Battery UVLO (Under-Voltage Lock-Out)" in _faults(text)


def test_uvlo_reported_once_not_twice():
    names = [f["name"] for f in _parse(_CYCLE).get("faults_detected", [])]
    assert names.count("Battery UVLO (Under-Voltage Lock-Out)") == 1, names


def test_healthy_multi_boot_capture_is_clean():
    # The 13:12 capture: two boots, good voltage, only Xiaomi noise.
    ok = (_PBL.replace("PBL, End", "PBL, End") + """PM: HARD_RESET by KPDPWR
PM: EntryVbat: 3770;
wj---IsPressPwrKeyOn: true
PONReason HARD_RESET 1 KPDPWR 1
Error Reading the GetDebugPolicyFlagbuqshuai1
Error Get DebugPolicy: Device Error
Exit EBS        [ 4451] UEFI End
""")
    shown = [f["name"] for f in _parse(ok).get("faults_detected", [])
             if f.get("confidence", 0) >= 50]
    assert not shown, shown


def test_mediatek_log_does_not_crash_battery_checks():
    # vi_pairs/vbat parsing must not be Qualcomm-scoped.
    mtk = "[PLFM] preloader build\n[BLDR] jump to BL33\nerror: nothing here\n"
    _parse(mtk)  # NameError if the battery checks reference unset locals


# ── config/fault_rules.json rule packs ──

def test_rule_pack_loads_and_merges_platform_onto_common():
    common = DeviceAutoDetector._load_fault_rules("")
    qcom = DeviceAutoDetector._load_fault_rules("qualcomm")
    assert common["faults"], "common pack failed to load"
    assert len(qcom["noise"]) > len(common["noise"]), "platform noise not merged"
    assert any(n == "Battery UVLO (Under-Voltage Lock-Out)"
               for _, n, _, _ in qcom["faults"])


def test_platform_noise_does_not_leak_across_chipsets():
    mtk = DeviceAutoDetector._load_fault_rules("mediatek")["noise"]
    assert not any("DebugPolicy" in n for n in mtk), "Xiaomi UEFI noise leaked into MediaTek"


def test_rules_sorted_so_specific_beats_generic():
    confs = [c for _, _, c, _ in DeviceAutoDetector._load_fault_rules("qualcomm")["faults"]]
    assert confs == sorted(confs, reverse=True), confs


def test_unknown_platform_still_gets_common_rules():
    assert DeviceAutoDetector._load_fault_rules("nonesuch")["faults"]


def test_repair_steps_reach_the_fault():
    f = next(f for f in _parse(_CYCLE).get("faults_detected", [])
             if f["name"].startswith("Battery UVLO"))
    assert f.get("repair_steps"), "repair steps from JSON not attached"


def test_unknown_error_line_stays_below_display_floor():
    odd = _CYCLE + "\nSomeNewThing: error frobnicating widget\n"
    for f in _parse(odd).get("faults_detected", []):
        if f["name"] == "Boot Log Error":
            assert f["confidence"] < 50, f



if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("all ok")
