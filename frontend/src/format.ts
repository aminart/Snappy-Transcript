const deux = (n: number) => String(n).padStart(2, "0");

/** 3725 → « 01:02:05 » */
export const hms = (secondes: number): string => {
  const s = Math.max(0, Math.floor(secondes));
  return `${deux(Math.floor(s / 3600))}:${deux(Math.floor((s % 3600) / 60))}:${deux(s % 60)}`;
};

/** 1 536 000 → « 1,5 Mo » */
export const taille = (octets: number): string => {
  if (octets < 1024 * 1024) return `${Math.max(1, Math.round(octets / 1024))} Ko`;
  const mo = octets / (1024 * 1024);
  return mo < 1024 ? `${mo.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mo` : `${(mo / 1024).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} Go`;
};

/** 95 → « 1 min 35 s » (durées d'attente) */
export const duree = (secondes: number): string => {
  const s = Math.max(0, Math.round(secondes));
  if (s >= 3600) return `${Math.floor(s / 3600)} h ${deux(Math.floor((s % 3600) / 60))} min`;
  return s >= 60 ? `${Math.floor(s / 60)} min ${deux(s % 60)} s` : `${s} s`;
};

export const LIBELLES_STATUT: Record<string, string> = {
  LISTENING: "À l'écoute",
  TRANSCRIBING: "Transcription",
  DECODING: "Lecture du fichier",
  PAUSED: "En pause",
  STOPPED: "Terminé",
  ERROR: "Erreur",
};
