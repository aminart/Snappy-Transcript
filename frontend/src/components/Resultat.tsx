import React from "react";
import { api, messageErreur } from "../api";
import { hms } from "../format";
import type { Intervenant, Segment } from "../types";
import { Alerte } from "./ui";

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

/** Texte à coller dans un compte rendu : une réplique par intervenant, sans horodatage. */
export function texteACopier(segments: Segment[]): string {
  const blocs: { qui: string | null; texte: string[] }[] = [];
  for (const s of segments) {
    const dernier = blocs[blocs.length - 1];
    if (dernier && dernier.qui === s.speaker) dernier.texte.push(s.text);
    else blocs.push({ qui: s.speaker, texte: [s.text] });
  }
  return blocs.map((b) => (b.qui ? `${b.qui} : ` : "") + b.texte.join(" ")).join(blocs.some((b) => b.qui) ? "\n\n" : "\n");
}

async function copier(texte: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(texte);
  } catch {
    // Presse-papiers refusé (page non sécurisée…) : ancienne méthode
    const zone = document.createElement("textarea");
    zone.value = texte;
    zone.style.position = "fixed";
    zone.style.opacity = "0";
    document.body.appendChild(zone);
    zone.select();
    document.execCommand("copy");
    zone.remove();
  }
}

interface LigneProps {
  segment: Segment; index: number; actif: boolean; motActif: number; edition: boolean; lecteur: boolean;
  aller: (t: number) => void; corriger: (index: number, texte: string) => void;
}

const Ligne = React.memo(React.forwardRef<HTMLDivElement, LigneProps>(({ segment, index, actif, motActif, edition, lecteur, aller, corriger }, ref) => {
  const [brouillon, setBrouillon] = React.useState(segment.text);
  React.useEffect(() => setBrouillon(segment.text), [segment.text]);
  const classes = `grid w-full grid-cols-[72px_1fr] gap-2 rounded border-l-[3px] px-2.5 py-2 text-left text-sm text-ink-body
    ${actif ? "border-l-accent bg-accent-soft" : "border-l-transparent"}`;
  const qui = segment.speaker && (
    <span className="mr-2 inline-block rounded-full bg-accent-soft px-1.5 py-0.5 text-[11px] font-bold text-accent-ink">{segment.speaker}</span>
  );
  const heure = <span className="pt-0.5 font-mono text-xs text-ink-muted">{hms(segment.start)}</span>;

  if (edition) {
    return (
      <div ref={ref} className={classes}>
        {heure}
        <div className="flex flex-col gap-1">
          {qui && <span>{qui}</span>}
          <textarea aria-label={`Phrase de ${hms(segment.start)}`} className="nn-input min-h-[44px] resize-y py-1.5 leading-snug"
            rows={Math.max(1, Math.ceil(brouillon.length / 90))} value={brouillon}
            onChange={(e) => setBrouillon(e.target.value)}
            onBlur={() => { if (brouillon.trim() && brouillon !== segment.text) corriger(index, brouillon); else setBrouillon(segment.text); }} />
        </div>
      </div>
    );
  }
  const contenu = segment.words && segment.words.length > 0
    ? segment.words.map((m, j) => (
      <React.Fragment key={j}>
        <span className={`rounded px-0.5 ${actif && j === motActif ? "bg-primary text-primary-on" : ""}`}>{m[2]}</span>{" "}
      </React.Fragment>
    ))
    : segment.text;
  if (!lecteur) return <div ref={ref} className={classes}>{heure}<span>{qui}{contenu}</span></div>;
  return (
    <div ref={ref}>
      <button type="button" data-index={index} onClick={() => aller(segment.start)} aria-current={actif ? "true" : undefined}
        className={`${classes} cursor-pointer border-y-0 border-r-0 ${actif ? "" : "bg-transparent hover:bg-surface-3"}`}>
        {heure}<span>{qui}{contenu}</span>
      </button>
    </div>
  );
}));
Ligne.displayName = "Ligne";

