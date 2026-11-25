"""Interfaces WASAPI minimales (Windows uniquement), via comtypes : sessions audio et capture d'un processus.

Références : IAudioSessionManager2 / IAudioSessionControl2 / IAudioMeterInformation pour lister les applications,
ActivateAudioInterfaceAsync + AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK pour la capture (exemple Microsoft
« ApplicationLoopback »). Seules les méthodes appelées sont typées précisément ; les autres gardent leur place dans
la table virtuelle.
"""
from __future__ import annotations

import ctypes
import sys
import threading
from contextlib import contextmanager
from ctypes import POINTER, Structure, byref, c_float, c_int, c_longlong, c_long, c_ubyte, c_uint32, c_uint64, c_ushort, c_ulong, c_void_p
from ctypes.wintypes import DWORD, HANDLE, LPCWSTR
from typing import Iterator


def _importer_comtypes() -> None:
    """comtypes initialise COM (en STA) dans le fil qui l'importe, et échoue si ce fil est déjà en MTA : on l'importe
    une fois dans un fil jetable, pour que les fils de capture choisissent librement leur mode."""
    if "comtypes" in sys.modules:
        return
    erreur: list[BaseException] = []

    def importer():
        try:
            import comtypes  # noqa: F401
        except BaseException as exc:  # remonté dans le fil appelant
            erreur.append(exc)

    t = threading.Thread(target=importer, name="import-comtypes")
    t.start()
    t.join()
    if erreur:
        raise erreur[0]


_importer_comtypes()

from comtypes import CLSCTX_ALL, COMMETHOD, COMObject, GUID, HRESULT, IUnknown, CoCreateInstance  # noqa: E402

# --- Énumération des sessions -------------------------------------------------------------------------------

E_RENDER, DEVICE_STATE_ACTIVE, SESSION_ACTIVE = 0, 1, 1
_V = c_void_p  # paramètre d'une méthode jamais appelée


class IAudioSessionControl2(IUnknown):
    _iid_ = GUID("{bfb7ff88-7239-4fc9-8fa2-07c950be9c6d}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetState", (["out"], POINTER(c_int), "pRetVal")),
        COMMETHOD([], HRESULT, "GetDisplayName", (["in"], _V, "p")),
        COMMETHOD([], HRESULT, "SetDisplayName", (["in"], _V, "a"), (["in"], _V, "b")),
        COMMETHOD([], HRESULT, "GetIconPath", (["in"], _V, "p")),
        COMMETHOD([], HRESULT, "SetIconPath", (["in"], _V, "a"), (["in"], _V, "b")),
        COMMETHOD([], HRESULT, "GetGroupingParam", (["in"], _V, "p")),
        COMMETHOD([], HRESULT, "SetGroupingParam", (["in"], _V, "a"), (["in"], _V, "b")),
        COMMETHOD([], HRESULT, "RegisterAudioSessionNotification", (["in"], _V, "p")),
        COMMETHOD([], HRESULT, "UnregisterAudioSessionNotification", (["in"], _V, "p")),
        COMMETHOD([], HRESULT, "GetSessionIdentifier", (["in"], _V, "p")),
        COMMETHOD([], HRESULT, "GetSessionInstanceIdentifier", (["in"], _V, "p")),
        COMMETHOD([], HRESULT, "GetProcessId", (["out"], POINTER(DWORD), "pRetVal")),
    ]


class IAudioMeterInformation(IUnknown):
    _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
    _methods_ = [COMMETHOD([], HRESULT, "GetPeakValue", (["out"], POINTER(c_float), "pfPeak"))]


class IAudioSessionEnumerator(IUnknown):
    _iid_ = GUID("{E2F5BB11-0570-40CA-ACDD-3AA01277DEE8}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_int), "SessionCount")),
        COMMETHOD([], HRESULT, "GetSession", (["in"], c_int, "SessionCount"), (["out"], POINTER(POINTER(IUnknown)), "Session")),
    ]


