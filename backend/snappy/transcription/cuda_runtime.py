from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path

CPU_SEUL = "Pas de carte graphique NVIDIA utilisable : le calcul se fera sur le processeur, ce qui fonctionne très bien."

_DLL_HANDLES: dict[str, object] = {}  # un seul add_dll_directory par dossier, même si on est appelé à chaque requête


@dataclass(frozen=True)
class CudaRuntimeStatus:
    gpu_count: int
    cublas_dir: Path | None
    cudnn_dir: Path | None
    ready: bool
    detail: str   # technique : pour le diagnostic
    message: str = ""  # pour l'utilisateur


def _racines() -> list[Path]:
    """Dossiers qui peuvent contenir « nvidia/… » : exe PyInstaller, venv Windows, paquet nvidia trouvé par Python."""
    racines: list[Path] = []
    if getattr(sys, "frozen", False):
        racines.append(Path(getattr(sys, "_MEIPASS")))
    racines.append(Path(sys.prefix) / "Lib" / "site-packages")
    try:
        spec = importlib.util.find_spec("nvidia")  # espace de noms : plusieurs emplacements possibles
    except (ImportError, ValueError):
        spec = None
    if spec is not None:  # None : paquets NVIDIA absents, cas le plus courant (PC sans GPU)
        racines.extend(Path(p).parent for p in (spec.submodule_search_locations or []))
    return racines


def _dossier(sous_dossier: str) -> Path | None:
    return next((r / "nvidia" / sous_dossier / "bin" for r in _racines() if (r / "nvidia" / sous_dossier / "bin").is_dir()), None)


def prepare_cuda_runtime() -> CudaRuntimeStatus:
    """Expose les DLL NVIDIA installées par pip (cuBLAS, cuDNN) à ce processus seulement, puis teste CTranslate2."""
    cublas, cudnn = _dossier("cublas"), _dossier("cudnn")
    dirs = [p for p in (cublas, cudnn) if p]

    # os.add_dll_directory est le mécanisme propre de Windows ; PATH sert aux bibliothèques natives qui
    # résolvent leurs dépendances avec LoadLibrary.
    if os.name == "nt":
        for p in dirs:
            if str(p) not in _DLL_HANDLES:
                try:
                    _DLL_HANDLES[str(p)] = os.add_dll_directory(str(p))
                    os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")
                except (OSError, AttributeError):
                    pass

    try:
        import ctranslate2
        gpu_count = int(ctranslate2.get_cuda_device_count())
    except Exception as exc:
        return CudaRuntimeStatus(0, cublas, cudnn, False, f"CTranslate2/CUDA indisponible : {type(exc).__name__}: {exc}",
                                 CPU_SEUL)

    has_cublas = bool(cublas and (cublas / "cublas64_12.dll").is_file())
    has_cudnn = bool(cudnn and (cudnn / "cudnn64_9.dll").is_file()) or any(
        (r / "ctranslate2" / "cudnn64_9.dll").is_file() for r in _racines())
    ready = gpu_count > 0 and has_cublas and has_cudnn
    missing = []
    if gpu_count < 1:
        missing.append("GPU CUDA")
    if not has_cublas:
        missing.append("cublas64_12.dll")
    if not has_cudnn:
        missing.append("cudnn64_9.dll")
    detail = "CUDA prêt (GPU + cuBLAS 12 + cuDNN 9)." if ready else "Manquant : " + ", ".join(missing)
    if ready:
        message = f"Carte graphique NVIDIA prête ({gpu_count} GPU) : la transcription sera plus rapide."
    elif gpu_count > 0:
        message = ("Carte NVIDIA détectée, mais les composants GPU de cette installation sont incomplets : "
                   "le calcul se fera sur le processeur.")
    else:
        message = CPU_SEUL
    return CudaRuntimeStatus(gpu_count, cublas, cudnn, ready, detail, message)
