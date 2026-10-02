# Pipeline anatomy and measurement hooks

See `ti-edgeai-dev/references/gst-apps-and-plugins.md` for the element chain and SoC plugin map. Practical points:

- The full pipeline strings are printed at start-up (`[INPUT PIPELINE(S)]`, `[OUTPUT PIPELINE]`). Capture them with
  `grep -a "tiovx\|v4l2src\|multifilesrc\|kmssink" /tmp/run.log`.
- Example input branch (video file, dumped on a TDA4VM with `SOC=j721e`): `... h264parse ! v4l2h264dec ! tiovxmemalloc ! tiovxdlcolorconvert ! NV12 !
  tiovxmultiscaler name=split_01` then `split_01. ! ... ! tiovxdlpreproc out-pool-size=4 data-type=3 tensor-format=1 ! application/x-tensor-tiovx
  ! appsink name=pre_0` (inference branch) and `split_01. ! ... ! tiovxdlcolorconvert ! RGB ! appsink name=sen_0` (display/overlay branch).
- Output examples: image: `appsrc ! videoconvert ! NV12 ! jpegenc ! multifilesink`; video: `... ! v4l2h264enc ! h264parse ! matroskamux ! filesink`.
- Per-element latency/FPS for any config: `ti-edgeai-profile-pipeline/scripts/trace_pipeline.sh`. Verified on a 30 fps video: `tiovxdlpreproc` ~2 ms,
  colorconvert 3-5 ms, `v4l2h264enc` ~11-14 ms, whole chain 30 fps (frame spacing 33 ms).
- Inference time is not inside these elements (the Python app runs ONNX Runtime between `pre_0` and the output `appsrc`).
- Variants: `/opt/edgeai-gst-apps/optiflow/optiflow.sh` (pure GStreamer, TI plugins `tidlinferer`/`tidlpostproc`), and the C++ app
  in `apps_cpp/` (needs building). Neither has been exercised here; use the Python app unless the user needs them.
