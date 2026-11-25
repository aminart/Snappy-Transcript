import React from "react";
import { api, envoyerFichier, messageErreur } from "./api";
import { DiarizationPanel, Reprise } from "./components/DiarizationPanel";
import { type ChoixFichier, FilePicker } from "./components/FilePicker";
import { SettingsPanel } from "./components/SettingsPanel";
import { SyncPlayer } from "./components/SyncPlayer";
import { Alerte, Chiffre, Progression, Section } from "./components/ui";
import { LIBELLES_STATUT, duree, hms } from "./format";
import type { AvancementFichier, Capabilities, Cuda, Devices, Mode, ModeleEquipe, Segment, Settings, SessionState, Verification } from "./types";
import { useSession } from "./useSession";

const LIGNES_AFFICHEES = 400;

/** Réglages mémorisés côté serveur : chaque changement est enregistré après une courte pause de frappe. */
function useReglages() {
  const [reglages, setReglages] = React.useState<Settings | null>(null);
  const attente = React.useRef<Record<string, unknown>>({});
  const minuteur = React.useRef<number | undefined>(undefined);

  React.useEffect(() => { api<Settings>("/api/settings").then(setReglages).catch(() => undefined); }, []);

  const regler = React.useCallback(<K extends keyof Settings>(cle: K, valeur: Settings[K]) => {
    setReglages((s) => (s ? { ...s, [cle]: valeur } : s));
    attente.current[cle] = valeur;
    window.clearTimeout(minuteur.current);
    minuteur.current = window.setTimeout(() => {
      const valeurs = attente.current;
      attente.current = {};
      api("/api/settings", { method: "PUT", json: valeurs }).catch(() => undefined);
    }, 500);
  }, []);
  return { reglages, regler };
}

/** Vérifie un chemin saisi (modèle, pipeline) auprès du serveur, une fois la frappe terminée. */
function useVerification(url: string, chemin: string): Verification | null {
  const [resultat, setResultat] = React.useState<Verification | null>(null);
  React.useEffect(() => {
    if (!chemin.trim()) { setResultat(null); return; }
    let annule = false;
    const t = setTimeout(() => {
      api<Verification>(url, { method: "POST", json: { path: chemin } })
        .then((v) => { if (!annule) setResultat(v); })
        .catch(() => { if (!annule) setResultat(null); });
    }, 400);
    return () => { annule = true; clearTimeout(t); };
  }, [url, chemin]);
  return resultat;
}

const Direct: React.FC<{ segments: Segment[]; horodatage: boolean; termine: boolean }> = ({ segments, horodatage, termine }) => {
  const zone = React.useRef<HTMLDivElement>(null);
  const colle = React.useRef(true); // reste collé en bas, sauf si la personne remonte lire
  const visibles = segments.length > LIGNES_AFFICHEES ? segments.slice(-LIGNES_AFFICHEES) : segments;

  React.useLayoutEffect(() => {
    const z = zone.current;
    if (z && colle.current) z.scrollTop = z.scrollHeight;
  }, [segments]);

  return (
    <div>
      {segments.length > LIGNES_AFFICHEES && (
        <p className="m-0 mb-2 text-[13px] text-ink-muted">Affichage limité aux {LIGNES_AFFICHEES} dernières lignes ; le texte complet est conservé dans le fichier de récupération.</p>
      )}
      <div ref={zone} tabIndex={0} aria-label="Transcription en direct"
        onScroll={(e) => { const z = e.currentTarget; colle.current = z.scrollTop + z.clientHeight >= z.scrollHeight - 40; }}
        className="nn-card max-h-[460px] min-h-[200px] overflow-auto whitespace-pre-wrap p-4 font-mono text-sm leading-relaxed text-ink">
        {visibles.length === 0 ? (
          <span className="font-sans text-ink-muted">{termine ? "Aucune parole détectée." : "En attente du premier bloc transcrit…"}</span>
        ) : visibles.map((s, i) => (
          <div key={segments.length - visibles.length + i}>
            {horodatage && <span className="text-ink-muted">[{hms(s.start)}] </span>}
            {s.speaker && <span className="font-bold">{s.speaker} : </span>}
            {s.text}
          </div>
        ))}
      </div>
    </div>
  );
};

