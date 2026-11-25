import React from "react";
import { api } from "./api";
import type { Segment, SessionState } from "./types";

/**
 * Suit la session du serveur : une requête par seconde pendant l'enregistrement, toutes les 2 s pendant la
 * diarisation, puis plus rien. Seuls les segments nouveaux sont transférés (paramètre `after`).
 * Une page rechargée en cours de session retrouve la session et tout son texte.
 */
export function useSession() {
  const [state, setState] = React.useState<SessionState | null>(null);
  const [segments, setSegments] = React.useState<Segment[]>([]);
  const possedes = React.useRef(0);
  const ordre = React.useRef(0);

  const appliquer = React.useCallback((s: SessionState) => {
    if (!s.active) {
      possedes.current = 0;
      setSegments([]);
      setState(null);
      return;
    }
    // `from` : à partir de quel segment le serveur répond (0 si le client était désynchronisé)
    setSegments((avant) => (s.from === 0 ? s.segments : [...avant.slice(0, s.from), ...s.segments]));
    possedes.current = s.total;
    setState(s);
  }, []);

  const rafraichir = React.useCallback(async () => {
    const numero = ++ordre.current;
    const s = await api<SessionState>(`/api/session?after=${possedes.current}`);
    if (numero === ordre.current) appliquer(s); // une réponse plus ancienne ne remplace jamais une plus récente
  }, [appliquer]);

  React.useEffect(() => { rafraichir().catch(() => undefined); }, [rafraichir]);

  const enCours = !!state && (!state.finalized || state.diarization.status === "RUNNING"
    || (state.diarization.wanted && state.diarization.status === "IDLE"));
  const finalisee = state?.finalized ?? false;
  React.useEffect(() => {
    if (!enCours) return;
    const minuteur = setInterval(() => rafraichir().catch(() => undefined), finalisee ? 2000 : 1000);
    return () => clearInterval(minuteur);
  }, [enCours, finalisee, rafraichir]);

  const action = React.useCallback(async (chemin: string, corps?: unknown) => {
    ordre.current++;
    possedes.current = 0; // la réponse d'une action contient tous les segments
    appliquer(await api<SessionState>(chemin, { method: "POST", json: corps }));
  }, [appliquer]);

  const oublier = React.useCallback(async () => {
    await api("/api/session", { method: "DELETE" });
    appliquer({ active: false } as SessionState);
  }, [appliquer]);

  return { state, segments, action, oublier, rafraichir };
}
