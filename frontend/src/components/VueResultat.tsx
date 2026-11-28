import React from "react";
import { api } from "../api";
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
  /** Second bouton du haut (Transcrire) : « ← Mes transcriptions », pour sortir sans commencer une nouvelle transcription. */
  aussi?: { label: string; faire: () => void };
}

/** Résultat d'une session, affiché à la fin d'une transcription comme à la réouverture depuis Mes transcriptions. */
export const VueResultat: React.FC<Props> = ({ etat, reglages: r, regler, diarisationDispo, action, rafraichir, retour, vientDeFinir, diagnostic, aussi }) => {
  const [equipe, setEquipe] = React.useState(false);
  React.useEffect(() => {
    api<{ team_diarization: unknown }>("/api/model").then((m) => setEquipe(!!m.team_diarization)).catch(() => setEquipe(false));
  }, []);
  const parEquipe = equipe && !r.use_own_diarization_model;
  const fichiers = (etat.files ?? {}) as { wav?: boolean };
  const ajouterAuGlossaire = (mot: string) => {
    const mots = r.glossary.split(",").map((m) => m.trim()).filter(Boolean);
    if (!mots.some((m) => m.toLowerCase() === mot.toLowerCase())) regler("glossary", [...mots, mot].join(", "));
  };
  return (
    <div className="flex flex-col gap-5">
      {etat.error && <Alerte type={etat.archived ? "info" : "danger"}>{etat.error}</Alerte>}
      {vientDeFinir && etat.status !== "ERROR" && (
        <Alerte type="success">{etat.kind === "file" && etat.stopping
          ? "Transcription arrêtée : le texte obtenu jusque-là est enregistré."
          : "Terminé : le texte est prêt et enregistré dans « Mes transcriptions »."}</Alerte>
      )}
      <ResultatPage etat={etat} audio={!!fichiers.wav} rafraichir={() => { rafraichir().catch(() => undefined); }}
        ajouterAuGlossaire={ajouterAuGlossaire} retour={retour} aussi={aussi}
        panneauIntervenants={<DiarizationPanel etat={etat} cheminPipeline={parEquipe ? "" : r.diarization_model_path}
          pipelinePret={parEquipe || !!r.diarization_model_path.trim()} locuteurs={r.speaker_hint} disponible={diarisationDispo}
          relancer={async (corps) => { await action("/api/session/diarization", corps); }}
          rafraichir={() => { rafraichir().catch(() => undefined); }} />} />
      {diagnostic}
    </div>
  );
};