const NomsIntervenants: React.FC<{ intervenants: Intervenant[]; enregistrer: (noms: Record<string, string>) => Promise<void> }> = ({ intervenants, enregistrer }) => {
  const [noms, setNoms] = React.useState<Record<string, string>>(() => Object.fromEntries(intervenants.map((i) => [i.label, i.name])));
  const [etat, setEtat] = React.useState<"" | "occupe" | "fait">("");
  const [erreur, setErreur] = React.useState("");
  const modifie = intervenants.some((i) => (noms[i.label] ?? "") !== i.name);
  const valider = async (e: React.FormEvent) => {
    e.preventDefault();
    setEtat("occupe");
    setErreur("");
    try { await enregistrer(noms); setEtat("fait"); } catch (err) { setErreur(messageErreur(err)); setEtat(""); }
  };
  return (
    <form onSubmit={valider} className="flex flex-col gap-3 rounded border border-line bg-surface-2 p-4">
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-semibold text-ink">Qui est qui ?</span>
        <span className="text-[13px] text-ink-muted">Écoutez une réplique, puis donnez un nom : il remplace l'étiquette dans le texte et les fichiers.</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {intervenants.map((i) => (
          <label key={i.label} className="flex flex-col gap-1 text-[13px] text-ink-muted">
            {i.label} · parle {i.seconds >= 60 ? `${Math.round(i.seconds / 60)} min` : `${i.seconds} s`}
            <input className="nn-input" value={noms[i.label] ?? ""} placeholder="Nom (ex. Marie)" maxLength={40}
              onChange={(e) => { setNoms({ ...noms, [i.label]: e.target.value }); setEtat(""); }} />
          </label>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <button type="submit" className="nn-btn nn-btn-secondary" disabled={!modifie || etat === "occupe"}>Enregistrer les noms</button>
        {etat === "fait" && <span role="status" className="text-[13px] text-success-text">✓ Noms appliqués au texte et aux fichiers</span>}
      </div>
      {erreur && <Alerte>{erreur}</Alerte>}
    </form>
  );
};

interface Props {
  sessionId: string;
  avecIntervenants: boolean;
  intervenants: Intervenant[];
  audio: boolean;
  /** Prévient la page quand les noms changent (pour rafraîchir l'état de la session). */
  apresNoms: () => void;
}

/**
 * Le résultat d'une session : texte seul ou avec intervenants, à copier, corriger et réécouter.
 * Le lecteur lit le WAV servi par le serveur local (déplacement possible, aucune limite de taille).
 */
