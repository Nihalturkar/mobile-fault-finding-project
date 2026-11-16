"""
Advanced Audio Subsystem Testing Module for Mobile Repair Technicians.

Performs deep audio diagnostics on a connected Android device via ADB by
querying AudioFlinger, audio policy, ALSA sound cards, mixer controls,
and sysfs nodes.  Identifies audio codec ICs, amplifier ICs, and DAC
chips from a built-in knowledge database of 35+ components, then
evaluates speaker, microphone, headphone jack, and audio routing health.

Results are structured into typed dataclasses that feed the downstream
fault-analysis engine.

Requires: Android Platform Tools (adb) on PATH, USB Debugging enabled.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Progress callback type alias
# ---------------------------------------------------------------------------
ProgressCallback = Optional[Callable[[float, str], None]]


# ---------------------------------------------------------------------------
#  Knowledge databases — Audio Codec / Amplifier / DAC ICs
# ---------------------------------------------------------------------------

KNOWN_AUDIO_ICS: Dict[str, Dict[str, Any]] = {
    # ── Qualcomm Audio Codecs ──
    "WCD9380": {
        "manufacturer": "Qualcomm",
        "type": "Codec",
        "description": "Qualcomm Aqstic WCD9380 Hi-Fi Audio Codec (SM8250/8350)",
        "max_sample_rate": 384000,
        "bit_depth": 32,
        "channels": 8,
        "common_failures": [
            "No audio output — codec not initialising after board rework",
            "Distorted earpiece — WCD9380 HPHL/HPHR DAC path degradation",
            "Microphone path failure — TX macro DMA timeout",
            "Codec firmware crash on call connect — slimbus reset required",
        ],
    },
    "WCD9385": {
        "manufacturer": "Qualcomm",
        "type": "Codec",
        "description": "Qualcomm Aqstic WCD9385 Hi-Fi Audio Codec (SM8450/8550)",
        "max_sample_rate": 384000,
        "bit_depth": 32,
        "channels": 8,
        "common_failures": [
            "Audio glitch during handoff between speaker and earpiece",
            "WCD9385 slimbus communication failure after drop damage",
            "Low volume on earpiece — HPHL gain register corruption",
            "Codec DSP watchdog timeout during Hi-Res playback",
        ],
    },
    "WCD9370": {
        "manufacturer": "Qualcomm",
        "type": "Codec",
        "description": "Qualcomm Aqstic WCD9370 Mid-Range Audio Codec (SM7150/7250)",
        "max_sample_rate": 192000,
        "bit_depth": 24,
        "channels": 4,
        "common_failures": [
            "Earpiece audio cuts out intermittently — loose BGA solder joint",
            "Microphone static noise — AMIC bias voltage drift",
            "No sound after water damage — codec power rail short",
        ],
    },
    "WCD9375": {
        "manufacturer": "Qualcomm",
        "type": "Codec",
        "description": "Qualcomm Aqstic WCD9375 Mid-Range Audio Codec (SM7325/7350)",
        "max_sample_rate": 192000,
        "bit_depth": 24,
        "channels": 4,
        "common_failures": [
            "One-sided earpiece audio — headphone detect pin damaged",
            "Buzzing noise on speaker — codec DAC clock jitter",
            "Voice call audio dropout — DMA underrun on TX path",
        ],
    },
    "WCD9340": {
        "manufacturer": "Qualcomm",
        "type": "Codec",
        "description": "Qualcomm Aqstic WCD9340 Audio Codec (SDM845)",
        "max_sample_rate": 384000,
        "bit_depth": 32,
        "channels": 8,
        "common_failures": [
            "Audio IC not detected after motherboard repair",
            "Slimbus enumeration failure — check MCLK crystal",
            "Headphone detection stuck — MBHC block register fault",
        ],
    },
    "WCD9341": {
        "manufacturer": "Qualcomm",
        "type": "Codec",
        "description": "Qualcomm Aqstic WCD9341 Audio Codec (SDM845 variant)",
        "max_sample_rate": 384000,
        "bit_depth": 32,
        "channels": 8,
        "common_failures": [
            "Identical to WCD9340 failure modes",
            "Codec power-on sequence failure — check VDDA supply",
            "MBHC headphone insertion detection intermittent",
        ],
    },
    "WCD9335": {
        "manufacturer": "Qualcomm",
        "type": "Codec",
        "description": "Qualcomm Aqstic WCD9335 (Tasha) Audio Codec (MSM8996/8998)",
        "max_sample_rate": 192000,
        "bit_depth": 24,
        "channels": 8,
        "common_failures": [
            "No audio — Tasha codec not responding on slimbus",
            "Headphone jack detection failure — MBHC calibration lost",
            "Microphone gain stuck at minimum — MIC BIAS LDO damaged",
        ],
    },
    # ── Qualcomm Smart Speaker Amplifiers ──
    "WSA8835": {
        "manufacturer": "Qualcomm",
        "type": "Amplifier",
        "description": "Qualcomm WSA8835 Smart Speaker Amplifier (Class-D, 2W)",
        "max_sample_rate": 192000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "Speaker not working — WSA8835 soundwire enumeration failure",
            "Speaker distortion at high volume — thermal shutdown triggering",
            "Popping noise on speaker enable — power sequencing fault",
            "Low speaker volume — amplifier gain set to minimum after reset",
        ],
    },
    "WSA8830": {
        "manufacturer": "Qualcomm",
        "type": "Amplifier",
        "description": "Qualcomm WSA8830 Smart Speaker Amplifier (Class-D, 1W)",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "Speaker cuts out during loud playback — OCP protection",
            "WSA8830 not enumerating on soundwire bus",
            "Intermittent speaker crackling — loose flex cable connection",
        ],
    },
    "WSA8815": {
        "manufacturer": "Qualcomm",
        "type": "Amplifier",
        "description": "Qualcomm WSA8815 Smart Speaker Amplifier (Class-D, 1.5W)",
        "max_sample_rate": 192000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "No speaker audio — WSA8815 I2S/soundwire connection broken",
            "Speaker clicks on call connect/disconnect",
            "Amplifier thermal throttling in warm environments",
        ],
    },
    "WSA8810": {
        "manufacturer": "Qualcomm",
        "type": "Amplifier",
        "description": "Qualcomm WSA8810 Smart Speaker Amplifier (Class-D, 1W)",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "Speaker completely dead — WSA8810 IC failure from ESD",
            "Low speaker output — gain registers not configured",
            "WSA8810 overheating — check speaker coil impedance",
        ],
    },
    # ── Realtek Audio Codecs ──
    "ALC5682": {
        "manufacturer": "Realtek",
        "type": "Codec",
        "description": "Realtek ALC5682 Low-Power Audio Codec with Headphone Amp",
        "max_sample_rate": 192000,
        "bit_depth": 24,
        "channels": 2,
        "common_failures": [
            "Headphone output crackling — DAC clock source unstable",
            "Jack detection unreliable — RT5682 IRQ line floating",
            "No audio on resume from sleep — codec lost I2C state",
        ],
    },
    "ALC5665": {
        "manufacturer": "Realtek",
        "type": "Codec",
        "description": "Realtek ALC5665 Audio Codec (budget smartphones)",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 2,
        "common_failures": [
            "Headphone audio distorted — output coupling capacitor failure",
            "Codec I2C address conflict with other peripherals",
            "Microphone bias voltage out of spec — external MEMS mic affected",
        ],
    },
    "ALC298": {
        "manufacturer": "Realtek",
        "type": "Codec",
        "description": "Realtek ALC298 HD Audio Codec (tablets, Chromebooks)",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 2,
        "common_failures": [
            "No audio after firmware update — codec verb table mismatch",
            "Headphone jack loose — ALC298 MBHC detect pin bent",
            "Speaker muted after dock/undock — audio route not restored",
        ],
    },
    # ── Cirrus Logic Amplifiers and Codecs ──
    "CS35L41": {
        "manufacturer": "Cirrus Logic",
        "type": "Amplifier",
        "description": "Cirrus Logic CS35L41 Boosted Class-D Smart Amplifier (11W)",
        "max_sample_rate": 192000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "Speaker protection tripping at normal volume — calibration lost",
            "CS35L41 firmware load failure — SPI flash corrupt",
            "Amplifier not powering up — VBST boost converter damaged",
            "Loud pop/click on amplifier enable — power sequence timing",
        ],
    },
    "CS35L45": {
        "manufacturer": "Cirrus Logic",
        "type": "Amplifier",
        "description": "Cirrus Logic CS35L45 Boosted Class-D Amplifier (next-gen, 12W)",
        "max_sample_rate": 384000,
        "bit_depth": 32,
        "channels": 1,
        "common_failures": [
            "Speaker protection mode stuck — recalibrate impedance model",
            "CS35L45 DSP firmware crash during haptic feedback playback",
            "Boost converter failure — no output above 0.5W",
        ],
    },
    "CS47L35": {
        "manufacturer": "Cirrus Logic",
        "type": "Codec",
        "description": "Cirrus Logic CS47L35 (Marley) Smart Codec with DSP",
        "max_sample_rate": 192000,
        "bit_depth": 24,
        "channels": 4,
        "common_failures": [
            "Voice wakeword detection failure — DSP firmware not loaded",
            "Audio routing broken after OTA update — mixer path mismatch",
            "CS47L35 SPI communication timeout — clock source issue",
        ],
    },
    "CS47L63": {
        "manufacturer": "Cirrus Logic",
        "type": "Codec",
        "description": "Cirrus Logic CS47L63 Smart Codec with Haptics",
        "max_sample_rate": 192000,
        "bit_depth": 24,
        "channels": 4,
        "common_failures": [
            "Haptic feedback stopped — CS47L63 haptic actuator driver fault",
            "Audio distortion during haptic events — resource contention",
            "Codec lockup during concurrent audio + haptic streams",
        ],
    },
    "CS47L92": {
        "manufacturer": "Cirrus Logic",
        "type": "Codec",
        "description": "Cirrus Logic CS47L92 Hi-Fi Codec with dual DSP",
        "max_sample_rate": 384000,
        "bit_depth": 32,
        "channels": 8,
        "common_failures": [
            "Hi-Res audio playback glitches — DSP memory overflow",
            "Dual DSP synchronisation failure during ANC processing",
            "CS47L92 overheating during concurrent recording + playback",
        ],
    },
    "CS43130": {
        "manufacturer": "Cirrus Logic",
        "type": "DAC",
        "description": "Cirrus Logic CS43130 Hi-Fi DAC (LG V-series phones)",
        "max_sample_rate": 384000,
        "bit_depth": 32,
        "channels": 2,
        "common_failures": [
            "Hi-Fi DAC mode not activating — CS43130 not detected on I2C",
            "DSD playback failure — DoP framing error",
            "DAC output clipping — voltage reference drift after aging",
            "Headphone impedance detection wrong — quad DAC not engaging",
        ],
    },
    # ── Texas Instruments Amplifiers ──
    "TAS2780": {
        "manufacturer": "Texas Instruments",
        "type": "Amplifier",
        "description": "TI TAS2780 Mono Class-D Smart Amplifier (7.1W, digital input)",
        "max_sample_rate": 192000,
        "bit_depth": 32,
        "channels": 1,
        "common_failures": [
            "Speaker protection mode — recalibrate TAS2780 impedance model",
            "I2C NACK on TAS2780 — address pin soldering issue",
            "Amplifier clicking noise — PVDD supply ripple too high",
        ],
    },
    "TAS2764": {
        "manufacturer": "Texas Instruments",
        "type": "Amplifier",
        "description": "TI TAS2764 Mono Class-D Amplifier (5.7W, I2S/TDM input)",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "Speaker output weak — TAS2764 gain not set after cold boot",
            "Amplifier enters thermal shutdown repeatedly — check heatsink",
            "I2S framing error — BCLK/LRCK ratio mismatch with SoC",
        ],
    },
    "TAS2562": {
        "manufacturer": "Texas Instruments",
        "type": "Amplifier",
        "description": "TI TAS2562 Mono Class-D Amplifier with speaker protection",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "Speaker distortion at mid-range frequencies — resonance issue",
            "TAS2562 not responding on I2C after ESD event",
            "Over-current protection latching — speaker coil damaged",
        ],
    },
    "TAS2557": {
        "manufacturer": "Texas Instruments",
        "type": "Amplifier",
        "description": "TI TAS2557 Class-D Amplifier with DSP (Google Pixel 2)",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "Speaker buzz at low volume — TAS2557 DSP firmware mismatch",
            "Amplifier not initialising — firmware blob missing from /vendor",
            "Speaker protection tripping early — impedance model stale",
        ],
    },
    # ── Maxim Integrated Amplifiers ──
    "MAX98390": {
        "manufacturer": "Maxim Integrated",
        "type": "Amplifier",
        "description": "Maxim MAX98390 Class-D DSP Amplifier with IV sense (10W)",
        "max_sample_rate": 192000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "Speaker IV sense calibration failure — open speaker connection",
            "MAX98390 DSP firmware load error on boot",
            "Amplifier output muted — safety flag set after brown-out",
        ],
    },
    "MAX98373": {
        "manufacturer": "Maxim Integrated",
        "type": "Amplifier",
        "description": "Maxim MAX98373 Class-D Smart Amplifier (5W, SoundWire)",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "SoundWire bus enumeration failure — clock not stable",
            "Speaker volume capped at 50% — thermal limit register wrong",
            "MAX98373 brownout detection false triggers on battery sag",
        ],
    },
    "MAX98927": {
        "manufacturer": "Maxim Integrated",
        "type": "Amplifier",
        "description": "Maxim MAX98927 Class-D Speaker Amplifier (5W, I2S)",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "No speaker output — MAX98927 PVDD rail missing",
            "Amplifier oscillation at certain frequencies",
            "Speaker crackling — decoupling capacitor failure on PVDD",
        ],
    },
    # ── NXP Speaker Amplifiers ──
    "TFA9874": {
        "manufacturer": "NXP Semiconductors",
        "type": "Amplifier",
        "description": "NXP TFA9874 Smart Speaker Amplifier with DSP (Xiaomi, Samsung)",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "Speaker protection tripping — TFA9874 calibration data corrupt",
            "Amplifier not starting — I2C pull-up resistor missing",
            "Audio DSP crash during concurrent notification + media playback",
            "Low speaker output after screen replacement — flex cable issue",
        ],
    },
    "TFA9873": {
        "manufacturer": "NXP Semiconductors",
        "type": "Amplifier",
        "description": "NXP TFA9873 Smart Speaker Amplifier (cost-optimised)",
        "max_sample_rate": 48000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "Speaker clicks during volume ramp — slew rate too fast",
            "TFA9873 overheating — PCB thermal via insufficient",
            "Audio dropout during Bluetooth + speaker concurrent output",
        ],
    },
    "TFA9894": {
        "manufacturer": "NXP Semiconductors",
        "type": "Amplifier",
        "description": "NXP TFA9894 Smart Speaker Amplifier with IV sense",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 1,
        "common_failures": [
            "Speaker protection stuck — recalibrate after speaker swap",
            "TFA9894 firmware version mismatch with kernel driver",
            "Amplifier thermal shutdown loop — check thermal pad contact",
        ],
    },
    "TFA9895": {
        "manufacturer": "NXP Semiconductors",
        "type": "Amplifier",
        "description": "NXP TFA9895 Boosted Class-D Speaker Amplifier",
        "max_sample_rate": 48000,
        "bit_depth": 16,
        "channels": 1,
        "common_failures": [
            "No audio — TFA9895 boost converter not starting",
            "Speaker distortion — aging electrolytic cap on PVDD",
            "I2C communication failure after water damage to connector",
        ],
    },
    # ── Analog Devices ──
    "SSM3582": {
        "manufacturer": "Analog Devices",
        "type": "Amplifier",
        "description": "Analog Devices SSM3582 Class-D Amplifier (2x31W stereo)",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 2,
        "common_failures": [
            "One channel dead — SSM3582 output MOSFET failure",
            "Amplifier enters fault mode — over-temperature or short",
            "Audible hiss on idle — input stage noise floor too high",
        ],
    },
    "ADAU1761": {
        "manufacturer": "Analog Devices",
        "type": "Codec",
        "description": "Analog Devices ADAU1761 Low-Power Stereo Codec with DSP",
        "max_sample_rate": 96000,
        "bit_depth": 24,
        "channels": 2,
        "common_failures": [
            "ADAU1761 not booting — SigmaDSP firmware load timeout",
            "Record path noisy — ADC input bias resistor damaged",
            "Playback muted — DAC output register stuck at zero",
        ],
    },
    # ── AKM (Asahi Kasei Microdevices) DACs ──
    "AK4376": {
        "manufacturer": "AKM",
        "type": "DAC",
        "description": "AKM AK4376 32-bit DAC with Headphone Amplifier",
        "max_sample_rate": 384000,
        "bit_depth": 32,
        "channels": 2,
        "common_failures": [
            "Hi-Fi DAC not engaging — AK4376 I2C init sequence failure",
            "Headphone output channel imbalance — volume register mismatch",
            "AK4376 power-on pop — charge pump startup timing",
        ],
    },
    "AK4377": {
        "manufacturer": "AKM",
        "type": "DAC",
        "description": "AKM AK4377 32-bit DAC with Headphone Amplifier (low power)",
        "max_sample_rate": 384000,
        "bit_depth": 32,
        "channels": 2,
        "common_failures": [
            "AK4377 not detected — I2C address pin floating",
            "Distorted output at high sample rates — MCLK unstable",
            "DAC click/pop on stream start — soft-ramp not configured",
        ],
    },
    "AK4497": {
        "manufacturer": "AKM",
        "type": "DAC",
        "description": "AKM AK4497EQ Flagship 32-bit Velvet Sound DAC",
        "max_sample_rate": 768000,
        "bit_depth": 32,
        "channels": 2,
        "common_failures": [
            "DSD512 playback fails — I2S interface cannot sustain bandwidth",
            "AK4497 reference voltage drift — THD+N degradation over time",
            "DAC output DC offset — coupling capacitor leakage",
        ],
    },
}

# Mapping of common kernel/driver string fragments to IC names
IC_IDENTIFICATION_PATTERNS: Dict[str, str] = {
    "wcd938": "WCD9380",
    "wcd9385": "WCD9385",
    "wcd937": "WCD9370",
    "wcd9375": "WCD9375",
    "wcd934": "WCD9340",
    "wcd9341": "WCD9341",
    "wcd9335": "WCD9335",
    "tasha": "WCD9335",
    "tavil": "WCD9340",
    "bolero": "WCD9370",
    "wsa883": "WSA8835",
    "wsa8835": "WSA8835",
    "wsa8830": "WSA8830",
    "wsa881": "WSA8815",
    "wsa8815": "WSA8815",
    "wsa8810": "WSA8810",
    "rt5682": "ALC5682",
    "alc5682": "ALC5682",
    "rt5665": "ALC5665",
    "alc5665": "ALC5665",
    "alc298": "ALC298",
    "rt298": "ALC298",
    "cs35l41": "CS35L41",
    "cs35l45": "CS35L45",
    "cs47l35": "CS47L35",
    "marley": "CS47L35",
    "cs47l63": "CS47L63",
    "cs47l92": "CS47L92",
    "cs43130": "CS43130",
    "tas2780": "TAS2780",
    "tas2764": "TAS2764",
    "tas2562": "TAS2562",
    "tas2557": "TAS2557",
    "max98390": "MAX98390",
    "max98373": "MAX98373",
    "max98927": "MAX98927",
    "tfa9874": "TFA9874",
    "tfa9873": "TFA9873",
    "tfa9894": "TFA9894",
    "tfa9895": "TFA9895",
    "tfa98xx": "TFA9874",
    "ssm3582": "SSM3582",
    "adau1761": "ADAU1761",
    "ak4376": "AK4376",
    "ak4377": "AK4377",
    "ak4497": "AK4497",
}

# Audio route type descriptions
AUDIO_ROUTE_TYPES: Dict[str, str] = {
    "speaker": "Built-in loudspeaker",
    "earpiece": "Earpiece receiver for calls",
    "headset": "Wired headset (3.5mm or USB-C with mic)",
    "headphone": "Wired headphones (no mic)",
    "bt_sco": "Bluetooth SCO (voice calls)",
    "bt_a2dp": "Bluetooth A2DP (media streaming)",
    "usb_device": "USB audio device (DAC/headset)",
    "hdmi": "HDMI audio output",
    "telephony": "Telephony downlink/uplink",
    "fm_tuner": "FM radio tuner input",
}


# ---------------------------------------------------------------------------
#  Data classes — test results
# ---------------------------------------------------------------------------

@dataclass
class AudioCodecInfo:
    """Identified audio codec IC and its operating parameters."""
    name: str = ""
    manufacturer: str = ""
    codec_type: str = ""            # Codec, Amplifier, DAC
    sample_rate: str = ""
    bit_depth: str = ""
    channels: str = ""
    status: str = "Unknown"
    driver_name: str = ""
    firmware_version: str = ""
    detected_ics: List[str] = field(default_factory=list)


@dataclass
class SpeakerInfo:
    """Built-in loudspeaker subsystem status."""
    present: bool = False
    count: int = 0
    amplifier_ic: str = ""
    amplifier_manufacturer: str = ""
    impedance: str = ""
    max_power: str = ""
    status: str = "Unknown"
    warnings: List[str] = field(default_factory=list)


@dataclass
class MicrophoneInfo:
    """Microphone subsystem status."""
    present: bool = False
    count: int = 0
    types: List[str] = field(default_factory=list)  # primary, secondary, noise_cancel
    input_sources: List[str] = field(default_factory=list)
    status: str = "Unknown"
    warnings: List[str] = field(default_factory=list)


@dataclass
class HeadphoneInfo:
    """Headphone / headset jack subsystem status."""
    jack_present: bool = False
    jack_type: str = ""             # 3.5mm, USB-C, not_present
    connected: bool = False
    dac_ic: str = ""
    dac_manufacturer: str = ""
    mbhc_status: str = ""           # Microphone Bias Headphone Controller
    status: str = "Unknown"


@dataclass
class AudioTestResult:
    """Top-level container returned by ``detect_audio_status``."""
    connected: bool = False
    error: Optional[str] = None
    codec_info: AudioCodecInfo = field(default_factory=AudioCodecInfo)
    speaker_info: SpeakerInfo = field(default_factory=SpeakerInfo)
    microphone_info: MicrophoneInfo = field(default_factory=MicrophoneInfo)
    headphone_info: HeadphoneInfo = field(default_factory=HeadphoneInfo)
    audio_routes: List[str] = field(default_factory=list)
    volume_levels: Dict[str, str] = field(default_factory=dict)
    sound_cards: List[str] = field(default_factory=list)
    pcm_devices: List[str] = field(default_factory=list)
    overall_health: str = "Unknown"
    health_score: int = 0
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
#  ADB helpers
# ---------------------------------------------------------------------------

def _adb(cmd: str, timeout: int = 10) -> str:
    """Execute ``adb shell <cmd>`` and return stdout (empty on failure)."""
    full_cmd = f"adb shell {cmd}"
    logger.debug("ADB >>> %s", full_cmd)
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
        )
        output = proc.stdout.strip()
        if proc.returncode != 0:
            err = proc.stderr.strip()
            logger.debug("ADB command failed (rc=%d): %s", proc.returncode, err)
            return ""
        return output
    except FileNotFoundError:
        logger.error("adb binary not found on PATH")
        return ""
    except subprocess.TimeoutExpired:
        logger.error("ADB command timed out after %ds: %s", timeout, full_cmd)
        return ""
    except Exception as exc:
        logger.error("ADB error: %s", exc)
        return ""


def _run_adb_host(args: List[str], timeout: int = 10) -> Tuple[bool, str]:
    """Execute an ADB host-level command (e.g. ``adb devices``)."""
    cmd = ["adb"] + args
    logger.debug("ADB host >>> %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = proc.stdout.strip()
        if proc.returncode != 0:
            return False, proc.stderr.strip()
        return True, output
    except FileNotFoundError:
        return False, "adb not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "adb command timed out"
    except Exception as exc:
        return False, str(exc)


def _notify(callback: ProgressCallback, pct: float, msg: str) -> None:
    """Fire the progress callback if provided."""
    if callback is not None:
        try:
            callback(pct, msg)
        except Exception:
            logger.debug("Progress callback raised; ignoring", exc_info=True)


def _parse_int(value: str, default: int = 0) -> int:
    """Safely parse an integer from a raw string."""
    try:
        cleaned = re.sub(r"[^\d\-]", "", value.split("\n")[0].strip())
        return int(cleaned) if cleaned else default
    except (ValueError, IndexError):
        return default


# ---------------------------------------------------------------------------
#  Step 1 — ADB connection check
# ---------------------------------------------------------------------------

def _check_adb_connection(callback: ProgressCallback) -> Tuple[bool, str]:
    """Verify ADB connectivity.  Returns ``(connected, error_or_serial)``."""
    _notify(callback, 0.0, "Checking ADB connection...")
    ok, output = _run_adb_host(["devices"])
    if not ok:
        return False, f"Cannot run 'adb devices': {output}"

    lines = [ln for ln in output.splitlines() if "\tdevice" in ln]
    if not lines:
        unauthorized = [ln for ln in output.splitlines() if "\tunauthorized" in ln]
        if unauthorized:
            return False, "Device connected but USB Debugging not authorized"
        return False, "No ADB device detected"

    serial = lines[0].split("\t")[0]
    logger.info("ADB device connected: %s", serial)
    _notify(callback, 3.0, f"ADB connected — serial {serial}")
    return True, serial


# ---------------------------------------------------------------------------
#  Step 2 — Collect raw audio data from device
# ---------------------------------------------------------------------------

def _collect_audio_flinger(callback: ProgressCallback) -> str:
    """Dump ``media.audio_flinger`` for hardware info."""
    _notify(callback, 5.0, "Reading AudioFlinger state...")
    return _adb("dumpsys media.audio_flinger", timeout=15)


def _collect_audio_policy(callback: ProgressCallback) -> str:
    """Dump ``media.audio_policy`` for route/device config."""
    _notify(callback, 8.0, "Reading audio policy...")
    return _adb("dumpsys media.audio_policy", timeout=15)


def _collect_dumpsys_audio(callback: ProgressCallback) -> str:
    """Dump ``audio`` service for policies, routes, and devices."""
    _notify(callback, 11.0, "Reading dumpsys audio...")
    return _adb("dumpsys audio", timeout=15)


def _collect_sound_cards(callback: ProgressCallback) -> str:
    """Read ``/proc/asound/cards`` for ALSA sound card listing."""
    _notify(callback, 14.0, "Reading ALSA sound cards...")
    return _adb("cat /proc/asound/cards")


def _collect_pcm_devices(callback: ProgressCallback) -> str:
    """Read ``/proc/asound/pcm`` for PCM device listing."""
    _notify(callback, 16.0, "Reading ALSA PCM devices...")
    return _adb("cat /proc/asound/pcm")


def _collect_asound_codecs(callback: ProgressCallback) -> str:
    """Read ``/proc/asound/codecs`` (may not exist on all devices)."""
    _notify(callback, 17.0, "Reading ALSA codecs...")
    return _adb("cat /proc/asound/codecs 2>/dev/null")


def _collect_tinymix(callback: ProgressCallback) -> str:
    """Run ``tinymix`` to list all mixer controls."""
    _notify(callback, 19.0, "Reading tinymix controls...")
    return _adb("tinymix 2>/dev/null")


def _collect_audio_properties(callback: ProgressCallback) -> Dict[str, str]:
    """Read audio-related system properties."""
    _notify(callback, 21.0, "Reading audio system properties...")
    props: Dict[str, str] = {}
    prop_keys = [
        "ro.hardware.audio",
        "ro.audio.monitorRotation",
        "ro.hardware.audio.primary",
        "ro.config.media_vol_steps",
        "ro.config.alarm_vol_steps",
        "persist.audio.fluence.voicecall",
        "persist.audio.fluence.voicerec",
        "persist.audio.fluence.speaker",
        "ro.vendor.audio.sdk.fluencetype",
        "vendor.audio.offload.buffer.size.kb",
        "vendor.audio.hal.output.suspend.supported",
        "ro.audio.usb.period_us",
        "persist.bluetooth.a2dp_offload.disabled",
        "vendor.audio.feature.a2dp_offload.enable",
    ]
    for key in prop_keys:
        val = _adb(f"getprop {key}")
        if val:
            props[key] = val
    return props


def _collect_sound_class(callback: ProgressCallback) -> Tuple[List[str], Dict[str, str]]:
    """List ``/sys/class/sound/`` entries and read their IDs."""
    _notify(callback, 23.0, "Reading /sys/class/sound/ entries...")
    listing_raw = _adb("ls /sys/class/sound/ 2>/dev/null")
    entries = [e.strip() for e in listing_raw.splitlines() if e.strip()]

    ids: Dict[str, str] = {}
    for entry in entries:
        id_val = _adb(f"cat /sys/class/sound/{entry}/id 2>/dev/null")
        if id_val:
            ids[entry] = id_val
    return entries, ids


# ---------------------------------------------------------------------------
#  Step 3 — Identify audio codec ICs
# ---------------------------------------------------------------------------

def _identify_codec_ics(
    audio_flinger: str,
    dumpsys_audio: str,
    sound_cards: str,
    pcm_devices: str,
    asound_codecs: str,
    tinymix: str,
    audio_props: Dict[str, str],
    sound_class_ids: Dict[str, str],
    callback: ProgressCallback,
) -> AudioCodecInfo:
    """Identify the audio codec, amplifier, and DAC ICs from collected data."""
    _notify(callback, 28.0, "Identifying audio codec ICs...")
    codec = AudioCodecInfo()

    # Combine all text sources for pattern matching
    combined = "\n".join([
        audio_flinger,
        dumpsys_audio,
        sound_cards,
        pcm_devices,
        asound_codecs,
        tinymix,
        " ".join(audio_props.values()),
        " ".join(sound_class_ids.values()),
    ]).lower()

    detected_ic_names: List[str] = []

    # Match against known IC patterns
    for pattern, ic_name in IC_IDENTIFICATION_PATTERNS.items():
        if pattern.lower() in combined:
            if ic_name not in detected_ic_names:
                detected_ic_names.append(ic_name)

    codec.detected_ics = detected_ic_names

    # Pick the primary codec (prefer Codec type over Amplifier/DAC)
    primary_codec = ""
    primary_amp = ""
    primary_dac = ""

    for ic_name in detected_ic_names:
        ic_info = KNOWN_AUDIO_ICS.get(ic_name, {})
        ic_type = ic_info.get("type", "")
        if ic_type == "Codec" and not primary_codec:
            primary_codec = ic_name
        elif ic_type == "Amplifier" and not primary_amp:
            primary_amp = ic_name
        elif ic_type == "DAC" and not primary_dac:
            primary_dac = ic_name

    # The primary IC is the codec if found, otherwise the first detected
    primary_ic = primary_codec or primary_dac or primary_amp
    if not primary_ic and detected_ic_names:
        primary_ic = detected_ic_names[0]

    if primary_ic and primary_ic in KNOWN_AUDIO_ICS:
        ic_data = KNOWN_AUDIO_ICS[primary_ic]
        codec.name = primary_ic
        codec.manufacturer = ic_data["manufacturer"]
        codec.codec_type = ic_data["type"]
        codec.sample_rate = f"{ic_data.get('max_sample_rate', 0)} Hz"
        codec.bit_depth = f"{ic_data.get('bit_depth', 0)}-bit"
        codec.channels = str(ic_data.get("channels", 0))
    elif detected_ic_names:
        codec.name = detected_ic_names[0]
        codec.manufacturer = KNOWN_AUDIO_ICS.get(
            detected_ic_names[0], {}
        ).get("manufacturer", "Unknown")

    # Try to extract driver name from audio_flinger output
    driver_match = re.search(
        r"(?:HAL|Hardware)\s*(?:module|library)\s*[:=]\s*(.+)",
        audio_flinger,
        re.IGNORECASE,
    )
    if driver_match:
        codec.driver_name = driver_match.group(1).strip()[:80]

    # Extract hardware audio property
    hw_audio = audio_props.get("ro.hardware.audio", "")
    if hw_audio and not codec.driver_name:
        codec.driver_name = hw_audio

    # Parse sample rate from AudioFlinger
    sr_match = re.search(r"(?:sample\s*rate|sampleRate)\s*[:=]\s*(\d+)", audio_flinger)
    if sr_match and not codec.sample_rate:
        codec.sample_rate = f"{sr_match.group(1)} Hz"

    # Parse bit depth / format from AudioFlinger
    fmt_match = re.search(
        r"(?:format|Format)\s*[:=]\s*(AUDIO_FORMAT_PCM_\d+_BIT|\d+[_-]bit|S\d+_LE)",
        audio_flinger,
        re.IGNORECASE,
    )
    if fmt_match and not codec.bit_depth:
        codec.bit_depth = fmt_match.group(1)

    # Parse channel count from AudioFlinger
    ch_match = re.search(r"(?:channel\s*count|channelCount)\s*[:=]\s*(\d+)", audio_flinger)
    if ch_match and not codec.channels:
        codec.channels = ch_match.group(1)

    # Extract firmware version (Cirrus Logic, NXP often expose this)
    fw_match = re.search(
        r"(?:firmware|fw)[_\s]*(?:version|ver|rev)\s*[:=]\s*([\w.]+)",
        combined,
        re.IGNORECASE,
    )
    if fw_match:
        codec.firmware_version = fw_match.group(1)

    # Determine status
    if codec.name:
        codec.status = "Detected"
    elif detected_ic_names:
        codec.status = "Partially Detected"
    else:
        # Check if we at least see generic audio hardware
        if "audio" in combined and ("hal" in combined or "flinger" in combined):
            codec.status = "Generic Audio HAL (IC not identified)"
        else:
            codec.status = "Not Detected"

    _notify(callback, 35.0, f"Audio codec: {codec.name or 'Unknown'} "
                            f"({codec.manufacturer}), {len(detected_ic_names)} IC(s) found")
    return codec


# ---------------------------------------------------------------------------
#  Step 4 — Speaker subsystem analysis
# ---------------------------------------------------------------------------

def _analyze_speakers(
    audio_flinger: str,
    dumpsys_audio: str,
    tinymix: str,
    codec_info: AudioCodecInfo,
    callback: ProgressCallback,
) -> SpeakerInfo:
    """Analyze the built-in speaker subsystem."""
    _notify(callback, 40.0, "Analyzing speaker subsystem...")
    spk = SpeakerInfo()

    combined = (audio_flinger + "\n" + dumpsys_audio + "\n" + tinymix).lower()

    # Check if speaker output device is present in audio policy
    speaker_patterns = [
        r"speaker",
        r"spk",
        r"loudspeaker",
        r"AUDIO_DEVICE_OUT_SPEAKER",
    ]
    for pattern in speaker_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            spk.present = True
            break

    if not spk.present:
        spk.status = "Not Detected"
        _notify(callback, 45.0, "Speaker: NOT DETECTED")
        return spk

    # Count speakers — look for stereo speaker indicators
    stereo_patterns = [
        r"stereo[\s_]*speaker",
        r"spk[_\s]*l.*spk[_\s]*r",
        r"speaker[_\s]*left.*speaker[_\s]*right",
        r"dual[\s_]*speaker",
        r"wsa883[05].*wsa883[05]",  # Two WSA amplifiers
        r"tfa98\d\d.*tfa98\d\d",    # Two TFA amplifiers
    ]
    is_stereo = False
    for pattern in stereo_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            is_stereo = True
            break

    # Also check tinymix for L/R speaker mixer controls
    if "spkl" in combined and "spkr" in combined:
        is_stereo = True
    if "speaker left" in combined and "speaker right" in combined:
        is_stereo = True

    spk.count = 2 if is_stereo else 1

    # Identify amplifier IC from detected ICs
    for ic_name in codec_info.detected_ics:
        ic_data = KNOWN_AUDIO_ICS.get(ic_name, {})
        if ic_data.get("type") == "Amplifier":
            spk.amplifier_ic = ic_name
            spk.amplifier_manufacturer = ic_data.get("manufacturer", "")
            spk.max_power = f"{ic_data.get('description', '').split('(')[-1].rstrip(')')}" \
                if "(" in ic_data.get("description", "") else ""
            break

    # Try to extract speaker impedance from tinymix or driver data
    impedance_match = re.search(
        r"(?:speaker|spk)\s*(?:impedance|imp|re)\s*[:=]\s*([\d.]+)\s*(?:ohm)?",
        combined,
        re.IGNORECASE,
    )
    if impedance_match:
        spk.impedance = f"{impedance_match.group(1)} ohm"
    else:
        # Default typical smartphone speaker impedance
        spk.impedance = "Typical 4-8 ohm (not directly read)"

    # Generate warnings
    if not spk.amplifier_ic:
        spk.warnings.append("Speaker amplifier IC not identified")

    # Check for mute or low-volume indicators in tinymix
    mute_patterns = [
        r"spk.*mute.*1",
        r"speaker.*mute.*on",
        r"speaker.*switch.*off",
        r"spk.*enable.*0",
    ]
    for pattern in mute_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            spk.warnings.append("Speaker may be muted in mixer controls")
            break

    # Check for thermal/protection warnings
    protection_patterns = [
        r"thermal\s*shutdown",
        r"over[\s_]*current\s*protect",
        r"speaker\s*protection\s*(?:trip|active|engaged)",
        r"ocp\s*fault",
    ]
    for pattern in protection_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            spk.warnings.append("Speaker amplifier protection/fault flag detected")
            break

    # Determine status
    if spk.warnings:
        spk.status = "Warning"
    else:
        spk.status = "OK"

    _notify(callback, 47.0, f"Speaker: {spk.status} — {spk.count} speaker(s), "
                            f"amp={spk.amplifier_ic or 'unknown'}")
    return spk


# ---------------------------------------------------------------------------
#  Step 5 — Microphone subsystem analysis
# ---------------------------------------------------------------------------

def _analyze_microphones(
    audio_flinger: str,
    dumpsys_audio: str,
    tinymix: str,
    callback: ProgressCallback,
) -> MicrophoneInfo:
    """Analyze the microphone subsystem."""
    _notify(callback, 50.0, "Analyzing microphone subsystem...")
    mic = MicrophoneInfo()

    combined = (audio_flinger + "\n" + dumpsys_audio + "\n" + tinymix).lower()

    # Check for microphone presence
    mic_patterns = [
        r"microphone",
        r"AUDIO_DEVICE_IN_BUILTIN_MIC",
        r"AUDIO_DEVICE_IN_BACK_MIC",
        r"built[\s_-]*in[\s_-]*mic",
        r"amic",
        r"dmic",
        r"mic[\s_]*bias",
    ]
    for pattern in mic_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            mic.present = True
            break

    if not mic.present:
        mic.status = "Not Detected"
        _notify(callback, 55.0, "Microphone: NOT DETECTED")
        return mic

    # Identify microphone types
    mic_type_checks = [
        ("primary", [r"primary[\s_]*mic", r"mic[\s_]*1", r"main[\s_]*mic",
                      r"AUDIO_DEVICE_IN_BUILTIN_MIC", r"bottom[\s_]*mic"]),
        ("secondary", [r"secondary[\s_]*mic", r"mic[\s_]*2", r"back[\s_]*mic",
                        r"AUDIO_DEVICE_IN_BACK_MIC", r"top[\s_]*mic"]),
        ("noise_cancel", [r"noise[\s_]*cancel", r"third[\s_]*mic", r"mic[\s_]*3",
                           r"anc[\s_]*mic", r"reference[\s_]*mic"]),
        ("wide_band", [r"wide[\s_]*band[\s_]*mic", r"wb[\s_]*mic"]),
    ]

    for mic_type, patterns in mic_type_checks:
        for pattern in patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                if mic_type not in mic.types:
                    mic.types.append(mic_type)
                break

    # If no specific type detected but mic is present, assume primary
    if not mic.types:
        mic.types.append("primary")

    mic.count = len(mic.types)

    # Detect input sources from audio policy
    input_source_patterns = [
        ("voice_call", r"AUDIO_SOURCE_VOICE_CALL"),
        ("voice_recognition", r"AUDIO_SOURCE_VOICE_RECOGNITION"),
        ("camcorder", r"AUDIO_SOURCE_CAMCORDER"),
        ("mic", r"AUDIO_SOURCE_MIC"),
        ("voice_communication", r"AUDIO_SOURCE_VOICE_COMMUNICATION"),
        ("unprocessed", r"AUDIO_SOURCE_UNPROCESSED"),
    ]
    for source_name, pattern in input_source_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            mic.input_sources.append(source_name)

    # Check for noise suppression / acoustic echo cancellation
    fluence_patterns = [
        r"fluence",
        r"noise[\s_]*suppress",
        r"echo[\s_]*cancel",
        r"aec",
        r"ns[\s_]*enable",
    ]
    has_processing = False
    for pattern in fluence_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            has_processing = True
            break

    # Generate warnings
    # Check for mic bias issues
    bias_fault_patterns = [
        r"mic[\s_]*bias[\s_]*(?:fault|error|fail)",
        r"micb[\s_]*(?:fault|short|open)",
        r"mic[\s_]*detect[\s_]*fail",
    ]
    for pattern in bias_fault_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            mic.warnings.append("Microphone bias voltage fault detected")
            break

    # Check for muted mic
    mic_mute_patterns = [
        r"mic.*mute.*(?:1|on|true)",
        r"tx[\s_]*mute.*(?:1|on|true)",
        r"capture.*mute.*(?:1|on|true)",
    ]
    for pattern in mic_mute_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            mic.warnings.append("Microphone may be muted in mixer")
            break

    # Determine status
    if mic.warnings:
        mic.status = "Warning"
    elif mic.count >= 2 and has_processing:
        mic.status = "OK (with noise processing)"
    elif mic.count >= 1:
        mic.status = "OK"
    else:
        mic.status = "Degraded"

    _notify(callback, 57.0, f"Microphone: {mic.status} — {mic.count} mic(s) "
                            f"({', '.join(mic.types)})")
    return mic


# ---------------------------------------------------------------------------
#  Step 6 — Headphone jack / headset analysis
# ---------------------------------------------------------------------------

def _analyze_headphone_jack(
    audio_flinger: str,
    dumpsys_audio: str,
    tinymix: str,
    codec_info: AudioCodecInfo,
    callback: ProgressCallback,
) -> HeadphoneInfo:
    """Analyze headphone / headset jack subsystem."""
    _notify(callback, 60.0, "Analyzing headphone jack subsystem...")
    hp = HeadphoneInfo()

    combined = (audio_flinger + "\n" + dumpsys_audio + "\n" + tinymix).lower()

    # Check for 3.5mm jack presence
    jack_35mm_patterns = [
        r"headphone[\s_]*jack",
        r"headset[\s_]*jack",
        r"3\.5\s*mm",
        r"hp[\s_]*jack",
        r"AUDIO_DEVICE_OUT_WIRED_HEADPHONE",
        r"AUDIO_DEVICE_OUT_WIRED_HEADSET",
        r"h2w",
        r"mbhc",
        r"jack[\s_]*detect",
        r"headphone\s*detect",
    ]
    for pattern in jack_35mm_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            hp.jack_present = True
            hp.jack_type = "3.5mm"
            break

    # Check for USB-C audio
    usbc_audio_patterns = [
        r"usb[\s_-]*c[\s_]*audio",
        r"usb[\s_]*headset",
        r"AUDIO_DEVICE_OUT_USB_HEADSET",
        r"usb[\s_]*device[\s_]*audio",
    ]
    if not hp.jack_present:
        for pattern in usbc_audio_patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                hp.jack_present = True
                hp.jack_type = "USB-C"
                break

    if not hp.jack_present:
        hp.status = "No headphone jack detected"
        hp.jack_type = "not_present"
        _notify(callback, 65.0, "Headphone jack: NOT DETECTED (may be USB-C only)")
        return hp

    # Check if headphones are currently connected
    connected_patterns = [
        r"headphone.*(?:connected|plugged|inserted|state\s*[:=]\s*1)",
        r"headset.*(?:connected|plugged|inserted|state\s*[:=]\s*1)",
        r"jack.*(?:state|status)\s*[:=]\s*(?:1|connected|plugged)",
        r"h2w.*state\s*[:=]\s*(?:1|2)",
        r"microphone.*acc.*connected",
    ]
    for pattern in connected_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            hp.connected = True
            break

    # Also check via switch state
    h2w_state = _adb("cat /sys/class/switch/h2w/state 2>/dev/null")
    if h2w_state.strip() in ("1", "2"):
        hp.connected = True

    # Identify dedicated DAC IC for headphone output
    for ic_name in codec_info.detected_ics:
        ic_data = KNOWN_AUDIO_ICS.get(ic_name, {})
        if ic_data.get("type") == "DAC":
            hp.dac_ic = ic_name
            hp.dac_manufacturer = ic_data.get("manufacturer", "")
            break

    # Check MBHC (Microphone Bias Headphone Controller) status for Qualcomm
    mbhc_patterns = [
        r"mbhc[\s_]*(?:status|state)\s*[:=]\s*(\w+)",
        r"headphone[\s_]*(?:det|detect|detection)\s*[:=]\s*(\w+)",
    ]
    for pattern in mbhc_patterns:
        m = re.search(pattern, combined, re.IGNORECASE)
        if m:
            hp.mbhc_status = m.group(1).strip()
            break

    # Determine status
    if hp.jack_present and not hp.connected:
        hp.status = "Jack present, nothing connected"
    elif hp.connected:
        hp.status = "Headphone/headset connected"
    else:
        hp.status = "OK"

    _notify(callback, 67.0, f"Headphone: {hp.status}, jack={hp.jack_type}, "
                            f"connected={hp.connected}, DAC={hp.dac_ic or 'integrated'}")
    return hp


# ---------------------------------------------------------------------------
#  Step 7 — Audio routes and volume levels
# ---------------------------------------------------------------------------

def _parse_audio_routes(
    dumpsys_audio: str,
    audio_flinger: str,
    callback: ProgressCallback,
) -> List[str]:
    """Extract active and available audio routes."""
    _notify(callback, 70.0, "Parsing audio routes...")
    routes: List[str] = []

    combined = dumpsys_audio + "\n" + audio_flinger

    # Look for output device listings
    device_patterns = [
        (r"AUDIO_DEVICE_OUT_SPEAKER", "speaker"),
        (r"AUDIO_DEVICE_OUT_EARPIECE", "earpiece"),
        (r"AUDIO_DEVICE_OUT_WIRED_HEADSET", "headset"),
        (r"AUDIO_DEVICE_OUT_WIRED_HEADPHONE", "headphone"),
        (r"AUDIO_DEVICE_OUT_BLUETOOTH_SCO", "bt_sco"),
        (r"AUDIO_DEVICE_OUT_BLUETOOTH_A2DP", "bt_a2dp"),
        (r"AUDIO_DEVICE_OUT_USB_DEVICE", "usb_device"),
        (r"AUDIO_DEVICE_OUT_AUX_DIGITAL|AUDIO_DEVICE_OUT_HDMI", "hdmi"),
        (r"AUDIO_DEVICE_OUT_TELEPHONY_TX", "telephony"),
        (r"AUDIO_DEVICE_IN_FM_TUNER", "fm_tuner"),
    ]

    for pattern, route_key in device_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            description = AUDIO_ROUTE_TYPES.get(route_key, route_key)
            routes.append(f"{route_key}: {description}")

    if not routes:
        # Fallback: look for generic route info
        route_match = re.findall(
            r"(?:output|input)\s*device\s*[:=]\s*(.+)",
            combined,
            re.IGNORECASE,
        )
        for match in route_match[:10]:
            routes.append(match.strip()[:100])

    return routes


def _parse_volume_levels(
    dumpsys_audio: str,
    callback: ProgressCallback,
) -> Dict[str, str]:
    """Extract current volume levels for each stream type."""
    _notify(callback, 73.0, "Parsing volume levels...")
    volumes: Dict[str, str] = {}

    # Pattern: "- STREAM_MUSIC: \n   Mute count: 0\n   Max: 150\n   Current: ..."
    # Or simpler: "STREAM_MUSIC: volume=12 (of 15)"
    stream_patterns = [
        r"STREAM_MUSIC",
        r"STREAM_RING",
        r"STREAM_NOTIFICATION",
        r"STREAM_ALARM",
        r"STREAM_VOICE_CALL",
        r"STREAM_SYSTEM",
        r"STREAM_BLUETOOTH_SCO",
    ]

    for stream in stream_patterns:
        # Try to find volume value near the stream name
        pattern = rf"{stream}.*?(?:volume|index|level)\s*[:=]\s*(\d+)"
        m = re.search(pattern, dumpsys_audio, re.IGNORECASE | re.DOTALL)
        if m:
            stream_name = stream.replace("STREAM_", "").lower()
            volumes[stream_name] = m.group(1)
            continue

        # Alternative: "- <stream>:\n   ... Current: N, ..."
        pattern2 = rf"{stream}.*?(?:current|cur)\s*[:=]\s*(\d+)"
        m2 = re.search(pattern2, dumpsys_audio, re.IGNORECASE | re.DOTALL)
        if m2:
            stream_name = stream.replace("STREAM_", "").lower()
            volumes[stream_name] = m2.group(1)

    # Also try reading via settings
    if not volumes:
        for stream_type, settings_key in [
            ("music", "volume_music"),
            ("ring", "volume_ring"),
            ("notification", "volume_notification"),
            ("alarm", "volume_alarm"),
            ("voice_call", "volume_voice"),
            ("system", "volume_system"),
        ]:
            val = _adb(f"settings get system {settings_key} 2>/dev/null")
            if val and val.strip().isdigit():
                volumes[stream_type] = val.strip()

    return volumes


# ---------------------------------------------------------------------------
#  Step 8 — Parse sound cards and PCM devices
# ---------------------------------------------------------------------------

def _parse_sound_cards(raw: str) -> List[str]:
    """Parse ``/proc/asound/cards`` into a list of card descriptions."""
    cards: List[str] = []
    if not raw:
        return cards

    # Format: " 0 [msm8998tasha  ]: msm8998-tasha - msm8998-tasha-snd-card\n"
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Lines with card numbers start with a digit
        if line and line[0].isdigit():
            cards.append(line)
        elif cards and not line[0].isdigit():
            # Continuation line for the previous card
            cards[-1] += " " + line

    return cards


def _parse_pcm_devices(raw: str) -> List[str]:
    """Parse ``/proc/asound/pcm`` into a list of PCM device strings."""
    devices: List[str] = []
    if not raw:
        return devices

    for line in raw.splitlines():
        line = line.strip()
        if line:
            devices.append(line)

    return devices


# ---------------------------------------------------------------------------
#  Step 9 — Health scoring and warnings
# ---------------------------------------------------------------------------

def _compute_health_score(
    codec_info: AudioCodecInfo,
    speaker_info: SpeakerInfo,
    microphone_info: MicrophoneInfo,
    headphone_info: HeadphoneInfo,
    audio_routes: List[str],
    volume_levels: Dict[str, str],
    sound_cards: List[str],
) -> Tuple[int, List[str]]:
    """Compute a 0-100 audio health score and generate warnings.

    Scoring breakdown:
      - Codec IC identified:       25 points
      - Speaker subsystem OK:      25 points
      - Microphone subsystem OK:   20 points
      - Audio routes available:    15 points
      - Sound cards present:       10 points
      - Headphone jack functional:  5 points
    """
    score = 0
    warnings: List[str] = []

    # --- Codec IC (25 points) ---
    if codec_info.status == "Detected":
        score += 25
    elif codec_info.status == "Partially Detected":
        score += 15
        warnings.append("Audio codec IC only partially identified")
    elif "Generic" in codec_info.status:
        score += 10
        warnings.append("Audio codec IC not specifically identified (generic HAL)")
    else:
        score += 0
        warnings.append("CRITICAL: Audio codec IC not detected — possible hardware failure")

    # --- Speaker (25 points) ---
    if speaker_info.present and speaker_info.status == "OK":
        score += 25
        if speaker_info.count >= 2:
            pass  # Stereo — great
        else:
            score -= 2  # Mono is fine but less
    elif speaker_info.present and speaker_info.status == "Warning":
        score += 15
        warnings.extend(speaker_info.warnings)
    else:
        score += 0
        warnings.append("CRITICAL: Built-in speaker not detected — check speaker flex cable")

    # --- Microphone (20 points) ---
    if microphone_info.present:
        if "OK" in microphone_info.status:
            score += 20
            if microphone_info.count < 2:
                score -= 3
                warnings.append("Only one microphone detected — noise cancellation may be limited")
        elif microphone_info.status == "Warning":
            score += 10
            warnings.extend(microphone_info.warnings)
        else:
            score += 5
    else:
        score += 0
        warnings.append("CRITICAL: No microphone detected — check mic flex cable and bias circuit")

    # --- Audio routes (15 points) ---
    if len(audio_routes) >= 3:
        score += 15
    elif len(audio_routes) >= 1:
        score += 10
        warnings.append("Limited audio routes detected")
    else:
        score += 0
        warnings.append("No audio output routes detected — audio policy may be misconfigured")

    # --- Sound cards (10 points) ---
    if len(sound_cards) >= 1:
        score += 10
    else:
        score += 0
        warnings.append("No ALSA sound cards detected — kernel audio driver may not be loaded")

    # --- Headphone jack (5 points) ---
    if headphone_info.jack_present:
        score += 5
    else:
        # Many modern phones lack a 3.5mm jack — not a critical issue
        score += 3  # Partial credit; USB-C audio is fine

    # --- Volume level checks ---
    music_vol = _parse_int(volume_levels.get("music", ""), -1)
    if music_vol == 0:
        warnings.append("Media volume is at zero — phone may appear to have no audio")

    voice_vol = _parse_int(volume_levels.get("voice_call", ""), -1)
    if voice_vol == 0:
        warnings.append("Voice call volume is at zero")

    # Clamp score
    score = max(0, min(100, score))

    return score, warnings


def _generate_overall_assessment(
    codec_info: AudioCodecInfo,
    speaker_info: SpeakerInfo,
    microphone_info: MicrophoneInfo,
    headphone_info: HeadphoneInfo,
    audio_routes: List[str],
    volume_levels: Dict[str, str],
    health_score: int,
    warnings: List[str],
    sound_cards: List[str],
    pcm_devices: List[str],
) -> str:
    """Generate a human-readable audio health assessment string."""
    lines: List[str] = []

    # Verdict
    if health_score >= 85:
        verdict = "EXCELLENT"
    elif health_score >= 70:
        verdict = "GOOD"
    elif health_score >= 50:
        verdict = "FAIR"
    elif health_score >= 30:
        verdict = "POOR"
    else:
        verdict = "CRITICAL"

    lines.append(f"Audio Health: {verdict} ({health_score}/100)")
    lines.append("")

    # Codec IC
    lines.append("--- Audio Codec IC ---")
    lines.append(f"  Primary IC     : {codec_info.name or 'Not Identified'}")
    lines.append(f"  Manufacturer   : {codec_info.manufacturer or 'Unknown'}")
    lines.append(f"  Type           : {codec_info.codec_type or 'Unknown'}")
    lines.append(f"  Sample Rate    : {codec_info.sample_rate or 'Unknown'}")
    lines.append(f"  Bit Depth      : {codec_info.bit_depth or 'Unknown'}")
    lines.append(f"  Channels       : {codec_info.channels or 'Unknown'}")
    lines.append(f"  Driver         : {codec_info.driver_name or 'Unknown'}")
    if codec_info.firmware_version:
        lines.append(f"  Firmware       : {codec_info.firmware_version}")
    if len(codec_info.detected_ics) > 1:
        lines.append(f"  All ICs found  : {', '.join(codec_info.detected_ics)}")
    lines.append(f"  Status         : {codec_info.status}")

    # Known failure patterns for identified IC
    if codec_info.name and codec_info.name in KNOWN_AUDIO_ICS:
        ic_data = KNOWN_AUDIO_ICS[codec_info.name]
        failures = ic_data.get("common_failures", [])
        if failures:
            lines.append(f"  Known Issues   :")
            for f in failures[:3]:
                lines.append(f"    - {f}")

    lines.append("")

    # Speaker
    lines.append("--- Speaker ---")
    lines.append(f"  Present        : {speaker_info.present}")
    lines.append(f"  Count          : {speaker_info.count} ({'stereo' if speaker_info.count >= 2 else 'mono'})")
    lines.append(f"  Amplifier IC   : {speaker_info.amplifier_ic or 'Not Identified'}")
    if speaker_info.amplifier_manufacturer:
        lines.append(f"  Amp Mfr        : {speaker_info.amplifier_manufacturer}")
    lines.append(f"  Impedance      : {speaker_info.impedance or 'Unknown'}")
    lines.append(f"  Status         : {speaker_info.status}")
    lines.append("")

    # Microphone
    lines.append("--- Microphone ---")
    lines.append(f"  Present        : {microphone_info.present}")
    lines.append(f"  Count          : {microphone_info.count}")
    lines.append(f"  Types          : {', '.join(microphone_info.types) if microphone_info.types else 'Unknown'}")
    if microphone_info.input_sources:
        lines.append(f"  Input Sources  : {', '.join(microphone_info.input_sources)}")
    lines.append(f"  Status         : {microphone_info.status}")
    lines.append("")

    # Headphone
    lines.append("--- Headphone Jack ---")
    lines.append(f"  Jack Present   : {headphone_info.jack_present}")
    lines.append(f"  Jack Type      : {headphone_info.jack_type or 'N/A'}")
    lines.append(f"  Connected      : {headphone_info.connected}")
    if headphone_info.dac_ic:
        lines.append(f"  DAC IC         : {headphone_info.dac_ic} ({headphone_info.dac_manufacturer})")
    if headphone_info.mbhc_status:
        lines.append(f"  MBHC Status    : {headphone_info.mbhc_status}")
    lines.append(f"  Status         : {headphone_info.status}")
    lines.append("")

    # Audio routes
    lines.append("--- Audio Routes ---")
    if audio_routes:
        for route in audio_routes:
            lines.append(f"  - {route}")
    else:
        lines.append("  No routes detected")
    lines.append("")

    # Volume levels
    lines.append("--- Volume Levels ---")
    if volume_levels:
        for stream, level in sorted(volume_levels.items()):
            lines.append(f"  {stream:20s}: {level}")
    else:
        lines.append("  Volume levels not read")
    lines.append("")

    # Sound cards
    lines.append("--- ALSA Sound Cards ---")
    if sound_cards:
        for card in sound_cards:
            lines.append(f"  {card}")
    else:
        lines.append("  No sound cards detected")
    lines.append("")

    # PCM devices
    lines.append("--- PCM Devices ---")
    if pcm_devices:
        for dev in pcm_devices[:10]:
            lines.append(f"  {dev}")
        if len(pcm_devices) > 10:
            lines.append(f"  ... and {len(pcm_devices) - 10} more")
    else:
        lines.append("  No PCM devices detected")
    lines.append("")

    # Warnings
    if warnings:
        lines.append("WARNINGS:")
        for w in warnings:
            lines.append(f"  - {w}")
    else:
        lines.append("No warnings.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def detect_audio_status(
    callback: ProgressCallback = None,
) -> AudioTestResult:
    """Run the full audio diagnostic sequence.

    Parameters
    ----------
    callback : optional
        A callable ``(pct: float, msg: str) -> None`` invoked with progress
        updates.  *pct* ranges from 0 to 100.

    Returns
    -------
    AudioTestResult
        Populated result dataclass with all sub-results and an overall
        health assessment string.
    """
    result = AudioTestResult()
    logger.info("Starting advanced audio test sequence")

    # ── Step 1: ADB connection ──
    connected, err_or_serial = _check_adb_connection(callback)
    if not connected:
        result.connected = False
        result.error = err_or_serial
        result.overall_health = f"UNABLE TO TEST — {err_or_serial}"
        _notify(callback, 100.0, f"Test aborted: {err_or_serial}")
        return result
    result.connected = True

    try:
        # ── Step 2: Collect raw audio data ──
        audio_flinger = _collect_audio_flinger(callback)
        audio_policy = _collect_audio_policy(callback)
        dumpsys_audio = _collect_dumpsys_audio(callback)
        sound_cards_raw = _collect_sound_cards(callback)
        pcm_devices_raw = _collect_pcm_devices(callback)
        asound_codecs = _collect_asound_codecs(callback)
        tinymix_raw = _collect_tinymix(callback)
        audio_props = _collect_audio_properties(callback)
        sound_entries, sound_ids = _collect_sound_class(callback)

        # Merge audio policy into dumpsys_audio for broader search
        full_audio = dumpsys_audio + "\n" + audio_policy

        # ── Step 3: Identify codec ICs ──
        result.codec_info = _identify_codec_ics(
            audio_flinger, full_audio, sound_cards_raw, pcm_devices_raw,
            asound_codecs, tinymix_raw, audio_props, sound_ids, callback,
        )

        # ── Step 4: Speaker analysis ──
        result.speaker_info = _analyze_speakers(
            audio_flinger, full_audio, tinymix_raw, result.codec_info, callback,
        )

        # ── Step 5: Microphone analysis ──
        result.microphone_info = _analyze_microphones(
            audio_flinger, full_audio, tinymix_raw, callback,
        )

        # ── Step 6: Headphone jack analysis ──
        result.headphone_info = _analyze_headphone_jack(
            audio_flinger, full_audio, tinymix_raw, result.codec_info, callback,
        )

        # ── Step 7: Audio routes and volume levels ──
        result.audio_routes = _parse_audio_routes(full_audio, audio_flinger, callback)
        result.volume_levels = _parse_volume_levels(full_audio, callback)

        # ── Step 8: Sound cards and PCM devices ──
        _notify(callback, 76.0, "Parsing sound cards and PCM devices...")
        result.sound_cards = _parse_sound_cards(sound_cards_raw)
        result.pcm_devices = _parse_pcm_devices(pcm_devices_raw)

        # ── Step 9: Health scoring ──
        _notify(callback, 80.0, "Computing audio health score...")
        result.health_score, result.warnings = _compute_health_score(
            result.codec_info,
            result.speaker_info,
            result.microphone_info,
            result.headphone_info,
            result.audio_routes,
            result.volume_levels,
            result.sound_cards,
        )

        # ── Step 10: Overall assessment ──
        _notify(callback, 90.0, "Generating overall audio assessment...")
        result.overall_health = _generate_overall_assessment(
            result.codec_info,
            result.speaker_info,
            result.microphone_info,
            result.headphone_info,
            result.audio_routes,
            result.volume_levels,
            result.health_score,
            result.warnings,
            result.sound_cards,
            result.pcm_devices,
        )

    except Exception as exc:
        logger.exception("Audio test sequence failed")
        result.error = str(exc)
        result.overall_health = f"TEST ERROR — {exc}"

    _notify(callback, 100.0, "Audio test complete")
    logger.info("Audio test sequence finished")
    return result


# ---------------------------------------------------------------------------
#  CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys
    from dataclasses import asdict

    logging.basicConfig(
        level=logging.DEBUG if "--debug" in sys.argv else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    def _cli_callback(pct: float, msg: str) -> None:
        print(f"  [{pct:5.1f}%] {msg}")

    print("=" * 70)
    print("  Advanced Audio Tester — Mooxy AI Fault Detector")
    print("=" * 70)
    print()

    test_result = detect_audio_status(callback=_cli_callback)

    print()
    print("-" * 70)
    print(test_result.overall_health)
    print("-" * 70)

    if "--json" in sys.argv:
        print()
        print(json.dumps(asdict(test_result), indent=2, default=str))
