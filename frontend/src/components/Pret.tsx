import React from "react";
import type { Acceleration, AppAudio, Applications, Capabilities, Cuda, Devices, ModeleEquipe, Settings, Verification } from "../types";
import { type Ecoute, ListeApplications, avecApplication, ecouteDe, versSource } from "./ChoixSource";
import { Champ, Verifie } from "./ui";

export interface MesureSource { level: number; heard: boolean; error: string }
export interface Apercu { active: boolean; voix?: MesureSource; autre?: MesureSource; erreur?: string }

const LANGUES: Record<Settings["language"], string> = { fr: "Français", en: "Anglais", auto: "Détection automatique" };
const ACCELERATIONS: { id: Acceleration; label: string }[] = [
  { id: "auto", label: "Automatique" },
  { id: "gpu", label: "GPU NVIDIA" },
  { id: "cpu", label: "Processeur" },
];
const CHIPS: { id: Ecoute; label: string }[] = [
  { id: "voix", label: "Ma voix" },
  { id: "app", label: "Une application" },
  { id: "tout", label: "Tout le son du PC" },
  { id: "voix_app", label: "Ma voix + une application" },
];
const lien = "self-start border-0 bg-transparent p-0 text-[13px] font-medium text-accent underline disabled:opacity-60";

/** Petites barres de niveau ; vertes quand le son est assez fort pour être transcrit. */
export const Barres: React.FC<{ niveau: number; nb?: number }> = ({ niveau, nb = 6 }) => (
  <span className="flex h-[18px] items-end gap-[3px]" aria-hidden="true">
    {Array.from({ length: nb }, (_, i) => (
      <span key={i} className={`w-[5px] rounded-sm transition-colors duration-100 ${niveau >= (i + 1) / (nb + 1) ? "bg-success" : "bg-line-strong"}`}
        style={{ height: 6 + Math.round((12 * i) / (nb - 1)) }} />
    ))}
  </span>
);

/** Une ligne de « Prêt ? » : libellé, valeur, et un éditeur qui s'ouvre sur place avec « Changer ». */
const Ligne: React.FC<{
  id: string; label: string; children: React.ReactNode; editeur?: React.ReactNode; action?: string; bloque?: boolean;
  ouvert?: boolean; basculer?: () => void; fin?: React.ReactNode;
}> = ({ id, label, children, editeur, action = "Changer", bloque, ouvert, basculer, fin }) => (
  <div className="flex flex-col gap-2 border-b border-line py-3.5 last:border-b-0">
    <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2">
      <span id={`${id}-label`} className="w-[132px] shrink-0 text-[13px] text-ink-muted">{label}</span>
      <div className="flex min-w-0 flex-[1_1_220px] flex-wrap items-center gap-2">{children}</div>
      {fin}
      {editeur && basculer && (
        <button type="button" className="nn-btn nn-btn-secondary h-9 px-3" aria-expanded={ouvert} aria-controls={`${id}-editeur`}
          aria-describedby={`${id}-label`} disabled={bloque} onClick={basculer}>{ouvert ? "Fermer" : action}</button>
      )}
    </div>
    {editeur && ouvert && <div id={`${id}-editeur`} className="pl-0 sm:pl-[146px]">{editeur}</div>}
  </div>
);

const EtatSon: React.FC<{ mesure?: MesureSource; ok: string; attente: string }> = ({ mesure, ok, attente }) => {
  if (!mesure) return <span className="text-[12px] text-ink-subtle">Vérification…</span>;
  if (mesure.error) return <span className="nn-chip nn-chip-warning">Source indisponible</span>;
  return (
    <span className="flex items-center gap-2">
      <Barres niveau={mesure.level} />
      {mesure.heard ? <span className="nn-chip nn-chip-success">✓ {ok}</span> : <span className="text-[12px] text-ink-subtle">{attente}</span>}
    </span>
  );
};

interface Props {
  reglages: Settings;
  regler: <K extends keyof Settings>(cle: K, valeur: Settings[K]) => void;
  capacites: Capabilities | null;
  peripheriques: Devices | null;
  applications: Applications | null;
  apercu: Apercu | null;
  actualiser: () => void;
  pipeline: Verification | null;
  modeleOk: boolean;
  blocModele: React.ReactNode;
  occupe: boolean;
}