class IAudioSessionManager2(IUnknown):
    _iid_ = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetAudioSessionControl", (["in"], _V, "a"), (["in"], DWORD, "b"), (["in"], _V, "c")),
        COMMETHOD([], HRESULT, "GetSimpleAudioVolume", (["in"], _V, "a"), (["in"], DWORD, "b"), (["in"], _V, "c")),
        COMMETHOD([], HRESULT, "GetSessionEnumerator", (["out"], POINTER(POINTER(IAudioSessionEnumerator)), "SessionEnum")),
    ]


class IMMDevice(IUnknown):
    _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
    _methods_ = [
        COMMETHOD([], HRESULT, "Activate", (["in"], POINTER(GUID), "iid"), (["in"], DWORD, "dwClsCtx"),
                  (["in"], _V, "pActivationParams"), (["out"], POINTER(POINTER(IUnknown)), "ppInterface")),
    ]


class IMMDeviceCollection(IUnknown):
    _iid_ = GUID("{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_uint32), "pcDevices")),
        COMMETHOD([], HRESULT, "Item", (["in"], c_uint32, "nDevice"), (["out"], POINTER(POINTER(IMMDevice)), "ppDevice")),
    ]


class IMMDeviceEnumerator(IUnknown):
    _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    _methods_ = [
        COMMETHOD([], HRESULT, "EnumAudioEndpoints", (["in"], c_int, "dataFlow"), (["in"], DWORD, "dwStateMask"),
                  (["out"], POINTER(POINTER(IMMDeviceCollection)), "ppDevices")),
    ]


CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")


def sessions_audio() -> list[tuple[int, bool, float]]:
    """(pid, active, crête) de chaque session audio, sur toutes les sorties actives. COM doit être initialisé."""
    enum = CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, CLSCTX_ALL)
    sorties = enum.EnumAudioEndpoints(E_RENDER, DEVICE_STATE_ACTIVE)
    out: list[tuple[int, bool, float]] = []
    for i in range(sorties.GetCount()):
        try:
            mgr = sorties.Item(i).Activate(byref(IAudioSessionManager2._iid_), CLSCTX_ALL, None).QueryInterface(IAudioSessionManager2)
            liste = mgr.GetSessionEnumerator()
            for j in range(liste.GetCount()):
                try:
                    s = liste.GetSession(j)
                    ctl = s.QueryInterface(IAudioSessionControl2)
                    pid = int(ctl.GetProcessId())
                    active = ctl.GetState() == SESSION_ACTIVE
                    try:
                        crete = float(s.QueryInterface(IAudioMeterInformation).GetPeakValue())
                    except Exception:
                        crete = 0.0
                    out.append((pid, active, crete))
                except Exception:
                    continue
        except Exception:
            continue
    return out


# --- Capture d'un processus ---------------------------------------------------------------------------------

class WAVEFORMATEX(Structure):
    _pack_ = 1
    _fields_ = [("wFormatTag", c_ushort), ("nChannels", c_ushort), ("nSamplesPerSec", DWORD), ("nAvgBytesPerSec", DWORD),
                ("nBlockAlign", c_ushort), ("wBitsPerSample", c_ushort), ("cbSize", c_ushort)]


class IAudioCaptureClient(IUnknown):
    _iid_ = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetBuffer", (["out"], POINTER(POINTER(c_ubyte)), "ppData"), (["out"], POINTER(c_uint32), "pNumFramesToRead"),
                  (["out"], POINTER(DWORD), "pdwFlags"), (["out"], POINTER(c_uint64), "pu64DevicePosition"),
                  (["out"], POINTER(c_uint64), "pu64QPCPosition")),
        COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], c_uint32, "NumFramesRead")),
        COMMETHOD([], HRESULT, "GetNextPacketSize", (["out"], POINTER(c_uint32), "pNumFramesInNextPacket")),
    ]


