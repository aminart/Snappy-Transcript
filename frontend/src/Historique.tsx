import React from "react";
import { api, messageErreur } from "./api";
import { dateSession, dureeCourte } from "./components/ResultatPage";
import { taille } from "./format";
import { Alerte } from "./components/ui";
import type { SessionPassee } from "./types";

type Filtre = "tout" | "live" | "file" | "intervenants";
const FILTRES: { id: Filtre; label: string }[] = [
  { id: "tout", label: "Tout" },
  { id: "live", label: "En direct" },
  { id: "file", label: "Fichiers" },
  { id: "intervenants", label: "Avec intervenants" },
];

const dateDepuisId = (id: string) => {
  const [j, h] = id.split("_");
  return `${j}T${h.slice(0, 8).replace(/-/g, ":")}`;
};
const titreParDefaut = (s: SessionPassee) => {
  if (s.name) return s.name;
  const [j, h] = s.id.split("_");
  return `Enregistrement du ${j.slice(8, 10)}/${j.slice(5, 7)}, ${h.slice(0, 5).replace("-", ":")}`;
};
const conserve = (s: SessionPassee) => {
  const audio = s.audio ? `L'audio${s.duration ? ` (${dureeCourte(s.duration)})` : ""}` : "";
  if (audio && s.recoverable) return `${audio} et le texte déjà transcrit sont conservés.`;
  if (audio) return `${audio} est conservé.`;
  return s.recoverable ? "Le texte déjà transcrit est conservé." : "";
};
const VIDEO = /\.(mp4|m4v|mov|mkv|avi|wmv|webm|mpe?g|ts|mts|m2ts|3gp|flv)$/i;

const Crayon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16z" /></svg>
);

