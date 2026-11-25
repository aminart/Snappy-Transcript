import React from "react";
import { api, messageErreur } from "../api";
import { duree } from "../format";
import { Alerte, Progression } from "./ui";
import type { SessionState } from "../types";

interface Props {
  etat: SessionState;
  cheminPipeline: string;
  locuteurs: number;
  disponible: boolean;
  relancer: (corps: { model_path: string; speakers: number }) => Promise<void>;
}

export const DiarizationPanel: React.FC<Props> = ({ etat, cheminPipeline, locuteurs, disponible, relancer }) => {
  const d = etat.diarization;
  const [erreur, setErreur] = React.useState("");
  const [occupe, setOccupe] = React.useState(false);
  const wav = Boolean((etat.files as { wav?: boolean }).wav);

  const lancer = async () => {
    setOccupe(true);
    setErreur("");
    try { await relancer({ model_path: cheminPipeline, speakers: locuteurs }); } catch (e) { setErreur(messageErreur(e)); } finally { setOccupe(false); }
  };
  const bouton = (libelle: string) => (
    <button type="button" className="nn-btn nn-btn-secondary self-start" onClick={lancer} disabled={occupe || !disponible || !wav || !cheminPipeline.trim()}>
      {libelle}
    </button>
  );
  const impossible = !disponible ? "L'identification des intervenants n'est pas incluse dans cette installation."
    : !wav ? "L'enregistrement audio n'a pas été gardé : les intervenants ne peuvent plus être identifiés."
    : !cheminPipeline.trim() ? "Indiquez le dossier du modèle d'identification dans les réglages (section Intervenants)." : "";

  return (
    <div className="flex flex-col gap-3" aria-live="polite">
      {d.status === "RUNNING" && (
        <Progression fraction={d.fraction}
          libelle={`Identification des intervenants · ${d.phase}${d.fraction !== null ? ` · ${Math.round(d.fraction * 100)} %` : ""} · ${duree(d.elapsed)} écoulées${d.eta !== null ? ` · reste environ ${duree(d.eta)}` : ""}`} />
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

/** Reprise après coup : un WAV et un SRT déjà sur le disque ; rien ne transite par le navigateur. */
export const Reprise: React.FC<{ cheminPipeline: string; locuteurs: number; disponible: boolean }> = ({ cheminPipeline, locuteurs, disponible }) => {
  const [wav, setWav] = React.useState("");
  const [srt, setSrt] = React.useState("");
  const [n, setN] = React.useState(0);
  const [etat, setEtat] = React.useState<SessionState["diarization"] | null>(null);
  const [erreur, setErreur] = React.useState("");

  const suivre = React.useCallback(async () => { setEtat(await api("/api/posthoc")); }, []);
  React.useEffect(() => { suivre().catch(() => undefined); }, [suivre]);
  React.useEffect(() => {
    if (etat?.status !== "RUNNING") return;
    const t = setInterval(() => suivre().catch(() => undefined), 1500);
    return () => clearInterval(t);
  }, [etat?.status, suivre]);

  const lancer = async () => {
    setErreur("");
    try { setEtat(await api("/api/posthoc", { method: "POST", json: { wav_path: wav, srt_path: srt, model_path: cheminPipeline, speakers: n || locuteurs } })); }
    catch (e) { setErreur(messageErreur(e)); }
  };

  const sorties = etat?.outputs;
  return (
    <details className="nn-card p-5">
      <summary className="cursor-pointer text-[15px] font-bold text-ink">Identifier les intervenants d'un enregistrement existant</summary>
      <div className="mt-4 flex flex-col gap-4">
        <p className="m-0 text-[13px] text-ink-muted">Indiquez les chemins locaux du WAV et du SRT : aucun gros fichier ne passe par le navigateur. Les fichiers « _diarized » sont écrits à côté du WAV.</p>
        {!disponible && <Alerte type="warning">L'identification des intervenants n'est pas incluse dans cette installation.</Alerte>}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="reprise-wav" className="text-sm font-medium text-ink">Chemin du WAV</label>
          <input id="reprise-wav" className="nn-input" value={wav} onChange={(e) => setWav(e.target.value)} placeholder="C:\…\recording.wav" spellCheck={false} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="reprise-srt" className="text-sm font-medium text-ink">Chemin du SRT</label>
          <input id="reprise-srt" className="nn-input" value={srt} onChange={(e) => setSrt(e.target.value)} placeholder="C:\…\transcript.srt" spellCheck={false} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="reprise-n" className="text-sm font-medium text-ink">Nombre d'intervenants (0 = comme dans les réglages)</label>
          <input id="reprise-n" type="number" min={0} max={20} className="nn-input max-w-[160px]" value={n}
            onChange={(e) => setN(Math.max(0, Math.min(20, Math.floor(Number(e.target.value) || 0))))} />
        </div>
        <button type="button" className="nn-btn nn-btn-primary self-start" onClick={lancer}
          disabled={!disponible || !wav.trim() || !srt.trim() || etat?.status === "RUNNING"}>Identifier les intervenants</button>
        {erreur && <Alerte>{erreur}</Alerte>}
        {etat?.status === "RUNNING" && (
          <Progression fraction={etat.fraction} libelle={`${etat.phase}${etat.fraction !== null ? ` · ${Math.round(etat.fraction * 100)} %` : ""} · écoulé ${duree(etat.elapsed)}${etat.eta !== null ? ` · reste ~${duree(etat.eta)}` : ""}`} />
        )}
        {etat?.status === "ERROR" && <Alerte type="warning">{etat.error}</Alerte>}
        {etat?.status === "DONE" && sorties && (
          <>
            <Alerte type="success">Terminé : {etat.segments} segments. Fichiers écrits à côté du WAV :<br /><span className="font-mono text-[13px]">{sorties.txt}<br />{sorties.srt}</span></Alerte>
            <div className="flex gap-2">
              <a className="nn-btn nn-btn-secondary" href="/api/posthoc/file/txt" download>⬇ TXT</a>
              <a className="nn-btn nn-btn-secondary" href="/api/posthoc/file/srt" download>⬇ SRT</a>
            </div>
          </>
        )}
      </div>
    </details>
  );
};
