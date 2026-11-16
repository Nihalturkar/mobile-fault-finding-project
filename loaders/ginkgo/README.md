# Redmi Note 8 (ginkgo / willow) - SM6125 EDL files

| File | Source | MD5[:16] | Notes |
|---|---|---|---|
| prog_emmc_firehose_Sm6125_ddr.elf | Xiaomi fastboot ROM V12.0.1.0.QCOMIXM (bigota.d.miui.com), images/ | b8817f540d25f179 | Official, **auth-locked** (only nop/sig before Mi auth). Good only to prove the PBL signature. |
| sm6125_emmc_noauth.elf | hoplik/Firehose-Finder fh_collection/9FCADFE3/1 = bkerler/Loaders xiaomi/0010a0e100720000_1bebe3863a6781db_fhprg.bin | 0e69d6eca0fe2842 | Xiaomi-signed engineering loader, **no auth**. HWID 0x0010A0E1 (SM6125) OEM 0x0072 PK 1bebe3863a6781db. Use this for diagnosis/flash. |
| rawprogram0.xml, patch0.xml | same ROM | | Flash maps for a full EDL flash after an eMMC replacement. |

Index used to verify hashes: https://www.temblast.com/ref/loaders.htm
