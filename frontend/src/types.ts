export type Source = "microphone" | "system" | "mixed";
export type Engine = "local" | "mock";
export type Acceleration = "auto" | "gpu" | "cpu";
export type Language = "fr" | "en" | "auto";
export type Mode = "live" | "file";

export interface Settings {
  mode: Mode;
  source: Source;
  engine: Engine;
  input_device: string;
  output_device: string;
  /** Programme dont on capte le son seul (« ms-teams.exe ») ; vide : tout le son de l'ordinateur. */
  app: string;
  app_name: string;
  model_path: string;
  use_own_model: boolean;
  acceleration: Acceleration;
  language: Language;
  glossary: string;
  chunk_seconds: number;
  overlap_seconds: number;
  vad_filter: boolean;
  save_audio: boolean;
  diarization: boolean;
  diarization_model_path: string;
  speaker_hint: number;
}

export interface Capabilities {
  platform: string;
  stt: boolean;
  diarization: boolean;
  system_audio: boolean;
  /** Le son d'une seule application peut être capté (Windows 10 2004 ou plus récent). */
  app_audio: boolean;
  files: boolean;
  file_extensions: string[];
}

export interface InputDevice { index: number; name: string; channels: number; default_samplerate: number }
export interface OutputDevice { name: string; id: string }
export interface Devices { inputs: InputDevice[]; input_error: string; outputs: OutputDevice[] }

export interface AppAudio { exe: string; name: string; pid: number; active: boolean; level: number; visio: boolean }
export interface Applications { supported: boolean; reason: string; apps: AppAudio[]; recommended: string }

export interface Verification { valid: boolean; message: string; name?: string; missing?: string[] }
export interface ModeleEquipe { name: string; version: string | null; path: string }

export interface Cuda { ready: boolean; gpu_count: number; detail: string; message: string }

/** [début, fin, texte] en secondes */
export type Mot = [number, number, string];

export interface Segment {
  start: number;
  end: number;
  text: string;
  speaker: string | null;
  words?: Mot[];
}

export interface Diarisation {
  status: "IDLE" | "RUNNING" | "DONE" | "ERROR";
  phase: string;
  fraction: number | null;
  elapsed: number;
  eta: number | null;
  error: string;
  note: string;
  wanted?: boolean;
  segments?: number;
  outputs?: { txt?: string; srt?: string };
}

export interface FichiersSession { wav: boolean; raw_txt: boolean; raw_srt: boolean; diarized_txt: boolean; diarized_srt: boolean }

export interface AvancementFichier {
  name: string;
  phase: "decoding" | "transcribing" | "done";
  fraction: number | null;
  eta: number | null;
  media_duration: number | null;
}

export interface SessionState {
  active: boolean;
  id: string;
  kind: Mode;
  file: AvancementFichier | null;
  status: "LISTENING" | "TRANSCRIBING" | "DECODING" | "PAUSED" | "STOPPED" | "ERROR";
  paused: boolean;
  stopping: boolean;
  finalized: boolean;
  duration: number;
  queue: number;
  stats: {
    chunks: number;
    last_latency: number;
    last_chunk_duration: number;
    realtime_ratio: number;
    average_realtime_ratio: number;
    duplicate_words_removed: number;
  };
  error: string;
  provider: { engine: string; faster_whisper?: string; ctranslate2?: string; compute?: string; fallback?: string };
  from: number;
  total: number;
  segments: Segment[];
  diarization: Diarisation & { wanted: boolean };
  files: FichiersSession | Record<string, never>;
  session_dir: string;
  recovery_copy: string;
  save_audio: boolean;
  speakers: Intervenant[];
  /** Session rouverte depuis « Mes transcriptions ». */
  archived: boolean;
  title: string;
  default_title: string;
  started: string;
  marks: Marque[];
  /** La dernière correction ou le dernier « Tout remplacer » peut être annulé (Ctrl+Z). */
  can_undo: boolean;
  undo_label: string;
}

/** Moment marqué : t en secondes ; label choisi, ou la phrase prononcée à ce moment (named = false). */
export interface Marque { t: number; label: string; named: boolean }

export interface Extrait { before: string; match: string; after: string }

export interface Intervenant { label: string; name: string; seconds: number }

export interface Niveau { level: number | null; silence: number }

export interface SessionPassee {
  id: string;
  interrupted: boolean;
  kind: Mode;
  name: string | null;
  started?: string;
  duration: number | null;
  segments: number | null;
  diarized: boolean;
  audio: boolean;
  error?: string;
  current: boolean;
  title: string;
  recoverable?: boolean;
  excerpt: Extrait | null;
  matches: number;
  speakers: string[];
  unnamed: number;
  marks: number;
  /** Place occupée par la session et par son audio (octets). */
  size: number;
  audio_size: number;
}
