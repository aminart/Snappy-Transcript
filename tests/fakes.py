"""Sources audio factices pour les tests : pas de micro, pas de PortAudio."""
import queue

from snappy.audio.base import AudioSource

RATE = 16000
BLOC = b"\x00\x00" * (RATE // 10)  # 100 ms de silence PCM16


class SourceFactice(AudioSource):
    sample_rate = RATE

    def __init__(self, blocs=0, echec_apres_arret=False, echec_au_demarrage=False):
        self.q: queue.Queue = queue.Queue()
        for _ in range(blocs):
            self.q.put(BLOC)
        self.arretee = False
        self.echec_apres_arret = echec_apres_arret
        self.echec_au_demarrage = echec_au_demarrage

    def start(self):
        if self.echec_au_demarrage:
            raise OSError("périphérique occupé")

    def stop(self):
        self.arretee = True

    def read_chunk(self, timeout=0.2):
        if self.arretee and self.echec_apres_arret:
            raise RuntimeError("boucle système perdue")
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None


class SourceContinue(SourceFactice):
    """Comme un vrai micro : un bloc de 100 ms toutes les 10 ms (10× le temps réel), sans fin."""

    def read_chunk(self, timeout=0.2):
        import time
        if self.arretee:  # comme un micro fermé : plus rien à lire
            return None
        time.sleep(0.01)
        return BLOC
