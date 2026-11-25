import React from "react";
import { duree, hms } from "../format";
import type { AvancementFichier, Marque, Segment, SessionState } from "../types";
import { Progression } from "./ui";

const LIGNES_AFFICHEES = 400;
const SVG = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "currentColor", "aria-hidden": true } as const;
export const IconeLecture = () => <svg {...SVG}><path d="M7 4.5v15l12.5-7.5z" /></svg>;
export const IconePause = () => <svg {...SVG}><rect x="6" y="4.5" width="4" height="15" rx="1" /><rect x="14" y="4.5" width="4" height="15" rx="1" /></svg>;
export const IconeArret = () => <svg {...SVG}><rect x="5.5" y="5.5" width="13" height="13" rx="2" /></svg>;
export const IconeMarque = ({ taille = 16 }: { taille?: number }) => (
  <svg width={taille} height={taille} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 3h12v18l-6-4-6 4z" /></svg>
);

/** Index des phrases marquées : pour chaque moment, la dernière phrase commencée avant lui. */
export function phrasesMarquees(segments: Segment[], marques: Marque[]): Map<number, Marque> {
  const out = new Map<number, Marque>();
  for (const m of marques) {
    let i = -1;
    for (let k = 0; k < segments.length && segments[k].start <= m.t + 0.5; k++) i = k;
    if (i >= 0 && !out.has(i)) out.set(i, m);
  }
  return out;
}

/** Vu-mètre en barres, mis à jour plusieurs fois par seconde. */
const VuMetre: React.FC<{ niveau: number }> = ({ niveau }) => {
  const pct = Math.round(niveau * 100);
  return (
    <span role="meter" aria-label="Niveau du son reçu" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="flex h-7 items-center gap-[3px]">
      {Array.from({ length: 10 }, (_, i) => (
        <span key={i} className={`w-1 rounded-sm transition-colors duration-100 ${niveau >= (i + 1) / 11 ? (i >= 9 ? "bg-warning" : "bg-success") : "bg-line-strong"}`}
          style={{ height: 8 + Math.round(Math.sin(((i + 1) / 11) * Math.PI) * 18) }} />
      ))}
    </span>
  );
};

interface Props {
  etat: SessionState;
  segments: Segment[];
  niveau: number | null;
  resume: string;
  pauseOuReprise: () => void;
  arreter: () => void;
  marquer: () => void;
  enRetard: boolean;
}

/**
 * Pendant l'enregistrement (ou la transcription d'un fichier) : mode concentration. Les réglages disparaissent,
 * le texte prend toute la place ; la barre du haut reste visible (chrono, niveau, Marquer, Pause, Arrêter).
 */
