import React from "react";
import { api, envoyerFichier, messageErreur } from "./api";
import { DiarizationPanel } from "./components/DiarizationPanel";
import { type ChoixFichier, FilePicker } from "./components/FilePicker";
import { avecApplication, ecouteDe } from "./components/ChoixSource";
import { SettingsPanel } from "./components/SettingsPanel";
import { Resultat } from "./components/Resultat";
import { Alerte, Progression, Section } from "./components/ui";
import { LIBELLES_STATUT, duree, hms } from "./format";
import type { Applications, AvancementFichier, Capabilities, Cuda, Devices, Mode, ModeleEquipe, Niveau, Segment, Settings, SessionState, Verification } from "./types";
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

const Direct: React.FC<{ segments: Segment[]; horodatage: boolean }> = ({ segments, horodatage }) => {
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
        <p className="m-0 mb-2 text-[13px] text-ink-muted">Seules les {LIGNES_AFFICHEES} dernières phrases sont affichées pendant l'enregistrement ; tout le texte sera là à la fin.</p>
      )}
      <div ref={zone} tabIndex={0} aria-label="Transcription en direct"
        onScroll={(e) => { const z = e.currentTarget; colle.current = z.scrollTop + z.clientHeight >= z.scrollHeight - 40; }}
        className="nn-card max-h-[460px] min-h-[200px] overflow-auto p-4 text-[15px] leading-relaxed text-ink">
        {visibles.length === 0 ? (
          <span className="text-ink-muted">Le texte apparaît ici quelques secondes après qu'on a parlé…</span>
        ) : visibles.map((s, i) => (
          <p key={segments.length - visibles.length + i} className="m-0 mb-1.5 grid grid-cols-[auto_1fr] gap-3">
            {horodatage ? <span className="select-none pt-0.5 font-mono text-xs text-ink-subtle">{hms(s.start)}</span> : <span />}
            <span>{s.speaker && <strong className="font-semibold">{s.speaker} : </strong>}{s.text}</span>
          </p>
        ))}
      </div>
    </div>
  );
};

/** Annonce aux lecteurs d'écran la fin de la transcription et de l'identification des intervenants. */
function useAnnonce(state: SessionState | null): string {
  const [annonce, setAnnonce] = React.useState("");
  const avant = React.useRef<{ id: string; fini: boolean; diar: string } | null>(null);
  React.useEffect(() => {
    const p = avant.current;
    if (state && p && p.id === state.id) {
      if (!p.fini && state.finalized) {
        setAnnonce(state.status === "ERROR" ? "La transcription s'est arrêtée sur une erreur." : "Transcription terminée : le texte est prêt.");
      } else if (p.diar === "RUNNING" && state.diarization.status === "DONE") {
        setAnnonce("Intervenants identifiés.");
      } else if (p.diar === "RUNNING" && state.diarization.status === "ERROR") {
        setAnnonce("L'identification des intervenants a échoué ; le texte reste intact.");
      }
    }
    avant.current = state ? { id: state.id, fini: state.finalized, diar: state.diarization.status } : null;
  }, [state]);
  return annonce;
}

/** Applications qui utilisent le son, rafraîchies toutes les 2 s tant que le choix de la source est ouvert. */
function useApplications(actif: boolean): Applications | null {
  const [apps, setApps] = React.useState<Applications | null>(null);
  React.useEffect(() => {
    if (!actif) return;
    let arrete = false;
    const boucle = async () => {
      while (!arrete) {
        try { const a = await api<Applications>("/api/audio-apps"); if (!arrete) setApps(a); } catch { /* on réessaie */ }
        await new Promise((r) => setTimeout(r, 2000));
      }
    };
    boucle();
    return () => { arrete = true; };
  }, [actif]);
  return apps;
}

/** Niveau du son reçu, plusieurs fois par seconde, et alerte si plus rien n'arrive. */
function useNiveau(actif: boolean): Niveau {
  const [niveau, setNiveau] = React.useState<Niveau>({ level: null, silence: 0 });
  React.useEffect(() => {
    if (!actif) { setNiveau({ level: null, silence: 0 }); return; }
    let arrete = false;
    const boucle = async () => {
      while (!arrete) {
        try { setNiveau(await api<Niveau>("/api/session/level")); } catch { /* serveur occupé : on réessaie */ }
        await new Promise((r) => setTimeout(r, 150));
      }
    };
    boucle();
    return () => { arrete = true; };
  }, [actif]);
  return niveau;
}