const AvancementFichierVue: React.FC<{ etat: SessionState; avancement: AvancementFichier }> = ({ etat, avancement: a }) => {
  const pct = a.fraction === null ? null : Math.round(a.fraction * 100);
  const etape = a.phase === "decoding" ? "Lecture du fichier" : a.phase === "transcribing" ? "Transcription" : "Terminé";
  const details = [
    pct !== null && a.phase !== "done" ? `${pct} %` : "",
    etat.paused ? "en pause" : a.eta !== null ? `reste ~${duree(a.eta)}` : "",
  ].filter(Boolean).join(" · ");
  return (
    <div className="nn-card flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="min-w-0 break-all text-sm font-medium text-ink">{a.name}</span>
        <span className="text-[13px] text-ink-muted">{a.media_duration ? `Durée ${hms(a.media_duration)}` : ""}</span>
      </div>
      {!etat.finalized && <Progression fraction={a.fraction} libelle={`${etape}${details ? ` · ${details}` : ""}`} />}
    </div>
  );
};

const Diagnostic: React.FC<{ etat: SessionState }> = ({ etat }) => {
  const p = etat.provider;
  const lignes: [string, string][] = [
    ["Moteur", p.engine],
    ["faster-whisper", p.faster_whisper ?? "—"],
    ["CTranslate2", p.ctranslate2 ?? "—"],
    ["Calcul", p.compute ?? "—"],
    ["Repli d'accélération", p.fallback || "—"],
    ["Dernière latence STT", `${etat.stats.last_latency.toFixed(2)} s pour ${etat.stats.last_chunk_duration.toFixed(2)} s d'audio`],
    ["Ratio temps réel moyen", `${etat.stats.average_realtime_ratio.toFixed(2)}× (moins de 1× : le STT suit ; plus de 1× : il prend du retard)`],
    ["Mots de recouvrement retirés", String(etat.stats.duplicate_words_removed)],
    ["Dossier de la session", etat.session_dir],
    ["Copie de récupération", etat.recovery_copy],
  ];
  return (
    <details className="nn-card p-5">
      <summary className="cursor-pointer text-[15px] font-bold text-ink">Diagnostic</summary>
      <dl className="m-0 mt-4 grid gap-x-6 gap-y-2 text-sm" style={{ gridTemplateColumns: "210px minmax(0, 1fr)" }}>
        {lignes.map(([k, v]) => (
          <React.Fragment key={k}><dt className="text-ink-muted">{k}</dt><dd className="m-0 break-words text-ink">{v}</dd></React.Fragment>
        ))}
      </dl>
    </details>
  );
};

