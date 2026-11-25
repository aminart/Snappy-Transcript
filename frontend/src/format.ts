const deux = (n: number) => String(n).padStart(2, "0");

/** 3725 → « 01:02:05 » */
export const hms = (secondes: number): string => {
  const s = Math.max(0, Math.floor(secondes));
  return `${deux(Math.floor(s / 3600))}:${deux(Math.floor((s % 3600) / 60))}:${deux(s % 60)}`;
};

/** 95 → « 1 min 35 s » (durées d'attente) */
export const duree = (secondes: number): string => {
  const s = Math.max(0, Math.round(secondes));
  return s >= 60 ? `${Math.floor(s / 60)} min ${deux(s % 60)} s` : `${s} s`;
};

export const LIBELLES_STATUT: Record<string, string> = {
  LISTENING: "À l'écoute",
  TRANSCRIBING: "Transcription",
  PAUSED: "En pause",
  STOPPED: "Terminé",
  ERROR: "Erreur",
};