class IAudioClient(IUnknown):
    _iid_ = GUID("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}")
    _methods_ = [
        COMMETHOD([], HRESULT, "Initialize", (["in"], c_int, "ShareMode"), (["in"], DWORD, "StreamFlags"),
                  (["in"], c_longlong, "hnsBufferDuration"), (["in"], c_longlong, "hnsPeriodicity"),
                  (["in"], POINTER(WAVEFORMATEX), "pFormat"), (["in"], POINTER(GUID), "AudioSessionGuid")),
        COMMETHOD([], HRESULT, "GetBufferSize", (["out"], POINTER(c_uint32), "pNumBufferFrames")),
        COMMETHOD([], HRESULT, "GetStreamLatency", (["in"], _V, "p")),
        COMMETHOD([], HRESULT, "GetCurrentPadding", (["in"], _V, "p")),
        COMMETHOD([], HRESULT, "IsFormatSupported", (["in"], c_int, "a"), (["in"], _V, "b"), (["in"], _V, "c")),
        COMMETHOD([], HRESULT, "GetMixFormat", (["in"], _V, "p")),
        COMMETHOD([], HRESULT, "GetDevicePeriod", (["in"], _V, "a"), (["in"], _V, "b")),
        COMMETHOD([], HRESULT, "Start"),
        COMMETHOD([], HRESULT, "Stop"),
        COMMETHOD([], HRESULT, "Reset"),
        COMMETHOD([], HRESULT, "SetEventHandle", (["in"], HANDLE, "eventHandle")),
        COMMETHOD([], HRESULT, "GetService", (["in"], POINTER(GUID), "riid"), (["out"], POINTER(POINTER(IUnknown)), "ppv")),
    ]


class IActivateAudioInterfaceAsyncOperation(IUnknown):
    _iid_ = GUID("{72A22D78-CDE4-431D-B8CC-843A71199B6D}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetActivateResult", (["out"], POINTER(c_long), "activateResult"),
                  (["out"], POINTER(POINTER(IUnknown)), "activatedInterface")),
    ]


class IActivateAudioInterfaceCompletionHandler(IUnknown):
    _iid_ = GUID("{41D949AB-9862-444A-80F6-C261334DA5EB}")
    _methods_ = [
        COMMETHOD([], HRESULT, "ActivateCompleted", (["in"], POINTER(IActivateAudioInterfaceAsyncOperation), "activateOperation")),
    ]


class IAgileObject(IUnknown):
    """Sans méthode : signale que le gestionnaire peut être appelé depuis n'importe quel fil (exigé par Windows)."""
    _iid_ = GUID("{94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90}")
    _methods_: list = []


class _FinActivation(COMObject):
    _com_interfaces_ = [IActivateAudioInterfaceCompletionHandler, IAgileObject]

    def __init__(self):
        super().__init__()
        self.fini = threading.Event()

    def ActivateCompleted(self, operation):  # noqa: N802 (nom imposé par l'interface)
        self.fini.set()


class _ParamsLoopback(Structure):
    _fields_ = [("TargetProcessId", DWORD), ("ProcessLoopbackMode", c_int)]


class _ParamsActivation(Structure):
    _fields_ = [("ActivationType", c_int), ("ProcessLoopbackParams", _ParamsLoopback)]


class _Blob(Structure):
    _fields_ = [("cbSize", c_ulong), ("pBlobData", c_void_p)]


class _PropVariant(Structure):
    _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort), ("blob", _Blob)]


VT_BLOB = 65
ACTIVATION_PROCESS_LOOPBACK = 1
LOOPBACK_INCLURE_ARBRE = 0  # PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE
CHEMIN_PROCESS_LOOPBACK = "VAD\\Process_Loopback"
AUDCLNT_SHAREMODE_SHARED = 0
FLAGS = 0x00020000 | 0x00040000 | 0x80000000 | 0x08000000  # LOOPBACK | EVENTCALLBACK | AUTOCONVERTPCM | SRC_DEFAULT_QUALITY
SILENCE = 0x2  # AUDCLNT_BUFFERFLAGS_SILENT
FORMATS = ((16000, 1), (48000, 2), (44100, 2))  # du plus direct au plus courant