export const Transcription: React.FC = () => {
  const { reglages, regler } = useReglages();
  const { state, segments, action, oublier } = useSession();
  const [capacites, setCapacites] = React.useState<Capabilities | null>(null);
  const [peripheriques, setPeripheriques] = React.useState<Devices | null>(null);
  const [cuda, setCuda] = React.useState<Cuda | null>(null);
  const [equipe, setEquipe] = React.useState<ModeleEquipe | null | undefined>(undefined);
  const [erreur, setErreur] = React.useState("");
  const [demarrage, setDemarrage] = React.useState(false);
  const [horodatage, setHorodatage] = React.useState(true);
  const [choix, setChoix] = React.useState<ChoixFichier>(null);
  const [envoi, setEnvoi] = React.useState<number | null>(null); // avancement de l'envoi du fichier

  const actualiser = React.useCallback(() => { api<Devices>("/api/devices").then(setPeripheriques).catch(() => undefined); }, []);
  React.useEffect(() => {
    api<Capabilities>("/api/capabilities").then(setCapacites).catch(() => undefined);
    api<Cuda>("/api/cuda").then(setCuda).catch(() => undefined);
    api<{ team: ModeleEquipe | null }>("/api/model").then((m) => setEquipe(m.team)).catch(() => setEquipe(null));
    actualiser();
  }, [actualiser]);

  const modele = useVerification("/api/model/check", reglages?.model_path ?? "");
  const pipeline = useVerification("/api/diarization/check", reglages?.diarization_model_path ?? "");

  if (!reglages) return <p className="m-0 text-sm text-ink-muted">Chargement…</p>;

  const r = reglages;
  const entrees = peripheriques?.inputs ?? [];
  const sorties = peripheriques?.outputs ?? [];
  const micChoisi = entrees.find((d) => d.name === r.input_device) ?? entrees[0];
  const avecMicro = r.source !== "system";
  const avecSysteme = r.source !== "microphone";
  const occupe = !!state && !state.finalized;
  const enCours = occupe && !state!.stopping;
  const diarisationEnCours = state?.diarization.status === "RUNNING";
  const diarisationDispo = capacites?.diarization ?? false;

  const modeFichier = r.mode === "file";
  const modeleEquipe = !!equipe && !r.use_own_model;
  const moteurPret = r.engine === "mock" || ((modeleEquipe || modele?.valid === true) && capacites?.stt !== false);
  const sourcePrete = modeFichier
    ? !!choix && (capacites?.files ?? false)
    : (!avecMicro || !!micChoisi) && (!avecSysteme || !!capacites?.system_audio);
  const peutDemarrer = !occupe && !demarrage && !diarisationEnCours && sourcePrete && moteurPret;

  const changerMode = (m: Mode) => { setErreur(""); regler("mode", m); };

  const options = () => ({
    engine: r.engine, model_path: modeleEquipe ? "" : r.model_path, acceleration: r.acceleration, language: r.language, glossary: r.glossary,
    vad_filter: r.vad_filter, save_audio: r.save_audio, diarization: r.diarization && diarisationDispo,
    diarization_model_path: r.diarization_model_path, speaker_hint: r.speaker_hint,
  });

  const transcrireFichier = async () => {
    if (!choix) return;
    let upload_id = "";
    if (choix.type === "envoi") {
      setEnvoi(0);
      try { upload_id = await envoyerFichier(choix.fichier, setEnvoi); } finally { setEnvoi(null); }
    }
    await action("/api/session/start-file", { ...options(), upload_id, path: choix.type === "chemin" ? choix.chemin : "" });
  };

  const demarrer = async () => {
    setErreur("");
    setDemarrage(true);
    try {
      if (modeFichier) { await transcrireFichier(); return; }
      await action("/api/session/start", {
        source: r.source, engine: r.engine, input_device: avecMicro ? micChoisi?.index ?? null : null,
        output_device: r.output_device || sorties[0]?.name || "", model_path: modeleEquipe ? "" : r.model_path, acceleration: r.acceleration,
        language: r.language, glossary: r.glossary, chunk_seconds: r.chunk_seconds,
        overlap_seconds: Math.min(r.overlap_seconds, r.chunk_seconds - 0.5), vad_filter: r.vad_filter, save_audio: r.save_audio,
        diarization: r.diarization && diarisationDispo, diarization_model_path: r.diarization_model_path, speaker_hint: r.speaker_hint,
      });
    } catch (e) { setErreur(messageErreur(e)); } finally { setDemarrage(false); }
  };
  const commande = (chemin: string) => async () => {
    setErreur("");
    try { await action(chemin); } catch (e) { setErreur(messageErreur(e)); }
  };
  const nouvelle = async () => {
    setErreur("");
    try { await oublier(); } catch (e) { setErreur(messageErreur(e)); }
  };

  // Rien à exporter ni à écouter : fichier illisible, micro en panne dès le départ…
  const echecSansTexte = !!state && state.finalized && state.status === "ERROR" && state.total === 0;
  const fichiers = (state?.files ?? {}) as { wav?: boolean; raw_txt?: boolean; raw_srt?: boolean };

  return (
    <>
      <div className="nn-page-head">
        <div>
          <h1 className="nn-page-title">{modeFichier ? "Transcrire un fichier" : "Transcription en direct"}</h1>
          <p className="nn-page-subtitle">
            {modeFichier ? "Un enregistrement audio ou une vidéo, dans son format d'origine. " : "Du micro ou du son du PC au texte. "}
            Tout reste en local : aucun audio ne quitte cet ordinateur.
          </p>
        </div>
        <div className="nn-segmented" role="group" aria-label="Que transcrire ?">
          <button type="button" aria-pressed={!modeFichier} disabled={occupe || demarrage} onClick={() => changerMode("live")}>En direct</button>
          <button type="button" aria-pressed={modeFichier} disabled={occupe || demarrage} onClick={() => changerMode("file")}>Depuis un fichier</button>
        </div>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        <aside aria-label="Réglages" className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto lg:pr-1">
          <SettingsPanel reglages={r} regler={regler} capacites={capacites} peripheriques={peripheriques} actualiser={actualiser}
            modele={modele} pipeline={pipeline} cuda={cuda} equipe={equipe} occupe={occupe || demarrage}
            zoneFichier={<FilePicker choix={choix} choisir={setChoix} extensions={capacites?.file_extensions ?? []}
              disponible={capacites?.files ?? true} occupe={occupe || demarrage} />} />
        </aside>

        <div className="flex min-w-0 flex-col gap-5">
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="nn-btn nn-btn-primary" onClick={demarrer} disabled={!peutDemarrer}>
              {envoi !== null ? `Envoi… ${Math.round(envoi * 100)} %`
                : demarrage ? (r.engine === "local" ? "Chargement du modèle…" : "Démarrage…")
                : modeFichier ? "▶ Transcrire le fichier" : "▶ Démarrer"}
            </button>
            <button type="button" className="nn-btn nn-btn-secondary" disabled={!enCours}
              onClick={commande(state?.paused ? "/api/session/resume" : "/api/session/pause")}>
              {state?.paused ? "▶ Reprendre" : "⏸ Pause"}
            </button>
            <button type="button" className="nn-btn nn-btn-secondary" disabled={!enCours} onClick={commande("/api/session/stop")}>■ Arrêter</button>
            {state && (
              <span className={`nn-chip ${state.status === "ERROR" ? "nn-chip-danger" : state.status === "PAUSED" ? "nn-chip-warning" : state.finalized ? "nn-chip-success" : ""}`}
                role="status">{LIBELLES_STATUT[state.status] ?? state.status}</span>
            )}
          </div>

          {!peutDemarrer && !occupe && !demarrage && (
            <p className="m-0 text-[13px] text-ink-muted">
              {diarisationEnCours ? "Une diarisation est encore en cours : attendez sa fin pour démarrer une nouvelle session."
                : r.engine === "local" && !moteurPret ? (equipe === null && !r.model_path.trim()
                  ? "Aucun modèle de transcription sur ce poste : voir le cadre « Transcription » à gauche."
                  : "Le dossier de modèle indiqué n'est pas valide.")
                : modeFichier ? (capacites?.files === false ? "La lecture des fichiers n'est pas disponible ici." : "Choisissez un fichier audio ou vidéo.")
                : avecMicro && !micChoisi ? "Aucun microphone disponible."
                : avecSysteme && !capacites?.system_audio ? "La capture du son du PC n'est pas disponible ici." : ""}
            </p>
          )}

          {erreur && <Alerte>{erreur}</Alerte>}
          {state?.error && <Alerte>{state.error}</Alerte>}

          {!state ? (
            <p className="m-0 rounded-lg border border-dashed border-line-dashed px-6 py-10 text-center text-sm text-ink-muted">
              {modeFichier ? "Choisissez un fichier, puis cliquez sur « Transcrire le fichier »." : "Choisissez une source et un moteur, puis cliquez sur « Démarrer »."}
            </p>
          ) : (
            <>
              {state.kind === "file" && state.file ? (
                <AvancementFichierVue etat={state} avancement={state.file} />
              ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-live="off">
                <Chiffre label="Durée enregistrée" valeur={hms(state.duration)} />
                <Chiffre label="Blocs traités" valeur={state.stats.chunks} />
                <Chiffre label="Temps réel" valeur={state.stats.chunks ? `${state.stats.realtime_ratio.toFixed(2)}×` : "—"} />
                <Chiffre label="File d'attente" valeur={state.queue} />
              </div>
              )}

              {!echecSansTexte && (
              <section aria-labelledby="direct" className="flex flex-col gap-3">
                <div className="flex items-center justify-between gap-3">
                  <h2 id="direct" className="m-0 text-[19px] font-bold text-ink">{state.finalized || state.kind === "file" ? "Transcription" : "Transcription en direct"}</h2>
                  <label className="nn-check text-sm"><input type="checkbox" checked={horodatage} onChange={(e) => setHorodatage(e.target.checked)} /> <span>Horodatages</span></label>
                </div>
                {state.paused && <Alerte type="info">{state.kind === "file"
                  ? "⏸ En pause : « Reprendre » continue la transcription là où elle s'est arrêtée."
                  : "⏸ En pause : l'audio est ignoré. « Reprendre » continue le même enregistrement."}</Alerte>}
                {state.stopping && !state.finalized && <Alerte type="warning">{state.kind === "file"
                  ? "Arrêt demandé : le texte déjà transcrit est conservé."
                  : "Capture arrêtée. Transcription des derniers blocs en cours…"}</Alerte>}
                <Direct segments={segments} horodatage={horodatage} termine={state.finalized} />
              </section>
              )}

              {echecSansTexte && (
                <div><button type="button" className="nn-btn nn-btn-secondary" onClick={nouvelle}>Nouvelle session</button></div>
              )}

              {state.finalized && !echecSansTexte && (
                <>
                  <Section titre="Exports">
                    {state.status !== "ERROR" && <Alerte type="success">{state.kind === "file" && state.stopping
                      ? "Transcription arrêtée : le texte obtenu jusque-là est exporté."
                      : "Session terminée : la transcription brute est disponible immédiatement, sans attendre la diarisation."}</Alerte>}
                    <div className="flex flex-wrap gap-2">
                      {fichiers.wav && state.kind !== "file" && <a className="nn-btn nn-btn-secondary" href="/api/session/file/wav?download=true" download>⬇ Audio WAV</a>}
                      {fichiers.raw_txt && <a className="nn-btn nn-btn-secondary" href="/api/session/file/raw_txt?download=true" download>⬇ TXT brut</a>}
                      {fichiers.raw_srt && <a className="nn-btn nn-btn-secondary" href="/api/session/file/raw_srt?download=true" download>⬇ SRT brut</a>}
                    </div>
                    <p className="m-0 text-[13px] text-ink-muted">
                      Fichiers conservés dans <span className="font-mono">{state.session_dir}</span>
                      {!state.save_audio && " · l'enregistrement WAV n'est pas conservé (réglage « Conserver l'enregistrement »)."}
                    </p>
                  </Section>

                  {fichiers.wav && (
                    <Section titre="Audio et transcription synchronisés">
                      <SyncPlayer key={state.id} avecLocuteurs={state.diarization.status === "DONE"} />
                    </Section>
                  )}

                  <Section titre="Locuteurs">
                    <DiarizationPanel etat={state} cheminPipeline={r.diarization_model_path} locuteurs={r.speaker_hint} disponible={diarisationDispo}
                      relancer={(corps) => action("/api/session/diarization", corps)} />
                  </Section>

                  <div>
                    <button type="button" className="nn-btn nn-btn-secondary" onClick={nouvelle} disabled={diarisationEnCours}>Nouvelle session</button>
                  </div>
                </>
              )}

              <Diagnostic etat={state} />
            </>
          )}

          <Reprise cheminPipeline={r.diarization_model_path} locuteurs={r.speaker_hint} disponible={diarisationDispo} />
        </div>
      </div>
    </>
  );
};
