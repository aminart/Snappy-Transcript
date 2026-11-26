import React from "react";
import { api, messageErreur } from "../api";
import { hms } from "../format";
import type { Intervenant, Marque, Segment, SessionState } from "../types";
import { IconeLecture, IconeMarque, IconePause, phrasesMarquees } from "./EnDirect";
import { Alerte } from "./ui";

type Variante = "raw" | "diarized";
interface Occurrence { seg: number; debut: number; fin: number }

/** Teintes des intervenants : bleus et gris du design system (jamais de couleur propre à l'app). */
export const TEINTES = ["var(--nn-primary)", "var(--nn-accent-muted)", "var(--nn-ink-subtle)", "var(--nn-ink-body)", "var(--nn-accent)", "var(--nn-line-strong)"];

/** Dernier segment dont le début est ≤ t, tant que t n'a pas dépassé sa fin (ou le début du suivant). */
function segmentA(segments: Segment[], t: number): number {
  let bas = 0, haut = segments.length - 1, meilleur = -1;
  while (bas <= haut) {
    const milieu = (bas + haut) >> 1;
    if (segments[milieu].start <= t) { meilleur = milieu; bas = milieu + 1; } else haut = milieu - 1;
  }
  if (meilleur < 0) return -1;
  const s = segments[meilleur];
  const suivant = meilleur + 1 < segments.length ? segments[meilleur + 1].start : s.end;
  return t < Math.max(s.end, suivant) ? meilleur : -1;
}

/** Texte à coller dans un compte rendu : une réplique par intervenant, sans horodatage. */
export function texteACopier(segments: Segment[], nom: (s: Segment) => string | null = (s) => s.speaker): string {
  const blocs: { qui: string | null; texte: string[] }[] = [];
  for (const s of segments) {
    const qui = nom(s);
    const dernier = blocs[blocs.length - 1];
    if (dernier && dernier.qui === qui) dernier.texte.push(s.text);
    else blocs.push({ qui, texte: [s.text] });
  }
  return blocs.map((b) => (b.qui ? `${b.qui} : ` : "") + b.texte.join(" ")).join(blocs.some((b) => b.qui) ? "\n\n" : "\n");
}

async function copier(texte: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(texte);
  } catch { // presse-papiers refusé : ancienne méthode
    const zone = document.createElement("textarea");
    zone.value = texte;
    zone.style.position = "fixed";
    zone.style.opacity = "0";
    document.body.appendChild(zone);
    zone.select();
    document.execCommand("copy");
    zone.remove();
  }
}

/** Même règle que le serveur : recherche littérale, mot entier et majuscules en option. */
export function motif(cherche: string, casse: boolean, motEntier: boolean): RegExp | null {
  if (!cherche) return null;
  const corps = cherche.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(motEntier ? `(?<![\\p{L}\\p{N}_])${corps}(?![\\p{L}\\p{N}_])` : corps, casse ? "gu" : "giu");
}

export const dateSession = (iso: string, avecJour = true): string => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const heure = d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  const auj = new Date();
  const hier = new Date(auj.getTime() - 86400000);
  const meme = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (meme(d, auj)) return `Aujourd'hui, ${heure}`;
  if (meme(d, hier)) return `Hier, ${heure}`;
  if (auj.getTime() - d.getTime() < 6 * 86400000 && avecJour) {
    const jour = d.toLocaleDateString("fr-FR", { weekday: "long" });
    return `${jour.charAt(0).toUpperCase()}${jour.slice(1)}, ${heure}`;
  }
  return `${d.toLocaleDateString("fr-FR")}, ${heure}`;
};

