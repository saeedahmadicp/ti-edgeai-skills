# Matching tools, firmware and runtime (all SoCs)

TIDL artifacts embed a network-format version. The C7x firmware (shipped in the SDK's RTOS image) only loads artifacts whose
format it understands. TI maintains the mapping in `docs/version_compatibility_table.md` of edgeai-tidl-tools: one row per tool
tag, one column per SoC family. **Read the table in the tag you intend to use; do not guess from the tag number.**

## Procedure
1. Read the board's SDK: `ssh root@<board-ip> 'env | grep -i -E "EDGEAI|SDK"; uname -r'` (also `/opt/edgeai-gst-apps/docker/*`).
   The remoteproc trace shows the Sciserver/PSDK banner: `cat /sys/kernel/debug/remoteproc/remoteproc*/trace0`.
2. Find that SDK's row in the SoC's column of the table and take the tag. Rows whose notes mention an **additional C7x firmware
   patch** need the board patched first (`docs/update_target.md`) and models compiled with `c7x_firmware_version` set; do not use
   them on an unpatched board.
3. Build the tools image with that tag (`ti-edgeai-import-model/scripts/Dockerfile.tidl-tools`).
4. After compiling, check the artifact stamp (below).

## Snapshot of the table (tag 11_00_06_00)
| edgeai-tidl-tools tag | Linux / RTOS SDK (AM68A, AM68PA/TDA4VM, AM69A, AM67A columns) | AM62A column |
|---|---|---|
| 11_00_06_00 | 11.00.00.08 / 11.00.00.06 | NOT AVAILABLE |
| 10_01_04_00 (needs firmware patch) | 10.01.00.04 / 10.01.00.04 | Linux 10.01.XX.XX |
| 10_01_00_02 | 10.01.00.04 / 10.01.00.04 | Linux 10.01.XX.XX |
| 10_00_08_00 (firmware patch available) | 10.00.00.08 / 10.00.00.05 | Linux 10.00.00.08 |
| 09_02_09_00 / 09_02_07_00 / 09_02_06_00 | 09.02.00.05 / 09.02.00.05 | Linux 09.02.00.05 |
| 09_01_07_00 ... 09_01_00_02 | 09.01.00.06 / 09.01.00.06 (AM67A: NA) | Linux 09.01.00.07 |
| 09_00_00_07 / 09_00_00_06 | 09.00.00.08 / 09.00.00.02 (AM67A: NA) | Linux 09.00.00.08 |

Newer tags (11_00_07_00, 11_00_08_00, master / 11_02) exist: check their rows and firmware-patch notes before use. The table
changes with every release; this snapshot dates from tag 11_00_06_00.

Verified: on a TDA4VM with SDK 11.0 (unpatched firmware) tag 11_00_06_00 works and tag 11_00_08_00 output was rejected
(`TIVX_CMD_NODE_CREATE failed`). The other SoC columns are copied from the table, not tested.

## Artifact version stamp (fast sanity check)
The first 4 bytes of `subgraph_*_tidl_net.bin` are a stamp. A model the firmware accepts has the same stamp as the TI zoo models
already on the board.
```bash
python3 ti-edgeai-import-model/scripts/check_artifacts_version.py artifacts/subgraph_0_tidl_net.bin --board root@<board-ip>
```
On the verified TDA4VM board all ten zoo models carry `29 04 25 20`; tag 11_00_06_00 output carries it; 11_00_08_00 carries
`30 06 25 20` and was rejected.

## Upgrading instead of downgrading tools
If you need newer tools (operators, features), the board needs the matching firmware and libraries: follow `docs/update_target.md`
for that tag, then recompile every model. That changes the board's system software: get the owner's agreement first, and re-test
the zoo models already on the board afterwards.

## Runtime versions
Host compile and board runtime both use TI's ONNX Runtime fork (`onnxruntime-tidl`; 1.15.0 on the verified SDK 11.0 board). The pip
`onnxruntime` has no TIDL provider and cannot compile or run the artifacts. Keep it in a separate environment from the training
venv (the supplied Dockerfile does).