export const Resultat: React.FC<Props> = ({ sessionId, avecIntervenants, intervenants, audio, apresNoms }) => {
  const [variante, setVariante] = React.useState<Variante>(avecIntervenants ? "diarized" : "raw");
  const [segments, setSegments] = React.useState<Segment[]>([]);
  const [erreur, setErreur] = React.useState("");
  const [edition, setEdition] = React.useState(false);
  const [copie, setCopie] = React.useState(false);
  const [version, setVersion] = React.useState(0);
  const [pos, setPos] = React.useState<Position>({ seg: -1, mot: -1 });
  const lecteur = React.useRef<HTMLAudioElement>(null);
  const liste = React.useRef<HTMLDivElement>(null);
  const lignes = React.useRef<Map<number, HTMLDivElement>>(new Map());

  React.useEffect(() => { if (avecIntervenants) setVariante("diarized"); }, [avecIntervenants]);

  React.useEffect(() => {
    let annule = false;
    api<{ segments: Segment[] }>(`/api/session/transcript?variant=${variante}`)
      .then((d) => { if (!annule) { setSegments(d.segments); setErreur(""); } })
      .catch((e) => { if (!annule) setErreur(messageErreur(e)); });
    return () => { annule = true; };
  }, [variante, sessionId, version]);

  const synchroniser = React.useCallback(() => {
    const a = lecteur.current;
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

  // Pendant la lecture, on suit l'image du navigateur : timeupdate (4 fois par seconde) est trop lent pour les mots.
  React.useEffect(() => {
    const a = lecteur.current;
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

  React.useEffect(() => {
    const conteneur = liste.current, ligne = lignes.current.get(pos.seg);
    if (!conteneur || !ligne || edition) return;
    const haut = ligne.offsetTop - conteneur.offsetTop;
    if (haut < conteneur.scrollTop || haut + ligne.offsetHeight > conteneur.scrollTop + conteneur.clientHeight) {
      conteneur.scrollTo({ top: haut - conteneur.clientHeight / 3, behavior: "smooth" });
    }
  }, [pos.seg, edition]);

  const aller = React.useCallback((t: number) => {
    const a = lecteur.current;
    if (!a) return;
    a.currentTime = t;
    a.play().catch(() => undefined);
  }, []);

  const corriger = React.useCallback((index: number, texte: string) => {
    api<Segment>("/api/session/segment", { method: "PUT", json: { variant: variante, index, text: texte } })
      .then((s) => { setSegments((avant) => avant.map((x, i) => (i === index ? s : x))); setErreur(""); })
      .catch((e) => setErreur(messageErreur(e)));
  }, [variante]);

  const toutCopier = async () => {
    await copier(texteACopier(segments));
    setCopie(true);
    setTimeout(() => setCopie(false), 2000);
  };

  const enregistrerNoms = async (noms: Record<string, string>) => {
    await api("/api/session/speakers", { method: "PUT", json: { names: noms } });
    setVersion((v) => v + 1);
    apresNoms();
  };

  const nbMots = segments.reduce((n, s) => n + (s.words?.length ?? 0), 0);
  const suffixe = variante === "diarized" ? "diarized" : "raw";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {avecIntervenants && (
          <div className="nn-segmented mr-auto" role="group" aria-label="Texte affiché">
            <button type="button" aria-pressed={variante === "raw"} onClick={() => setVariante("raw")}>Texte seul</button>
            <button type="button" aria-pressed={variante === "diarized"} onClick={() => setVariante("diarized")}>Avec intervenants</button>
          </div>
        )}
        <button type="button" className="nn-btn nn-btn-primary" onClick={toutCopier} disabled={!segments.length}>
          {copie ? "✓ Copié" : "Copier le texte"}
        </button>
        <a className="nn-btn nn-btn-secondary" href={`/api/session/file/${suffixe}_txt?download=true`} download>Télécharger (.txt)</a>
        <a className="nn-btn nn-btn-secondary" href={`/api/session/file/${suffixe}_srt?download=true`} download
          title="Sous-titres, avec les horaires de chaque phrase">Sous-titres (.srt)</a>
        <button type="button" className="nn-btn nn-btn-secondary" aria-pressed={edition} onClick={() => setEdition(!edition)}>
          {edition ? "Terminer la correction" : "Corriger le texte"}
        </button>
      </div>

      {variante === "diarized" && intervenants.length > 0 && (
        <NomsIntervenants key={intervenants.map((i) => i.label).join("|")} intervenants={intervenants} enregistrer={enregistrerNoms} />
      )}

      {audio && <audio ref={lecteur} controls preload="metadata" src={`/api/session/file/wav?s=${sessionId}`} className="w-full" />}
      <p className="m-0 text-[13px] text-ink-muted">
        {edition ? "Cliquez dans une phrase pour la corriger : elle est enregistrée dès que vous passez à la suivante, dans l'app et dans les fichiers."
          : audio ? `Cliquez sur une phrase pour l'écouter.${nbMots ? " Le mot lu est surligné." : ""}`
          : "L'enregistrement audio n'a pas été gardé : le texte reste à copier, corriger et télécharger."}
      </p>
      {erreur && <Alerte>{erreur}</Alerte>}
      <div ref={liste} className="relative max-h-[460px] overflow-auto rounded border border-line bg-surface p-1" tabIndex={0} aria-label="Transcription">
        {segments.map((s, i) => (
          <Ligne key={i} ref={(el) => { if (el) lignes.current.set(i, el); else lignes.current.delete(i); }}
            segment={s} index={i} actif={pos.seg === i} motActif={pos.seg === i ? pos.mot : -1}
            edition={edition} lecteur={audio} aller={aller} corriger={corriger} />
        ))}
        {segments.length === 0 && !erreur && <p className="m-3 text-sm text-ink-muted">Aucune parole détectée.</p>}
      </div>
    </div>
  );
};
