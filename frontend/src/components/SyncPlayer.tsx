import React from "react";
import { api, messageErreur } from "../api";
import { hms } from "../format";
import type { Segment } from "../types";

type Variante = "raw" | "diarized";

interface Position { seg: number; mot: number }

/** Dernier segment dont le début est ≤ t, tant que t n'a pas dépassé sa fin (ou le début du suivant). */
function segmentA(segments: Segment[], t: number): number {
  let bas = 0, haut = segments.length - 1, meilleur = -1;
  while (bas <= haut) {
    const milieu = (bas + haut) >> 1;
    if (segments[milieu].start <= t) { meilleur = milieu; bas = milieu + 1; } else haut = milieu - 1;
  }
  if (meilleur < 0) return -1;
  const s = segments[meilleur];
  const suivant = meilleur + 1 < segments.length ? segments[meilleur + 1].start : s.end;
  return t < Math.max(s.end, suivant) ? meilleur : -1;
}

interface LigneProps { segment: Segment; index: number; actif: boolean; motActif: number; aller: (t: number) => void }

const Ligne = React.memo(React.forwardRef<HTMLButtonElement, LigneProps>(({ segment, index, actif, motActif, aller }, ref) => (
  <button ref={ref} type="button" data-index={index} onClick={() => aller(segment.start)} aria-current={actif ? "true" : undefined}
    className={`grid w-full cursor-pointer grid-cols-[72px_1fr] gap-2 rounded border-0 border-l-[3px] px-2.5 py-2 text-left text-sm text-ink-body
      ${actif ? "border-l-accent bg-accent-soft" : "border-l-transparent bg-transparent hover:bg-surface-3"}`}>
    <span className="pt-0.5 font-mono text-xs text-ink-muted">{hms(segment.start)}</span>
    <span>
      {segment.speaker && <span className="mr-2 inline-block rounded-full bg-accent-soft px-1.5 py-0.5 text-[11px] font-bold text-accent-ink">{segment.speaker}</span>}
      {segment.words && segment.words.length > 0
        ? segment.words.map((m, j) => (
          <React.Fragment key={j}>
            <span className={`rounded px-0.5 ${actif && j === motActif ? "bg-primary text-primary-on" : ""}`}>{m[2]}</span>{" "}
          </React.Fragment>
        ))
        : segment.text}
    </span>
  </button>
)));
Ligne.displayName = "Ligne";

/**
 * Lecteur synchronisé : le WAV est servi par le serveur local (déplacement possible, aucune limite de taille) ;
 * le segment et le mot courants sont surlignés, un clic sur une phrase y emmène la lecture.
 */
export const SyncPlayer: React.FC<{ avecLocuteurs: boolean }> = ({ avecLocuteurs }) => {
  const [variante, setVariante] = React.useState<Variante>("raw");
  const [segments, setSegments] = React.useState<Segment[]>([]);
  const [erreur, setErreur] = React.useState("");
  const [pos, setPos] = React.useState<Position>({ seg: -1, mot: -1 });
  const audio = React.useRef<HTMLAudioElement>(null);
  const liste = React.useRef<HTMLDivElement>(null);
  const lignes = React.useRef<Map<number, HTMLButtonElement>>(new Map());

  React.useEffect(() => {
    let annule = false;
    api<{ segments: Segment[] }>(`/api/session/transcript?variant=${variante}`)
      .then((d) => { if (!annule) { setSegments(d.segments); setErreur(""); } })
      .catch((e) => { if (!annule) setErreur(messageErreur(e)); });
    return () => { annule = true; };
  }, [variante]);

  const synchroniser = React.useCallback(() => {
    const a = audio.current;
    if (!a) return;
    const t = a.currentTime;
    const i = segmentA(segments, t);
    let m = -1;
    const mots = i >= 0 ? segments[i].words : undefined;
    if (mots) {
      for (let j = 0; j < mots.length; j++) {
        if (t >= mots[j][0] && t < Math.max(mots[j][1], mots[j][0] + 0.03)) { m = j; break; }
      }
    }
    setPos((p) => (p.seg === i && p.mot === m ? p : { seg: i, mot: m }));
  }, [segments]);

  // Pendant la lecture, on suit l'image du navigateur : timeupdate (4 fois par seconde) est trop lent pour surligner les mots.
  React.useEffect(() => {
    const a = audio.current;
    if (!a) return;
    let image = 0;
    const boucle = () => { synchroniser(); image = requestAnimationFrame(boucle); };
    const lire = () => { cancelAnimationFrame(image); image = requestAnimationFrame(boucle); };
    const arreter = () => { cancelAnimationFrame(image); synchroniser(); };
    a.addEventListener("play", lire);
    a.addEventListener("pause", arreter);
    a.addEventListener("ended", arreter);
    a.addEventListener("seeked", synchroniser);
    if (!a.paused) lire();
    return () => {
      cancelAnimationFrame(image);
      a.removeEventListener("play", lire);
      a.removeEventListener("pause", arreter);
      a.removeEventListener("ended", arreter);
      a.removeEventListener("seeked", synchroniser);
    };
  }, [synchroniser]);

  // Garde la ligne active visible dans la liste, sans faire défiler la page.
  React.useEffect(() => {
    const conteneur = liste.current, ligne = lignes.current.get(pos.seg);
    if (!conteneur || !ligne) return;
    const haut = ligne.offsetTop - conteneur.offsetTop;
    if (haut < conteneur.scrollTop || haut + ligne.offsetHeight > conteneur.scrollTop + conteneur.clientHeight) {
      conteneur.scrollTo({ top: haut - conteneur.clientHeight / 3, behavior: "smooth" });
    }
  }, [pos.seg]);

  const aller = React.useCallback((t: number) => {
    const a = audio.current;
    if (!a) return;
    a.currentTime = t;
    a.play().catch(() => undefined);
  }, []);

  const nbMots = React.useMemo(() => segments.reduce((n, s) => n + (s.words?.length ?? 0), 0), [segments]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <audio ref={audio} controls preload="metadata" src="/api/session/file/wav" className="min-w-[260px] flex-1" />
        {avecLocuteurs && (
          <div className="nn-segmented" role="group" aria-label="Transcription affichée">
            <button type="button" aria-pressed={variante === "raw"} onClick={() => setVariante("raw")}>Brute</button>
            <button type="button" aria-pressed={variante === "diarized"} onClick={() => setVariante("diarized")}>Avec locuteurs</button>
          </div>
        )}
      </div>
      <p className="m-0 text-[13px] text-ink-muted">
        Cliquez sur une phrase pour y aller. {nbMots > 0 ? `${nbMots.toLocaleString("fr-FR")} mots horodatés : le mot lu est surligné.` : "Sans horodatage mot à mot pour cette transcription."}
      </p>
      {erreur && <p role="alert" className="m-0 text-sm text-danger-text">{erreur}</p>}
      <div ref={liste} className="relative max-h-[420px] overflow-auto rounded border border-line bg-surface p-1" tabIndex={0} aria-label="Transcription synchronisée">
        {segments.map((s, i) => (
          <Ligne key={i} ref={(el) => { if (el) lignes.current.set(i, el); else lignes.current.delete(i); }}
            segment={s} index={i} actif={pos.seg === i} motActif={pos.seg === i ? pos.mot : -1} aller={aller} />
        ))}
        {segments.length === 0 && !erreur && <p className="m-3 text-sm text-ink-muted">Aucun texte transcrit.</p>}
      </div>
    </div>
  );
};
