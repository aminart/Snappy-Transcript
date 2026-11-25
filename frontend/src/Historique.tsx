import React from "react";
import { api, messageErreur } from "./api";
import { Reprise } from "./components/DiarizationPanel";
import { Alerte } from "./components/ui";
import { hms } from "./format";
import type { Capabilities, SessionPassee, Settings } from "./types";

const date = (id: string) => {
  const [j, h] = id.split("_");
  const [a, m, d] = j.split("-");
  return `${d}/${m}/${a} à ${h.slice(0, 5).replace("-", ":")}`;
};

/** Sessions passées : rouvrir (texte, lecteur, corrections, intervenants), ouvrir le dossier, supprimer. */
export const Historique: React.FC = () => {
  const [sessions, setSessions] = React.useState<SessionPassee[] | null>(null);
  const [reglages, setReglages] = React.useState<Settings | null>(null);
  const [capacites, setCapacites] = React.useState<Capabilities | null>(null);
  const [erreur, setErreur] = React.useState("");
  const [aSupprimer, setASupprimer] = React.useState<string | null>(null);

  const charger = React.useCallback(() => {
    api<{ sessions: SessionPassee[] }>("/api/history").then((r) => setSessions(r.sessions)).catch((e) => setErreur(messageErreur(e)));
  }, []);
  React.useEffect(() => {
    charger();
    api<Settings>("/api/settings").then(setReglages).catch(() => undefined);
    api<Capabilities>("/api/capabilities").then(setCapacites).catch(() => undefined);
  }, [charger]);

  const faire = async (f: () => Promise<unknown>) => {
    setErreur("");
    try { await f(); } catch (e) { setErreur(messageErreur(e)); }
  };
  const rouvrir = (id: string) => faire(async () => {
    await api(`/api/history/${id}/open`, { method: "POST" });
    window.location.hash = "#/";
  });
  const dossier = (id: string) => faire(() => api(`/api/history/${id}/folder`, { method: "POST" }));
  const supprimer = (id: string) => faire(async () => {
    setSessions((await api<{ sessions: SessionPassee[] }>(`/api/history/${id}`, { method: "DELETE" })).sessions);
    setASupprimer(null);
  });

  return (
    <>
      <div className="nn-page-head">
        <div>
          <h1 className="nn-page-title">Mes transcriptions</h1>
          <p className="nn-page-subtitle">Toutes vos transcriptions, enregistrées sur cet ordinateur. Rouvrez-en une pour la réécouter, la corriger ou nommer les intervenants.</p>
        </div>
      </div>
      {erreur && <Alerte>{erreur}</Alerte>}
      {!sessions ? <p className="m-0 text-sm text-ink-muted">Chargement…</p> : sessions.length === 0 ? (
        <p className="m-0 rounded-lg border border-dashed border-line-dashed px-6 py-10 text-center text-sm text-ink-muted">
          Aucune transcription pour l'instant.
        </p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {sessions.map((s) => (
            <li key={s.id} className="nn-card flex flex-wrap items-center gap-3 p-4">
              <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-0.5">
                <span className="text-sm font-semibold text-ink">
                  {s.kind === "file" && s.name ? s.name : "Enregistrement en direct"}
                  {s.current && <span className="nn-chip ml-2 align-middle">Ouverte</span>}
                </span>
                <span className="text-[13px] text-ink-muted">
                  {date(s.id)}
                  {s.interrupted ? " · interrompue (application fermée pendant l'enregistrement)" : [
                    s.duration ? ` · ${hms(s.duration)}` : "",
                    s.segments !== null ? ` · ${s.segments} phrase${s.segments === 1 ? "" : "s"}` : "",
                    s.diarized ? " · avec intervenants" : "",
                    s.audio ? "" : " · sans audio",
                  ].join("")}
                </span>
              </div>
              {aSupprimer === s.id ? (
                <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Confirmer la suppression">
                  <span className="text-[13px] text-danger-text">Supprimer le texte et l'audio ?</span>
                  <button type="button" className="nn-btn nn-btn-secondary" onClick={() => supprimer(s.id)}>Supprimer</button>
                  <button type="button" className="nn-btn nn-btn-secondary" onClick={() => setASupprimer(null)}>Annuler</button>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {!s.interrupted && <button type="button" className="nn-btn nn-btn-primary" onClick={() => rouvrir(s.id)}>Rouvrir</button>}
                  <button type="button" className="nn-btn nn-btn-secondary" onClick={() => dossier(s.id)}>Ouvrir le dossier</button>
                  {!s.current && <button type="button" className="nn-btn nn-btn-secondary" onClick={() => setASupprimer(s.id)}>Supprimer</button>}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {reglages && (
        <Reprise cheminPipeline={reglages.diarization_model_path} locuteurs={reglages.speaker_hint} disponible={capacites?.diarization ?? false} />
      )}
    </>
  );
};