const VuMetre: React.FC<{ niveau: number }> = ({ niveau }) => {
  const pct = Math.round(niveau * 100);
  return (
    <div className="flex items-center gap-2" title="Niveau du son reçu">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="shrink-0 text-ink-muted" aria-hidden="true">
        <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
      </svg>
      <div role="meter" aria-label="Niveau du son reçu" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
        className="h-2 w-28 overflow-hidden rounded-full bg-surface-3">
        <div className={`h-full rounded-full transition-[width] duration-100 ${niveau > 0.92 ? "bg-warning" : "bg-success"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
};

const AvancementFichierVue: React.FC<{ etat: SessionState; avancement: AvancementFichier }> = ({ etat, avancement: a }) => {
  const pct = a.fraction === null ? null : Math.round(a.fraction * 100);
  const etape = a.phase === "decoding" ? "Lecture du fichier" : a.phase === "transcribing" ? "Transcription" : "Terminé";
  const details = [
    pct !== null && a.phase !== "done" ? `${pct} %` : "",
    etat.paused ? "en pause" : a.eta !== null ? `reste environ ${duree(a.eta)}` : "",
  ].filter(Boolean).join(" · ");
  return (
    <div className="flex min-w-0 flex-col gap-2">
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
    ["Blocs traités", String(etat.stats.chunks)],
    ["File d'attente", String(etat.queue)],
    ["Dernière latence", `${etat.stats.last_latency.toFixed(2)} s pour ${etat.stats.last_chunk_duration.toFixed(2)} s d'audio`],
    ["Ratio temps réel moyen", `${etat.stats.average_realtime_ratio.toFixed(2)}× (moins de 1× : la transcription suit ; plus : elle prend du retard)`],
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

const MODES: { id: Mode; titre: string; detail: string; icone: React.ReactNode }[] = [
  {
    id: "live", titre: "En direct", detail: "Micro ou son du PC, pendant une réunion",
    icone: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>,
  },
  {
    id: "file", titre: "Depuis un fichier", detail: "Un enregistrement audio ou une vidéo",
    icone: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M10 17v-5l4 2.5z" /></svg>,
  },
];

/** Premier choix de la page : grand sélecteur à deux options (groupe de boutons radio, flèches gauche / droite). */
const ChoixMode: React.FC<{ mode: Mode; changer: (m: Mode) => void; bloque: boolean }> = ({ mode, changer, bloque }) => {
  const boutons = React.useRef<(HTMLButtonElement | null)[]>([]);
  const clavier = (e: React.KeyboardEvent, i: number) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key) || bloque) return;
    e.preventDefault();
    const j = (i + (e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1) + MODES.length) % MODES.length;
    changer(MODES[j].id);
    boutons.current[j]?.focus();
  };
  return (
    <div role="radiogroup" aria-label="Que voulez-vous transcrire ?"
      title={bloque ? "Terminez la session en cours pour changer" : undefined}
      className="mt-5 grid w-full max-w-[760px] grid-cols-2 gap-1.5 rounded-lg border border-line bg-surface-2 p-1.5">
      {MODES.map((m, i) => {
        const actif = mode === m.id;
        return (
          <button key={m.id} ref={(el) => { boutons.current[i] = el; }} type="button" role="radio" aria-checked={actif}
            tabIndex={actif ? 0 : -1} disabled={bloque && !actif} onClick={() => !bloque && changer(m.id)} onKeyDown={(e) => clavier(e, i)}
            className={`flex min-w-0 items-center gap-3 rounded-md border px-3 py-3 text-left transition-colors sm:px-4
              focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus
              ${actif ? "border-accent bg-surface text-ink shadow-sm" : "border-transparent bg-transparent text-ink-muted hover:bg-surface-3"}
              disabled:cursor-not-allowed disabled:opacity-50`}>
            <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${actif ? "bg-accent-soft text-accent" : "bg-surface-3 text-ink-subtle"}`}>
              {m.icone}
            </span>
            <span className="flex min-w-0 flex-col">
              <span className={`text-[16px] font-semibold leading-tight ${actif ? "text-ink" : "text-ink-body"}`}>{m.titre}</span>
              <span className="mt-0.5 hidden text-[13px] leading-snug text-ink-muted sm:block">{m.detail}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
};

const SVG = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "currentColor", "aria-hidden": true } as const;
const IconeLecture = () => <svg {...SVG}><path d="M7 4.5v15l12.5-7.5z" /></svg>;
const IconePause = () => <svg {...SVG}><rect x="6" y="4.5" width="4" height="15" rx="1" /><rect x="14" y="4.5" width="4" height="15" rx="1" /></svg>;
const IconeArret = () => <svg {...SVG}><rect x="5.5" y="5.5" width="13" height="13" rx="2" /></svg>;

export const Transcription: React.FC = () => {
  const { reglages, regler } = useReglages();
  const { state, segments, action, oublier, rafraichir } = useSession();
  const [capacites, setCapacites] = React.useState<Capabilities | null>(null);
  const [peripheriques, setPeripheriques] = React.useState<Devices | null>(null);
  const [cuda, setCuda] = React.useState<Cuda | null>(null);
  const [equipe, setEquipe] = React.useState<ModeleEquipe | null | undefined>(undefined);
  const [erreur, setErreur] = React.useState("");
  const [demarrage, setDemarrage] = React.useState(false);
  const [horodatage, setHorodatage] = React.useState(true);
  const [choix, setChoix] = React.useState<ChoixFichier>(null);
  const [envoi, setEnvoi] = React.useState<number | null>(null); // avancement de l'envoi du fichier
  const envoiEnCours = React.useRef<AbortController | null>(null);

  const actualiser = React.useCallback(() => { api<Devices>("/api/devices").then(setPeripheriques).catch(() => undefined); }, []);
  React.useEffect(() => {
    api<Capabilities>("/api/capabilities").then(setCapacites).catch(() => undefined);
    api<Cuda>("/api/cuda").then(setCuda).catch(() => undefined);
    api<{ team: ModeleEquipe | null }>("/api/model").then((m) => setEquipe(m.team)).catch(() => setEquipe(null));
    actualiser();
  }, [actualiser]);

  const modele = useVerification("/api/model/check", reglages?.model_path ?? "");
  const pipeline = useVerification("/api/diarization/check", reglages?.diarization_model_path ?? "");

  const occupe = !!state && !state.finalized;
  const enCours = occupe && !state!.stopping;
  const ecoute = enCours && state!.kind === "live" && !state!.paused;
  const niveau = useNiveau(ecoute);
  const applications = useApplications(!!reglages && reglages.mode === "live" && !occupe && (capacites?.system_audio ?? false));
  const annonce = useAnnonce(state);

  // Raccourcis pendant une session : Espace = pause / reprise, Échap = arrêter (hors champs de saisie)
  const raccourcis = React.useRef<(e: KeyboardEvent) => void>(() => undefined);
  React.useEffect(() => {
    const ecouter = (e: KeyboardEvent) => raccourcis.current(e);
    window.addEventListener("keydown", ecouter);
    return () => window.removeEventListener("keydown", ecouter);
  }, []);

  if (!reglages) return <p className="m-0 text-sm text-ink-muted">Chargement…</p>;

  const r = reglages;
  const entrees = peripheriques?.inputs ?? [];
  const sorties = peripheriques?.outputs ?? [];
  const micChoisi = entrees.find((d) => d.name === r.input_device) ?? entrees[0];
  const avecMicro = r.source !== "system";
  const avecSysteme = r.source !== "microphone";
  const avecApp = avecApplication(ecouteDe(r));
  const appOuverte = !avecApp || (applications?.apps.some((a) => a.exe === r.app) ?? false);
  const diarisationEnCours = state?.diarization.status === "RUNNING";
  const diarisationDispo = capacites?.diarization ?? false;

  const modeFichier = r.mode === "file";
  const modeleEquipe = !!equipe && !r.use_own_model;
  const moteurPret = r.engine === "mock" || ((modeleEquipe || modele?.valid === true) && capacites?.stt !== false);
  const sourcePrete = modeFichier
    ? !!choix && (capacites?.files ?? false)
    : (!avecMicro || !!micChoisi) && (!avecSysteme || !!capacites?.system_audio) && appOuverte;
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
      const annulation = envoiEnCours.current = new AbortController();
      try { upload_id = await envoyerFichier(choix.fichier, setEnvoi, annulation.signal); } finally { setEnvoi(null); envoiEnCours.current = null; }
    }
    await action("/api/session/start-file", { ...options(), upload_id, path: choix.type === "chemin" ? choix.chemin : "" });
  };

  const demarrer = async () => {
    setErreur("");
    setDemarrage(true);
    try {
      if (modeFichier) { await transcrireFichier(); return; }
      await action("/api/session/start", {
        ...options(), source: r.source, input_device: avecMicro ? micChoisi?.index ?? null : null,
        output_device: r.output_device || sorties[0]?.name || "", app: avecApp ? r.app : "", chunk_seconds: r.chunk_seconds,
        overlap_seconds: Math.min(r.overlap_seconds, r.chunk_seconds - 0.5),
      });
    } catch (e) { if (!(e instanceof Error && e.message === "Envoi annulé.")) setErreur(messageErreur(e)); } finally { setDemarrage(false); }
  };
  const commande = (chemin: string) => async () => {
    setErreur("");
    try { await action(chemin); } catch (e) { setErreur(messageErreur(e)); }
  };
  const pauseOuReprise = commande(state?.paused ? "/api/session/resume" : "/api/session/pause");
  const arreter = commande("/api/session/stop");
  raccourcis.current = (e: KeyboardEvent) => {
    const cible = e.target as HTMLElement | null;
    if (!enCours || e.ctrlKey || e.metaKey || e.altKey || (cible && /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(cible.tagName))) return;
    if (e.key === " ") { e.preventDefault(); pauseOuReprise(); }
    if (e.key === "Escape") { e.preventDefault(); arreter(); }
  };
  const nouvelle = async () => {
    setErreur("");
    try { await oublier(); } catch (e) { setErreur(messageErreur(e)); }
  };
  const ouvrirDossier = () => api("/api/session/open-folder", { method: "POST" }).catch((e) => setErreur(messageErreur(e)));

  // Rien à exporter ni à écouter : fichier illisible, micro en panne dès le départ…
  const echecSansTexte = !!state && state.finalized && state.status === "ERROR" && state.total === 0;
  const fichiers = (state?.files ?? {}) as { wav?: boolean; raw_txt?: boolean };
  const enRetard = !!state && state.kind === "live" && enCours && (state.queue >= 3 || state.stats.average_realtime_ratio > 1.15);
  const statut = state && (state.finalized ? (state.status === "ERROR" ? "ERROR" : "STOPPED") : state.status);

  const pourquoiPas = !peutDemarrer && !occupe && !demarrage
    ? (diarisationEnCours ? "Attendez la fin de l'identification des intervenants."
      : r.engine === "local" && !moteurPret ? "Aucun modèle de transcription : voir « Transcription » dans les réglages."
      : modeFichier ? (capacites?.files === false ? "La lecture des fichiers n'est pas disponible ici." : "Choisissez d'abord un fichier.")
      : avecMicro && !micChoisi ? "Aucun microphone disponible."
      : avecSysteme && !capacites?.system_audio ? "Le son du PC n'est pas disponible ici."
      : !appOuverte ? (r.app ? `${r.app_name || "L'application choisie"} n'est pas ouvert : lancez-le, ou choisissez une autre source.` : "Choisissez l'application à écouter.")
      : "")
    : "";

  const barre = (
    <div id="commandes" tabIndex={-1} aria-label="Commandes" role="region"
      className="fixed inset-x-0 bottom-0 z-20 flex flex-col gap-2 outline-none focus-visible:ring-2 focus-visible:ring-focus border-t border-line bg-surface px-4 py-3 shadow-[0_-4px_16px_rgba(0,0,0,0.08)]
      lg:sticky lg:inset-x-auto lg:bottom-auto lg:top-[76px] lg:rounded-lg lg:border lg:px-4 lg:shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        {(!state || state.finalized) ? (
          <button type="button" className="nn-btn nn-btn-primary gap-2" onClick={demarrer} disabled={!peutDemarrer}>
            <IconeLecture />
            {envoi !== null ? `Envoi… ${Math.round(envoi * 100)} %`
              : demarrage ? (r.engine === "local" ? "Chargement du modèle…" : "Démarrage…")
              : modeFichier ? "Transcrire le fichier" : state ? "Nouvel enregistrement" : "Démarrer"}
          </button>
        ) : (
          <>
            <button type="button" className="nn-btn nn-btn-secondary gap-2" disabled={!enCours} onClick={pauseOuReprise} title="Raccourci : Espace">
              {state.paused ? <><IconeLecture /> Reprendre</> : <><IconePause /> Pause</>}
            </button>
            <button type="button" className="nn-btn nn-btn-primary gap-2" disabled={!enCours} onClick={arreter} title="Raccourci : Échap">
              <IconeArret /> Arrêter
            </button>
          </>
        )}
        {envoi !== null && (
          <button type="button" className="nn-btn nn-btn-secondary" onClick={() => envoiEnCours.current?.abort()}>Annuler l'envoi</button>
        )}
        {state && statut && (
          <span className={`nn-chip ${statut === "ERROR" ? "nn-chip-danger" : statut === "PAUSED" ? "nn-chip-warning" : statut === "STOPPED" ? "nn-chip-success" : ""}`}
            role="status">{LIBELLES_STATUT[statut] ?? statut}</span>
        )}
        {state && state.kind === "live" && <span className="font-mono text-sm tabular-nums text-ink" aria-label="Durée enregistrée">{hms(state.duration)}</span>}
        {ecoute && niveau.level !== null && <VuMetre niveau={niveau.level} />}
        {enRetard && <span className="nn-chip nn-chip-warning" title="Le texte arrivera après la fin de l'enregistrement : rien n'est perdu.">La transcription prend du retard</span>}
      </div>
      {state && state.kind === "file" && state.file && !state.finalized && <AvancementFichierVue etat={state} avancement={state.file} />}
      {pourquoiPas && <p className="m-0 text-[13px] text-ink-muted">{pourquoiPas}</p>}
    </div>
  );

  return (
    <div className="pb-28 lg:pb-0">
      <a href="#commandes" onClick={(e) => { e.preventDefault(); document.getElementById("commandes")?.focus(); }}
        className="sr-only focus:not-sr-only focus:absolute focus:left-6 focus:top-20 focus:z-30 focus:rounded focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:text-accent focus:shadow">
        Aller aux commandes (Démarrer, Pause, Arrêter)
      </a>
      <p className="sr-only" aria-live="polite">{annonce}</p>
      <div className="nn-page-head">
        <div>
          <h1 className="nn-page-title">Transcription</h1>
          <p className="nn-page-subtitle">Tout reste sur cet ordinateur : aucun son ne quitte le poste.</p>
        </div>
      </div>
      <ChoixMode mode={r.mode} changer={changerMode} bloque={occupe || demarrage} />

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        <aside aria-label="Réglages" className="order-2 lg:sticky lg:top-[76px] lg:order-none lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto lg:pr-1"
          tabIndex={occupe ? 0 : undefined}>
          <SettingsPanel reglages={r} regler={regler} capacites={capacites} peripheriques={peripheriques} applications={applications} actualiser={actualiser}
            modele={modele} pipeline={pipeline} cuda={cuda} equipe={equipe} occupe={occupe || demarrage}
            zoneFichier={<FilePicker choix={choix} choisir={setChoix} extensions={capacites?.file_extensions ?? []}
              disponible={capacites?.files ?? true} occupe={occupe || demarrage} />} />
        </aside>

        <div className="order-1 flex min-w-0 flex-col gap-5 lg:order-none">
          {barre}
          {erreur && <Alerte>{erreur}</Alerte>}
          {state?.error && <Alerte>{state.error}</Alerte>}
          {ecoute && niveau.silence >= 10 && (
            <Alerte type="warning">
              Aucun son reçu depuis {Math.round(niveau.silence)} s. {avecApp
                ? <>Vérifiez que {r.app_name || "l'application"} fait bien du son (réunion lancée, son non coupé)
                  {r.source === "mixed" ? " et que le bon microphone est choisi" : ""}.</>
                : <>Vérifiez que le bon {r.source === "system" ? "haut-parleur" : "microphone"} est choisi dans les réglages et qu'il n'est pas coupé.</>}
            </Alerte>
          )}

          {!state ? (
            <p className="m-0 rounded-lg border border-dashed border-line-dashed px-6 py-10 text-center text-sm text-ink-muted">
              {modeFichier ? "Choisissez un fichier, puis cliquez sur « Transcrire le fichier »." : "Vérifiez la source audio, puis cliquez sur « Démarrer »."}
            </p>
          ) : !state.finalized ? (
            <section aria-labelledby="direct" className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3">
                <h2 id="direct" className="m-0 text-[19px] font-bold text-ink">{state.kind === "file" ? "Transcription" : "En direct"}</h2>
                <label className="nn-check text-sm"><input type="checkbox" checked={horodatage} onChange={(e) => setHorodatage(e.target.checked)} /> <span>Horaires</span></label>
              </div>
              {state.paused && <Alerte type="info">{state.kind === "file"
                ? "En pause : « Reprendre » continue la transcription là où elle s'est arrêtée."
                : "En pause : rien n'est enregistré. « Reprendre » continue le même enregistrement."}</Alerte>}
              {state.stopping && <Alerte type="info">{state.kind === "file"
                ? "Arrêt demandé : le texte déjà transcrit est conservé."
                : "Enregistrement arrêté. Transcription des dernières secondes…"}</Alerte>}
              <Direct segments={segments} horodatage={horodatage} />
            </section>
          ) : echecSansTexte ? (
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className="nn-btn nn-btn-secondary" onClick={nouvelle}>Nouvelle session</button>
            </div>
          ) : (
            <>
              <Section titre={state.archived ? `Session du ${state.id.slice(8, 10)}/${state.id.slice(5, 7)}/${state.id.slice(0, 4)} à ${state.id.slice(11, 16).replace("-", ":")}` : "Résultat"}>
                {!state.archived && state.status !== "ERROR" && (
                  <Alerte type="success">{state.kind === "file" && state.stopping
                    ? "Transcription arrêtée : le texte obtenu jusque-là est enregistré."
                    : "Terminé : le texte est prêt et enregistré, sans attendre l'identification des intervenants."}</Alerte>
                )}
                <Resultat key={state.id} sessionId={state.id} avecIntervenants={state.diarization.status === "DONE"} intervenants={state.speakers}
                  audio={!!fichiers.wav} apresNoms={() => { rafraichir().catch(() => undefined); }} />
              </Section>

              <Section titre="Intervenants">
                <DiarizationPanel etat={state} cheminPipeline={r.diarization_model_path} locuteurs={r.speaker_hint} disponible={diarisationDispo}
                  relancer={(corps) => action("/api/session/diarization", corps)} />
              </Section>

              <div className="flex flex-wrap items-center gap-3">
                <button type="button" className="nn-btn nn-btn-secondary" onClick={nouvelle} disabled={diarisationEnCours}>Nouvelle session</button>
                <button type="button" className="nn-btn nn-btn-secondary" onClick={ouvrirDossier}>Ouvrir le dossier</button>
                {fichiers.wav && state.kind !== "file" && <a className="nn-btn nn-btn-secondary" href="/api/session/file/wav?download=true" download>Audio (.wav)</a>}
                <span className="text-[13px] text-ink-muted">Cette session reste disponible dans l'<a href="#/historique" className="text-accent underline">historique</a>.</span>
              </div>
            </>
          )}

          {state && !state.archived && <Diagnostic etat={state} />}
        </div>
      </div>
    </div>
  );
};
