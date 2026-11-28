import React from "react";
import { api, envoyerFichier, messageErreur } from "./api";
import { avecApplication, ecouteEffective, versSource } from "./components/ChoixSource";
import { EnDirect } from "./components/EnDirect";
import { type ChoixFichier, FilePicker } from "./components/FilePicker";
import { type Apercu, Pret, ReglagesAvances, useBlocModele } from "./components/Pret";
import { VueResultat } from "./components/VueResultat";
import { Alerte } from "./components/ui";
import type { Applications, Capabilities, Cuda, Devices, Mode, ModeleEquipe, Niveau, Settings, SessionState, Verification } from "./types";
import { useSession } from "./useSession";

/** Réglages mémorisés côté serveur : chaque changement est enregistré après une courte pause de frappe. */
export function useReglages() {
  const [reglages, setReglages] = React.useState<Settings | null>(null);
  const attente = React.useRef<Record<string, unknown>>({});
  const minuteur = React.useRef<number | undefined>(undefined);

  React.useEffect(() => {
    api<Settings>("/api/settings").then((s) => {
      // L'app s'ouvre toujours sur « En direct » : « Depuis un fichier » est un choix du moment, pas un réglage.
      setReglages({ ...s, mode: "live" });
      if (s.mode !== "live") api("/api/settings", { method: "PUT", json: { mode: "live" } }).catch(() => undefined);
    }).catch(() => undefined);
  }, []);

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
      } else if (p.diar === "RUNNING" && state.diarization.status === "CANCELLED") {
        setAnnonce("Identification des intervenants arrêtée ; le texte reste intact.");
      } else if (p.diar === "RUNNING" && state.diarization.status === "ERROR") {
        setAnnonce("L'identification des intervenants a échoué ; le texte reste intact.");
      }
    }
    avant.current = state ? { id: state.id, fini: state.finalized, diar: state.diarization.status } : null;
  }, [state]);
  return annonce;
}

/** Interroge une adresse à intervalle régulier tant que `actif` (vu-mètre, liste des applications…). */
function useSondage<T>(actif: boolean, url: string, delai: number): T | null {
  const [valeur, setValeur] = React.useState<T | null>(null);
  React.useEffect(() => {
    if (!actif) { setValeur(null); return; }
    let arrete = false;
    const boucle = async () => {
      while (!arrete) {
        try { const v = await api<T>(url); if (!arrete) setValeur(v); } catch { /* serveur occupé : on réessaie */ }
        await new Promise((r) => setTimeout(r, delai));
      }
    };
    boucle();
    return () => { arrete = true; };
  }, [actif, url, delai]);
  return valeur;
}

/** Applications qui utilisent le son : gardées entre deux sondages (la liste ne clignote pas). */
function useApplications(actif: boolean): Applications | null {
  const valeur = useSondage<Applications>(actif, "/api/audio-apps", 2000);
  const dernier = React.useRef<Applications | null>(null);
  if (valeur) dernier.current = valeur;
  return valeur ?? dernier.current;
}

/**
 * Test de la source avant de démarrer : le serveur ouvre micro et / ou application sans rien enregistrer.
 * Fermé dès que la page n'est plus au premier plan, au démarrage, ou si les réglages changent.
 */
function useApercu(actif: boolean, corps: Record<string, unknown>): Apercu | null {
  const [etat, setEtat] = React.useState<Apercu | null>(null);
  const [visible, setVisible] = React.useState(() => document.visibilityState === "visible");
  React.useEffect(() => {
    const suivre = () => setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", suivre);
    return () => document.removeEventListener("visibilitychange", suivre);
  }, []);
  const cle = JSON.stringify(corps);
  React.useEffect(() => {
    if (!actif || !visible) { setEtat(null); return; }
    let arrete = false;
    const t = setTimeout(async () => {
      try { await api("/api/preview", { method: "POST", json: JSON.parse(cle) }); }
      catch (e) { if (!arrete) setEtat({ active: false, erreur: messageErreur(e) }); return; }
      while (!arrete) {
        try { const e = await api<Apercu>("/api/preview"); if (!arrete) setEtat(e); } catch { /* on réessaie */ }
        await new Promise((r) => setTimeout(r, 200));
      }
    }, 350);
    return () => { arrete = true; clearTimeout(t); };
  }, [actif, visible, cle]);
  React.useEffect(() => {
    if (!actif || !visible) api("/api/preview", { method: "DELETE" }).catch(() => undefined);
  }, [actif, visible]);
  React.useEffect(() => () => { api("/api/preview", { method: "DELETE" }).catch(() => undefined); }, []);
  return etat;
}

