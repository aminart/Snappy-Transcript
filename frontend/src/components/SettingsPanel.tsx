import React from "react";
import { Champ, Section, Verifie } from "./ui";
import type { Acceleration, Capabilities, Cuda, Devices, Settings, Source, Verification } from "../types";

interface Props {
  reglages: Settings;
  regler: <K extends keyof Settings>(cle: K, valeur: Settings[K]) => void;
  capacites: Capabilities | null;
  peripheriques: Devices | null;
  actualiser: () => void;
  modele: Verification | null;
  pipeline: Verification | null;
  cuda: Cuda | null;
  occupe: boolean;
  /** Mode fichier : remplace la section « Source audio ». */
  zoneFichier?: React.ReactNode;
}

const SOURCES: { id: Source; label: string }[] = [
  { id: "microphone", label: "Microphone" },
  { id: "system", label: "Audio système (Windows)" },
  { id: "mixed", label: "Micro + audio système (Windows)" },
];
const ACCELERATIONS: { id: Acceleration; label: string }[] = [
  { id: "auto", label: "Automatique" },
  { id: "gpu", label: "GPU NVIDIA" },
  { id: "cpu", label: "CPU" },
];

export const SettingsPanel: React.FC<Props> = ({ reglages: r, regler, capacites, peripheriques, actualiser, modele, pipeline, cuda, occupe, zoneFichier }) => {
  const fichier = r.mode === "file";
  const systemeOk = capacites?.system_audio ?? false;
  const avecMicro = r.source !== "system";
  const avecSysteme = r.source !== "microphone";
  const entrees = peripheriques?.inputs ?? [];
  const sorties = peripheriques?.outputs ?? [];
  const micChoisi = entrees.find((d) => d.name === r.input_device) ?? entrees[0];
  const local = r.engine === "local";

  return (
    <div className="flex flex-col gap-4">
      {fichier ? zoneFichier : (
      <Section titre="Source audio">
        <Champ id="source" label="Source">
          <select id="source" className="nn-input" value={r.source} disabled={occupe}
            onChange={(e) => regler("source", e.target.value as Source)}>
            {SOURCES.map((s) => (
              <option key={s.id} value={s.id} disabled={s.id !== "microphone" && !systemeOk}>{s.label}</option>
            ))}
          </select>
        </Champ>
        {!systemeOk && capacites && (
          <p className="m-0 text-[13px] text-ink-muted">
            {capacites.platform === "win32"
              ? "Capture du son du PC indisponible : le paquet soundcard n'est pas installé."
              : "La capture du son du PC (WASAPI) n'existe que sous Windows."}
          </p>
        )}
        {avecMicro && (
          <Champ id="micro" label="Microphone"
            aide={peripheriques?.input_error ? `Microphones indisponibles : ${peripheriques.input_error}` : entrees.length === 0 && peripheriques ? "Aucun microphone détecté." : undefined}>
            <select id="micro" className="nn-input" disabled={occupe || entrees.length === 0} value={micChoisi?.name ?? ""}
              onChange={(e) => regler("input_device", e.target.value)}>
              {entrees.map((d) => <option key={d.index} value={d.name}>{d.index} · {d.name}</option>)}
            </select>
          </Champ>
        )}
        {avecSysteme && systemeOk && (
          <Champ id="sortie" label="Sortie Windows à capturer" aide="Le son de Teams, Jabber ou du navigateur tel qu'il sort du PC.">
            <select id="sortie" className="nn-input" disabled={occupe || sorties.length === 0} value={r.output_device || sorties[0]?.name || ""}
              onChange={(e) => regler("output_device", e.target.value)}>
              {sorties.map((s) => <option key={s.id} value={s.name}>{s.name}</option>)}
            </select>
          </Champ>
        )}
        <button type="button" className="nn-btn nn-btn-secondary self-start" onClick={actualiser} disabled={occupe}>Actualiser les périphériques</button>
      </Section>
      )}

      <Section titre="Transcription">
        <Champ id="moteur" label="Moteur">
          <select id="moteur" className="nn-input" value={r.engine} disabled={occupe}
            onChange={(e) => regler("engine", e.target.value as Settings["engine"])}>
            <option value="local">Whisper local (réel)</option>
            <option value="mock">Simulation (test)</option>
          </select>
        </Champ>
        {local && (
          <>
            {capacites && !capacites.stt && (
              <p role="alert" className="m-0 text-[13px] text-warning-text">faster-whisper n'est pas inclus dans cette installation : la transcription réelle est impossible.</p>
            )}
            <Champ id="modele" label="Dossier du modèle faster-whisper (CTranslate2)"
              aide={<Verifie resultat={r.model_path.trim() ? modele : null} vide="Renseignez le dossier de votre faster-whisper-small, ou utilisez la simulation." />}>
              <input id="modele" className="nn-input" value={r.model_path} disabled={occupe} spellCheck={false}
                placeholder="C:\Users\…\faster-whisper-small" onChange={(e) => regler("model_path", e.target.value)} />
            </Champ>
            <div className="flex flex-col gap-1.5">
              <span id="accel-label" className="text-sm font-medium text-ink">Calcul</span>
              <div className="nn-segmented" role="group" aria-labelledby="accel-label">
                {ACCELERATIONS.map((a) => (
                  <button key={a.id} type="button" aria-pressed={r.acceleration === a.id} disabled={occupe}
                    onClick={() => regler("acceleration", a.id)}>{a.label}</button>
                ))}
              </div>
              <span className="text-[13px] leading-snug text-ink-muted">
                {cuda?.ready ? `✓ CUDA prêt · ${cuda.gpu_count} GPU` : cuda ? `GPU non prêt : ${cuda.detail}` : "Vérification du GPU…"}
                {" "}Automatique essaie le GPU puis revient sur le CPU ; « GPU NVIDIA » affiche une erreur si CUDA n'est pas prêt.
              </span>
            </div>
          </>
        )}
        <Champ id="langue" label="Langue">
          <select id="langue" className="nn-input" value={r.language} disabled={occupe}
            onChange={(e) => regler("language", e.target.value as Settings["language"])}>
            <option value="fr">Français</option>
            <option value="en">Anglais</option>
            <option value="auto">Détection automatique</option>
          </select>
        </Champ>
        <Champ id="glossaire" label="Glossaire métier et noms propres"
          aide="Termes à favoriser : sigles, noms propres, jargon. Une liste courte et précise vaut mieux qu'un dictionnaire.">
          <textarea id="glossaire" className="nn-input min-h-[72px] py-2" value={r.glossary} disabled={occupe}
            placeholder="Ex. Jabber, RTX A1000, nom de projet…" onChange={(e) => regler("glossary", e.target.value)} />
        </Champ>
        {!fichier && (<>
        <Champ id="chunk" label={`Durée des blocs : ${r.chunk_seconds} s`}>
          <input id="chunk" type="range" min={3} max={15} step={1} className="w-full accent-primary" value={r.chunk_seconds} disabled={occupe}
            onChange={(e) => regler("chunk_seconds", Number(e.target.value))} />
        </Champ>
        <Champ id="recouvrement" label={`Recouvrement : ${r.overlap_seconds.toFixed(2)} s`}
          aide="Redonne du contexte à Whisper autour des coupures ; les mots répétés sont supprimés ensuite.">
          <input id="recouvrement" type="range" min={0} max={Math.min(2, r.chunk_seconds - 0.5)} step={0.25} className="w-full accent-primary"
            value={Math.min(r.overlap_seconds, r.chunk_seconds - 0.5)} disabled={occupe}
            onChange={(e) => regler("overlap_seconds", Number(e.target.value))} />
        </Champ>
        </>)}
        {local && (
          <label className="nn-check"><input type="checkbox" checked={r.vad_filter} disabled={occupe}
            onChange={(e) => regler("vad_filter", e.target.checked)} /> <span>Ignorer les silences (VAD)</span></label>
        )}
        <label className="nn-check"><input type="checkbox" checked={r.save_audio} disabled={occupe}
          onChange={(e) => regler("save_audio", e.target.checked)} /> <span>Conserver l'enregistrement WAV</span></label>
      </Section>

      <Section titre="Locuteurs">
        {capacites && !capacites.diarization && (
          <p className="m-0 text-[13px] text-ink-muted">La diarisation (pyannote, PyTorch) n'est pas incluse dans cette installation.</p>
        )}
        <label className="nn-check"><input type="checkbox" checked={r.diarization} disabled={occupe || capacites?.diarization === false}
          onChange={(e) => regler("diarization", e.target.checked)} /> <span>Identifier les locuteurs après l'arrêt</span></label>
        <Champ id="pipeline" label="Dossier du pipeline pyannote local"
          aide={<Verifie resultat={r.diarization_model_path.trim() ? pipeline : null} vide="Un pipeline déjà présent sur le disque. La transcription fonctionne sans lui." />}>
          <input id="pipeline" className="nn-input" value={r.diarization_model_path} disabled={occupe} spellCheck={false}
            placeholder=".\models\pyannote-speaker-diarization-community-1" onChange={(e) => regler("diarization_model_path", e.target.value)} />
        </Champ>
        <Champ id="locuteurs" label="Nombre de locuteurs (0 = automatique)">
          <input id="locuteurs" type="number" min={0} max={20} className="nn-input" value={r.speaker_hint} disabled={occupe}
            onChange={(e) => regler("speaker_hint", Math.max(0, Math.min(20, Math.floor(Number(e.target.value) || 0))))} />
        </Champ>
      </Section>
    </div>
  );
};
