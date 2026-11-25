import React from "react";
import { Champ, Section, Verifie } from "./ui";
import { ChoixSource, type Ecoute, ListeApplications, avecApplication, ecouteDe, versSource } from "./ChoixSource";
import type { Acceleration, AppAudio, Applications, Capabilities, Cuda, Devices, ModeleEquipe, Settings, Verification } from "../types";

interface Props {
  reglages: Settings;
  regler: <K extends keyof Settings>(cle: K, valeur: Settings[K]) => void;
  capacites: Capabilities | null;
  peripheriques: Devices | null;
  /** Applications qui utilisent le son (rafraîchies tant que la liste est affichée). */
  applications: Applications | null;
  actualiser: () => void;
  modele: Verification | null;
  pipeline: Verification | null;
  cuda: Cuda | null;
  /** Modèle de l'équipe installé par Studio Dock ; undefined : pas encore lu. */
  equipe: ModeleEquipe | null | undefined;
  occupe: boolean;
  /** Mode fichier : remplace la section « Source audio ». */
  zoneFichier?: React.ReactNode;
}

const ACCELERATIONS: { id: Acceleration; label: string }[] = [
  { id: "auto", label: "Automatique" },
  { id: "gpu", label: "GPU NVIDIA" },
  { id: "cpu", label: "Processeur" },
];
const lien = "self-start border-0 bg-transparent p-0 text-[13px] text-accent underline disabled:opacity-60";

/**
 * Réglages : ce qu'un utilisateur choisit à chaque fois reste visible (source, langue, glossaire, intervenants) ;
 * la technique (moteur, modèle, calcul, blocs, VAD, pipeline) est repliée dans « Réglages avancés », sauf quand
 * elle demande une action (modèle absent, pipeline à indiquer).
 */
