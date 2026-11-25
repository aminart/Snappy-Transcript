from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_DLL_HANDLES = []

@dataclass(frozen=True)
class CudaRuntimeStatus:
    gpu_count: int
    cublas_dir: Path | None
    cudnn_dir: Path | None
    ready: bool
    detail: str


def _site_packages() -> Path:
    return Path(sys.prefix) / "Lib" / "site-packages"


def prepare_cuda_runtime() -> CudaRuntimeStatus:
    """Expose pip-installed NVIDIA DLLs to this Python process only."""
    site = _site_packages()
    cublas = site / "nvidia" / "cublas" / "bin"
    cudnn = site / "nvidia" / "cudnn" / "bin"
    dirs = [p for p in (cublas, cudnn) if p.is_dir()]

    # os.add_dll_directory is the clean Windows mechanism. PATH is also updated
    # for native libraries that use LoadLibrary-style dependency resolution.
    if os.name == "nt":
        for p in dirs:
            try:
                _DLL_HANDLES.append(os.add_dll_directory(str(p)))
            except (OSError, AttributeError):
                pass
        if dirs:
            current = os.environ.get("PATH", "")
            prefix = os.pathsep.join(str(p) for p in dirs)
            os.environ["PATH"] = prefix + (os.pathsep + current if current else "")

    try:
        import ctranslate2
        gpu_count = int(ctranslate2.get_cuda_device_count())
    except Exception as exc:
        return CudaRuntimeStatus(0, cublas if cublas.is_dir() else None,
                                 cudnn if cudnn.is_dir() else None, False,
                                 f"CTranslate2/CUDA indisponible : {type(exc).__name__}: {exc}")

    has_cublas = (cublas / "cublas64_12.dll").is_file()
    has_cudnn = (cudnn / "cudnn64_9.dll").is_file() or (site / "ctranslate2" / "cudnn64_9.dll").is_file()
    ready = gpu_count > 0 and has_cublas and has_cudnn
    missing = []
    if gpu_count < 1: missing.append("GPU CUDA")
    if not has_cublas: missing.append("cublas64_12.dll")
    if not has_cudnn: missing.append("cudnn64_9.dll")
    detail = "CUDA prêt (GPU + cuBLAS 12 + cuDNN 9)." if ready else "Manquant : " + ", ".join(missing)
    return CudaRuntimeStatus(gpu_count, cublas if cublas.is_dir() else None,
                             cudnn if cudnn.is_dir() else None, ready, detail)