/** Toutes les transcriptions : rechercher dans leur texte, filtrer, renommer, rouvrir, récupérer une session interrompue. */
export const Historique: React.FC = () => {
  const [sessions, setSessions] = React.useState<SessionPassee[] | null>(null);
  const [q, setQ] = React.useState("");
  const [filtre, setFiltre] = React.useState<Filtre>("tout");
  const [erreur, setErreur] = React.useState("");
  const [menu, setMenu] = React.useState<string | null>(null);
  const [aSupprimer, setASupprimer] = React.useState<string | null>(null);
  const [renomme, setRenomme] = React.useState<string | null>(null);
  const [sansAudio, setSansAudio] = React.useState<string | null>(null);
  const [place, setPlace] = React.useState<{ count: number; size: number; audio_size: number } | null>(null);
  const [liberer, setLiberer] = React.useState(false);
  const [jours, setJours] = React.useState(30);
  const [avis, setAvis] = React.useState("");

  const charger = React.useCallback((recherche: string) => {
    api<{ sessions: SessionPassee[]; count: number; size: number; audio_size: number }>(`/api/history${recherche.trim() ? `?q=${encodeURIComponent(recherche.trim())}` : ""}`)
      .then((r) => { setSessions(r.sessions); setPlace({ count: r.count, size: r.size, audio_size: r.audio_size }); })
      .catch((e) => setErreur(messageErreur(e)));
  }, []);
  React.useEffect(() => {
    const t = setTimeout(() => charger(q), q ? 250 : 0);
    return () => clearTimeout(t);
  }, [q, charger]);
  React.useEffect(() => {
    if (!menu) return;
    const fermer = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent) { if (e.key === "Escape") setMenu(null); return; }
      if (!(e.target as HTMLElement).closest("[data-menu-session]")) setMenu(null);
    };
    window.addEventListener("mousedown", fermer);
    window.addEventListener("keydown", fermer);
    return () => { window.removeEventListener("mousedown", fermer); window.removeEventListener("keydown", fermer); };
  }, [menu]);

  const faire = async (f: () => Promise<unknown>) => {
    setErreur("");
    try { await f(); } catch (e) { setErreur(messageErreur(e)); }
  };
  const ouvrir = (id: string, recuperer = false) => faire(async () => {
    await api(`/api/history/${id}/${recuperer ? "recover" : "open"}`, { method: "POST" });
    window.location.hash = "#/";
  });
  const dossier = (id: string) => faire(() => api(`/api/history/${id}/folder`, { method: "POST" }));
  const supprimer = (id: string) => faire(async () => {
    await api(`/api/history/${id}`, { method: "DELETE" });
    setASupprimer(null);
    charger(q);
  });
  const supprimerAudio = (id: string) => faire(async () => {
    const r = await api<{ freed: number }>(`/api/history/${id}/audio`, { method: "DELETE" });
    setSansAudio(null);
    setAvis(`Audio supprimé : ${taille(r.freed)} libérés. Le texte est gardé.`);
    charger(q);
  });
  const purger = () => faire(async () => {
    const r = await api<{ freed: number; count: number }>("/api/history/purge-audio", { method: "POST", json: { days: jours } });
    setLiberer(false);
    setAvis(r.count ? `Audio supprimé pour ${r.count} transcription${r.count > 1 ? "s" : ""} : ${taille(r.freed)} libérés. Les textes sont gardés.` : "Aucun audio à supprimer pour cette période.");
    charger(q);
  });
  const limite = Date.now() - jours * 86400000;
  const aPurger = (sessions ?? []).filter((s) => !s.interrupted && s.audio && !s.current && new Date(s.started ?? dateDepuisId(s.id)).getTime() < limite);

  const renommer = (s: SessionPassee, titre: string) => faire(async () => {
    setRenomme(null);
    if (titre.trim() === (s.title || titreParDefaut(s))) return;
    const r = await api<{ title: string }>(`/api/history/${s.id}/title`, { method: "PUT", json: { title: titre } });
    setSessions((avant) => avant && avant.map((x) => (x.id === s.id ? { ...x, title: r.title } : x)));
  });

  const visibles = (sessions ?? []).filter((s) => filtre === "tout" || (filtre === "intervenants" ? s.diarized : s.kind === filtre && !s.interrupted)
    || (filtre === "live" && s.interrupted));

  return (
    <div className="mx-auto flex w-full max-w-[1040px] flex-col gap-5">
      <div className="nn-page-head">
        <div>
          <h1 className="nn-page-title">Mes transcriptions</h1>
          <p className="nn-page-subtitle">Vos transcriptions, enregistrées sur cet ordinateur.</p>
        </div>
      </div>
      {place && place.count > 0 && (
        <div className="-mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-muted">
          <span>{place.count} transcription{place.count > 1 ? "s" : ""} · {taille(place.size)} sur ce poste{place.audio_size ? `, dont ${taille(place.audio_size)} d'audio` : ""}</span>
          {place.audio_size > 0 && (
            <button type="button" className="border-0 bg-transparent p-0 text-[13px] font-medium text-accent underline" aria-expanded={liberer}
              aria-controls="liberer" onClick={() => setLiberer(!liberer)}>Libérer de la place…</button>
          )}
        </div>
      )}
      {liberer && (
        <section id="liberer" aria-labelledby="liberer-titre" className="nn-card flex flex-col gap-3 px-5 py-4">
          <h2 id="liberer-titre" className="m-0 text-[15px] font-bold text-ink">Libérer de la place</h2>
          <p className="m-0 text-[13px] leading-snug text-ink-muted">
            L'audio prend presque toute la place (environ 115 Mo par heure). En le supprimant, vous gardez le texte, les noms des intervenants,
            les titres et les moments marqués ; vous ne pourrez plus réécouter la session ni relancer l'identification des intervenants.
          </p>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label htmlFor="jours" className="text-ink-body">Supprimer l'audio des transcriptions de plus de</label>
            <select id="jours" className="nn-input h-9 w-auto" value={jours} onChange={(e) => setJours(Number(e.target.value))}>
              {[7, 30, 90, 180, 365].map((j) => <option key={j} value={j}>{j < 365 ? `${j} jours` : "1 an"}</option>)}
            </select>
            <span className="text-ink-muted" role="status">
              {aPurger.length ? `${aPurger.length} transcription${aPurger.length > 1 ? "s" : ""} · ${taille(aPurger.reduce((n, x) => n + x.audio_size, 0))} libérés` : "aucune transcription concernée"}
            </span>
          </div>
          <div className="flex gap-2">
            <button type="button" className="nn-btn nn-btn-primary" disabled={!aPurger.length} onClick={purger}>Supprimer l'audio</button>
            <button type="button" className="nn-btn nn-btn-secondary" onClick={() => setLiberer(false)}>Annuler</button>
          </div>
        </section>
      )}
      {avis && (
        <p role="status" className="m-0 flex items-center gap-3 rounded border border-line bg-surface-2 px-4 py-2.5 text-sm text-ink-body">
          {avis}<button type="button" className="nn-icon-btn ml-auto h-7 w-7" aria-label="Fermer le message" onClick={() => setAvis("")}>×</button>
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex h-11 flex-[1_1_360px] items-center gap-2 rounded border border-line-strong bg-surface px-3 focus-within:border-accent focus-within:ring-1 focus-within:ring-accent">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="text-ink-subtle" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></svg>
          <input type="search" aria-label="Rechercher dans toutes les transcriptions" placeholder="Rechercher un mot, un nom, une décision…"
            className="min-w-0 flex-1 border-0 bg-transparent text-sm text-ink outline-none" value={q} onChange={(e) => setQ(e.target.value)} />
          {q.trim() && sessions && (
            <span className="whitespace-nowrap text-[12px] text-ink-subtle" role="status">
              {sessions.length ? `dans ${sessions.length} session${sessions.length > 1 ? "s" : ""}` : "aucun résultat"}
            </span>
          )}
        </label>
        <div role="group" aria-label="Filtrer" className="nn-segmented">
          {FILTRES.map((f) => <button key={f.id} type="button" aria-pressed={filtre === f.id} onClick={() => setFiltre(f.id)}>{f.label}</button>)}
        </div>
      </div>

      {erreur && <Alerte>{erreur}</Alerte>}
      {!sessions ? <p className="m-0 text-sm text-ink-muted">Chargement…</p> : visibles.length === 0 ? (
        <p className="m-0 rounded-lg border border-dashed border-line-dashed px-6 py-10 text-center text-sm text-ink-muted">
          {q.trim() ? `Aucune transcription ne contient « ${q.trim()} ».` : sessions.length ? "Aucune transcription dans ce filtre." : "Aucune transcription pour l'instant."}
        </p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
          {visibles.map((s) => {
            const titre = s.title || titreParDefaut(s);
            const type = s.kind === "file" ? (s.name && VIDEO.test(s.name) ? "Fichier vidéo" : "Fichier audio") : "En direct";
            const meta = [dateSession(s.started ?? dateDepuisId(s.id)), type, s.duration ? dureeCourte(s.duration) : "",
              s.marks ? `${s.marks} moment${s.marks > 1 ? "s" : ""} marqué${s.marks > 1 ? "s" : ""}` : "",
              !s.diarized && s.kind === "file" ? "sans intervenants" : "", !s.audio ? "sans audio" : ""].filter(Boolean).join(" · ");
            return (
              <li key={s.id} className={`nn-card flex flex-wrap items-start gap-5 px-5 py-4 ${s.interrupted ? "border-warning-line" : ""}`}>
                <div className="flex min-w-0 flex-[1_1_480px] flex-col gap-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    {renomme === s.id ? (
                      <input autoFocus aria-label="Titre de la session" className="nn-input h-9 max-w-[420px] text-[15px] font-medium" defaultValue={titre} maxLength={120}
                        onBlur={(e) => renommer(s, e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") renommer(s, e.currentTarget.value); if (e.key === "Escape") setRenomme(null); }} />
                    ) : (
                      <>
                        <h2 className="m-0 text-[16px] font-medium text-ink">{titre}</h2>
                        {!s.interrupted && (
                          <button type="button" className="nn-icon-btn h-7 w-7" aria-label={`Renommer « ${titre} »`} onClick={() => setRenomme(s.id)}><Crayon /></button>
                        )}
                      </>
                    )}
                    {s.interrupted && <span className="nn-chip nn-chip-warning">Interrompue</span>}
                    {s.current && <span className="nn-chip">Ouverte</span>}
                  </div>
                  {s.interrupted ? (
                    <span className="text-[13px] text-ink-muted">L'application s'est fermée pendant l'enregistrement. {conserve(s)}</span>
                  ) : <span className="text-[13px] text-ink-muted">{meta}</span>}
                  {s.excerpt && (s.excerpt.before || s.excerpt.match || s.excerpt.after) && (
                    <p className={`m-0 mt-0.5 text-sm ${s.excerpt.match ? "text-ink-body" : "text-ink-muted"}`}>
                      « {s.excerpt.before}{s.excerpt.match && <mark className="rounded-sm bg-warning-soft px-0.5 text-ink">{s.excerpt.match}</mark>}{s.excerpt.after} »
                      {s.matches > 1 && <span className="ml-1.5 text-[12px] text-ink-subtle">({s.matches} fois)</span>}
                    </p>
                  )}
                  {(s.speakers.length > 0 || s.unnamed > 0) && (
                    <div className="flex flex-wrap gap-1.5" aria-label="Intervenants">
                      {s.speakers.map((n) => <span key={n} className="nn-chip">{n}</span>)}
                      {s.unnamed > 0 && <span className="rounded-full bg-surface-3 px-2.5 py-0.5 text-[12px] font-medium text-ink-body">+{s.unnamed} sans nom</span>}
                    </div>
                  )}
                </div>
                {sansAudio === s.id ? (
                  <div className="flex max-w-[360px] flex-wrap items-center gap-2" role="group" aria-label="Confirmer la suppression de l'audio">
                    <span className="text-[13px] text-ink-body">Supprimer l'audio ({taille(s.audio_size)}) ? Le texte est gardé, mais on ne pourra plus réécouter.</span>
                    <button type="button" className="nn-btn nn-btn-secondary" onClick={() => supprimerAudio(s.id)}>Supprimer l'audio</button>
                    <button type="button" className="nn-btn nn-btn-secondary" onClick={() => setSansAudio(null)}>Annuler</button>
                  </div>
                ) : aSupprimer === s.id ? (
                  <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Confirmer la suppression">
                    <span className="text-[13px] text-danger-text">Supprimer le texte et l'audio ?</span>
                    <button type="button" className="nn-btn nn-btn-secondary" onClick={() => supprimer(s.id)}>Supprimer</button>
                    <button type="button" className="nn-btn nn-btn-secondary" onClick={() => setASupprimer(null)}>Annuler</button>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    {!s.interrupted ? <button type="button" className="nn-btn nn-btn-primary" onClick={() => ouvrir(s.id)}>Rouvrir</button>
                      : s.recoverable ? <button type="button" className="nn-btn nn-btn-primary" onClick={() => ouvrir(s.id, true)}>Récupérer le texte</button> : null}
                    <div className="relative" data-menu-session>
                      <button type="button" className="nn-btn nn-btn-secondary w-10 px-0" aria-label={`Plus d'actions pour « ${titre} »`} aria-haspopup="menu"
                        aria-expanded={menu === s.id} onClick={() => setMenu(menu === s.id ? null : s.id)}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" /></svg>
                      </button>
                      {menu === s.id && (
                        <div role="menu" className="absolute right-0 top-11 z-20 w-[260px] rounded-md border border-line bg-surface p-1.5 shadow-lg">
                          <button type="button" role="menuitem" autoFocus className="block w-full rounded border-0 bg-transparent px-2.5 py-2 text-left text-sm text-ink hover:bg-surface-3 focus:bg-surface-3 focus:outline-none"
                            onClick={() => { setMenu(null); dossier(s.id); }}>Ouvrir le dossier</button>
                          {!s.interrupted && s.audio && (
                            <button type="button" role="menuitem" className="block w-full rounded border-0 bg-transparent px-2.5 py-2 text-left text-sm text-ink hover:bg-surface-3 focus:bg-surface-3 focus:outline-none"
                              onClick={() => { setMenu(null); setSansAudio(s.id); }}>Supprimer l'audio, garder le texte</button>
                          )}
                          {!s.current && (
                            <button type="button" role="menuitem" className="block w-full rounded border-0 bg-transparent px-2.5 py-2 text-left text-sm text-danger-text hover:bg-surface-3 focus:bg-surface-3 focus:outline-none"
                              onClick={() => { setMenu(null); setASupprimer(s.id); }}>Supprimer…</button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
