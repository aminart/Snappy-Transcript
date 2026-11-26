import React from "react";
import { api, messageErreur } from "../api";
import type { Settings, SessionState } from "../types";
import { DiarizationPanel } from "./DiarizationPanel";
import { ResultatPage } from "./ResultatPage";
import { Alerte } from "./ui";

interface Props {
  etat: SessionState;
  reglages: Settings;
  regler: <K extends keyof Settings>(cle: K, valeur: Settings[K]) => void;
  diarisationDispo: boolean;
  action: (chemin: string, corps?: unknown) => Promise<unknown>;
  rafraichir: () => Promise<unknown>;
  /** Bouton du haut : « Nouvelle transcription » (Transcrire) ou « Mes transcriptions » (retour à la liste). */
  retour: { label: string; faire: () => void };
  /** Bandeau « Terminé » et lien vers Mes transcriptions : seulement juste après une session. */
  vientDeFinir: boolean;
  diagnostic?: React.ReactNode;
}

/** Résultat d'une session, affiché à la fin d'une transcription comme à la réouverture depuis Mes transcriptions. */
export const VueResultat: React.FC<Props> = ({ etat, reglages: r, regler, diarisationDispo, action, rafraichir, retour, vientDeFinir, diagnostic }) => {
  const [erreur, setErreur] = React.useState("");
  const fichiers = (etat.files ?? {}) as { wav?: boolean };
  const ajouterAuGlossaire = (mot: string) => {
    const mots = r.glossary.split(",").map((m) => m.trim()).filter(Boolean);
    if (!mots.some((m) => m.toLowerCase() === mot.toLowerCase())) regler("glossary", [...mots, mot].join(", "));
  };
  const ouvrirDossier = () => api("/api/session/open-folder", { method: "POST" }).catch((e) => setErreur(messageErreur(e)));
  return (
    <div className="flex flex-col gap-5">
      {erreur && <Alerte>{erreur}</Alerte>}
      {etat.error && <Alerte type={etat.archived ? "info" : "danger"}>{etat.error}</Alerte>}
      {vientDeFinir && etat.status !== "ERROR" && (
        <Alerte type="success">{etat.kind === "file" && etat.stopping
          ? "Transcription arrêtée : le texte obtenu jusque-là est enregistré."
          : "Terminé : le texte est prêt et enregistré dans « Mes transcriptions »."}</Alerte>
      )}
      <ResultatPage etat={etat} audio={!!fichiers.wav} rafraichir={() => { rafraichir().catch(() => undefined); }}
        ajouterAuGlossaire={ajouterAuGlossaire} retour={retour}
        panneauIntervenants={<DiarizationPanel etat={etat} cheminPipeline={r.diarization_model_path} locuteurs={r.speaker_hint} disponible={diarisationDispo}
          relancer={async (corps) => { await action("/api/session/diarization", corps); }} />} />
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="nn-btn nn-btn-secondary" onClick={ouvrirDossier}>Ouvrir le dossier</button>
        {vientDeFinir && <span className="text-[13px] text-ink-muted">Cette session reste disponible dans <a href="#/historique" className="text-accent underline">Mes transcriptions</a>.</span>}
      </div>
      {diagnostic}
    </div>
  );
};
