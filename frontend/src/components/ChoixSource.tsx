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