export const SettingsPanel: React.FC<Props> = ({ reglages: r, regler, capacites, peripheriques, applications, actualiser, modele, pipeline, cuda, equipe, occupe, zoneFichier }) => {
  const fichier = r.mode === "file";
  const systemeOk = capacites?.system_audio ?? false;
  const ecoute = ecouteDe(r);
  const avecMicro = r.source !== "system";
  const toutLeSon = ecoute === "tout" || ecoute === "voix_tout";
  const entrees = peripheriques?.inputs ?? [];
  const sorties = peripheriques?.outputs ?? [];
  const micChoisi = entrees.find((d) => d.name === r.input_device) ?? entrees[0];
  const local = r.engine === "local";
  const modeleEquipe = !!equipe && !r.use_own_model;
  const modeleOk = !local || modeleEquipe || modele?.valid === true;
  const diarisationDispo = capacites?.diarization !== false;
  const intervenants = r.diarization && diarisationDispo;
  const pipelineOk = pipeline?.valid === true;

  const choisirApp = (a: AppAudio) => { regler("app", a.exe); regler("app_name", a.name); };
  const changerEcoute = (e: Ecoute) => {
    regler("source", versSource(e));
    if (!avecApplication(e)) { regler("app", ""); return; }
    if (r.app) return;
    const apps = applications?.apps ?? [];
    const a = apps.find((x) => x.exe === applications?.recommended) ?? apps.find((x) => x.active) ?? apps[0];
    if (a) choisirApp(a);
  };

  const blocModele = local && (
    <div className="flex flex-col gap-2">
      {capacites && !capacites.stt && (
        <p role="alert" className="m-0 text-[13px] text-warning-text">La transcription réelle n'est pas incluse dans cette installation : utilisez la simulation.</p>
      )}
      {modeleEquipe ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-ink">Modèle</span>
          <span className="nn-chip nn-chip-success self-start">✓ {equipe!.name}{equipe!.version ? ` ${equipe!.version}` : ""}</span>
          <span className="text-[13px] leading-snug text-ink-muted">Fourni par votre équipe via Studio Dock : rien à régler.</span>
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

  const champPipeline = (
    <Champ id="pipeline" label="Dossier du modèle d'identification des intervenants"
      aide={<Verifie resultat={r.diarization_model_path.trim() ? pipeline : null} vide="Dossier pyannote déjà présent sur le disque (avec config.yaml)." />}>
      <input id="pipeline" className="nn-input" value={r.diarization_model_path} disabled={occupe} spellCheck={false}
        placeholder=".\models\pyannote-speaker-diarization-community-1" onChange={(e) => regler("diarization_model_path", e.target.value)} />
    </Champ>
  );

  return (
    <div className="flex flex-col gap-4">
      {fichier ? zoneFichier : (
        <Section titre="Source audio">
          <ChoixSource ecoute={ecoute} changer={changerEcoute} applications={applications} systeme={systemeOk} bloque={occupe}
            raisonSysteme={capacites ? (capacites.platform === "win32" ? "Le son de l'ordinateur n'est pas disponible dans cette installation."
              : "Le son de l'ordinateur et des applications ne peut être capté que sous Windows.") : ""} />
          {avecApplication(ecoute) && (
            <ListeApplications applications={applications} choisie={r.app} nomChoisie={r.app_name} choisir={choisirApp} bloque={occupe} />
          )}
          {r.source === "mixed" && systemeOk && (
            <p className="m-0 text-[13px] leading-snug text-ink-muted">Avec des haut-parleurs, le micro réentend vos interlocuteurs : un casque évite les doublons.</p>
          )}
          {avecMicro && (
            <Champ id="micro" label="Microphone"
              aide={peripheriques?.input_error ? "Impossible de lister les microphones sur ce poste." : entrees.length === 0 && peripheriques ? "Aucun microphone détecté." : undefined}>
              <select id="micro" className="nn-input" disabled={occupe || entrees.length === 0} value={micChoisi?.name ?? ""}
                onChange={(e) => regler("input_device", e.target.value)}>
                {entrees.map((d) => <option key={d.index} value={d.name}>{d.name}</option>)}
              </select>
            </Champ>
          )}
          {toutLeSon && systemeOk && (
            <Champ id="sortie" label="Sortie où vous entendez la réunion">
              <select id="sortie" className="nn-input" disabled={occupe || sorties.length === 0} value={r.output_device || sorties[0]?.name || ""}
                onChange={(e) => regler("output_device", e.target.value)}>
                {sorties.map((s) => <option key={s.id} value={s.name}>{s.name}</option>)}
              </select>
            </Champ>
          )}
          <button type="button" className={lien} onClick={actualiser} disabled={occupe}>Actualiser la liste (casque branché à l'instant…)</button>
        </Section>
      )}

      <Section titre="Transcription">
        {!modeleOk && blocModele}
        <Champ id="langue" label="Langue parlée">
          <select id="langue" className="nn-input" value={r.language} disabled={occupe}
            onChange={(e) => regler("language", e.target.value as Settings["language"])}>
            <option value="fr">Français</option>
            <option value="en">Anglais</option>
            <option value="auto">Détection automatique</option>
          </select>
        </Champ>
        <Champ id="glossaire" label="Mots à bien reconnaître"
          aide="Noms propres, sigles, jargon : une liste courte et précise, séparée par des virgules.">
          <textarea id="glossaire" className="nn-input min-h-[72px] py-2" value={r.glossary} disabled={occupe}
            placeholder="Ex. Jabber, RTX A1000, nom de projet…" onChange={(e) => regler("glossary", e.target.value)} />
        </Champ>
        <label className="nn-check"><input type="checkbox" checked={r.save_audio} disabled={occupe}
          onChange={(e) => regler("save_audio", e.target.checked)} /> <span>Garder l'enregistrement audio (pour réécouter et identifier les intervenants plus tard)</span></label>
      </Section>

      <Section titre="Intervenants">
        {!diarisationDispo ? (
          <p className="m-0 text-[13px] text-ink-muted">L'identification des intervenants n'est pas incluse dans cette installation.</p>
        ) : (
          <>
            <label className="nn-check"><input type="checkbox" checked={r.diarization} disabled={occupe}
              onChange={(e) => regler("diarization", e.target.checked)} /> <span>Identifier qui parle, après l'arrêt</span></label>
            {intervenants && (
              <>
                <Champ id="locuteurs" label="Nombre d'intervenants (0 = je ne sais pas)">
                  <input id="locuteurs" type="number" min={0} max={20} className="nn-input max-w-[120px]" value={r.speaker_hint} disabled={occupe}
                    onChange={(e) => regler("speaker_hint", Math.max(0, Math.min(20, Math.floor(Number(e.target.value) || 0))))} />
                </Champ>
                {!pipelineOk && champPipeline}
              </>
            )}
          </>
        )}
      </Section>

      <details className="nn-card p-5">
        <summary className="cursor-pointer text-[15px] font-bold text-ink">Réglages avancés</summary>
        <div className="mt-4 flex flex-col gap-4">
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
              <div className="nn-segmented" role="group" aria-labelledby="accel-label">
                {ACCELERATIONS.map((a) => (
                  <button key={a.id} type="button" aria-pressed={r.acceleration === a.id} disabled={occupe}
                    onClick={() => regler("acceleration", a.id)}>{a.label}</button>
                ))}
              </div>
              <span className="text-[13px] leading-snug text-ink-muted" title={cuda?.detail}>
                {cuda ? cuda.message : "Vérification de la carte graphique…"}
              </span>
              {r.acceleration === "gpu" && cuda && !cuda.ready && (
                <span role="alert" className="text-[13px] leading-snug text-warning-text">
                  « GPU NVIDIA » impose la carte graphique : la transcription ne pourra pas démarrer. Choisissez « Automatique ».
                </span>
              )}
            </div>
          )}
          {!fichier && (
            <>
              <Champ id="chunk" label={`Durée des blocs : ${r.chunk_seconds} s`} aide="Plus court : le texte arrive plus vite ; plus long : un peu plus précis.">
                <input id="chunk" type="range" min={3} max={15} step={1} className="w-full accent-primary" value={r.chunk_seconds} disabled={occupe}
                  aria-valuetext={`${r.chunk_seconds} secondes`} onChange={(e) => regler("chunk_seconds", Number(e.target.value))} />
              </Champ>
              <Champ id="recouvrement" label={`Recouvrement : ${r.overlap_seconds.toFixed(2)} s`}
                aide="Contexte redonné autour des coupures ; les mots répétés sont retirés ensuite.">
                <input id="recouvrement" type="range" min={0} max={Math.min(2, r.chunk_seconds - 0.5)} step={0.25} className="w-full accent-primary"
                  value={Math.min(r.overlap_seconds, r.chunk_seconds - 0.5)} disabled={occupe}
                  aria-valuetext={`${r.overlap_seconds.toFixed(2).replace(".", ",")} seconde`}
                  onChange={(e) => regler("overlap_seconds", Number(e.target.value))} />
              </Champ>
            </>
          )}
          {local && (
            <label className="nn-check"><input type="checkbox" checked={r.vad_filter} disabled={occupe}
              onChange={(e) => regler("vad_filter", e.target.checked)} /> <span>Ignorer les silences (VAD)</span></label>
          )}
          {diarisationDispo && (!intervenants || pipelineOk) && champPipeline}
        </div>
      </details>
    </div>
  );
};