/** « Prêt ? » : une ligne par sujet, modifiable sur place ; la source se vérifie avant de démarrer. */
export const Pret: React.FC<Props> = ({ reglages: r, regler, capacites, peripheriques, applications, apercu, actualiser, pipeline, modeleOk, blocModele, occupe }) => {
  const [ouvert, setOuvert] = React.useState<string | null>(null);
  const basculer = (id: string) => () => setOuvert((o) => (o === id ? null : id));
  const fichier = r.mode === "file";
  const ecoute = ecouteDe(r);
  const systemeOk = capacites?.system_audio ?? false;
  const appOk = systemeOk && (applications?.supported ?? false);
  const entrees = peripheriques?.inputs ?? [];
  const sorties = peripheriques?.outputs ?? [];
  const micChoisi = entrees.find((d) => d.name === r.input_device) ?? entrees[0];
  const apps = applications?.apps ?? [];
  const app = apps.find((a) => a.exe === r.app);
  const diarisationDispo = capacites?.diarization !== false;
  const chips = React.useRef<(HTMLButtonElement | null)[]>([]);

  const choisirApp = (a: AppAudio) => { regler("app", a.exe); regler("app_name", a.name); setOuvert(null); };
  const changerEcoute = (e: Ecoute) => {
    regler("source", versSource(e));
    if (!avecApplication(e)) { regler("app", ""); return; }
    if (r.app) return;
    const a = apps.find((x) => x.exe === applications?.recommended) ?? apps.find((x) => x.active) ?? apps[0];
    if (a) { regler("app", a.exe); regler("app_name", a.name); } else setOuvert("application");
  };
  const dispo = (id: Ecoute) => id === "voix" || (id === "tout" ? systemeOk : appOk);
  const clavier = (e: React.KeyboardEvent, i: number) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key) || occupe) return;
    e.preventDefault();
    const pas = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1;
    for (let k = 1; k <= CHIPS.length; k++) {
      const j = (i + pas * k + CHIPS.length * 2) % CHIPS.length;
      if (dispo(CHIPS[j].id)) { changerEcoute(CHIPS[j].id); chips.current[j]?.focus(); return; }
    }
  };
  const actif = ecoute === "voix_tout" ? "tout" : ecoute;
  const recommande = appOk && !!applications?.recommended;

  return (
    <div className="flex flex-col">
      {!fichier && (
        <>
          <Ligne id="ecoute" label="On écoute">
            <div role="radiogroup" aria-labelledby="ecoute-label" className="flex flex-wrap gap-1.5">
              {CHIPS.map((c, i) => {
                const coche = actif === c.id;
                return (
                  <button key={c.id} ref={(el) => { chips.current[i] = el; }} type="button" role="radio" aria-checked={coche}
                    tabIndex={coche ? 0 : -1} disabled={!dispo(c.id) || (occupe && !coche)}
                    onClick={() => changerEcoute(c.id === "tout" && ecoute === "voix_tout" ? "voix_tout" : c.id)} onKeyDown={(e) => clavier(e, i)}
                    className={`h-8 rounded-md border px-3 text-[13px] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus
                      disabled:cursor-not-allowed disabled:opacity-50
                      ${coche ? "border-accent bg-accent-soft font-medium text-accent-ink" : "border-line-strong bg-surface text-ink-body hover:bg-surface-2"}`}>
                    {coche ? "✓ " : ""}{c.label}{c.id === "voix_app" && recommande && !coche ? " · recommandé" : ""}
                  </button>
                );
              })}
            </div>
          </Ligne>
          {!systemeOk && capacites && (
            <p className="m-0 -mt-1 pb-2 text-[13px] text-ink-muted sm:pl-[146px]">
              {capacites.platform === "win32" ? "Le son de l'ordinateur n'est pas disponible dans cette installation."
                : "Le son de l'ordinateur et des applications ne peut être capté que sous Windows."}
            </p>
          )}
          {systemeOk && applications && !applications.supported && applications.reason && (
            <p className="m-0 -mt-1 pb-2 text-[13px] text-warning-text sm:pl-[146px]">{applications.reason}</p>
          )}

          {avecApplication(ecoute) && (
            <Ligne id="application" label="Application" ouvert={ouvert === "application"} basculer={basculer("application")} bloque={occupe}
              editeur={<ListeApplications applications={applications} choisie={r.app} nomChoisie={r.app_name} choisir={choisirApp} bloque={occupe} />}
              fin={app && <EtatSon mesure={apercu?.autre} ok={`${app.name.split(" ").pop()} est bien capté`} attente="Pas encore de son" />}>
              {app ? (
                <>
                  <span className="flex h-[26px] w-[26px] items-center justify-center rounded-md bg-primary text-[13px] font-bold text-primary-on" aria-hidden="true">
                    {app.name.charAt(0).toUpperCase()}
                  </span>
                  <span className="font-medium text-ink">{app.name}</span>
                  {app.visio && <span className="text-[12px] text-ink-subtle">· visio détectée</span>}
                </>
              ) : (
                <span role="status" className="text-[13px] text-warning-text">
                  {r.app ? `${r.app_name || "L'application choisie"} n'est pas ouvert pour l'instant.` : "Choisissez l'application à écouter."}
                </span>
              )}
            </Ligne>
          )}

          {(ecoute === "tout" || ecoute === "voix_tout") && systemeOk && (
            <Ligne id="sortie" label="Sortie écoutée" ouvert={ouvert === "sortie"} basculer={basculer("sortie")} bloque={occupe || sorties.length === 0}
              fin={<EtatSon mesure={apercu?.autre} ok="Le son est bien capté" attente="Pas encore de son" />}
              editeur={
                <Champ id="sortie" label="Sortie où vous entendez la réunion">
                  <select id="sortie" className="nn-input max-w-[420px]" value={r.output_device || sorties[0]?.name || ""}
                    onChange={(e) => { regler("output_device", e.target.value); setOuvert(null); }}>
                    {sorties.map((s) => <option key={s.id} value={s.name}>{s.name}</option>)}
                  </select>
                </Champ>
              }>
              <span className="font-medium text-ink">{r.output_device || sorties[0]?.name || "Sortie par défaut"}</span>
            </Ligne>
          )}

          {(ecoute === "tout" || ecoute === "voix_tout") && systemeOk && (
            <label className="nn-check -mt-1 pb-2 text-sm sm:pl-[146px]">
              <input type="checkbox" checked={ecoute === "voix_tout"} disabled={occupe}
                onChange={(e) => changerEcoute(e.target.checked ? "voix_tout" : "tout")} />
              <span>Ajouter aussi ma voix (micro)</span>
            </label>
          )}

          {r.source !== "system" && (
            <Ligne id="micro" label="Microphone" ouvert={ouvert === "micro"} basculer={basculer("micro")} bloque={occupe || entrees.length === 0}
              fin={micChoisi && <EtatSon mesure={apercu?.voix} ok="On vous entend" attente="Parlez pour tester" />}
              editeur={
                <div className="flex flex-col gap-2">
                  <Champ id="micro" label="Microphone">
                    <select id="micro" className="nn-input max-w-[420px]" value={micChoisi?.name ?? ""}
                      onChange={(e) => { regler("input_device", e.target.value); setOuvert(null); }}>
                      {entrees.map((d) => <option key={d.index} value={d.name}>{d.name}</option>)}
                    </select>
                  </Champ>
                  <button type="button" className={lien} onClick={actualiser}>Actualiser la liste (casque branché à l'instant…)</button>
                </div>
              }>
              <span className="font-medium text-ink">
                {micChoisi?.name ?? (peripheriques?.input_error ? "Impossible de lister les microphones" : peripheriques ? "Aucun microphone détecté" : "…")}
              </span>
            </Ligne>
          )}
          {r.source === "mixed" && systemeOk && (
            <p className="m-0 pb-2 text-[13px] leading-snug text-ink-muted sm:pl-[146px]">Avec des haut-parleurs, le micro réentend vos interlocuteurs : un casque évite les doublons.</p>
          )}
        </>
      )}

      <Ligne id="langue" label="Langue" ouvert={ouvert === "langue"} basculer={basculer("langue")} bloque={occupe}
        editeur={
          <div role="group" aria-label="Langue parlée" className="nn-segmented">
            {(Object.keys(LANGUES) as Settings["language"][]).map((l) => (
              <button key={l} type="button" aria-pressed={r.language === l}
                onClick={() => { regler("language", l); setOuvert(null); }}>{LANGUES[l]}</button>
            ))}
          </div>
        }>
        <span className="font-medium text-ink">{LANGUES[r.language]}</span>
      </Ligne>

      <Ligne id="glossaire" label="Mots à bien reconnaître" action="Modifier" ouvert={ouvert === "glossaire"} basculer={basculer("glossaire")} bloque={occupe}
        editeur={
          <Champ id="glossaire" label="Noms propres, sigles, jargon" aide="Une liste courte et précise, séparée par des virgules.">
            <textarea id="glossaire" className="nn-input min-h-[72px] max-w-[560px] py-2" value={r.glossary}
              placeholder="Ex. Jabber, RTX A1000, nom de projet…" onChange={(e) => regler("glossary", e.target.value)} />
          </Champ>
        }>
        <span className={r.glossary.trim() ? "text-ink-body" : "text-ink-subtle"}>{r.glossary.trim() || "Aucun"}</span>
      </Ligne>

      <Ligne id="intervenants" label="Intervenants" action="Préciser" ouvert={ouvert === "intervenants"} basculer={diarisationDispo && r.diarization ? basculer("intervenants") : undefined}
        bloque={occupe}
        fin={diarisationDispo && (
          <label className="nn-check text-sm"><input type="checkbox" checked={r.diarization} disabled={occupe}
            onChange={(e) => regler("diarization", e.target.checked)} /> <span>Activé</span></label>
        )}
        editeur={
          <Champ id="locuteurs" label="Nombre d'intervenants (0 = je ne sais pas)">
            <input id="locuteurs" type="number" min={0} max={20} className="nn-input max-w-[120px]" value={r.speaker_hint}
              onChange={(e) => regler("speaker_hint", Math.max(0, Math.min(20, Math.floor(Number(e.target.value) || 0))))} />
          </Champ>
        }>
        <span className="text-ink-body">
          {!diarisationDispo ? "Non incluse dans cette installation"
            : !r.diarization ? "Non identifiés"
            : `Identifiés après l'arrêt · ${r.speaker_hint ? `${r.speaker_hint} personne${r.speaker_hint > 1 ? "s" : ""}` : "nombre inconnu"}`}
        </span>
        {diarisationDispo && r.diarization && pipeline?.valid !== true && (
          <span className="basis-full text-[13px] text-warning-text">Indiquez le dossier du modèle d'identification dans « Réglages avancés ».</span>
        )}
      </Ligne>

      {!modeleOk && (
        <div className="flex flex-col gap-2 py-3.5">
          <span className="text-[13px] text-ink-muted">Modèle de transcription</span>
          {blocModele}
        </div>
      )}
    </div>
  );
};

