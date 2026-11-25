import React from "react";
import type { AppAudio, Applications, Settings, Source } from "../types";

/** Ce que la personne choisit d'écouter ; se traduit en `source` + `app` côté serveur. */
export type Ecoute = "voix" | "app" | "tout" | "voix_app" | "voix_tout";

export function ecouteDe(r: Pick<Settings, "source" | "app">): Ecoute {
  if (r.source === "microphone") return "voix";
  if (r.source === "system") return r.app ? "app" : "tout";
  return r.app ? "voix_app" : "voix_tout";
}

export const avecApplication = (e: Ecoute) => e === "app" || e === "voix_app";

const ICONES: Record<string, React.ReactNode> = {
  voix: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>,
  app: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8M12 17v4" /><rect x="7" y="8" width="5" height="5" rx="1" /></>,
  tout: <><path d="M11 5 6 9H3v6h3l5 4z" /><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" /></>,
  voix_app: <><rect x="2" y="5" width="13" height="10" rx="2" /><path d="M15 9l5-3v8l-5-3M6 19h6" /></>,
};

interface Option { id: Ecoute; titre: string; detail: string; icone: string }
const OPTIONS: Option[] = [
  { id: "voix", titre: "Ma voix", detail: "Le micro seul : dictée, réunion dans la même pièce", icone: "voix" },
  { id: "app", titre: "Une application", detail: "Seulement le son de Teams, Zoom, un navigateur…", icone: "app" },
  { id: "tout", titre: "Tout le son de l'ordinateur", detail: "Ce qui sort par vos haut-parleurs ou votre casque", icone: "tout" },
  { id: "voix_app", titre: "Ma voix + une application", detail: "Pour une visio : vous et les autres participants", icone: "voix_app" },
];

interface Props {
  ecoute: Ecoute;
  changer: (e: Ecoute) => void;
  applications: Applications | null;
  /** Son du PC captable (Windows, soundcard présent). */
  systeme: boolean;
  /** Raison affichée quand le son du PC n'est pas captable. */
  raisonSysteme: string;
  bloque: boolean;
}

