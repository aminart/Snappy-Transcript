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
  model_path: string;
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
  files: boolean;
  file_extensions: string[];
}

export interface InputDevice { index: number; name: string; channels: number; default_samplerate: number }
export interface OutputDevice { name: string; id: string }
export interface Devices { inputs: InputDevice[]; input_error: string; outputs: OutputDevice[] }

export interface Verification { valid: boolean; message: string; name?: string; missing?: string[] }
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
}