interface PropsAvances {
  reglages: Settings;
  regler: <K extends keyof Settings>(cle: K, valeur: Settings[K]) => void;
  capacites: Capabilities | null;
  cuda: Cuda | null;
  modeleOk: boolean;
  blocModele: React.ReactNode;
  pipeline: Verification | null;
  occupe: boolean;
}

/** Réglages techniques, repliés : moteur, modèle, calcul, blocs, silences, audio gardé, modèle d'identification. */
export const ReglagesAvances: React.FC<PropsAvances> = ({ reglages: r, regler, capacites, cuda, modeleOk, blocModele, pipeline, occupe }) => {
  const local = r.engine === "local";
  const diarisationDispo = capacites?.diarization !== false;
  return (
    <details className="group">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-sm font-medium text-accent underline">Réglages avancés…</summary>
      <div className="mt-4 flex flex-col gap-4 rounded-lg border border-line bg-surface-2 p-5">
        <Champ id="moteur" label="Moteur">
          <select id="moteur" className="nn-input" value={r.engine} disabled={occupe}
            onChange={(e) => regler("engine", e.target.value as Settings["engine"])}>
            <option value="local">Transcription réelle (Whisper)</option>
            <option value="mock">Simulation (pour essayer sans modèle)</option>
          </select>
        </Champ>
        {modeleOk && blocModele}
        {local && (
          <div className="flex flex-col gap-1.5">
            <span id="accel-label" className="text-sm font-medium text-ink">Calcul</span>
            <div className="nn-segmented self-start" role="group" aria-labelledby="accel-label">
              {ACCELERATIONS.map((a) => (
                <button key={a.id} type="button" aria-pressed={r.acceleration === a.id} disabled={occupe}
                  onClick={() => regler("acceleration", a.id)}>{a.label}</button>
              ))}
            </div>
            <span className="text-[13px] leading-snug text-ink-muted" title={cuda?.detail}>{cuda ? cuda.message : "Vérification de la carte graphique…"}</span>
            {r.acceleration === "gpu" && cuda && !cuda.ready && (
              <span role="alert" className="text-[13px] leading-snug text-warning-text">
                « GPU NVIDIA » impose la carte graphique : la transcription ne pourra pas démarrer. Choisissez « Automatique ».
              </span>
            )}
          </div>
        )}
        {r.mode !== "file" && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Champ id="chunk" label={`Durée des blocs : ${r.chunk_seconds} s`} aide="Plus court : le texte arrive plus vite ; plus long : un peu plus précis.">
              <input id="chunk" type="range" min={3} max={15} step={1} className="w-full accent-primary" value={r.chunk_seconds} disabled={occupe}
                aria-valuetext={`${r.chunk_seconds} secondes`} onChange={(e) => regler("chunk_seconds", Number(e.target.value))} />
            </Champ>
            <Champ id="recouvrement" label={`Recouvrement : ${r.overlap_seconds.toFixed(2)} s`} aide="Contexte redonné autour des coupures.">
              <input id="recouvrement" type="range" min={0} max={Math.min(2, r.chunk_seconds - 0.5)} step={0.25} className="w-full accent-primary"
                value={Math.min(r.overlap_seconds, r.chunk_seconds - 0.5)} disabled={occupe}
                aria-valuetext={`${r.overlap_seconds.toFixed(2).replace(".", ",")} seconde`} onChange={(e) => regler("overlap_seconds", Number(e.target.value))} />
            </Champ>
          </div>
        )}
        {local && (
          <label className="nn-check"><input type="checkbox" checked={r.vad_filter} disabled={occupe}
            onChange={(e) => regler("vad_filter", e.target.checked)} /> <span>Ignorer les silences (VAD)</span></label>
        )}
        <label className="nn-check"><input type="checkbox" checked={r.save_audio} disabled={occupe}
          onChange={(e) => regler("save_audio", e.target.checked)} /> <span>Garder l'enregistrement audio (pour réécouter et identifier les intervenants plus tard)</span></label>
        {diarisationDispo && (
          <Champ id="pipeline" label="Dossier du modèle d'identification des intervenants"
            aide={<Verifie resultat={r.diarization_model_path.trim() ? pipeline : null} vide="Dossier pyannote déjà présent sur le disque (avec config.yaml)." />}>
            <input id="pipeline" className="nn-input" value={r.diarization_model_path} disabled={occupe} spellCheck={false}
              placeholder=".\models\pyannote-speaker-diarization-community-1" onChange={(e) => regler("diarization_model_path", e.target.value)} />
          </Champ>
        )}
      </div>
    </details>
  );
};