export const EnDirect: React.FC<Props> = ({ etat, segments, niveau, resume, pauseOuReprise, arreter, marquer, enRetard }) => {
  const zone = React.useRef<HTMLDivElement>(null);
  const [colle, setColle] = React.useState(true); // reste collé en bas, sauf si la personne remonte lire
  const [horodatage, setHorodatage] = React.useState(true);
  const fichier = etat.kind === "file";
  const enCours = !etat.stopping;
  const visibles = segments.length > LIGNES_AFFICHEES ? segments.slice(-LIGNES_AFFICHEES) : segments;
  const decalage = segments.length - visibles.length;
  const marquees = React.useMemo(() => phrasesMarquees(segments, etat.marks), [segments, etat.marks]);

  React.useEffect(() => {
    if (colle) window.scrollTo({ top: document.documentElement.scrollHeight });
  }, [segments, colle]);
  React.useEffect(() => {
    const suivre = () => setColle(window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 80);
    window.addEventListener("scroll", suivre, { passive: true });
    return () => window.removeEventListener("scroll", suivre);
  }, []);

  const pastille = etat.paused ? { texte: "En pause", point: "bg-warning", couleur: "text-warning-text" }
    : etat.stopping ? { texte: "Arrêt…", point: "bg-ink-subtle", couleur: "text-ink-muted" }
    : { texte: fichier ? "Transcription" : "Enregistrement", point: "bg-danger animate-pulse", couleur: "text-danger-text" };

  return (
    <div className="flex flex-col gap-6">
      <div id="commandes" tabIndex={-1} role="region" aria-label="Commandes de l'enregistrement"
        className="sticky top-[64px] z-10 -mx-6 border-b border-line bg-surface px-6 py-3.5 shadow-sm outline-none">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center gap-x-5 gap-y-3">
          <span className="flex items-center gap-2.5" role="status">
            <span className={`h-3 w-3 rounded-full ${pastille.point}`} aria-hidden="true" />
            <span className={`text-[13px] font-medium ${pastille.couleur}`}>{pastille.texte}</span>
          </span>
          {fichier && etat.file ? (
            <ProgressionFichier etat={etat} avancement={etat.file} />
          ) : (
            <span className="font-mono text-[30px] font-medium tabular-nums tracking-wide text-ink" aria-label={`Durée enregistrée : ${hms(etat.duration)}`}>{hms(etat.duration)}</span>
          )}
          {!fichier && niveau !== null && !etat.paused && <VuMetre niveau={niveau} />}
          {resume && <span className="text-[13px] text-ink-subtle">{resume}</span>}
          {enRetard && <span className="nn-chip nn-chip-warning" title="Le texte arrivera après la fin de l'enregistrement : rien n'est perdu.">La transcription prend du retard</span>}
          <span className="ml-auto flex flex-wrap gap-2">
            {!fichier && (
              <button type="button" className="nn-btn nn-btn-secondary h-11 gap-2" onClick={marquer} disabled={!enCours || etat.paused}
                aria-keyshortcuts="M" title="Épingle une décision ou une action, retrouvée dans le résultat">
                <IconeMarque /> Marquer ce moment <kbd className="rounded border border-line-strong px-1.5 font-sans text-[12px] text-ink-subtle">M</kbd>
              </button>
            )}
            <button type="button" className="nn-btn nn-btn-secondary h-11 gap-2" disabled={!enCours} onClick={pauseOuReprise} aria-keyshortcuts="Space" title="Raccourci : Espace">
              {etat.paused ? <><IconeLecture /> Reprendre</> : <><IconePause /> Pause</>}
            </button>
            <button type="button" className="nn-btn nn-btn-primary h-11 gap-2" disabled={!enCours} onClick={arreter} aria-keyshortcuts="Escape" title="Raccourci : Échap">
              <IconeArret /> Arrêter
            </button>
          </span>
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-[1180px] flex-wrap items-start gap-8">
        <article className="mx-auto min-w-0 max-w-[760px] flex-[999_1_560px]" aria-labelledby="texte-direct">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 id="texte-direct" className="m-0 text-[19px] font-bold text-ink">{fichier ? "Transcription" : "En direct"}</h2>
            <label className="nn-check text-sm"><input type="checkbox" checked={horodatage} onChange={(e) => setHorodatage(e.target.checked)} /> <span>Horaires</span></label>
          </div>
          {etat.paused && (
            <p role="status" className="m-0 mb-4 rounded border border-line bg-surface-2 px-4 py-3 text-sm text-ink-body">
              {fichier ? "En pause : « Reprendre » continue la transcription là où elle s'est arrêtée." : "En pause : rien n'est enregistré. « Reprendre » continue le même enregistrement."}
            </p>
          )}
          {decalage > 0 && <p className="m-0 mb-3 text-[13px] text-ink-muted">Seules les {LIGNES_AFFICHEES} dernières phrases sont affichées ; tout le texte sera là à la fin.</p>}
          <div ref={zone} aria-label="Transcription en direct" aria-live="off" className="flex flex-col gap-[18px] text-[16px] leading-[26px] text-ink-body">
            {visibles.length === 0 ? (
              <p className="m-0 rounded-lg border border-dashed border-line-dashed px-6 py-10 text-center text-sm text-ink-muted">
                Le texte apparaît ici quelques secondes après qu'on a parlé…
              </p>
            ) : visibles.map((s, k) => {
              const i = decalage + k;
              const m = marquees.get(i);
              return (
                <div key={i} className={`grid gap-3 ${horodatage ? "grid-cols-[64px_1fr]" : "grid-cols-1"}`}>
                  {horodatage && <span className="select-none pt-0.5 font-mono text-xs text-ink-subtle">{hms(s.start)}</span>}
                  {m ? (
                    <div className="rounded-md bg-accent-soft px-3.5 py-3">
                      <span className="mb-1 flex items-center gap-1.5 text-[12px] font-medium text-accent-ink"><IconeMarque taille={13} /> Moment marqué</span>
                      <div>{s.speaker && <strong className="font-semibold">{s.speaker} : </strong>}{s.text}</div>
                    </div>
                  ) : (
                    <span>{s.speaker && <strong className="font-semibold">{s.speaker} : </strong>}{s.text}</span>
                  )}
                </div>
              );
            })}
            {etat.stopping && <p role="status" className="m-0 text-sm text-ink-muted">{fichier ? "Arrêt demandé : le texte déjà transcrit est conservé." : "Enregistrement arrêté. Transcription des dernières secondes…"}</p>}
          </div>
          {!colle && (
            <div className="sticky bottom-6 mt-6 flex justify-center">
              <button type="button" className="nn-btn nn-btn-secondary gap-2 rounded-full shadow-sm" onClick={() => { setColle(true); window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" }); }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6" /></svg>
                Revenir au direct
              </button>
            </div>
          )}
        </article>

        {!fichier && (
          <aside className="flex max-w-[300px] flex-[1_1_260px] flex-col gap-3 lg:sticky lg:top-[150px]" aria-label="Moments marqués">
            <section className="nn-card p-5">
              <h2 className="m-0 mb-2.5 text-[15px] font-bold text-ink">Moments marqués</h2>
              {etat.marks.length === 0 ? (
                <p className="m-0 text-[13px] leading-snug text-ink-muted">Appuyez sur <kbd className="rounded border border-line-strong px-1 font-sans">M</kbd> quand une décision ou une action est prise : vous la retrouverez dans le résultat.</p>
              ) : (
                <ul className="m-0 flex list-none flex-col p-0">
                  {etat.marks.map((m, i) => (
                    <li key={i} className="grid grid-cols-[64px_1fr] gap-2 py-1.5 text-[13px] leading-[18px] text-ink-body">
                      <span className="font-mono text-ink-subtle">{hms(m.t)}</span><span>{m.label || "…"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </aside>
        )}
      </div>
    </div>
  );
};

const ProgressionFichier: React.FC<{ etat: SessionState; avancement: AvancementFichier }> = ({ etat, avancement: a }) => {
  const pct = a.fraction === null ? null : Math.round(a.fraction * 100);
  const etape = a.phase === "decoding" ? "Lecture du fichier" : a.phase === "transcribing" ? "Transcription" : "Terminé";
  const details = [pct !== null && a.phase !== "done" ? `${pct} %` : "", etat.paused ? "en pause" : a.eta !== null ? `reste environ ${duree(a.eta)}` : ""]
    .filter(Boolean).join(" · ");
  return (
    <div className="flex min-w-[240px] flex-[1_1_320px] flex-col gap-1">
      <span className="truncate text-sm font-medium text-ink" title={a.name}>{a.name}{a.media_duration ? ` · ${hms(a.media_duration)}` : ""}</span>
      <Progression fraction={a.fraction} libelle={`${etape}${details ? ` · ${details}` : ""}`} />
    </div>
  );
};