interface EtatModele { state: "idle" | "loading" | "ready" | "error"; message: string; device: string }

/** Charge le modèle en arrière-plan dès que la page est prête : « Démarrer » part ensuite tout de suite. */
function usePrechargement(actif: boolean, corps: { model_path: string; acceleration: string }): EtatModele | null {
  const [etat, setEtat] = React.useState<EtatModele | null>(null);
  const cle = JSON.stringify(corps);
  React.useEffect(() => {
    if (!actif) return;
    let arrete = false;
    const t = setTimeout(async () => {
      try { setEtat(await api<EtatModele>("/api/model/preload", { method: "POST", json: JSON.parse(cle) })); }
      catch (e) { if (!arrete) setEtat({ state: "error", message: messageErreur(e), device: "" }); return; }
      while (!arrete) {
        await new Promise((r) => setTimeout(r, 700));
        try {
          const e = await api<EtatModele>("/api/model/preload");
          if (!arrete) setEtat(e);
          if (e.state !== "loading") return;
        } catch { /* on réessaie */ }
      }
    }, 600);
    return () => { arrete = true; clearTimeout(t); };
  }, [actif, cle]);
  return actif ? etat : null;
}

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
    <div role="radiogroup" aria-label="Que voulez-vous transcrire ?" title={bloque ? "Terminez la session en cours pour changer" : undefined}
      className="grid w-full max-w-[760px] grid-cols-2 gap-1.5 rounded-lg border border-line bg-surface-2 p-1.5">
      {MODES.map((m, i) => {
        const actif = mode === m.id;
        return (
          <button key={m.id} ref={(el) => { boutons.current[i] = el; }} type="button" role="radio" aria-checked={actif}
            tabIndex={actif ? 0 : -1} disabled={bloque && !actif} onClick={() => !bloque && changer(m.id)} onKeyDown={(e) => clavier(e, i)}
            className={`flex min-w-0 items-center gap-3 rounded-md border px-3 py-3 text-left transition-colors sm:px-4
              focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus
              ${actif ? "border-accent bg-surface text-ink shadow-sm" : "border-transparent bg-transparent text-ink-muted hover:bg-surface-3"}
              disabled:cursor-not-allowed disabled:opacity-50`}>
            <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${actif ? "bg-accent-soft text-accent" : "bg-surface-3 text-ink-subtle"}`}>{m.icone}</span>
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

const IconeMicro = ({ taille }: { taille: number }) => (
  <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);

export const Transcription: React.FC = () => {
  const { reglages, regler } = useReglages();
  const { state, segments, action, oublier, rafraichir } = useSession();
  const [capacites, setCapacites] = React.useState<Capabilities | null>(null);
  const [peripheriques, setPeripheriques] = React.useState<Devices | null>(null);
  const [cuda, setCuda] = React.useState<Cuda | null>(null);
  const [equipe, setEquipe] = React.useState<ModeleEquipe | null | undefined>(undefined);
  const [equipeIntervenants, setEquipeIntervenants] = React.useState<ModeleEquipe | null>(null);
  const [erreur, setErreur] = React.useState("");
  const [demarrage, setDemarrage] = React.useState(false);
  const [choix, setChoix] = React.useState<ChoixFichier>(null);
  const [envoi, setEnvoi] = React.useState<number | null>(null);
  const envoiEnCours = React.useRef<AbortController | null>(null);

  const actualiser = React.useCallback(() => { api<Devices>("/api/devices").then(setPeripheriques).catch(() => undefined); }, []);
  React.useEffect(() => {
    // Rechargé tant que pyannote / PyTorch finissent de se charger en arrière-plan, pour connaître une éventuelle erreur
    let minuterie = 0;
    const capacitesDe = () => api<Capabilities>("/api/capabilities").then((c) => {
      setCapacites(c);
      if (c.diarization && c.diarization_ready === false) minuterie = window.setTimeout(capacitesDe, 3000);
    }).catch(() => undefined);
    capacitesDe();
    api<Cuda>("/api/cuda").then(setCuda).catch(() => undefined);
    api<{ team: ModeleEquipe | null; team_diarization: ModeleEquipe | null }>("/api/model")
      .then((m) => { setEquipe(m.team); setEquipeIntervenants(m.team_diarization); }).catch(() => setEquipe(null));
    actualiser();
    return () => window.clearTimeout(minuterie);
  }, [actualiser]);

  const modele = useVerification("/api/model/check", reglages?.model_path ?? "");
  const pipeline = useVerification("/api/diarization/check", reglages?.diarization_model_path ?? "");

  const occupe = !!state && !state.finalized;
  // Une session rouverte depuis Mes transcriptions s'affiche là-bas : ici, on reste prêt pour une nouvelle.
  const accueil = !state || state.archived;
  const enCours = occupe && !state!.stopping;
  const sonRecu = enCours && state!.kind === "live" && !state!.paused;
  const niveau = useSondage<Niveau>(sonRecu, "/api/session/level", 150);
  const annonce = useAnnonce(state);
  const live = !!reglages && reglages.mode === "live";
  const applications = useApplications(accueil && live && (capacites?.system_audio ?? false));

  const r = reglages;
  const entrees = peripheriques?.inputs ?? [];
  const sorties = peripheriques?.outputs ?? [];
  const micChoisi = r ? entrees.find((d) => d.name === r.input_device) ?? entrees[0] : undefined;
  const systemeOk = capacites?.system_audio ?? false;
  const ecoute = r ? ecouteEffective(r, systemeOk, systemeOk && (applications?.supported ?? capacites?.app_audio ?? false)) : "voix";
  const avecMicro = ecoute === "voix" || ecoute === "voix_app" || ecoute === "voix_tout";
  const avecSysteme = ecoute !== "voix";
  const avecApp = avecApplication(ecoute);
  const app = r ? applications?.apps.find((a) => a.exe === r.app) : undefined;
  const appOuverte = !avecApp || !!app;
  const sourcePrete = (!avecMicro || !!micChoisi) && (!avecSysteme || !!capacites?.system_audio) && appOuverte;
  const corpsSource = {
    source: versSource(ecoute), input_device: avecMicro ? micChoisi?.index ?? null : null,
    output_device: r?.output_device || sorties[0]?.name || "", app: avecApp ? r?.app ?? "" : "",
  };
  // Une application à écouter et aucune choisie : celle de la visio en cours, sinon la première qui fait du son
  React.useEffect(() => {
    if (!r || !avecApp || r.app || !applications) return;
    const a = applications.apps.find((x) => x.exe === applications.recommended) ?? applications.apps.find((x) => x.active);
    if (a) { regler("app", a.exe); regler("app_name", a.name); }
  }, [applications, avecApp, r?.app]); // eslint-disable-line react-hooks/exhaustive-deps
  const [avances, setAvances] = React.useState(false);
  const apercu = useApercu(accueil && live && sourcePrete && !demarrage, corpsSource);

  // Raccourcis pendant une session : Espace = pause / reprise, Échap = arrêter, M = marquer (hors champs de saisie)
  const raccourcis = React.useRef<(e: KeyboardEvent) => void>(() => undefined);
  React.useEffect(() => {
    const ecouter = (e: KeyboardEvent) => raccourcis.current(e);
    window.addEventListener("keydown", ecouter);
    return () => window.removeEventListener("keydown", ecouter);
  }, []);

  const prechargement = usePrechargement(accueil && !!r && r.engine === "local" && capacites?.stt !== false
    && (!!equipe && !r.use_own_model || modele?.valid === true),
  { model_path: r && !(equipe && !r.use_own_model) ? r.model_path : "", acceleration: r?.acceleration ?? "auto" });
  const { modeleOk, bloc: blocModele } = useBlocModele(r ?? ({} as Settings), regler, capacites, equipe, modele, occupe || demarrage);
  if (!r) return <p className="m-0 text-sm text-ink-muted">Chargement…</p>;

  const diarisationDispo = capacites?.diarization ?? false;
  const modeFichier = r.mode === "file";
  const modeleEquipe = !!equipe && !r.use_own_model;
  const intervenantsEquipe = !!equipeIntervenants && !r.use_own_diarization_model;
  const moteurPret = r.engine === "mock" || (modeleOk && capacites?.stt !== false);
  const pret = modeFichier ? !!choix && (capacites?.files ?? false) : sourcePrete;
  const peutDemarrer = !occupe && !demarrage && pret && moteurPret; // une identification en cours continue à côté

  const options = () => ({
    engine: r.engine, model_path: modeleEquipe ? "" : r.model_path, acceleration: r.acceleration, language: r.language, glossary: r.glossary,
    vad_filter: r.vad_filter, save_audio: r.save_audio, diarization: r.diarization && diarisationDispo,
    diarization_model_path: intervenantsEquipe ? "" : r.diarization_model_path, speaker_hint: r.speaker_hint,
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
        ...options(), ...corpsSource, chunk_seconds: r.chunk_seconds, overlap_seconds: Math.min(r.overlap_seconds, r.chunk_seconds - 0.5),
      });
      window.scrollTo({ top: 0 });
    } catch (e) { if (!(e instanceof Error && e.message === "Envoi annulé.")) setErreur(messageErreur(e)); } finally { setDemarrage(false); }
  };
  const commande = (chemin: string) => async () => {
    setErreur("");
    try { await action(chemin); } catch (e) { setErreur(messageErreur(e)); }
  };
  const pauseOuReprise = commande(state?.paused ? "/api/session/resume" : "/api/session/pause");
  const arreter = commande("/api/session/stop");
  const marquer = async () => {
    try { await api("/api/session/marks", { method: "POST", json: {} }); await rafraichir(); } catch (e) { setErreur(messageErreur(e)); }
  };
  raccourcis.current = (e: KeyboardEvent) => {
    const cible = e.target as HTMLElement | null;
    if (!enCours || e.ctrlKey || e.metaKey || e.altKey || (cible && (/^(INPUT|TEXTAREA|SELECT)$/.test(cible.tagName) || cible.isContentEditable))) return;
    if (e.key === " " && cible?.tagName !== "BUTTON" && cible?.tagName !== "A") { e.preventDefault(); pauseOuReprise(); } // Espace active déjà un bouton
    if (e.key === "Escape") { e.preventDefault(); arreter(); }
    if ((e.key === "m" || e.key === "M") && state?.kind === "live" && !state.paused) { e.preventDefault(); marquer(); }
  };
  const nouvelle = async () => {
    setErreur("");
    try { await oublier(); window.scrollTo({ top: 0 }); } catch (e) { setErreur(messageErreur(e)); }
  };
  const ouvrirAvances = () => {
    setAvances(true);
    requestAnimationFrame(() => { const champ = document.getElementById("pipeline"); champ?.scrollIntoView({ block: "center" }); champ?.focus(); });
  };

  const echecSansTexte = !!state && state.finalized && state.status === "ERROR" && state.total === 0 && !state.archived;
  const enRetard = !!state && state.kind === "live" && enCours && (state.queue >= 3 || state.stats.average_realtime_ratio > 1.15);

  const nomApp = app?.name ?? (r.app_name || "l'application");
  const resume = ({
    voix: `Votre voix${micChoisi ? ` · ${micChoisi.name}` : ""}`,
    app: nomApp,
    tout: "Tout le son du PC",
    voix_app: `Votre voix + ${nomApp}`,
    voix_tout: "Votre voix + le son du PC",
  } as const)[ecoute];

  const pourquoiPas = !peutDemarrer && !occupe && !demarrage
    ? (r.engine === "local" && !moteurPret ? "Aucun modèle de transcription : voir « Modèle de transcription » ci-contre."
      : modeFichier ? (capacites?.files === false ? "La lecture des fichiers n'est pas disponible ici." : "Choisissez d'abord un fichier.")
      : avecMicro && !micChoisi ? "Aucun microphone disponible."
      : avecSysteme && !capacites?.system_audio ? "Le son du PC n'est pas disponible ici."
      : !appOuverte ? (r.app ? `${r.app_name || "L'application choisie"} n'est pas ouvert : lancez-le, ou choisissez « Ma voix ».`
        : "Aucune application ne fait de son pour l'instant : lancez la réunion, ou choisissez « Ma voix ».")
      : "")
    : "";

  const lienCommandes = (
    <a href="#commandes" onClick={(e) => { e.preventDefault(); document.getElementById("commandes")?.focus(); }}
      className="sr-only focus:not-sr-only focus:absolute focus:left-6 focus:top-20 focus:z-30 focus:rounded focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:text-accent focus:shadow">
      Aller aux commandes (Démarrer, Pause, Arrêter)
    </a>
  );
  const alertes = (
    <>
      {erreur && <Alerte>{erreur}</Alerte>}
      {state?.error && <Alerte type={state.archived ? "info" : "danger"}>{state.error}</Alerte>}
      {apercu?.erreur && accueil && <Alerte type="warning">{apercu.erreur}</Alerte>}
    </>
  );

  // --- Pendant l'enregistrement ou la transcription d'un fichier ---------------------------------------------
  if (state && !state.finalized) {
    return (
      <div className="-mt-8">
        {lienCommandes}
        <p className="sr-only" aria-live="polite">{annonce}</p>
        <EnDirect etat={state} segments={segments} niveau={niveau?.level ?? null}
          resume={state.kind === "live" ? `${resume} · ${({ fr: "Français", en: "Anglais", auto: "Langue détectée" } as const)[r.language]}` : ""}
          pauseOuReprise={pauseOuReprise} arreter={arreter} marquer={marquer} enRetard={enRetard} />
        <div className="mx-auto mt-4 flex max-w-[1180px] flex-col gap-3">
          {alertes}
          {sonRecu && niveau && niveau.silence >= 10 && (
            <Alerte type="warning">
              Aucun son reçu depuis {Math.round(niveau.silence)} s.{" "}
              {avecApp ? `Vérifiez que ${nomApp} fait bien du son (réunion lancée, son non coupé)${r.source === "mixed" ? " et que le bon microphone est choisi" : ""}.`
                : `Vérifiez que le bon ${r.source === "system" ? "haut-parleur" : "microphone"} est choisi et qu'il n'est pas coupé.`}
            </Alerte>
          )}
          <Diagnostic etat={state} />
        </div>
      </div>
    );
  }

  // --- Résultat ------------------------------------------------------------------------------------------------
  if (state && !state.archived && !echecSansTexte) {
    return (
      <>
        <p className="sr-only" aria-live="polite">{annonce}</p>
        {erreur && <Alerte>{erreur}</Alerte>}
        <VueResultat etat={state} reglages={r} regler={regler} diarisationDispo={diarisationDispo} action={action} rafraichir={rafraichir}
          retour={{ label: "Nouvelle transcription", faire: nouvelle }} vientDeFinir
          aussi={{ label: "Mes transcriptions", faire: async () => {
            setErreur("");
            try { await oublier(); window.location.hash = "#/historique"; } catch (e) { setErreur(messageErreur(e)); }
          } }} diagnostic={<Diagnostic etat={state} />} />
      </>
    );
  }

  // --- Avant de démarrer -------------------------------------------------------------------------------------
  return (
    <div className="flex flex-col gap-6">
      {lienCommandes}
      <p className="sr-only" aria-live="polite">{annonce}</p>
      <div className="nn-page-head">
        <div>
          <h1 className="nn-page-title">Transcrire</h1>
          <p className="nn-page-subtitle">Tout reste sur cet ordinateur : aucun son ne quitte le poste.</p>
        </div>
      </div>
      <ChoixMode mode={r.mode} changer={(m) => { setErreur(""); regler("mode", m); }} bloque={demarrage} />
      {echecSansTexte && (
        <div className="flex flex-wrap items-center gap-3">
          <Alerte>{state!.error || "La transcription s'est arrêtée sur une erreur."}</Alerte>
          <button type="button" className="nn-btn nn-btn-secondary" onClick={nouvelle}>Fermer</button>
        </div>
      )}

      <section className="nn-card flex flex-wrap overflow-hidden p-0">
        <div id="commandes" tabIndex={-1} role="region" aria-label="Démarrer"
          className={`relative flex flex-[1_1_340px] flex-col items-center ${avances ? "justify-start" : "justify-center"} gap-4 border-line bg-surface-2 px-6 py-10 outline-none max-md:border-b md:border-r`}>
          {/* Centré sur la hauteur ; en haut quand les réglages avancés allongent la carte (il ne descend pas avec eux) */}
          {modeFichier ? (
            <>
              <FilePicker choix={choix} choisir={setChoix} extensions={capacites?.file_extensions ?? []} disponible={capacites?.files ?? true} occupe={demarrage} />
              <div className="flex w-full flex-wrap items-center gap-2">
                <button type="button" className="nn-btn nn-btn-primary h-12 flex-1 gap-2 text-[16px]" onClick={demarrer} disabled={!peutDemarrer}>
                  {envoi !== null ? `Envoi… ${Math.round(envoi * 100)} %` : demarrage ? (r.engine === "local" ? "Chargement du modèle…" : "Démarrage…") : "Transcrire le fichier"}
                </button>
                {envoi !== null && <button type="button" className="nn-btn nn-btn-secondary h-12" onClick={() => envoiEnCours.current?.abort()}>Annuler l'envoi</button>}
              </div>
            </>
          ) : (
            <>
              <button type="button" onClick={demarrer} disabled={!peutDemarrer} aria-describedby="demarrer-detail"
                className="flex h-28 w-28 items-center justify-center rounded-full border-0 bg-primary text-primary-on shadow-[0_0_0_10px_var(--nn-accent-soft)] transition-transform
                  hover:bg-primary-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[14px] focus-visible:outline-focus enabled:hover:scale-[1.03]
                  disabled:cursor-not-allowed disabled:bg-primary-disabled disabled:text-primary-on-disabled">
                <IconeMicro taille={44} />
                <span className="sr-only">Démarrer l'enregistrement</span>
              </button>
              <div id="demarrer-detail" className="text-center">
                <div className="text-[19px] font-bold text-ink" aria-hidden="true">{demarrage ? (r.engine === "local" && prechargement?.state !== "ready" ? "Chargement du modèle…" : "Démarrage…") : "Démarrer l'enregistrement"}</div>
                <div className="mt-1 text-sm text-ink-muted">{resume}</div>
                <div className="mt-0.5 text-[13px] text-ink-subtle">Espace : pause · Échap : arrêter · M : marquer un moment</div>
              </div>
            </>
          )}
          {prechargement && !pourquoiPas && (
            <p role="status" className={`m-0 flex items-center gap-1.5 text-[12px] ${prechargement.state === "error" ? "max-w-[320px] text-center text-warning-text" : "text-ink-subtle"}`}>
              {prechargement.state === "loading" && <span className="h-3 w-3 animate-spin rounded-full border-2 border-line-strong border-t-accent" aria-hidden="true" />}
              {prechargement.state === "loading" ? "Préparation du modèle de transcription…"
                : prechargement.state === "ready" ? `✓ Modèle prêt${prechargement.device ? ` (${prechargement.device.startsWith("CUDA") ? "carte graphique" : "processeur"})` : ""}`
                : prechargement.state === "error" ? `Le modèle n'a pas pu être chargé : ${prechargement.message}` : ""}
            </p>
          )}
          {pourquoiPas && <p className="m-0 max-w-[320px] text-center text-[13px] text-warning-text">{pourquoiPas}</p>}
        </div>

        <div className="flex flex-[2_1_520px] flex-col gap-1 px-7 pb-6 pt-7">
          <h2 className="m-0 mb-1 text-[19px] font-bold text-ink">Prêt ?</h2>
          <Pret reglages={r} regler={regler} ecoute={ecoute} ouvrirAvances={ouvrirAvances} capacites={capacites} peripheriques={peripheriques} applications={applications} apercu={apercu}
            actualiser={actualiser} pipeline={pipeline} intervenantsEquipe={equipeIntervenants} modeleOk={modeleOk} blocModele={blocModele} occupe={demarrage} />
          <ReglagesAvances ouvert={avances} basculer={() => setAvances(!avances)} reglages={r} regler={regler} capacites={capacites} cuda={cuda} modeleOk={modeleOk} blocModele={blocModele} pipeline={pipeline} intervenantsEquipe={equipeIntervenants} occupe={demarrage} />
        </div>
      </section>
      {alertes}
    </div>
  );
};
