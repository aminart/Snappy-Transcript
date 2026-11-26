import React from "react";
import { api } from "./api";
import { hms } from "./format";
import { Historique } from "./Historique";
import { Transcription } from "./Transcription";

/*
 * Coque de l'app : en-tête commun de la suite (nn-appbar), deux pages (Transcrire, Mes transcriptions), version en pied de page. Règle de la suite : seule l'icône a sa couleur
 * propre ; tout le reste suit Night Navy. Les pages sont dans Transcription.tsx.
 */

type Page = "transcription" | "historique";

interface Sante {
  name: string;
  version: string;
}

const PAGES: { id: Page; label: string }[] = [
  { id: "transcription", label: "Transcrire" },
  { id: "historique", label: "Mes transcriptions" },
];

const pageDepuisAdresse = (): Page =>
  window.location.hash.startsWith("#/historique") ? "historique" : "transcription";

interface Bref { active: boolean; kind?: "live" | "file"; paused?: boolean; stopping?: boolean; duration?: number }

/** Point rouge « Enregistrement en cours » dans la barre des onglets, visible depuis toutes les pages ;
 *  un clic ramène à l'enregistrement. */
const IndicateurSession: React.FC = () => {
  const [bref, setBref] = React.useState<Bref>({ active: false });
  React.useEffect(() => {
    let arrete = false;
    const boucle = async () => {
      while (!arrete) {
        try { const b = await api<Bref>("/api/session/brief"); if (!arrete) setBref(b); } catch { /* serveur occupé */ }
        await new Promise((r) => setTimeout(r, 1000));
      }
    };
    boucle();
    return () => { arrete = true; };
  }, []);
  if (!bref.active) return null;
  const fichier = bref.kind === "file";
  const texte = bref.stopping ? (fichier ? "Arrêt de la transcription…" : "Fin de l'enregistrement…")
    : bref.paused ? (fichier ? "Transcription en pause" : "Enregistrement en pause")
    : fichier ? "Transcription en cours" : "Enregistrement en cours";
  const point = bref.paused || bref.stopping ? "bg-warning" : fichier ? "bg-accent" : "bg-danger";
  return (
    <a href="#/" title="Revenir à l'enregistrement"
      className="ml-2 inline-flex items-center gap-2 self-center rounded-full border border-line bg-surface px-3 py-1 text-[13px] font-medium text-ink no-underline hover:bg-surface-3">
      <span className="relative flex h-2.5 w-2.5" aria-hidden="true">
        {!bref.paused && !bref.stopping && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${point}`} />}
        <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${point}`} />
      </span>
      <span>{texte}</span>
      {!fichier && bref.duration !== undefined && <span className="font-mono text-[12px] tabular-nums text-ink-muted">{hms(bref.duration)}</span>}
    </a>
  );
};

export const App: React.FC = () => {
  const [page, setPage] = React.useState<Page>(pageDepuisAdresse);
  const [sante, setSante] = React.useState<Sante | null>(null);

  React.useEffect(() => {
    const suivre = () => setPage(pageDepuisAdresse());
    window.addEventListener("hashchange", suivre);
    fetch("/health").then((r) => r.json()).then(setSante).catch(() => undefined);
    return () => window.removeEventListener("hashchange", suivre);
  }, []);

  const nom = sante?.name ?? "Snappy Transcript";
  React.useEffect(() => { document.title = nom; }, [nom]);

  return (
    <div className="flex min-h-screen flex-col bg-bg text-ink-body">
      <header className="nn-appbar sticky top-0 z-10">
        {/* 1 · Identité : icône (sa couleur propre) et nom */}
        <a className="nn-appbar-brand" href="#/">
          <img className="nn-appbar-icon" src="/icone.svg" alt="" />
          {nom}
        </a>
        {/* 2 · Navigation : onglets, l'actif porte aria-current */}
        <nav className="nn-appbar-nav" aria-label="Navigation principale">
          {PAGES.map((p) => (
            <a key={p.id} className="nn-appbar-tab" href={p.id === "transcription" ? "#/" : `#/${p.id}`}
              aria-current={page === p.id ? "page" : undefined}>
              {p.label}
            </a>
          ))}
        </nav>
        <IndicateurSession />
        {/* 3 · Utilitaires, dans cet ordre : aide, langue, thème, réglages (omettre ceux qui manquent) */}
        <div className="nn-appbar-tools">
          <BoutonTheme />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1280px] flex-1 flex-col gap-6 px-6 py-8">
        {page === "transcription" ? <Transcription /> : <Historique />}
      </main>
      {/* Version, pour le support : discrète, toujours en bas de la fenêtre (main occupe la hauteur restante) */}
      <footer className="mx-auto w-full max-w-[1280px] px-6 pb-6 text-[12px] text-ink-muted">
        {nom}{sante?.version ? ` ${sante.version}` : ""} · tout reste sur cet ordinateur
      </footer>
    </div>
  );
};

const BoutonTheme: React.FC = () => {
  const [sombre, setSombre] = React.useState(() => window.NightNavy?.current() === "dark");
  React.useEffect(() => {
    const suivre = () => setSombre(window.NightNavy.current() === "dark");
    document.documentElement.addEventListener("nn-themechange", suivre);
    return () => document.documentElement.removeEventListener("nn-themechange", suivre);
  }, []);
  return (
    <button type="button" className="nn-icon-btn" onClick={() => window.NightNavy.toggle()}
      aria-label={sombre ? "Passer en thème clair" : "Passer en thème sombre"} title="Changer de thème">
      {sombre ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
};