@contextmanager
def com_mta() -> Iterator[None]:
    ole32 = ctypes.windll.ole32
    hr = int(ole32.CoInitializeEx(None, 0)) & 0xFFFFFFFF  # COINIT_MULTITHREADED
    ici = hr in (0, 1)
    try:
        yield
    finally:
        if ici:
            ole32.CoUninitialize()


def _activer(pid: int) -> "POINTER(IAudioClient)":
    params = _ParamsActivation(ACTIVATION_PROCESS_LOOPBACK, _ParamsLoopback(pid, LOOPBACK_INCLURE_ARBRE))
    pv = _PropVariant()
    pv.vt = VT_BLOB
    pv.blob.cbSize = ctypes.sizeof(params)
    pv.blob.pBlobData = ctypes.cast(ctypes.pointer(params), c_void_p)

    fonction = ctypes.WinDLL("Mmdevapi.dll").ActivateAudioInterfaceAsync
    fonction.argtypes = [LPCWSTR, POINTER(GUID), POINTER(_PropVariant), POINTER(IActivateAudioInterfaceCompletionHandler),
                         POINTER(POINTER(IActivateAudioInterfaceAsyncOperation))]
    fonction.restype = HRESULT  # lève OSError si Windows refuse
    fin = _FinActivation()
    operation = POINTER(IActivateAudioInterfaceAsyncOperation)()
    fonction(CHEMIN_PROCESS_LOOPBACK, byref(IAudioClient._iid_), byref(pv),
             fin.QueryInterface(IActivateAudioInterfaceCompletionHandler), byref(operation))
    if not fin.fini.wait(5):
        raise OSError("délai d'activation dépassé")
    hr, interface = operation.GetActivateResult()
    if hr < 0:
        raise OSError(f"HRESULT 0x{hr & 0xFFFFFFFF:08X}")
    return interface.QueryInterface(IAudioClient)


class CaptureProcessus:
    """Capture du son d'un processus et de ses descendants ; `lire()` renvoie des paquets PCM16 entrelacés."""

    def __init__(self, pid: int):
        derniere: Exception | None = None
        for taux, canaux in FORMATS:
            try:
                client = _activer(pid)
                fmt = WAVEFORMATEX(1, canaux, taux, taux * canaux * 2, canaux * 2, 16, 0)
                client.Initialize(AUDCLNT_SHAREMODE_SHARED, FLAGS, 2_000_000, 0, byref(fmt), None)
                break
            except Exception as exc:
                derniere = exc
        else:
            raise OSError(str(derniere) if derniere else "format refusé")
        self.client, self.taux, self.canaux, self.octets_par_trame = client, taux, canaux, canaux * 2
        k32 = ctypes.windll.kernel32
        k32.CreateEventW.restype = HANDLE
        self._evenement = k32.CreateEventW(None, False, False, None)
        self.client.SetEventHandle(self._evenement)
        self.capture = self.client.GetService(byref(IAudioCaptureClient._iid_)).QueryInterface(IAudioCaptureClient)

    def __enter__(self) -> "CaptureProcessus":
        self.client.Start()
        return self

    def __exit__(self, *exc) -> None:
        try:
            self.client.Stop()
        finally:
            ctypes.windll.kernel32.CloseHandle(self._evenement)

    def lire(self, attente_ms: int = 200) -> list[bytes]:
        ctypes.windll.kernel32.WaitForSingleObject(self._evenement, attente_ms)
        paquets: list[bytes] = []
        n = self.capture.GetNextPacketSize()
        while n:
            donnees, trames, drapeaux, _, _ = self.capture.GetBuffer()
            taille = trames * self.octets_par_trame
            paquets.append(bytes(taille) if drapeaux & SILENCE else ctypes.string_at(donnees, taille))
            self.capture.ReleaseBuffer(trames)
            n = self.capture.GetNextPacketSize()
        return paquets
