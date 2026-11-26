import React from "react";
import type { Acceleration, AppAudio, Applications, Capabilities, Cuda, Devices, ModeleEquipe, Settings, Verification } from "../types";
import { type Ecoute, ListeApplications, avecApplication, versSource } from "./ChoixSource";
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
  { id: "voix_app", label: "Ma voix + une application" },
  { id: "voix", label: "Ma voix" },
  { id: "app", label: "Une application" },
  { id: "tout", label: "Tout le son du PC" },
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
  /** Précision sous la ligne (case à cocher, conseil, raison) : reste entre les deux séparateurs, alignée sur la valeur. */
  aide?: React.ReactNode;
}> = ({ id, label, children, editeur, action = "Changer", bloque, ouvert, basculer, fin, aide }) => (
  <div className="flex flex-col gap-2 border-b border-line py-3.5 last:border-b-0">
    <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2">
      <span id={`${id}-label`} className="w-[150px] shrink-0 text-[13px] text-ink-muted">{label}</span>
      <div className="flex min-w-0 flex-[1_1_220px] flex-wrap items-center gap-2">{children}</div>
      {fin}
      {editeur && basculer && (
        <button type="button" className="nn-btn nn-btn-secondary h-9 px-3" aria-expanded={ouvert} aria-controls={`${id}-editeur`}
          aria-describedby={`${id}-label`} disabled={bloque} onClick={basculer}>{ouvert ? "Fermer" : action}</button>
      )}
    </div>
    {aide && <div className="flex flex-col gap-1.5 text-[13px] leading-snug text-ink-muted sm:pl-[164px]">{aide}</div>}
    {editeur && ouvert && <div id={`${id}-editeur`} className="pl-0 sm:pl-[164px]">{editeur}</div>}
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
  /** Choix « On écoute » applicable sur ce poste (voir ecouteEffective). */
  ecoute: Ecoute;
  capacites: Capabilities | null;
  peripheriques: Devices | null;
  applications: Applications | null;
  apercu: Apercu | null;
  actualiser: () => void;
  pipeline: Verification | null;
  /** Modèle d'identification des intervenants fourni par l'équipe (Studio Dock), s'il y en a un. */
  intervenantsEquipe: ModeleEquipe | null;
  modeleOk: boolean;
  blocModele: React.ReactNode;
  occupe: boolean;
  ouvrirAvances: () => void;
}

