import React from "react";
import { taille } from "../format";

export type ChoixFichier = { type: "envoi"; fichier: File } | { type: "chemin"; chemin: string } | null;

interface Props {
  choix: ChoixFichier;
  choisir: (c: ChoixFichier) => void;
  extensions: string[];
  disponible: boolean;
  occupe: boolean;
}

/** Choix du fichier : glisser-déposer, parcourir, ou chemin d'un fichier déjà sur ce PC (gros fichiers : aucune copie). */
export const FilePicker: React.FC<Props> = ({ choix, choisir, extensions, disponible, occupe }) => {
  const entree = React.useRef<HTMLInputElement>(null);
  const [survol, setSurvol] = React.useState(false);
  const desactive = occupe || !disponible;
  const fichier = choix?.type === "envoi" ? choix.fichier : null;
  const chemin = choix?.type === "chemin" ? choix.chemin : "";
  const accept = ["audio/*", "video/*", ...extensions].join(",");

  const deposer = (e: React.DragEvent) => {
    e.preventDefault();
    setSurvol(false);
    const f = e.dataTransfer.files?.[0];
    if (f && !desactive) choisir({ type: "envoi", fichier: f });
  };

  return (
    <div className="flex w-full flex-col gap-4">
      <h2 className="m-0 text-[17px] font-bold text-ink">Fichier à transcrire</h2>
      {!disponible && (
        <p role="alert" className="m-0 text-[13px] text-warning-text">La lecture des fichiers (PyAV) n'est pas incluse dans cette installation.</p>
      )}
      <div
        onDragOver={(e) => { e.preventDefault(); if (!desactive) setSurvol(true); }}
        onDragLeave={() => setSurvol(false)}
        onDrop={deposer}
        className={`flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors
          ${survol ? "border-accent bg-accent-soft" : "border-line-dashed bg-surface-2"} ${desactive ? "opacity-60" : ""}`}
      >
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="text-ink-muted" aria-hidden="true">
          <path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
        </svg>
        {fichier ? (
          <>
            <span className="max-w-full break-all text-sm font-medium text-ink">{fichier.name}</span>
            <span className="text-[13px] text-ink-muted">{taille(fichier.size)}</span>
          </>
        ) : (
          <span className="text-sm text-ink-body">Glissez un fichier audio ou vidéo ici</span>
        )}
        <button type="button" className="nn-btn nn-btn-secondary" disabled={desactive} onClick={() => entree.current?.click()}>
          {fichier ? "Choisir un autre fichier" : "Parcourir…"}
        </button>
        <input ref={entree} type="file" className="sr-only" accept={accept} tabIndex={-1} aria-hidden="true"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) choisir({ type: "envoi", fichier: f }); e.target.value = ""; }} />
      </div>
      <p className="m-0 text-[13px] leading-snug text-ink-muted">
        MP3, WAV, M4A, AAC, FLAC, OGG, Opus, WMA, AIFF… et les vidéos MP4, MOV, MKV, AVI, WMV, WebM, MPEG : la piste son est lue
        directement, sans conversion.
      </p>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="chemin-fichier" className="text-sm font-medium text-ink">Ou chemin d'un fichier sur ce PC</label>
        <input id="chemin-fichier" className="nn-input" value={chemin} disabled={desactive} spellCheck={false}
          placeholder="C:\…\reunion.mp4" aria-describedby="chemin-fichier-aide"
          onChange={(e) => choisir(e.target.value.trim() ? { type: "chemin", chemin: e.target.value } : null)} />
        <span id="chemin-fichier-aide" className="text-[13px] leading-snug text-ink-muted">Pratique pour les très gros fichiers : ils sont lus sur place, sans copie.</span>
      </div>
    </div>
  );
};
