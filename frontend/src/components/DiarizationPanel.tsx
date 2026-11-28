import React from "react";
import { api, messageErreur } from "../api";
import { duree } from "../format";
import { Alerte, Progression } from "./ui";
import type { SessionState } from "../types";

interface Props {
  etat: SessionState;
  /** Dossier du modèle ; vide quand celui de l'équipe (Studio Dock) est utilisé. */
  cheminPipeline: string;
  /** Un modèle est disponible : celui de l'équipe, ou un dossier indiqué. */
  pipelinePret: boolean;
  locuteurs: number;
  disponible: boolean;
  relancer: (corps: { model_path: string; speakers: number }) => Promise<void>;
  /** Recharger l'état de la session (après « Arrêter »). */
  rafraichir?: () => void;
}

export const DiarizationPanel: React.FC<Props> = ({ etat, cheminPipeline, pipelinePret, locuteurs, disponible, relancer, rafraichir }) => {
  const d = etat.diarization;
  const [erreur, setErreur] = React.useState("");
  const [occupe, setOccupe] = React.useState(false);
  const wav = Boolean((etat.files as { wav?: boolean }).wav);

  const lancer = async () => {
    setOccupe(true);
    setErreur("");
    try { await relancer({ model_path: cheminPipeline, speakers: locuteurs }); } catch (e) { setErreur(messageErreur(e)); } finally { setOccupe(false); }
  };
  const arreter = async () => {
    setErreur("");
    try { await api("/api/session/diarization/stop", { method: "POST" }); rafraichir?.(); } catch (e) { setErreur(messageErreur(e)); }
  };
  const bouton = (libelle: string) => (
    <button type="button" className="nn-btn nn-btn-secondary self-start" onClick={lancer} disabled={occupe || !disponible || !wav || !pipelinePret}>
      {libelle}
    </button>
  );
  const impossible = !disponible ? "L'identification des intervenants n'est pas incluse dans cette installation."
    : !wav ? "L'enregistrement audio n'a pas été gardé : les intervenants ne peuvent plus être identifiés."
    : !pipelinePret ? "Aucun modèle d'identification des intervenants : indiquez son dossier dans Transcrire › Réglages avancés." : "";

  return (
    <div className="flex flex-col gap-3" aria-live="polite">
      {d.status === "RUNNING" && (
        <>
          <Progression fraction={d.stopping ? null : d.fraction}
            libelle={d.stopping ? "Arrêt de l'identification…"
              : `${d.phase}${d.fraction !== null ? ` · ${Math.round(d.fraction * 100)} %` : ""}${d.eta !== null ? ` · reste environ ${duree(d.eta)}` : ` · ${duree(d.elapsed)} écoulées`}`} />
          <div className="flex items-center gap-3">
            <p className="m-0 min-w-0 flex-1 text-[13px] text-ink-muted">Le texte est déjà utilisable. Vous pouvez quitter cette page : l'identification continue.</p>
            <button type="button" className="nn-btn nn-btn-secondary shrink-0" onClick={arreter} disabled={d.stopping}>
              {d.stopping ? "Arrêt…" : "Arrêter"}
            </button>
          </div>
        </>
      )}
      {d.status === "IDLE" && d.wanted && <Alerte type="info">Les intervenants seront identifiés juste après la transcription.</Alerte>}
      {d.status === "IDLE" && !d.wanted && (
        <>
          <p className="m-0 text-sm text-ink-muted">{d.note ? d.note.replace(/^Diarisation non lancée/, "Intervenants non identifiés") : "Les intervenants n'ont pas été identifiés pour cette session."}</p>
          {impossible ? <p className="m-0 text-[13px] text-ink-muted">{impossible}</p> : bouton("Identifier les intervenants maintenant")}
        </>
      )}
      {d.status === "DONE" && (
        <>
          <p className="m-0 text-sm text-ink-body">
            ✓ Identification terminée.
          </p>
          {!impossible && bouton("Recommencer l'identification")}
        </>
      )}
      {d.status === "CANCELLED" && (
        <>
          <p className="m-0 text-sm text-ink-body">Identification arrêtée. Le texte reste intact.</p>
          {impossible ? <p className="m-0 text-[13px] text-ink-muted">{impossible}</p> : bouton("Relancer l'identification")}
        </>
      )}
      {d.status === "ERROR" && (
        <>
          <Alerte type="warning">L'identification des intervenants a échoué ; le texte reste intact. {d.error}</Alerte>
          {!impossible && bouton("Réessayer")}
        </>
      )}
      {erreur && <Alerte>{erreur}</Alerte>}
    </div>
  );
};