/** « Prêt ? » : une ligne par sujet, modifiable sur place ; la source se vérifie avant de démarrer. */
export const Pret: React.FC<Props> = ({ reglages: r, regler, ecoute, capacites, peripheriques, applications, apercu, actualiser, pipeline, intervenantsEquipe, modeleOk, blocModele, occupe, ouvrirAvances }) => {
  const pipelineOk = (!!intervenantsEquipe && !r.use_own_diarization_model) || pipeline?.valid === true;
  const [ouvert, setOuvert] = React.useState<string | null>(null);
  const basculer = (id: string) => () => setOuvert((o) => (o === id ? null : id));
  const fichier = r.mode === "file";
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
    regler("ecoute", e);
    regler("source", versSource(e));
    if (!avecApplication(e)) { regler("app", ""); return; }
    if (r.app) return;
    const a = apps.find((x) => x.exe === applications?.recommended) ?? apps.find((x) => x.active);
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

  return (
    <div className="flex flex-col">
      {!fichier && (
        <>
          <Ligne id="ecoute" label="On écoute"
            aide={<>
              {(ecoute === "tout" || ecoute === "voix_tout") && (
                <label className="nn-check text-[13px] text-ink-body">
                  <input type="checkbox" checked={ecoute === "voix_tout"} disabled={occupe}
                    onChange={(e) => changerEcoute(e.target.checked ? "voix_tout" : "tout")} />
                  <span>Ajouter aussi ma voix (micro)</span>
                </label>
              )}
              {!systemeOk && capacites && (
                <span>{capacites.platform === "win32" ? "Le son de l'ordinateur n'est pas disponible dans cette installation."
                  : "Le son d'une application ou de tout l'ordinateur ne peut être capté que sous Windows."}</span>
              )}
              {systemeOk && applications && !applications.supported && applications.reason && <span className="text-warning-text">{applications.reason}</span>}
            </>}>
            <div role="radiogroup" aria-labelledby="ecoute-label" className="flex flex-wrap gap-1.5 xl:flex-nowrap">
              {CHIPS.map((c, i) => {
                const coche = actif === c.id;
                return (
                  <button key={c.id} ref={(el) => { chips.current[i] = el; }} type="button" role="radio" aria-checked={coche}
                    tabIndex={coche ? 0 : -1} disabled={!dispo(c.id) || (occupe && !coche)}
                    onClick={() => changerEcoute(c.id === "tout" && ecoute === "voix_tout" ? "voix_tout" : c.id)} onKeyDown={(e) => clavier(e, i)}
                    className={`h-8 whitespace-nowrap rounded-md border px-2.5 text-[13px] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus
                      disabled:cursor-not-allowed disabled:opacity-50
                      ${coche ? "border-accent bg-accent-soft font-medium text-accent-ink" : "border-line-strong bg-surface text-ink-body hover:bg-surface-2"}`}>
                    {c.label}
                  </button>
                );
              })}
            </div>
          </Ligne>

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


          {ecoute !== "app" && ecoute !== "tout" && (
            <Ligne id="micro" label="Microphone" ouvert={ouvert === "micro"} basculer={basculer("micro")} bloque={occupe || entrees.length === 0}
              fin={micChoisi && <EtatSon mesure={apercu?.voix} ok="On vous entend" attente="Parlez pour tester" />}
              editeur={
                <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
                  <legend className="sr-only">Microphone</legend>
                  <div className="flex flex-col gap-1">
                    {entrees.map((d) => {
                      const coche = d.name === micChoisi?.name;
                      return (
                        <label key={d.index} className={`flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 ${coche ? "border-accent bg-accent-softer ring-1 ring-accent" : "border-line hover:bg-surface-2"}`}>
                          <input type="radio" name="micro" className="m-0 h-[18px] w-[18px] accent-[var(--nn-primary)]" checked={coche}
                            onChange={() => regler("input_device", d.name)} />
                          <span className="min-w-0 flex-1 text-sm text-ink">{d.name}</span>
                          {d.default && <span className="text-[12px] text-ink-subtle">micro par défaut de Windows</span>}
                          {coche && apercu?.voix && <Barres niveau={apercu.voix.level} />}
                        </label>
                      );
                    })}
                  </div>
                  <button type="button" className={lien} onClick={actualiser}>Actualiser la liste (casque branché à l'instant…)</button>
                </fieldset>
              }>
              <span className="font-medium text-ink">
                {micChoisi?.name ?? (peripheriques?.input_error ? "Impossible de lister les microphones" : peripheriques ? "Aucun microphone détecté" : "…")}
              </span>
            </Ligne>
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

      <Ligne id="intervenants" label="Intervenants" action={diarisationDispo ? "Préciser" : "Comment l'ajouter ?"} ouvert={ouvert === "intervenants"}
        basculer={!diarisationDispo || r.diarization ? basculer("intervenants") : undefined}
        bloque={occupe && diarisationDispo}
        aide={diarisationDispo && r.diarization && !pipelineOk ? (
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-warning-text">
            Il manque le dossier du modèle d'identification des intervenants.
            <button type="button" className={lien} onClick={ouvrirAvances}>L'indiquer dans les réglages avancés</button>
          </span>
        ) : undefined}
        fin={diarisationDispo && (
          <label className="nn-check text-sm"><input type="checkbox" checked={r.diarization} disabled={occupe}
            onChange={(e) => regler("diarization", e.target.checked)} /> <span>Activé</span></label>
        )}
        editeur={!diarisationDispo ? (
          <div className="flex max-w-[560px] flex-col gap-2 rounded-md border border-line bg-surface-2 px-4 py-3 text-[13px] leading-snug text-ink-body">
            <span>L'identification des intervenants (« qui a dit quoi ») n'a pas été installée sur ce poste (installation « leger », ou échec du téléchargement) :</span>
            <ol className="m-0 flex flex-col gap-1 pl-5">
              <li>fermez Snappy Transcript ;</li>
              <li>dans le dossier du projet, relancez <code className="rounded bg-surface-3 px-1">install.bat</code>, sans l'option « leger » (sur Mac : <code className="rounded bg-surface-3 px-1">./install.sh</code>, Mac Apple Silicon seulement) ;</li>
              <li>relancez l'app : le modèle fourni par votre équipe dans Studio Dock est utilisé tout seul (sinon, indiquez son dossier dans « Réglages avancés »).</li>
            </ol>
          </div>
        ) : (
          <Champ id="locuteurs" label="Nombre d'intervenants (0 = je ne sais pas)">
            <input id="locuteurs" type="number" min={0} max={20} className="nn-input max-w-[120px]" value={r.speaker_hint}
              onChange={(e) => regler("speaker_hint", Math.max(0, Math.min(20, Math.floor(Number(e.target.value) || 0))))} />
          </Champ>
        )}>
        <span className="text-ink-body">
          {!diarisationDispo ? "Non incluse dans cette installation"
            : !r.diarization ? "Non identifiés"
            : `Identifiés après l'arrêt · ${r.speaker_hint ? `${r.speaker_hint} personne${r.speaker_hint > 1 ? "s" : ""}` : "nombre inconnu"}`}
        </span>
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
  intervenantsEquipe: ModeleEquipe | null;
  occupe: boolean;
  ouvert: boolean;
  basculer: () => void;
}

/** Réglages techniques, repliés : moteur, modèle, calcul, blocs, silences, audio gardé, modèle d'identification. */
export const ReglagesAvances: React.FC<PropsAvances> = ({ reglages: r, regler, capacites, cuda, modeleOk, blocModele, pipeline, intervenantsEquipe, occupe, ouvert, basculer }) => {
  const local = r.engine === "local";
  const diarisationDispo = capacites?.diarization !== false;
  return (
    <div className="mt-3 flex flex-col">
      <button type="button" className="nn-btn nn-btn-secondary self-start gap-2" aria-expanded={ouvert} aria-controls="reglages-avances" onClick={basculer}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true"
          className={`transition-transform ${ouvert ? "rotate-180" : ""}`}><path d="M6 9l6 6 6-6" /></svg>
        Réglages avancés
      </button>
      {ouvert && <div id="reglages-avances" className="mt-4 flex flex-col gap-4 rounded-lg border border-line bg-surface-2 p-5">
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
        {diarisationDispo && intervenantsEquipe && !r.use_own_diarization_model && (
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-ink">Modèle d'identification des intervenants</span>
            <span className="nn-chip nn-chip-success self-start">✓ {intervenantsEquipe.name}{intervenantsEquipe.version ? ` ${intervenantsEquipe.version}` : ""} · fourni par votre équipe</span>
            <button type="button" className={lien} disabled={occupe} onClick={() => regler("use_own_diarization_model", true)}>Utiliser un autre dossier sur ce poste</button>
          </div>
        )}
        {diarisationDispo && !(intervenantsEquipe && !r.use_own_diarization_model) && (
          <Champ id="pipeline" label="Dossier du modèle d'identification des intervenants"
            aide={<Verifie resultat={r.diarization_model_path.trim() ? pipeline : null} vide="Dossier pyannote déjà présent sur le disque (avec config.yaml)." />}>
            <input id="pipeline" className="nn-input" value={r.diarization_model_path} disabled={occupe} spellCheck={false}
              placeholder=".\models\pyannote-speaker-diarization-community-1" onChange={(e) => regler("diarization_model_path", e.target.value)} />
          </Champ>
        )}
        {diarisationDispo && intervenantsEquipe && r.use_own_diarization_model && (
          <button type="button" className={lien} disabled={occupe} onClick={() => regler("use_own_diarization_model", false)}>
            Revenir au modèle de l'équipe ({intervenantsEquipe.name})
          </button>
        )}
      </div>}
    </div>
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