export const dureeCourte = (s: number): string => {
  const m = Math.round(s / 60);
  if (s < 60) return `${Math.round(s)} s`;
  return m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}` : `${m} min`;
};

const Crayon = ({ taille = 16 }: { taille?: number }) => (
  <svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16z" /></svg>
);
const Loupe = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></svg>
);

/** Petit champ qui remplace un texte le temps de le modifier : Entrée enregistre, Échap annule. */
const ChampEnLigne: React.FC<{ valeur: string; label: string; enregistrer: (v: string) => void; annuler: () => void; className?: string; max?: number }> =
  ({ valeur, label, enregistrer, annuler, className = "", max = 120 }) => {
    const [v, setV] = React.useState(valeur);
    return (
      <input autoFocus aria-label={label} className={`nn-input ${className}`} value={v} maxLength={max}
        onChange={(e) => setV(e.target.value)} onBlur={() => enregistrer(v)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); enregistrer(v); } if (e.key === "Escape") { e.preventDefault(); annuler(); } }} />
    );
  };

interface Props {
  etat: SessionState;
  audio: boolean;
  rafraichir: () => void;
  ajouterAuGlossaire: (mot: string) => void;
  /** Panneau d'identification des intervenants (lancer, avancement, réessayer). */
  panneauIntervenants: React.ReactNode;
  /** Bouton du haut : « Nouvelle transcription », ou retour à la liste depuis Mes transcriptions. */
  retour: { label: string; faire: () => void };
}

/**
 * Résultat d'une session : titre, texte à corriger sur place, intervenants à nommer d'un clic, lecteur avec forme
 * d'onde par intervenant, moments marqués, rechercher / remplacer, copier et exporter (dont Word).
 */
export const ResultatPage: React.FC<Props> = ({ etat, audio, rafraichir, ajouterAuGlossaire, panneauIntervenants, retour }) => {
  const avecIntervenants = etat.diarization.status === "DONE";
  // Une seule version affichée : avec intervenants dès qu'ils sont identifiés (les corrections sont reportées dans
  // le texte seul par le serveur, qui reste téléchargeable dans « Exporter »).
  const variante: Variante = avecIntervenants ? "diarized" : "raw";
  const [segments, setSegments] = React.useState<Segment[]>([]);
  const [version, setVersion] = React.useState(0);
  const [erreur, setErreur] = React.useState("");
  const [copie, setCopie] = React.useState(false);
  const [edition, setEdition] = React.useState<number | null>(null);
  const [titreEdite, setTitreEdite] = React.useState(false);
  const [renomme, setRenomme] = React.useState<{ label: string; ligne: number } | null>(null); // une seule ligne à la fois
  const [menu, setMenu] = React.useState(false);
  const [recherche, setRecherche] = React.useState(false);
  const [cherche, setCherche] = React.useState("");
  const [par, setPar] = React.useState("");
  const [casse, setCasse] = React.useState(false);
  const [motEntier, setMotEntier] = React.useState(true);
  const [glossaire, setGlossaire] = React.useState(true);
  const [courante, setCourante] = React.useState(0);
  const [avis, setAvis] = React.useState<{ texte: string; annuler?: boolean } | null>(null);
  const [lecture, setLecture] = React.useState({ t: 0, enCours: false, vitesse: 1 });
  const [pos, setPos] = React.useState({ seg: -1, mot: -1 });
  const lecteur = React.useRef<HTMLAudioElement>(null);
  const lignes = React.useRef<Map<number, HTMLDivElement>>(new Map());
  const champRecherche = React.useRef<HTMLInputElement>(null);
  const boutonMenu = React.useRef<HTMLButtonElement>(null);

  React.useEffect(() => {
    let annule = false;
    api<{ segments: Segment[] }>(`/api/session/transcript?variant=${variante}`)
      .then((d) => { if (!annule) { setSegments(d.segments); setErreur(""); } })
      .catch((e) => { if (!annule) setErreur(messageErreur(e)); });
    return () => { annule = true; };
  }, [variante, etat.id, version, JSON.stringify(etat.speakers)]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- intervenants : couleur et nom affiché ---
  const intervenants: Intervenant[] = etat.speakers;
  const parEtiquette = React.useMemo(() => {
    const m = new Map<string, { i: number; nom: string; label: string }>();
    intervenants.forEach((x, i) => {
      const info = { i, nom: x.name || `Intervenant ${i + 1}`, label: x.label };
      m.set(x.label, info);
      if (x.name) m.set(x.name, info);
    });
    return m;
  }, [intervenants]);
  const infoDe = (s: Segment) => (s.speaker ? parEtiquette.get(s.speaker) : undefined);
  const nomAffiche = (s: Segment) => (variante === "diarized" ? infoDe(s)?.nom ?? s.speaker : null);

  const renommer = async (label: string, nom: string) => {
    setRenomme(null);
    const noms = Object.fromEntries(intervenants.map((x) => [x.label, x.name]));
    if ((noms[label] ?? "") === nom.trim()) return;
    noms[label] = nom.trim();
    try { await api("/api/session/speakers", { method: "PUT", json: { names: noms } }); rafraichir(); }
    catch (e) { setErreur(messageErreur(e)); }
  };

  // --- recherche ---
  const re = React.useMemo(() => motif(cherche, casse, motEntier), [cherche, casse, motEntier]);
  const occurrences = React.useMemo(() => {
    const out: Occurrence[] = [];
    if (!re || !recherche) return out;
    segments.forEach((s, seg) => { for (const m of s.text.matchAll(re)) out.push({ seg, debut: m.index ?? 0, fin: (m.index ?? 0) + m[0].length }); });
    return out;
  }, [re, segments, recherche]);
  const actuelle = occurrences.length ? occurrences[Math.min(courante, occurrences.length - 1)] : null;
  React.useEffect(() => { setCourante(0); }, [cherche, casse, motEntier]);
  React.useEffect(() => {
    if (actuelle) lignes.current.get(actuelle.seg)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [actuelle?.seg, actuelle?.debut]); // eslint-disable-line react-hooks/exhaustive-deps

  const ouvrirRecherche = React.useCallback(() => {
    setRecherche(true);
    requestAnimationFrame(() => { champRecherche.current?.focus(); champRecherche.current?.select(); });
  }, []);

  const annuler = React.useCallback(async () => {
    try {
      const r = await api<{ undone: string }>("/api/session/undo", { method: "POST" });
      setAvis({ texte: `${r.undone.charAt(0).toUpperCase()}${r.undone.slice(1)} est annulé${r.undone.startsWith("la") ? "e" : ""}.` });
      setVersion((v) => v + 1);
      rafraichir();
    } catch (e) { setErreur(messageErreur(e)); }
  }, [rafraichir]);

  // Raccourcis : Ctrl+F rechercher, Ctrl+H remplacer, Ctrl+Z annuler la dernière correction ou le dernier remplacement
  React.useEffect(() => {
    const touche = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const k = e.key.toLowerCase();
      if (k === "f" || k === "h") { e.preventDefault(); ouvrirRecherche(); }
      const cible = e.target as HTMLElement | null;
      if (k === "z" && etat.can_undo && !(cible && /^(INPUT|TEXTAREA)$/.test(cible.tagName))) { e.preventDefault(); annuler(); }
    };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [ouvrirRecherche, annuler, etat.can_undo]);

  const corriger = React.useCallback(async (index: number, texte: string) => {
    setEdition(null);
    if (!texte.trim() || texte === segments[index]?.text) return;
    try {
      const s = await api<Segment>("/api/session/segment", { method: "PUT", json: { variant: variante, index, text: texte } });
      setSegments((avant) => avant.map((x, i) => (i === index ? s : x)));
      setErreur("");
      setAvis({ texte: "Phrase corrigée, dans l'app et dans les fichiers.", annuler: true });
      rafraichir();
    } catch (e) { setErreur(messageErreur(e)); }
  }, [segments, variante, rafraichir]);

  const remplacerUne = async () => {
    if (!actuelle) return;
    const s = segments[actuelle.seg];
    await corriger(actuelle.seg, s.text.slice(0, actuelle.debut) + par + s.text.slice(actuelle.fin));
  };
  const toutRemplacer = async () => {
    if (!cherche) return;
    try {
      const r = await api<{ replaced: number }>("/api/session/replace", { method: "POST", json: { find: cherche, replace: par, case: casse, whole_word: motEntier } });
      if (r.replaced && glossaire && par.trim()) ajouterAuGlossaire(par.trim());
      setAvis(r.replaced ? { texte: `${r.replaced} remplacement${r.replaced > 1 ? "s" : ""}${glossaire && par.trim() ? ` · « ${par.trim()} » ajouté aux mots à bien reconnaître` : ""}.`, annuler: true }
        : { texte: "Aucune occurrence." });
      setVersion((v) => v + 1);
      rafraichir();
    } catch (e) { setErreur(messageErreur(e)); }
  };

  // --- lecteur ---
  const synchroniser = React.useCallback(() => {
    const a = lecteur.current;
    if (!a) return;
    const t = a.currentTime;
    const i = segmentA(segments, t);
    let m = -1;
    const mots = i >= 0 ? segments[i].words : undefined;
    if (mots) for (let j = 0; j < mots.length; j++) if (t >= mots[j][0] && t < Math.max(mots[j][1], mots[j][0] + 0.03)) { m = j; break; }
    setPos((p) => (p.seg === i && p.mot === m ? p : { seg: i, mot: m }));
    setLecture((l) => (Math.abs(l.t - t) < 0.05 && l.enCours === !a.paused ? l : { ...l, t, enCours: !a.paused }));
  }, [segments]);
  React.useEffect(() => {
    const a = lecteur.current;
    if (!a) return;
    let image = 0;
    const boucle = () => { synchroniser(); image = requestAnimationFrame(boucle); };
    const lire = () => { cancelAnimationFrame(image); image = requestAnimationFrame(boucle); };
    const arreter = () => { cancelAnimationFrame(image); synchroniser(); };
    a.addEventListener("play", lire);
    a.addEventListener("pause", arreter);
    a.addEventListener("ended", arreter);
    a.addEventListener("seeked", synchroniser);
    return () => { cancelAnimationFrame(image); a.removeEventListener("play", lire); a.removeEventListener("pause", arreter); a.removeEventListener("ended", arreter); a.removeEventListener("seeked", synchroniser); };
  }, [synchroniser]);
  const aller = React.useCallback((t: number, jouer = true) => {
    const a = lecteur.current;
    if (!a) return;
    a.currentTime = Math.max(0, t);
    if (jouer) a.play().catch(() => undefined);
    else synchroniser();
  }, [synchroniser]);
  React.useEffect(() => {
    if (pos.seg >= 0 && lecture.enCours && edition === null && !recherche) {
      const l = lignes.current.get(pos.seg);
      if (l) { const r = l.getBoundingClientRect(); if (r.top < 140 || r.bottom > window.innerHeight - 40) l.scrollIntoView({ block: "center", behavior: "smooth" }); }
    }
  }, [pos.seg]); // eslint-disable-line react-hooks/exhaustive-deps

  const marquees = React.useMemo(() => phrasesMarquees(segments, etat.marks), [segments, etat.marks]);
  const titre = etat.title || etat.default_title;
  const fichiers = etat.files as { wav?: boolean };
  const suffixe = avecIntervenants ? "diarized" : "raw";

  const enregistrerTitre = async (v: string) => {
    setTitreEdite(false);
    if (v.trim() === titre) return;
    try { await api("/api/session/title", { method: "PUT", json: { title: v } }); rafraichir(); } catch (e) { setErreur(messageErreur(e)); }
  };
  const modifierMarque = async (i: number, label: string | null) => {
    try { await api(`/api/session/marks/${i}`, { method: "PUT", json: { label } }); rafraichir(); } catch (e) { setErreur(messageErreur(e)); }
  };

  React.useEffect(() => {
    if (!menu) return;
    document.querySelector<HTMLElement>("[data-menu-export] [role=menuitem]")?.focus(); // le menu s'ouvre sur son premier choix
    const fermer = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent) { if (e.key === "Escape") { setMenu(false); boutonMenu.current?.focus(); } return; }
      if (!(e.target as HTMLElement).closest("[data-menu-export]")) setMenu(false);
    };
    window.addEventListener("mousedown", fermer);
    window.addEventListener("keydown", fermer);
    return () => { window.removeEventListener("mousedown", fermer); window.removeEventListener("keydown", fermer); };
  }, [menu]);

  const meta = [etat.started ? dateSession(etat.started) : "", etat.duration ? dureeCourte(etat.duration) : "",
    intervenants.length ? `${intervenants.length} intervenant${intervenants.length > 1 ? "s" : ""}` : "",
    etat.kind === "file" && etat.file?.name && etat.title ? etat.file.name : "", "enregistré sur ce poste"].filter(Boolean).join(" · ");

  return (
    <div className="flex flex-col gap-5">
      <button type="button" className="nn-btn nn-btn-secondary self-start gap-2" onClick={retour.faire}
        disabled={etat.diarization.status === "RUNNING" && retour.label === "Nouvelle transcription"}
        title={etat.diarization.status === "RUNNING" ? "Attendez la fin de l'identification des intervenants" : undefined}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          {retour.label === "Nouvelle transcription" ? <path d="M12 5v14M5 12h14" /> : <path d="M15 18l-6-6 6-6" />}
        </svg>
        {retour.label}
      </button>

      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-0 flex-[1_1_360px]">
          {titreEdite ? (
            <ChampEnLigne valeur={titre} label="Titre de la session" enregistrer={enregistrerTitre} annuler={() => setTitreEdite(false)} className="h-12 max-w-[560px] text-[22px] font-bold" />
          ) : (
            <div className="flex items-center gap-2">
              <h1 className="nn-page-title break-words">{titre}</h1>
              <button type="button" className="nn-icon-btn shrink-0" aria-label="Renommer la session" title="Renommer" onClick={() => setTitreEdite(true)}><Crayon /></button>
            </div>
          )}
          <p className="m-0 mt-1.5 text-[15px] text-ink-muted">{meta}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={`nn-btn gap-2 ${recherche ? "nn-btn-soft" : "nn-btn-secondary"}`} aria-expanded={recherche} aria-controls="rechercher"
            aria-keyshortcuts="Control+F Control+H" title="Ctrl+F : rechercher · Ctrl+H : remplacer" onClick={() => (recherche ? setRecherche(false) : ouvrirRecherche())}>
            <Loupe /> Rechercher et remplacer
          </button>
          <button type="button" className="nn-btn nn-btn-secondary gap-2" disabled={!segments.length}
            onClick={async () => { await copier(texteACopier(segments, nomAffiche)); setCopie(true); setTimeout(() => setCopie(false), 2000); }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></svg>
            {copie ? "✓ Copié" : "Copier le texte"}
          </button>
          <div className="relative" data-menu-export>
            <button ref={boutonMenu} type="button" className="nn-btn nn-btn-primary gap-2" aria-haspopup="menu" aria-expanded={menu}
              onClick={() => setMenu(!menu)}>
              Exporter
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
            </button>
            {menu && (
              <div role="menu" aria-label="Exporter" className="absolute right-0 top-[52px] z-20 w-[300px] rounded-md border border-line bg-surface p-1.5 shadow-lg"
                onKeyDown={(e) => {
                  const items = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("[role=menuitem]"));
                  const i = items.indexOf(document.activeElement as HTMLElement);
                  if (e.key === "ArrowDown") { e.preventDefault(); items[(i + 1) % items.length]?.focus(); }
                  if (e.key === "ArrowUp") { e.preventDefault(); items[(i - 1 + items.length) % items.length]?.focus(); }
                }}>
                <span className="block px-2.5 py-1.5 text-[12px] font-medium text-ink-subtle">{avecIntervenants ? "Avec les noms des intervenants" : "Le texte"}</span>
                {[
                  ["Word", ".docx", "/api/session/docx"],
                  ["Texte", ".txt", `/api/session/file/${suffixe}_txt?download=true`],
                  ["Sous-titres", ".srt", `/api/session/file/${suffixe}_srt?download=true`],
                ].map(([nom, ext, href]) => (
                  <a key={nom} role="menuitem" href={href} download onClick={() => setMenu(false)}
                    className="flex justify-between rounded px-2.5 py-2 text-ink no-underline hover:bg-surface-3 focus:bg-surface-3 focus:outline-none">{nom}<span className="text-ink-subtle">{ext}</span></a>
                ))}
                {(avecIntervenants || fichiers.wav) && <span className="my-1.5 block h-px bg-line" aria-hidden="true" />}
                {avecIntervenants && (
                  <a role="menuitem" href="/api/session/file/raw_txt?download=true" download onClick={() => setMenu(false)}
                    className="flex justify-between rounded px-2.5 py-2 text-ink no-underline hover:bg-surface-3 focus:bg-surface-3 focus:outline-none">Texte seul, sans intervenants<span className="text-ink-subtle">.txt</span></a>
                )}
                {fichiers.wav && (
                  <a role="menuitem" href="/api/session/file/wav?download=true" download onClick={() => setMenu(false)}
                    className="flex justify-between rounded px-2.5 py-2 text-ink no-underline hover:bg-surface-3 focus:bg-surface-3 focus:outline-none">Audio<span className="text-ink-subtle">.wav</span></a>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {recherche && (
        <div id="rechercher" role="search" aria-label="Rechercher et remplacer dans le texte" className="nn-card flex flex-col gap-2.5 px-4 py-3.5">
          <div className="flex flex-wrap items-center gap-2.5">
            <label className="flex h-10 w-[300px] max-w-full items-center gap-2 rounded border border-line-strong bg-surface px-2.5 focus-within:border-accent focus-within:ring-1 focus-within:ring-accent">
              <span className="text-ink-subtle"><Loupe /></span>
              <input ref={champRecherche} aria-label="Rechercher" className="min-w-0 flex-1 border-0 bg-transparent text-sm text-ink outline-none" value={cherche}
                onChange={(e) => setCherche(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && occurrences.length) { e.preventDefault(); setCourante((c) => (c + (e.shiftKey ? -1 : 1) + occurrences.length) % occurrences.length); }
                  if (e.key === "Escape") setRecherche(false);
                }} />
              <span className="whitespace-nowrap text-[12px] text-ink-subtle" aria-live="polite">{cherche ? (occurrences.length ? `${Math.min(courante, occurrences.length - 1) + 1} / ${occurrences.length}` : "0 / 0") : ""}</span>
              <button type="button" aria-label="Occurrence précédente" className="h-7 w-7 rounded border-0 bg-transparent text-ink-muted hover:bg-surface-3 disabled:opacity-40"
                disabled={!occurrences.length} onClick={() => setCourante((c) => (c - 1 + occurrences.length) % occurrences.length)}>↑</button>
              <button type="button" aria-label="Occurrence suivante" className="h-7 w-7 rounded border-0 bg-transparent text-ink-muted hover:bg-surface-3 disabled:opacity-40"
                disabled={!occurrences.length} onClick={() => setCourante((c) => (c + 1) % occurrences.length)}>↓</button>
            </label>
            <span aria-hidden="true" className="text-ink-subtle">→</span>
            <input aria-label="Remplacer par" placeholder="Remplacer par…" className="nn-input h-10 w-[240px] max-w-full" value={par} onChange={(e) => setPar(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); remplacerUne(); } }} />
            <button type="button" className="nn-btn nn-btn-secondary h-10" disabled={!actuelle} onClick={remplacerUne}>Remplacer</button>
            <button type="button" className="nn-btn nn-btn-primary h-10" disabled={!occurrences.length} onClick={toutRemplacer}>Tout remplacer{occurrences.length ? ` (${occurrences.length})` : ""}</button>
            <button type="button" className="nn-icon-btn ml-auto" aria-label="Fermer la recherche" onClick={() => setRecherche(false)}>×</button>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[13px] text-ink-body">
            <label className="nn-check text-[13px]"><input type="checkbox" checked={casse} onChange={(e) => setCasse(e.target.checked)} /> <span>Respecter les majuscules</span></label>
            <label className="nn-check text-[13px]"><input type="checkbox" checked={motEntier} onChange={(e) => setMotEntier(e.target.checked)} /> <span>Mot entier</span></label>
            <label className="nn-check text-[13px]"><input type="checkbox" checked={glossaire} onChange={(e) => setGlossaire(e.target.checked)} />
              <span>Ajouter {par.trim() ? `« ${par.trim()} »` : "le nouveau mot"} aux mots à bien reconnaître (prochaines sessions)</span></label>
            <span className="ml-auto text-ink-subtle">Les noms des intervenants ne sont pas modifiés · Ctrl+Z annule</span>
          </div>
        </div>
      )}
      {avis && (
        <p role="status" className="m-0 flex flex-wrap items-center gap-3 rounded border border-line bg-surface-2 px-4 py-2.5 text-sm text-ink-body">
          {avis.texte}
          {avis.annuler && etat.can_undo && <button type="button" className="border-0 bg-transparent p-0 text-sm font-medium text-accent underline" onClick={annuler}>Annuler</button>}
          <button type="button" className="nn-icon-btn ml-auto h-7 w-7" aria-label="Fermer le message" onClick={() => setAvis(null)}>×</button>
        </p>
      )}
      {erreur && <Alerte>{erreur}</Alerte>}

      <div className="flex flex-wrap items-start gap-6">
        <article className="nn-card min-w-0 flex-[999_1_560px] px-5 pb-4 pt-2 sm:px-7" aria-label="Transcription">
          {segments.length === 0 && !erreur && <p className="m-3 text-sm text-ink-muted">Aucune parole détectée.</p>}
          {segments.map((s, i) => {
            const info = variante === "diarized" ? infoDe(s) : undefined;
            const marque = marquees.get(i);
            const actif = pos.seg === i;
            const parts: React.ReactNode[] = [];
            if (recherche && re) {
              let dernier = 0;
              occurrences.forEach((o) => {
                if (o.seg !== i) return;
                parts.push(s.text.slice(dernier, o.debut));
                const courant = actuelle === o;
                parts.push(<mark key={o.debut} className={`rounded-sm px-0.5 text-ink ${courant ? "bg-warning-line ring-2 ring-warning" : "bg-warning-soft"}`}>{s.text.slice(o.debut, o.fin)}</mark>);
                dernier = o.fin;
              });
              parts.push(s.text.slice(dernier));
            } else if (actif && s.words?.length) {
              s.words.forEach((m, j) => parts.push(<React.Fragment key={j}><span className={`rounded px-0.5 ${j === pos.mot ? "bg-primary text-primary-on" : ""}`}>{m[2]}</span>{" "}</React.Fragment>));
            } else parts.push(s.text);
            return (
              <div key={i} ref={(el) => { if (el) lignes.current.set(i, el); else lignes.current.delete(i); }}
                className={`grid gap-3.5 border-b border-line py-4 last:border-b-0 ${variante === "diarized" ? "grid-cols-[150px_1fr]" : "grid-cols-[72px_1fr]"} max-sm:grid-cols-1`}>
                <div className="flex flex-col items-start gap-1">
                  {info && (renomme?.label === info.label && renomme.ligne === i ? (
                    <ChampEnLigne valeur={intervenants[info.i]?.name ?? ""} label={`Nom de ${info.nom}`} max={40} className="h-8 w-[140px] text-[13px]"
                      enregistrer={(v) => renommer(info.label, v)} annuler={() => setRenomme(null)} />
                  ) : (
                    <button type="button" onClick={() => setRenomme({ label: info.label, ligne: i })} title="Cliquez pour changer ce nom partout"
                      className={`inline-flex h-7 max-w-full items-center gap-1.5 rounded-full border bg-surface px-2.5 text-[13px] font-medium text-ink hover:bg-surface-3 ${intervenants[info.i]?.name ? "border-line-strong" : "border-dashed border-ink-subtle"}`}>
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: TEINTES[info.i % TEINTES.length] }} aria-hidden="true" />
                      <span className="truncate">{info.nom}</span>
                      {!intervenants[info.i]?.name && <Crayon taille={12} />}
                    </button>
                  ))}
                  {audio ? (
                    <button type="button" className="border-0 bg-transparent p-0 font-mono text-xs text-ink-subtle underline-offset-2 hover:text-accent hover:underline"
                      aria-label={`Écouter à partir de ${hms(s.start)}`} onClick={() => aller(s.start)}>{hms(s.start)}</button>
                  ) : <span className="font-mono text-xs text-ink-subtle">{hms(s.start)}</span>}
                </div>
                {edition === i ? (
                  <ZoneCorrection texte={s.text} enregistrer={(t) => corriger(i, t)} annuler={() => setEdition(null)} />
                ) : (
                  <div className={`rounded-md ${marque ? "bg-accent-soft px-3 py-2.5" : ""} ${actif ? "ring-2 ring-accent-soft" : ""}`}>
                    {marque && <span className="mb-1 flex items-center gap-1.5 text-[12px] font-medium text-accent-ink"><IconeMarque taille={13} /> Moment marqué</span>}
                    <button type="button" onClick={() => setEdition(i)} title="Cliquez pour corriger cette phrase"
                      className="w-full cursor-text border-0 bg-transparent p-0 text-left text-[15px] leading-6 text-ink-body hover:bg-surface-2">
                      {parts}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </article>

        <aside className="flex max-w-[380px] flex-[1_1_320px] flex-col gap-4 lg:sticky lg:top-[80px]" aria-label="Écoute, intervenants et moments marqués">
          {audio && (
            <Lecteur etat={etat} lecture={lecture} segments={variante === "diarized" ? segments : []} couleur={(s) => TEINTES[(infoDe(s)?.i ?? 0) % TEINTES.length]}
              marques={etat.marks} aller={aller} lecteur={lecteur}
              vitesse={(v) => { if (lecteur.current) lecteur.current.playbackRate = v; setLecture((l) => ({ ...l, vitesse: v })); }} />
          )}
          {audio && <audio ref={lecteur} preload="metadata" src={`/api/session/file/wav?s=${etat.id}`} className="hidden" />}

          <section className="nn-card flex flex-col gap-3 px-5 py-4">
            <h2 className="m-0 text-[15px] font-bold text-ink">Intervenants</h2>
            {intervenants.length > 0 && (() => {
              const total = intervenants.reduce((n, x) => n + x.seconds, 0) || 1;
              return intervenants.map((x, i) => (
                <div key={x.label} className="grid grid-cols-[14px_1fr_56px] items-center gap-2.5">
                  <span className="h-3 w-3 rounded-full" style={{ background: TEINTES[i % TEINTES.length] }} aria-hidden="true" />
                  <div>
                    <button type="button" className="border-0 bg-transparent p-0 text-left text-sm text-ink hover:underline" onClick={() => {
                      const ligne = segments.findIndex((s) => parEtiquette.get(s.speaker ?? "")?.label === x.label);
                      if (ligne >= 0) { setRenomme({ label: x.label, ligne }); lignes.current.get(ligne)?.scrollIntoView({ block: "center", behavior: "smooth" }); }
                    }}>
                      {x.name || `Intervenant ${i + 1}`}
                    </button>
                    <div className="mt-1 h-1.5 rounded-full bg-surface-3"><div className="h-1.5 rounded-full" style={{ width: `${Math.round((x.seconds / total) * 100)}%`, background: TEINTES[i % TEINTES.length] }} /></div>
                  </div>
                  <span className="text-right text-[13px] text-ink-muted">{dureeCourte(x.seconds)}</span>
                </div>
              ));
            })()}
            {intervenants.length > 0 && <p className="m-0 text-[13px] text-ink-subtle">Cliquez sur un nom dans le texte pour le changer partout.</p>}
            {panneauIntervenants}
          </section>

          {etat.marks.length > 0 && (
            <section className="nn-card px-5 py-4">
              <h2 className="m-0 mb-2 text-[15px] font-bold text-ink">Moments marqués</h2>
              <ul className="m-0 flex list-none flex-col p-0">
                {etat.marks.map((m, i) => <LigneMarque key={`${i}-${m.t}`} marque={m} index={i} aller={(t) => {
                  if (audio) aller(t, false);
                  const k = [...marquees.entries()].find(([, x]) => x === m)?.[0];
                  if (k !== undefined) lignes.current.get(k)?.scrollIntoView({ block: "center", behavior: "smooth" });
                }} modifier={modifierMarque} />)}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
};

const ZoneCorrection: React.FC<{ texte: string; enregistrer: (t: string) => void; annuler: () => void }> = ({ texte, enregistrer, annuler }) => {
  const [v, setV] = React.useState(texte);
  const zone = React.useRef<HTMLTextAreaElement>(null);
  React.useLayoutEffect(() => {
    const z = zone.current;
    if (z) { z.focus(); z.setSelectionRange(z.value.length, z.value.length); z.style.height = "auto"; z.style.height = `${z.scrollHeight + 2}px`; }
  }, []);
  return (
    <div className="flex flex-col gap-1">
      <textarea ref={zone} aria-label="Corriger la phrase" aria-describedby="aide-correction" className="nn-input min-h-[44px] resize-none py-2 text-[15px] leading-6"
        value={v} onChange={(e) => { setV(e.target.value); e.target.style.height = "auto"; e.target.style.height = `${e.target.scrollHeight + 2}px`; }}
        onBlur={() => enregistrer(v)}
        onKeyDown={(e) => {
          if (e.key === "Escape") { e.preventDefault(); annuler(); }
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enregistrer(v); }
        }} />
      <span id="aide-correction" className="text-[12px] text-ink-subtle">Entrée : enregistrer · Échap : laisser comme avant · Ctrl+Z ensuite : annuler la correction</span>
    </div>
  );
};

const LigneMarque: React.FC<{ marque: Marque; index: number; aller: (t: number) => void; modifier: (i: number, label: string | null) => void }> = ({ marque, index, aller, modifier }) => {
  const [edite, setEdite] = React.useState(false);
  return (
    <li className="group grid grid-cols-[64px_1fr_auto] items-start gap-2 py-1.5 text-[13px] leading-[18px]">
      <span className="font-mono text-ink-subtle">{hms(marque.t)}</span>
      {edite ? (
        <ChampEnLigne valeur={marque.label} label="Nom du moment" className="h-8 text-[13px]"
          enregistrer={(v) => { setEdite(false); if (v.trim() !== marque.label) modifier(index, v); }} annuler={() => setEdite(false)} />
      ) : (
        <button type="button" className="border-0 bg-transparent p-0 text-left text-ink-body hover:text-accent hover:underline" onClick={() => aller(marque.t)}>{marque.label || "Moment marqué"}</button>
      )}
      {!edite && (
        <span className="flex gap-0.5">
          <button type="button" className="nn-icon-btn h-7 w-7" aria-label={`Renommer le moment de ${hms(marque.t)}`} onClick={() => setEdite(true)}><Crayon taille={13} /></button>
          <button type="button" className="nn-icon-btn h-7 w-7" aria-label={`Supprimer le moment de ${hms(marque.t)}`} onClick={() => modifier(index, null)}>×</button>
        </span>
      )}
    </li>
  );
};

const VITESSES = [1, 1.25, 1.5, 2, 0.75];

/** Lecteur : lecture / pause, temps, vitesse, et forme d'onde colorée par intervenant (cliquer pour s'y rendre). */
const Lecteur: React.FC<{
  etat: SessionState; lecture: { t: number; enCours: boolean; vitesse: number }; segments: Segment[]; couleur: (s: Segment) => string;
  marques: Marque[]; aller: (t: number, jouer?: boolean) => void; lecteur: React.RefObject<HTMLAudioElement | null>; vitesse: (v: number) => void;
}> = ({ etat, lecture, segments, couleur, marques, aller, lecteur, vitesse }) => {
  const [onde, setOnde] = React.useState<{ peaks: number[]; duration: number } | null>(null);
  React.useEffect(() => {
    let annule = false;
    api<{ peaks: number[]; duration: number }>("/api/session/waveform?n=120").then((o) => { if (!annule) setOnde(o); }).catch(() => undefined);
    return () => { annule = true; };
  }, [etat.id]);
  const total = onde?.duration || etat.duration || 1;
  const n = onde?.peaks.length ?? 120;
  const teinte = (k: number) => {
    if (!segments.length) return "var(--nn-accent-muted)";
    const t = ((k + 0.5) / n) * total;
    const s = segments.find((x) => x.start <= t && t < x.end);
    return s ? couleur(s) : "var(--nn-line-strong)";
  };
  const deplacer = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    aller(((e.clientX - r.left) / r.width) * total, !!lecture.enCours);
  };
  const jouer = () => { const a = lecteur.current; if (a) { if (a.paused) a.play().catch(() => undefined); else a.pause(); } };
  return (
    <section className="nn-card flex flex-col gap-3 px-5 py-4" aria-label="Lecteur">
      <div className="flex items-center gap-3">
        <button type="button" className="flex h-11 w-11 items-center justify-center rounded-full border-0 bg-primary text-primary-on hover:bg-primary-hover"
          aria-label={lecture.enCours ? "Pause" : "Lire"} onClick={jouer}>{lecture.enCours ? <IconePause /> : <IconeLecture />}</button>
        <span className="whitespace-nowrap font-mono text-[13px] text-ink">{hms(lecture.t)} <span className="text-ink-subtle">/ {hms(total)}</span></span>
        <button type="button" className="ml-auto whitespace-nowrap rounded border-0 bg-transparent px-2 py-1 text-[13px] text-ink-muted hover:bg-surface-3"
          aria-label={`Vitesse de lecture : ${lecture.vitesse}×. Changer`}
          onClick={() => vitesse(VITESSES[(VITESSES.indexOf(lecture.vitesse) + 1) % VITESSES.length])}>Vitesse {String(lecture.vitesse).replace(".", ",")}×</button>
      </div>
      <div role="slider" tabIndex={0} aria-label="Position dans l'enregistrement" aria-valuemin={0} aria-valuemax={Math.round(total)} aria-valuenow={Math.round(lecture.t)}
        aria-valuetext={hms(lecture.t)} onClick={deplacer}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") { e.preventDefault(); aller(lecture.t + 5, lecture.enCours); }
          if (e.key === "ArrowLeft") { e.preventDefault(); aller(lecture.t - 5, lecture.enCours); }
          if (e.key === " " || e.key === "Enter") { e.preventDefault(); jouer(); }
        }}
        className="relative flex h-12 cursor-pointer items-center gap-[2px] rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
        {(onde?.peaks ?? Array.from({ length: n }, () => 0.15)).map((p, k) => (
          <span key={k} className="flex-1 rounded-sm" style={{ height: `${Math.max(8, Math.round(p * 100))}%`, background: teinte(k), opacity: (k + 0.5) / n * total <= lecture.t ? 1 : 0.55 }} />
        ))}
        <span className="pointer-events-none absolute -bottom-1 -top-1 w-0.5 bg-ink" style={{ left: `${Math.min(100, (lecture.t / total) * 100)}%` }} aria-hidden="true" />
        {marques.map((m, i) => (
          <span key={i} className="pointer-events-none absolute -top-3 text-accent" style={{ left: `calc(${Math.min(100, (m.t / total) * 100)}% - 5px)` }} aria-hidden="true"><IconeMarque taille={10} /></span>
        ))}
      </div>
      {marques.length > 0 && <span className="flex items-center gap-1 text-[12px] text-ink-muted"><span className="text-accent"><IconeMarque taille={10} /></span>{marques.length} moment{marques.length > 1 ? "s" : ""} marqué{marques.length > 1 ? "s" : ""}</span>}
    </section>
  );
};
