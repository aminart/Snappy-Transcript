"""Liste des microphones : une ligne par appareil, nom complet, micro par défaut en premier."""
from types import SimpleNamespace

from snappy.audio.microphone import list_input_devices


def faux_sd(appareils, apis, api_defaut, entree_defaut):
    return SimpleNamespace(query_devices=lambda: appareils, query_hostapis=lambda: apis,
                           default=SimpleNamespace(hostapi=api_defaut, device=(entree_defaut, -1)))


def micro(nom, api, canaux=2):
    return {"name": nom, "hostapi": api, "max_input_channels": canaux, "default_samplerate": 48000}


def test_windows_un_micro_une_ligne_nom_complet_defaut_en_premier():
    apis = [{"name": "MME"}, {"name": "Windows DirectSound"}, {"name": "Windows WASAPI"}, {"name": "Windows WDM-KS"}]
    appareils = [
        micro("Mappeur de sons Microsoft - Input", 0),
        micro("Microphone (Realtek(R) Audio)", 0),
        micro("Casque (Jabra Evolve2 65 Strea", 0),          # MME : coupé à 31 caractères
        micro("Haut-parleurs (Realtek)", 0, canaux=0),       # sortie : ignorée
        micro("Pilote de capture audio principal", 1),
        micro("Microphone (Realtek(R) Audio)", 1),
        micro("Casque (Jabra Evolve2 65 Stream)", 2),        # WASAPI : nom complet
        micro("Microphone (Realtek(R) Audio)", 2),
        micro("Microphone (Realtek HD Audio Mic input)", 3),
        micro("Mixage stéréo (Realtek(R) Audio)", 0),       # le son du PC, pas un micro
    ]
    liste = list_input_devices(faux_sd(appareils, apis, 0, 2))
    assert [(d["index"], d["name"], d["default"]) for d in liste] == [
        (2, "Casque (Jabra Evolve2 65 Stream)", True),
        (1, "Microphone (Realtek(R) Audio)", False),
    ]


def test_mac_rien_n_est_retire():
    apis = [{"name": "Core Audio"}]
    appareils = [micro("Micro MacBook Pro", 0, 1), micro("AirPods de Marie", 0, 1)]
    liste = list_input_devices(faux_sd(appareils, apis, 0, 1))
    assert [d["name"] for d in liste] == ["AirPods de Marie", "Micro MacBook Pro"]