/** « Qu'est-ce qu'on écoute ? » : quatre réponses en groupe de boutons radio (flèches haut / bas). */
export const ChoixSource: React.FC<Props> = ({ ecoute, changer, applications, systeme, raisonSysteme, bloque }) => {
  const appOk = systeme && (applications?.supported ?? false);
  const recommande = appOk && !!applications?.recommended;
  const actif = ecoute === "voix_tout" ? "tout" : ecoute;
  const dispo = (o: Option) => o.id === "voix" || (o.id === "tout" ? systeme : appOk);
  const boutons = React.useRef<(HTMLButtonElement | null)[]>([]);

  const clavier = (e: React.KeyboardEvent, i: number) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key) || bloque) return;
    e.preventDefault();
    const pas = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1;
    for (let k = 1; k <= OPTIONS.length; k++) {
      const j = (i + pas * k + OPTIONS.length * 2) % OPTIONS.length;
      if (dispo(OPTIONS[j])) { changer(OPTIONS[j].id); boutons.current[j]?.focus(); return; }
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <span id="ecoute-titre" className="text-sm font-medium text-ink">Qu'est-ce qu'on écoute ?</span>
      <div role="radiogroup" aria-labelledby="ecoute-titre" className="flex flex-col gap-1.5">
        {OPTIONS.map((o, i) => {
          const choisi = actif === o.id;
          const ok = dispo(o);
          return (
            <button key={o.id} ref={(el) => { boutons.current[i] = el; }} type="button" role="radio" aria-checked={choisi}
              aria-labelledby={`ecoute-${o.id}`} aria-describedby={`ecoute-${o.id}-detail`} tabIndex={choisi ? 0 : -1} disabled={!ok || (bloque && !choisi)}
              onClick={() => !bloque && changer(o.id === "tout" && ecoute === "voix_tout" ? "voix_tout" : o.id)} onKeyDown={(e) => clavier(e, i)}
              className={`flex min-w-0 items-center gap-3 rounded-md border px-3 py-2.5 text-left transition-colors
                focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus
                ${choisi ? "border-accent bg-surface shadow-sm ring-1 ring-accent" : "border-line bg-surface hover:bg-surface-2"}
                disabled:cursor-not-allowed disabled:opacity-50`}>
              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${choisi ? "bg-accent-soft text-accent" : "bg-surface-3 text-ink-subtle"}`}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONES[o.icone]}</svg>
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="flex flex-wrap items-center gap-x-2 text-[15px] font-semibold leading-tight text-ink">
                  <span id={`ecoute-${o.id}`}>{o.titre}</span>
                  {o.id === "voix_app" && recommande && <span className="nn-chip text-[12px]">Recommandé</span>}
                </span>
                <span id={`ecoute-${o.id}-detail`} className="mt-0.5 text-[13px] leading-snug text-ink-muted">{o.detail}</span>
              </span>
            </button>
          );
        })}
      </div>
      {!systeme && raisonSysteme && <p className="m-0 text-[13px] leading-snug text-ink-muted">{raisonSysteme}</p>}
      {systeme && applications && !applications.supported && applications.reason && (
        <p className="m-0 rounded border border-warning-line bg-warning-soft px-3 py-2.5 text-[13px] leading-snug text-warning-text">{applications.reason}</p>
      )}
      {actif === "tout" && (
        <label className="nn-check text-sm">
          <input type="checkbox" checked={ecoute === "voix_tout"} disabled={bloque}
            onChange={(e) => changer(e.target.checked ? "voix_tout" : "tout")} />
          <span>Ajouter aussi ma voix (micro)</span>
        </label>
      )}
    </div>
  );
};

const TEINTES = ["bg-primary", "bg-accent-muted", "bg-ink-muted", "bg-ink-body"];

const Niveau: React.FC<{ niveau: number }> = ({ niveau }) => {
  const barres = [0.02, 0.08, 0.2, 0.4];
  return (
    <span className="flex h-[18px] items-end gap-[3px]" aria-hidden="true">
      {barres.map((seuil, i) => (
        <span key={i} className={`w-1 rounded-sm ${niveau >= seuil ? "bg-success" : "bg-line-strong"}`} style={{ height: 6 + i * 4 }} />
      ))}
    </span>
  );
};

/** Liste des applications ouvertes qui utilisent le son ; celles qui en font en ce moment d'abord. */
export const ListeApplications: React.FC<{
  applications: Applications | null;
  choisie: string;
  nomChoisie: string;
  choisir: (a: AppAudio) => void;
  bloque: boolean;
}> = ({ applications, choisie, nomChoisie, choisir, bloque }) => {
  const apps = applications?.apps ?? [];
  const absente = !!choisie && applications !== null && !apps.some((a) => a.exe === choisie);
  return (
    <div className="flex flex-col gap-2">
      <span id="appli-titre" className="text-sm font-medium text-ink">Quelle application ?</span>
      {applications === null ? (
        <span className="text-[13px] text-ink-muted">Recherche des applications…</span>
      ) : apps.length === 0 ? (
        <p className="m-0 text-[13px] leading-snug text-ink-muted">
          Aucune application n'utilise le son pour l'instant. Lancez la réunion ou la vidéo : elle apparaîtra ici d'elle-même.
        </p>
      ) : (
        <div role="radiogroup" aria-labelledby="appli-titre" className="flex flex-col gap-1.5">
          {apps.map((a, i) => {
            const coche = a.exe === choisie;
            return (
              <label key={a.exe} className={`flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 ${coche ? "border-accent bg-accent-softer ring-1 ring-accent" : "border-line"} ${bloque ? "cursor-not-allowed opacity-60" : ""}`}>
                <input type="radio" name="application" className="m-0 h-[18px] w-[18px] accent-[var(--nn-primary)]"
                  checked={coche} disabled={bloque} onChange={() => choisir(a)} />
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-sm font-bold text-white ${TEINTES[i % TEINTES.length]}`} aria-hidden="true">
                  {a.name.charAt(0).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-ink">{a.name}</span>
                  <span className="block text-[12px] text-ink-muted">{a.active ? "Fait du son" : "Ouvert, silencieux pour l'instant"}</span>
                </span>
                {a.active && <Niveau niveau={a.level} />}
              </label>
            );
          })}
        </div>
      )}
      {absente && (
        <p role="status" className="m-0 rounded border border-warning-line bg-warning-soft px-3 py-2.5 text-[13px] leading-snug text-warning-text">
          {nomChoisie || "L'application choisie"} n'est pas ouvert pour l'instant. Lancez-le (ou la réunion), il apparaîtra dans la liste.
        </p>
      )}
      <span className="text-[13px] leading-snug text-ink-muted">Choisir un navigateur capte tous ses onglets.</span>
    </div>
  );
};

/** Source serveur correspondant au choix. */
export function versSource(e: Ecoute): Source {
  return e === "voix" ? "microphone" : e === "app" || e === "tout" ? "system" : "mixed";
}
