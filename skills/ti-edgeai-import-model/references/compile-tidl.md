# Compiling for TIDL (host emulation + artifacts)

## Environment
- TI's compile tools are Ubuntu 22.04 / Python 3.10 binaries. On a newer host run them in Docker (`scripts/Dockerfile.tidl-tools`).
- Use a tools release TI lists as compatible with the board SDK, normally the same release line
  (`ti-edgeai-dev/references/sdk-versions.md`); e.g. TDA4VM on SDK 11.0 -> `11_00_06_00`. Rows marked "firmware patch needed" require
  updating the target first. Confirm with the artifact stamp check.
- `setup.sh` needs `SOC=<tools soc>` (e.g. `am68pa` == j721e/TDA4VM) at build time or it silently skips downloading `tidl_tools`.
  Tools land in `/opt/edgeai-tidl-tools/tools/<SOC upper-case>/tidl_tools`; `run_in_container.sh` exports `TIDL_TOOLS_PATH` and `LD_LIBRARY_PATH`.
- Container flags: `--shm-size=4g` (else Bus error); the project folder is mounted at the same absolute path; the scripts folder is
  mounted read-only and exported as `$SCRIPTS`. Use `EXTRA_MOUNTS="-v /data:/data:ro"` for data outside WORKDIR.
- The compile uses TI's `onnxruntime-tidl` (1.15.0 for SDK 11.0): `TIDLCompilationProvider` first, `CPUExecutionProvider` second.
  Running `session.run` on calibration frames *is* the calibration; artifacts are written at the end.

## Output handling
`compile_tidl.py` compiles into `<artifacts>.staging-<pid>` and moves it to `--artifacts` only when the compile produced `allowedNode.txt`.
An existing `--artifacts` folder is renamed to `<artifacts>.previous-<time>` (never deleted; remove old ones yourself). A failed or
interrupted compile removes only its own staging folder.

## Provider options (set by `compile_tidl.py`; verified)
```
tidl_tools_path, artifacts_folder, platform J7, version 7.2, tensor_bits 8, debug_level 1, max_num_subgraphs 16,
accuracy_level 1, advanced_options:calibration_frames 50, advanced_options:calibration_iterations 10,
advanced_options:quantization_scale_type 0 (symmetric; the only mode on TDA4VM; `--quant-scale-type 4` is asymmetric on the other SoCs, not run here), advanced_options:add_data_convert_ops 3,
ti_internal_nc_flag 1601
detection only: object_detection:meta_layers_names_list <prototxt>, object_detection:meta_arch_type <N>
```
`add_data_convert_ops 3` embeds input/output layout and dtype conversion in the DSP. Add or override any option with
`--extra key=value`. Provider option reference: edgeai-tidl-tools `examples/osrt_python/README.md`.

## Calibration data
- >= 50 frames for `accuracy_level 1` (TI: clear accuracy boost versus 20); cover the deployment conditions (lighting, scale,
  backgrounds, classes). Evenly spaced picks from the training set are a fair default; `--calib` takes a directory or a text list.
- Same preprocessing as the board, via the shared flags (`--hw` | `--resize/--crop` | `--letterbox`, `--channels`).
- Never calibrate with validation/test images (it leaks into the reported int8 accuracy).

## Timing
Calibration frames dominate. A YOLOX-tiny-sized detector with 50 frames took about 25-35 minutes on a desktop CPU; a tiny classifier
with 8 frames took ~2 minutes; a 2-frame smoke compile is a fast way to test the setup. Run in the background and poll `calib i / N`;
progress bars after that are the quantization/bias-calibration phase.

## What success looks like
```
Version Summary:  TIDL Tools Version 11_00_06_00, C7x Firmware Version 11_00_00_00, Runtime 1.15.0
======================== Subgraph Compiled Successfully ========================
artifacts/: subgraph_0_tidl_net.bin, subgraph_0_tidl_io_1.bin, allowedNode.txt, onnxrtMetaData.txt (numGraphNodes, inDataNames,
            outDataNames), tempDir/{*.layer_info.txt,*.svg,*_netLog.txt}
```
One subgraph means everything is on the accelerator; with a detection meta-architecture its outputs are `dets,labels`. Several
subgraphs / `UNSUPPORTED` lines mean ARM fallbacks: read `allowedNode.txt` and the log.

## Known failure modes
`ti-edgeai-dev/references/troubleshooting.md` (compile table). Two that look like your fault but are not: `onnxsim` missing in the image
(`NoSuchFile ..._sim.onnx`), and an artifacts dir holding `tempDir/` from a previous run (the script clears it).

## Variants
Each variant needs its own `--artifacts` directory (`artifacts_int8/`, `artifacts_mixed/`); compare with the eval scripts using
`--tidl-artifacts` before packaging the winner.