/** Bloc « modèle de transcription » : modèle de l'équipe (Studio Dock) ou dossier choisi sur ce poste. */
export function useBlocModele(r: Settings, regler: Props["regler"], capacites: Capabilities | null, equipe: ModeleEquipe | null | undefined,
  modele: Verification | null, occupe: boolean): { modeleOk: boolean; bloc: React.ReactNode } {
  const local = r.engine === "local";
  const modeleEquipe = !!equipe && !r.use_own_model;
  const modeleOk = !local || modeleEquipe || modele?.valid === true;
  const bloc = local && (
    <div className="flex flex-col gap-2">
      {capacites && !capacites.stt && (
        <p role="alert" className="m-0 text-[13px] text-warning-text">La transcription réelle n'est pas incluse dans cette installation : utilisez la simulation.</p>
      )}
      {modeleEquipe ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-ink">Modèle</span>
          <span className="nn-chip nn-chip-success self-start">✓ {equipe!.name}{equipe!.version ? ` ${equipe!.version}` : ""} · fourni par votre équipe</span>
          <button type="button" className={lien} disabled={occupe} onClick={() => regler("use_own_model", true)}>Utiliser un autre modèle sur ce poste</button>
        </div>
      ) : (
        <>
          {equipe === null && (
            <p className="m-0 rounded border border-warning-line bg-warning-soft px-3 py-2.5 text-[13px] leading-snug text-warning-text">
              Aucun modèle de transcription sur ce poste. Il est normalement fourni par votre équipe : ouvrez Studio Dock,
              Réglages › Modèles d'IA › Transcription audio. Vous pouvez aussi indiquer ci-dessous le dossier d'un modèle.
            </p>
          )}
          <Champ id="modele" label="Dossier du modèle de transcription"
            aide={<Verifie resultat={r.model_path.trim() ? modele : null} vide="Le dossier qui contient config.json et model.bin (modèle faster-whisper)." />}>
            <input id="modele" className="nn-input" value={r.model_path} disabled={occupe} spellCheck={false}
              placeholder="C:\Users\…\faster-whisper-small" onChange={(e) => regler("model_path", e.target.value)} />
          </Champ>
          {equipe && (
            <button type="button" className={lien} disabled={occupe} onClick={() => regler("use_own_model", false)}>
              Revenir au modèle de l'équipe ({equipe.name})
            </button>
          )}
        </>
      )}
    </div>
  );
  return { modeleOk, bloc };
}
